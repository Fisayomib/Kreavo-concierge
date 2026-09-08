from app.app import app
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
    assert response.status_code == 200
    assert len(FakeClient.calls) == 1
    assert FakeClient.calls[0]["body"] == "Thanks for your message — we've received it and will get back to you shortly."

def test_webhook_handles_missing_body(monkeypatch):
    FakeClient.calls = []
    monkeypatch.setattr("app.app.Client", FakeClient)
    client = app.test_client()
    response = client.post("/webhook",
                           data={"From": "whatsapp:+2340000000000"})
    assert response.status_code == 200
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