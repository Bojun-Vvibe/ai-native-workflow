"""Good cases — should NOT be flagged."""
import os
from flask import Flask

app = Flask(__name__)

# 1. default — debug not set
app.run()

# 2. explicit False
app.run(debug=False)

# 3. host/port no debug
app.run(host="127.0.0.1", port=8080)

# 4. config DEBUG False
app.config["DEBUG"] = False

# 5. config update with DEBUG=False
app.config.update(DEBUG=False)

# 6. FLASK_DEBUG=0
os.environ["FLASK_DEBUG"] = "0"

# 7. FLASK_ENV=production
os.environ["FLASK_ENV"] = "production"

# 8. suppression marker on an audited debug=True
app.run(debug=True)  # flask-debug-ok: dev-only entrypoint, gated by argv

# Plus: docstring/comment containing the literal string is masked.
"""Note: do not ever set app.run(debug=True) in prod."""
# Reminder: app.config["DEBUG"] = True is forbidden.
