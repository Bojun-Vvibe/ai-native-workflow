"""Bad cases — should be flagged."""
import os
from flask import Flask

app = Flask(__name__)
api = Flask(__name__)

# 1. classic app.run(debug=True)
app.run(debug=True)

# 2. with host/port + debug=True
app.run(host="0.0.0.0", port=5000, debug=True)

# 3. different name (api) — also a Flask app
api.run(debug=True)

# 4. config dict assignment
app.config["DEBUG"] = True

# 5. config update kwarg
app.config.update(DEBUG=True, TESTING=False)

# 6. os.environ FLASK_DEBUG=1
os.environ["FLASK_DEBUG"] = "1"

# 7. os.environ FLASK_DEBUG=true
os.environ["FLASK_DEBUG"] = "true"

# 8. os.environ FLASK_ENV=development
os.environ["FLASK_ENV"] = "development"
