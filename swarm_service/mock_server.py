"""Mock enterprise target server for Swarm-Forge demo at localhost:3000."""
from flask import Flask, jsonify
import jwt, datetime

app = Flask(__name__)
SECRET = "demo-secret-key"

# --- Intentionally misconfigured for demo ---
@app.route("/api/v1/health")
def health():
    return jsonify({"status": "ok", "version": "1.0.0"}), 200

@app.route("/api/v1/users")
def users():  # No auth required — intentional misconfiguration
    return jsonify([
        {"id": 1, "username": "alice", "role": "admin"},
        {"id": 2, "username": "bob",   "role": "user"},
    ]), 200

@app.route("/api/v1/auth/token")
def token():  # Returns a JWT with 'none' algorithm for demo
    payload = {"sub": "demo_user", "role": "guest",
               "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)}
    tok = jwt.encode(payload, "", algorithm="none")
    return jsonify({"token": tok, "algorithm": "none"}), 200

@app.route("/api/v1/admin/users")
def admin_users():
    return jsonify([
        {"id": 1, "username": "alice", "role": "admin", "email": "alice@corp.com"},
        {"id": 2, "username": "bob",   "role": "user",  "email": "bob@corp.com"},
    ]), 200

if __name__ == "__main__":
    print("\033[92m[MOCK SERVER] Enterprise target running at http://localhost:3000\033[0m")
    app.run(port=3000, debug=False)
