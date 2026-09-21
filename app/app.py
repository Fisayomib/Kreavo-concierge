VERSION = "0.1.0"
from dotenv import load_dotenv 
import os
from flask import Flask, request 
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
import logging
import uuid
from datetime import datetime, timezone
from app.db import get_connection, find_tenant_id, record_inbound_turn, set_reply_status, record_unrecognised_message


load_dotenv()
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_SANDBOX_NUMBER = os.environ.get("TWILIO_SANDBOX_NUMBER", "").strip()

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
    received_at = datetime.now(timezone.utc)  # stamped before anything else: this is what conversation order is built on
    request_id = uuid.uuid4().hex[:8]
    message_sid = request.form.get("MessageSid", "")
    business_number = request.form.get("To", "")
    sender = request.form.get("From", "")
    message = request.form.get("Body", "")
    num_media = int(request.form.get("NumMedia", "0") or 0)
    logger.info("event=message_received request_id=%s message_sid=%s sender=%s received_at=%s", request_id, message_sid, sender, received_at.isoformat())

    if not message_sid:
        logger.warning("event=missing_message_sid request_id=%s sender=%s", request_id, sender)
        return "Missing MessageSid", 400

    storing = "turn"
    try:
        with get_connection() as conn:
            tenant_id = find_tenant_id(conn, business_number)
            if tenant_id is None:
                storing = "unrecognised"
                stored = record_unrecognised_message(conn, message_sid, business_number, sender, message, num_media, received_at)
                logger.error("event=unrecognised_number request_id=%s message_sid=%s to=%s from=%s stored=%s", request_id, message_sid, business_number, sender, "true" if stored else "false")
                return "", 204
            is_new = record_inbound_turn(conn, tenant_id, message_sid, sender, message, num_media, received_at)
    except Exception as e:
        if storing == "unrecognised":
            logger.error("event=unrecognised_store_failed request_id=%s message_sid=%s to=%s error=%s", request_id, message_sid, business_number, e)
        else:
            logger.error("event=turn_store_failed request_id=%s message_sid=%s error=%s", request_id, message_sid, e)
        return "Store failed", 500

    if not is_new:
        logger.info("event=duplicate_delivery request_id=%s message_sid=%s tenant_id=%s", request_id, message_sid, tenant_id)
        return "", 204

    logger.info("event=turn_stored request_id=%s message_sid=%s tenant_id=%s", request_id, message_sid, tenant_id)

    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    try:
        client.messages.create(
            body="Thanks for your message — we've received it and will get back to you shortly.",
            from_=f"whatsapp:{TWILIO_SANDBOX_NUMBER}",
            to=sender
        )
        reply_status = "sent"
        logger.info("event=reply_sent request_id=%s message_sid=%s sender=%s", request_id, message_sid, sender)
    except Exception as e:
        reply_status = "failed"
        logger.error("event=reply_failed request_id=%s message_sid=%s sender=%s error=%s", request_id, message_sid, sender, e)

    # Twilio gets 204 either way; the turn's reply_status is what records whether a reply is still owed.
    try:
        with get_connection() as conn:
            set_reply_status(conn, message_sid, reply_status)
    except Exception as e:
        logger.error("event=reply_status_update_failed request_id=%s message_sid=%s status=%s error=%s", request_id, message_sid, reply_status, e)
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









