"""Safe CORS configurations — none of these should trigger."""
from flask import Flask, jsonify
from flask_cors import CORS, cross_origin

app = Flask(__name__)

# Explicit allowlist — fine.
CORS(app, origins=["https://app.example.com"])

# Per-resource explicit allowlist — fine.
CORS(app, resources={r"/api/*": {"origins": ["https://app.example.com"]}})


@app.route("/x")
@cross_origin(origins=["https://app.example.com"])
def x():
    return jsonify(ok=True)


@app.route("/y")
def y():
    response = jsonify(ok=True)
    # Echo a single allowed origin, not a wildcard.
    response.headers["Access-Control-Allow-Origin"] = "https://app.example.com"
    return response


# Django: explicit allowlist.
CORS_ALLOWED_ORIGINS = [
    "https://app.example.com",
    "https://admin.example.com",
]

# Django: explicitly disabled allow-all.
CORS_ALLOW_ALL_ORIGINS = False
CORS_ORIGIN_ALLOW_ALL = False

# Audited wildcard — suppressed because intentional and reviewed.
CORS(app, origins="*")  # cors-wildcard-ok

# Discussion in a string literal should not trigger:
note = "Never write CORS(app, origins='*') in production."

# Discussion in a comment should not trigger:
# Setting Access-Control-Allow-Origin to * is bad. CORS(app) is bad.


# Starlette with explicit origins — fine.
def install_starlette(app):
    from starlette.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://app.example.com"],
    )
