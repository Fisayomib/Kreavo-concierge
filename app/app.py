VERSION = "0.1.0"
from dotenv import load_dotenv 
import os
from flask import Flask, request 
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
import logging
import uuid 


load_dotenv()
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_SANDBOX_NUMBER = os.environ.get("TWILIO_SANDBOX_NUMBER")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("kreavo-concierge")
logging.getLogger("twilio").setLevel(logging.WARNING)

app = Flask(__name__)
@app.route("/health")
def status():
    check = {"status": "healthy", "version": VERSION}
    return check

@app.route("/webhook", methods = ["POST"])
def hook():
    request_id = uuid.uuid4().hex[:8]
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    message = request.form.get("Body", "")
    sender = request.form.get("From", "")
    logger.info("event=message_received request_id=%s sender=%s", request_id, sender)
    try:
        message_sent = client.messages.create(
                    body="Thanks for your message — we've received it and will get back to you shortly.",
                    from_= f"whatsapp:{TWILIO_SANDBOX_NUMBER}",
                    to=sender
                )
        logger.info("event=reply_sent request_id=%s sender=%s", request_id, sender)
    except TwilioRestException  as e:
        logger.error("event=reply_failed request_id=%s sender=%s error=%s", request_id, sender, e)
        return "Send failed", 500
    except Exception as e:
        logger.error("event=reply_failed request_id=%s sender=%s error=%s", request_id, sender, e)
        return "Send failed", 500    
    return "", 204 
def check_settings():
    required = ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_SANDBOX_NUMBER"]
    missing = []
    for name in required:
        if not os.environ.get(name, "").strip():
            missing.append(name)
    if missing:
        raise RuntimeError(f"Missing required settings: {', '.join(missing)}. Set them in your local environment and start again.")
    port = os.environ.get("PORT", "").strip()
    if port and not port.isdigit():
        raise RuntimeError(f"Setting PORT must be a number, got '{port}'. Fix it in your local environment and start again.")
check_settings()
if __name__ == "__main__":
    logger.info("event=service_starting service=kreavo-concierge env=local version=%s", VERSION)
    port = int(os.environ.get("PORT", "").strip() or 5000)
    app.run(port = port)









