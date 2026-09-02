VERSION = "0.1.0"
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





