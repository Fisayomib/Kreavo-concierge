from app.app import app
from twilio.base.exceptions import TwilioRestException
import pytest
import logging 
from app.app import app, check_settings
class FakeMessages:
    def __init__(self, calls):
        self.calls = calls

    def create(self, **kwargs):
        self.calls.append(kwargs)


class FakeClient:
    calls = []
    def __init__(self, sid, token):
        self.messages = FakeMessages(FakeClient.calls)

def test_webhook_sends_acknowledgement(monkeypatch):
    FakeClient.calls = []
    monkeypatch.setattr("app.app.Client", FakeClient)
    client = app.test_client()
    response = client.post("/webhook", 
                           data={"Body": "hello", 
                                "From": "whatsapp:+2340000000000"})
    assert response.status_code == 204
    assert len(FakeClient.calls) == 1
    assert FakeClient.calls[0]["body"] == "Thanks for your message — we've received it and will get back to you shortly."

def test_webhook_handles_missing_body(monkeypatch):
    FakeClient.calls = []
    monkeypatch.setattr("app.app.Client", FakeClient)
    client = app.test_client()
    response = client.post("/webhook",
                           data={"From": "whatsapp:+2340000000000"})
    assert response.status_code == 204
    assert len(FakeClient.calls) == 1


def test_webhook_replies_to_each_message(monkeypatch):
    FakeClient.calls = []
    monkeypatch.setattr("app.app.Client", FakeClient)
    client = app.test_client()
    for _ in range(2):
        client.post("/webhook",
                    data={"Body": "hello", "From": "whatsapp:+2340000000000"})
    assert len(FakeClient.calls) == 2

def test_health_returns_healthy():
    client = app.test_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "healthy"

def test_missing_required_setting_raises(monkeypatch):
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="TWILIO_AUTH_TOKEN"):
        check_settings()


def test_empty_required_setting_raises(monkeypatch):
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "   ")
    with pytest.raises(RuntimeError, match="TWILIO_AUTH_TOKEN"):
        check_settings()


def test_non_numeric_port_raises(monkeypatch):
    monkeypatch.setenv("PORT", "abc")
    with pytest.raises(RuntimeError, match="PORT"):
        check_settings()

class RaisingMessages:
    def create(self, **kwargs):
        raise TwilioRestException(status=400, uri="", msg="test failure")


class RaisingClient:
    def __init__(self, sid, token):
        self.messages = RaisingMessages()


def test_webhook_returns_500_when_send_fails(monkeypatch, caplog):
    monkeypatch.setattr("app.app.Client", RaisingClient)
    client = app.test_client()
    with caplog.at_level(logging.ERROR):
        response = client.post("/webhook",
                               data={"Body": "hello", "From": "whatsapp:+2340000000000"})
    assert response.status_code == 500
    assert "event=reply_failed" in caplog.text

import re


def test_arrival_and_reply_share_request_id(monkeypatch, caplog):
    FakeClient.calls = []
    monkeypatch.setattr("app.app.Client", FakeClient)
    client = app.test_client()
    with caplog.at_level(logging.INFO):
        client.post("/webhook",
                    data={"Body": "hello", "From": "whatsapp:+2340000000000"})

    ids = re.findall(r"request_id=(\w+)", caplog.text)
    assert len(ids) == 2
    assert ids[0] == ids[1]


def test_two_messages_keep_separate_request_ids(monkeypatch, caplog):
    FakeClient.calls = []
    monkeypatch.setattr("app.app.Client", FakeClient)
    client = app.test_client()
    with caplog.at_level(logging.INFO):
        for _ in range(2):
            client.post("/webhook",
                        data={"Body": "hello", "From": "whatsapp:+2340000000000"})

    ids = re.findall(r"request_id=(\w+)", caplog.text)
    assert len(ids) == 4
    assert ids[0] == ids[1]
    assert ids[2] == ids[3]
    assert ids[0] != ids[2]