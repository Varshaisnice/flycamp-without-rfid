from flask import Flask, request, jsonify
import sqlite3
import socket

app = Flask(__name__)
DB_PATH = "/home/devesh/CONSOLE/nfctest/flycamp_project/flycamp_framework.db"

# =================== DB UTIL ===================
# In your Pi #1 server (API), inside query_db():
def query_db(query, args=(), one=False, commit=False):
    conn = sqlite3.connect(DB_PATH, timeout=5)  # wait up to 5s for writer lock
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    # Set per-connection pragmas
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA synchronous=NORMAL;")
    cur.execute("PRAGMA busy_timeout=5000;")  # extra safety
    cur.execute(query, args)
    if commit:
        conn.commit()
    rv = cur.fetchall()
    conn.close()
    return (rv[0] if rv else None) if one else rv

# =================== ROUTES ===================

# Get token_id by RFID UID
@app.route("/get_token", methods=["POST"])
def get_token():
    data = request.json
    rfid_uid = data.get("rfid_uid")
    if not rfid_uid:
        return jsonify({"error": "rfid_uid required"}), 400

    row = query_db("SELECT token_id FROM RFIDTokens WHERE rfid_uid = ?", (rfid_uid,), one=True)
    token_id = row["token_id"] if row else None
    return jsonify({"token_id": token_id})


@app.route("/")
def index():
    return jsonify({"status": "API running", "db": DB_PATH})

# List all RFID tokens
@app.route("/rfid_tokens", methods=["GET"])
def rfid_tokens():
    rows = query_db("SELECT * FROM RFIDTokens")
    return jsonify([dict(r) for r in rows])

# Register a new player
@app.route("/register", methods=["POST"])
def register():
    data = request.json
    token_id = data.get("token_id")
    player_name = data.get("player_name")

    if not token_id or not player_name:
        return jsonify({"error": "token_id and player_name required"}), 400

    query_db(
        "INSERT INTO PlayerRegistrations (token_id, player_name, registration_timestamp) VALUES (?, ?, strftime('%s','now'))",
        (token_id, player_name),
        commit=True,
    )
    return jsonify({"status": "registered", "player_name": player_name})

# Get all player registrations
@app.route("/registrations", methods=["GET"])
def registrations():
    rows = query_db("SELECT * FROM PlayerRegistrations")
    return jsonify([dict(r) for r in rows])

# Record a game play
@app.route("/game_play", methods=["POST"])
def game_play():
    data = request.json
    token_id = data.get("token_id")
    game_number = data.get("game_number")
    level_number = data.get("level_number")
    score = data.get("score")

    if not token_id or not game_number or not level_number or score is None:
        return jsonify({"error": "Missing fields"}), 400

    query_db(
        "INSERT INTO GamePlays (token_id, game_number, level_number, score, begin_timestamp, end_timestamp) VALUES (?, ?, ?, ?, strftime('%s','now'), strftime('%s','now'))",
        (token_id, game_number, level_number, score),
        commit=True,
    )
    return jsonify({"status": "game play recorded"})

# Get player bests
@app.route("/player_bests", methods=["GET"])
def player_bests():
    rows = query_db("SELECT * FROM PlayerBests")
    return jsonify([dict(r) for r in rows])

# Log interaction
@app.route("/log", methods=["POST"])
def log():
    data = request.json
    rfid_uid = data.get("rfid_uid")
    interaction_type = data.get("interaction_type")

    if not rfid_uid or not interaction_type:
        return jsonify({"error": "rfid_uid and interaction_type required"}), 400

    query_db(
        "INSERT INTO InteractionLog (rfid_uid, interaction_type, timestamp) VALUES (?, ?, strftime('%s','now'))",
        (rfid_uid, interaction_type),
        commit=True,
    )
    return jsonify({"status": "logged"})


# =================== MAIN ===================

def get_ip():
    """Get LAN IP for display."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

if __name__ == "__main__":
    ip = get_ip()
    print(f"API available at: http://{ip}:5005/")
    app.run(host="0.0.0.0", port=5005, debug=False, use_reloader=False)
