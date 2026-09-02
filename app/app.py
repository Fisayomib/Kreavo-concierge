VERSION = "0.1.0"
from dotenv import load_dotenv 
import os 

load_dotenv()
TWILIO_ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_SANDBOX_NUMBER = os.environ["TWILIO_SANDBOX_NUMBER"]
try:
    from flask import Flask 


    app = Flask(__name__)
    @app.route("/health")
    def status():
        check = {"status": "healthy", "version": VERSION}
        return check
    if __name__ == "__main__":
        app.run()
except ModuleNotFoundError:
    print("run pip install -r requirements.txt")





