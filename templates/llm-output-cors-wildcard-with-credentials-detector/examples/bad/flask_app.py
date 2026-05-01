# Flask-CORS with the broken combo.
from flask import Flask
from flask_cors import CORS

app = Flask(__name__)
# Bad: wildcard + supports_credentials.
CORS(app, origins="*", supports_credentials=True)


@app.get("/me")
def me():
    return {"ok": True}
