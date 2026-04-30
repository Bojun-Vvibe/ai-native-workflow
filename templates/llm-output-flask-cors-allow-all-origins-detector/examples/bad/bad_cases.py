"""Bad CORS configurations — every line below should trigger."""
from flask import Flask, jsonify
from flask_cors import CORS, cross_origin

app = Flask(__name__)

# 1. Bare CORS(app) — defaults to Access-Control-Allow-Origin: *
CORS(app)

# 2. Explicit wildcard origins string.
CORS(app, origins="*")

# 3. Explicit wildcard origins list.
CORS(app, origins=["*"])

# 4. Wildcard inside resources= mapping.
CORS(app, resources={r"/api/*": {"origins": "*"}})


# 5. cross_origin decorator with no args defaults to *.
@app.route("/a")
@cross_origin()
def a():
    return jsonify(ok=True)


# 6. cross_origin with explicit wildcard.
@app.route("/b")
@cross_origin(origins="*")
def b():
    return jsonify(ok=True)


# 7. Manual header set on response.
@app.route("/c")
def c():
    response = jsonify(ok=True)
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


# 8. Django legacy allow-all flag.
CORS_ORIGIN_ALLOW_ALL = True

# 9. Django modern allow-all flag.
CORS_ALLOW_ALL_ORIGINS = True

# 10. Django allowed-origins wildcard list.
CORS_ALLOWED_ORIGINS = ["*"]


# 11. Starlette / FastAPI CORSMiddleware with allow_origins=["*"].
def install_starlette(app):
    from starlette.middleware.cors import CORSMiddleware
    app.add_middleware(CORSMiddleware, allow_origins=["*"])
