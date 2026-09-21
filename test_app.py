import logging
import re

import pytest
from twilio.base.exceptions import TwilioRestException

from app.app import app, check_settings
from app.db import get_connection

TENANT_NUMBER = "whatsapp:+14155238886"
CUSTOMER_NUMBER = "whatsapp:+2340000000000"
ACK_TEXT = "Thanks for your message — we've received it and will get back to you shortly."


# ---------- helpers ----------

class FakeMessages:
    def __init__(self, calls):
        self.calls = calls

    def create(self, **kwargs):
        self.calls.append(kwargs)


class RaisingMessages:
    def create(self, **kwargs):
        raise TwilioRestException(status=400, uri="", msg="test failure")


@pytest.fixture
def sent(monkeypatch):
    """Replaces Twilio with a fake and returns the list of messages 'sent'."""
    calls = []

    class FakeClient:
        def __init__(self, sid, token):
            self.messages = FakeMessages(calls)

    monkeypatch.setattr("app.app.Client", FakeClient)
    return calls


def post_message(message_sid, body="hello", to=TENANT_NUMBER, num_media=None):
    data = {"MessageSid": message_sid, "To": to, "From": CUSTOMER_NUMBER}
    if body is not None:
        data["Body"] = body
    if num_media is not None:
        data["NumMedia"] = str(num_media)
    return app.test_client().post("/webhook", data=data)


def stored_turns():
    with get_connection() as conn:
        return conn.execute(
            "SELECT tenant_id, message_sid, body, num_media FROM turns ORDER BY id"
        ).fetchall()


def reply_status_of(message_sid):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT reply_status FROM turns WHERE message_sid = %s", (message_sid,)
        ).fetchone()
    return None if row is None else row[0]


def stored_unrecognised():
    with get_connection() as conn:
        return conn.execute(
            "SELECT message_sid, to_number, from_number, body, num_media FROM unrecognised_messages ORDER BY id"
        ).fetchall()


# ---------- acceptance criteria ----------

def test_new_message_stores_one_turn_for_the_tenant(sent):
    # Criterion 1
    response = post_message("SM001", body="hello")
    assert response.status_code == 204
    assert stored_turns() == [(1, "SM001", "hello", 0)]
    assert len(sent) == 1
    assert sent[0]["body"] == ACK_TEXT


def test_duplicate_delivery_stores_one_turn_and_logs_the_repeat(sent, caplog):
    # Criterion 2
    with caplog.at_level(logging.INFO):
        first = post_message("SM001")
        second = post_message("SM001")
    assert first.status_code == 204
    assert second.status_code == 204
    assert len(stored_turns()) == 1
    assert len(sent) == 1
    assert "event=duplicate_delivery" in caplog.text
    assert "message_sid=SM001" in caplog.text


def test_two_different_messages_are_two_turns_in_arrival_order(sent):
    # Criterion 3
    post_message("SM001", body="first")
    post_message("SM002", body="second")
    bodies = [turn[2] for turn in stored_turns()]
    assert bodies == ["first", "second"]
    assert len(sent) == 2


def test_same_text_twice_is_two_messages_not_a_duplicate(sent):
    # Criterion 3: identical text, different MessageSid, is a new message
    post_message("SM001", body="yes")
    post_message("SM002", body="yes")
    assert len(stored_turns()) == 2
    assert len(sent) == 2


def test_unrecognised_number_is_logged_and_creates_no_turn(sent, caplog):
    # Criterion 4
    with caplog.at_level(logging.ERROR):
        response = post_message("SM001", to="whatsapp:+19999999999")
    assert response.status_code == 204
    assert stored_turns() == []
    assert sent == []
    assert "event=unrecognised_number" in caplog.text


def test_media_without_caption_is_stored(sent):
    # Criterion 5
    response = post_message("MM001", body=None, num_media=1)
    assert response.status_code == 204
    assert stored_turns() == [(1, "MM001", "", 1)]


# ---------- unrecognised numbers ----------

UNKNOWN_NUMBER = "whatsapp:+19999999999"


def test_unrecognised_number_saves_the_message_and_logs_an_error(sent, caplog):
    with caplog.at_level(logging.ERROR):
        response = post_message("SM001", body="hello", to=UNKNOWN_NUMBER)
    assert response.status_code == 204
    assert stored_unrecognised() == [("SM001", UNKNOWN_NUMBER, CUSTOMER_NUMBER, "hello", 0)]
    assert stored_turns() == []
    assert sent == []
    error_lines = [r for r in caplog.records if r.levelno == logging.ERROR and "event=unrecognised_number" in r.getMessage()]
    assert len(error_lines) == 1
    assert "message_sid=SM001" in error_lines[0].getMessage()
    assert f"to={UNKNOWN_NUMBER}" in error_lines[0].getMessage()
    assert f"from={CUSTOMER_NUMBER}" in error_lines[0].getMessage()
    assert "stored=true" in error_lines[0].getMessage()


def test_unrecognised_number_delivered_twice_saves_one_row(sent, caplog):
    with caplog.at_level(logging.ERROR):
        first = post_message("SM001", to=UNKNOWN_NUMBER)
        second = post_message("SM001", to=UNKNOWN_NUMBER)
    assert first.status_code == 204
    assert second.status_code == 204
    assert len(stored_unrecognised()) == 1
    assert stored_turns() == []
    assert sent == []
    lines = [r.getMessage() for r in caplog.records if "event=unrecognised_number" in r.getMessage()]
    assert len(lines) == 2
    assert "stored=true" in lines[0]
    assert "stored=false" in lines[1]


def test_unrecognised_number_media_without_caption_is_saved(sent):
    response = post_message("MM001", body=None, num_media=1, to=UNKNOWN_NUMBER)
    assert response.status_code == 204
    assert stored_unrecognised() == [("MM001", UNKNOWN_NUMBER, CUSTOMER_NUMBER, "", 1)]
    assert stored_turns() == []


def test_unrecognised_number_log_does_not_contain_the_body(sent, caplog):
    with caplog.at_level(logging.INFO):
        post_message("SM001", body="secret-body-text", to=UNKNOWN_NUMBER)
    assert "event=unrecognised_number" in caplog.text
    assert "secret-body-text" not in caplog.text
    assert stored_unrecognised()[0][3] == "secret-body-text"


# ---------- failure paths ----------

def test_missing_message_sid_is_rejected_and_not_stored(sent):
    response = app.test_client().post(
        "/webhook", data={"To": TENANT_NUMBER, "From": CUSTOMER_NUMBER, "Body": "hello"}
    )
    assert response.status_code == 400
    assert stored_turns() == []
    assert sent == []


def test_store_failure_returns_500_so_twilio_can_retry(sent, monkeypatch, caplog):
    def broken_store(*args, **kwargs):
        raise RuntimeError("database down")

    monkeypatch.setattr("app.app.record_inbound_turn", broken_store)
    with caplog.at_level(logging.ERROR):
        response = post_message("SM001")
    assert response.status_code == 500
    assert "event=turn_store_failed" in caplog.text
    assert sent == []


def test_reply_failure_keeps_the_turn_and_returns_204(monkeypatch, caplog):
    class RaisingClient:
        def __init__(self, sid, token):
            self.messages = RaisingMessages()

    monkeypatch.setattr("app.app.Client", RaisingClient)
    with caplog.at_level(logging.ERROR):
        response = post_message("SM001")
    assert response.status_code == 204
    assert len(stored_turns()) == 1
    assert "event=reply_failed" in caplog.text


# ---------- reply status ----------

def test_successful_send_marks_the_turn_sent(sent):
    response = post_message("SM001")
    assert response.status_code == 204
    assert reply_status_of("SM001") == "sent"


def test_failed_send_marks_the_turn_failed_and_returns_204(monkeypatch, caplog):
    class RaisingClient:
        def __init__(self, sid, token):
            self.messages = RaisingMessages()

    monkeypatch.setattr("app.app.Client", RaisingClient)
    with caplog.at_level(logging.ERROR):
        response = post_message("SM001")
    assert response.status_code == 204
    assert reply_status_of("SM001") == "failed"
    assert "event=reply_failed" in caplog.text
    assert "message_sid=SM001" in caplog.text


def test_turn_is_pending_when_the_send_is_attempted(monkeypatch):
    seen = []

    class PeekingMessages:
        def create(self, **kwargs):
            seen.append(reply_status_of("SM001"))

    class PeekingClient:
        def __init__(self, sid, token):
            self.messages = PeekingMessages()

    monkeypatch.setattr("app.app.Client", PeekingClient)
    post_message("SM001")
    assert seen == ["pending"]
    assert reply_status_of("SM001") == "sent"


def test_duplicate_delivery_leaves_reply_status_unchanged(sent, monkeypatch):
    post_message("SM001")
    assert reply_status_of("SM001") == "sent"

    def must_not_be_called(*args, **kwargs):
        raise AssertionError("set_reply_status must not run for a duplicate delivery")

    monkeypatch.setattr("app.app.set_reply_status", must_not_be_called)
    response = post_message("SM001")
    assert response.status_code == 204
    assert reply_status_of("SM001") == "sent"
    assert len(sent) == 1


def test_status_update_failure_still_returns_204_and_leaves_pending(sent, monkeypatch, caplog):
    def broken_update(*args, **kwargs):
        raise RuntimeError("database down")

    monkeypatch.setattr("app.app.set_reply_status", broken_update)
    with caplog.at_level(logging.ERROR):
        response = post_message("SM001")
    assert response.status_code == 204
    assert len(sent) == 1
    assert "event=reply_status_update_failed" in caplog.text
    assert "message_sid=SM001" in caplog.text
    assert "status=sent" in caplog.text
    assert reply_status_of("SM001") == "pending"


# ---------- request ids ----------

def test_one_message_logs_share_a_request_id(sent, caplog):
    with caplog.at_level(logging.INFO):
        post_message("SM001")
    ids = re.findall(r"request_id=(\w+)", caplog.text)
    assert len(ids) == 3  # message_received, turn_stored, reply_sent
    assert len(set(ids)) == 1


def test_two_messages_keep_separate_request_ids(sent, caplog):
    with caplog.at_level(logging.INFO):
        post_message("SM001")
        post_message("SM002")
    ids = re.findall(r"request_id=(\w+)", caplog.text)
    assert len(ids) == 6
    assert len(set(ids[:3])) == 1
    assert len(set(ids[3:])) == 1
    assert ids[0] != ids[3]


# ---------- health and settings ----------

def test_health_returns_healthy():
    response = app.test_client().get("/health")
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