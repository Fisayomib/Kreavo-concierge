VERSION = "0.1.0"
from dotenv import load_dotenv 
import os
from flask import Flask, request 
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException 


load_dotenv()
TWILIO_ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_SANDBOX_NUMBER = os.environ["TWILIO_SANDBOX_NUMBER"]

app = Flask(__name__)
@app.route("/health")
def status():
    check = {"status": "healthy", "version": VERSION}
    return check

@app.route("/webhook", methods = ["POST"])
def hook():
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    message = request.form.get("Body", "")
    sender = request.form.get("From", "")
    try:
        message_sent = client.messages.create(
                    body="Thanks for your message — we've received it and will get back to you shortly.",
                    from_= f"whatsapp:{TWILIO_SANDBOX_NUMBER}",
                    to=sender
                )
    except TwilioRestException  as e:
        print("Twilio send failed:", e)
        return "OK"        
    print(message)
    print(sender)
    return "OK" 
def check_settings():
    required = ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_SANDBOX_NUMBER"]
    missing = []
    for name in required:
        if name not in os.environ:
            missing.append(name)
    if missing:
        raise RuntimeError(f"Missing required settings: {', '.join(missing)}. Set them in your local environment and start again.")
if __name__ == "__main__":
    check_settings()
    app.run()









