VERSION = "0.1.0"
from dotenv import load_dotenv 
import os 


load_dotenv()
TWILIO_ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_SANDBOX_NUMBER = os.environ["TWILIO_SANDBOX_NUMBER"]

try:
    from flask import Flask, request 
    from twilio.rest import Client 

    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

    app = Flask(__name__)
    @app.route("/health")
    def status():
        check = {"status": "healthy", "version": VERSION}
        return check

    @app.route("/webhook", methods = ["POST"])
    def hook():
        message = request.form.get("Body", "")
        sender = request.form.get("From", "")
        message_sent = client.messages.create(
            body="Thanks for your message — we've received it and will get back to you shortly.",
            from_=f"whatsapp:{TWILIO_SANDBOX_NUMBER}",
            to=sender
        )        
        print(message)
        print(sender)
        return "OK" 
    if __name__ == "__main__":
        app.run()
except ModuleNotFoundError:
    print("run pip install -r requirements.txt")





