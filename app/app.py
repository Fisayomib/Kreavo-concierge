try:
    from flask import Flask 


    app = Flask(__name__)
    if __name__ == "__main__":
        app.run()
except ModuleNotFoundError:
    print("run pip install -r requirements.txt")


