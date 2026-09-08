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
    monkeypatch.setattr("app.app.Client", FakeClient)
    client = app.test_client()
    response = client.post("/webhook", 
                           data={"Body": "hello", 
                                "From": "whatsapp:+2340000000000"})
    assert response.status_code == 200
    assert len(FakeClient.calls) == 1
    assert FakeClient.calls[0]["body"] == "Thanks for your message — we've received it and will get back to you shortly."