from flask import Flask, render_template, jsonify, request
import sqlite3
import subprocess
import os
import json
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

app = Flask(__name__, static_folder='static', template_folder='templates')

DB_PATH = '/home/devesh/CONSOLE/nfctest/flycamp_project/flycamp_framework.db'
TOKEN_FILE = '/home/devesh/rfid_token.txt'           # absolute path so games can read it
GAME_META_FILE = '/home/devesh/game_meta.json'       # game/level selection for scripts to read
GAME_DONE_FLAG = '/home/devesh/game_done.flag'       # completion flag written by game scripts
SOUND_DIR = '/home/devesh/CONSOLE/nfctest/flycamp_project/static/assets/sounds'

# --- Helpers -----------------------------------------------------------------

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def run_connection_check():
    # DEBUG: always succeed
    return True

def play_sound(filename: str):
    """Play an MP3 sound file asynchronously using mpg123."""
    full_path = os.path.join(SOUND_DIR, filename)
    if os.path.exists(full_path):
        threading.Thread(target=lambda: subprocess.run(["mpg123", "-q", full_path])).start()
    else:
        print(f"[play_sound] Missing file: {full_path}")

def start_game_process(game_number: int, level_number: int):
    """
    Maps selection to the exact script path and launches it via Popen.
    Also:
      - clears any stale game_done flag BEFORE start (prevents early leaderboard)
      - writes GAME_META_FILE so the game knows game/level (optional feature enabled)
    Returns (success(bool), error(str|None))
    """
    try:
        # --- CLEAR OLD DONE FLAG BEFORE STARTING ---
        try:
            if os.path.exists(GAME_DONE_FLAG):
                os.remove(GAME_DONE_FLAG)
        except Exception as e:
            print(f"[start_game_process] Could not remove old flag: {e}")

        # --- WRITE selection for the game to read (optional: enabled) ---
        try:
            with open(GAME_META_FILE, "w") as m:
                json.dump({"game_number": game_number, "level_number": level_number}, m)
        except Exception as e:
            print(f"[start_game_process] Could not write game_meta.json: {e}")

        # --- MAP to script ---
        if game_number == 1 and level_number in (1, 2):
            script = '/home/devesh/gamescripts/hoverandseek.py'
        elif game_number == 2 and level_number == 1:
            script = '/home/devesh/gamescripts/huestheboss.py'
        elif game_number == 2 and level_number == 2:
            script = '/home/devesh/gamescripts/colourchaos.py'
        else:
            return (False, f"Invalid game/level selection: G{game_number} L{level_number}")

        # Play button tap + initialization voice line (keep existing start sound too)
        play_sound("button selection.mp3")
        play_sound("initialising drone and nodes before game.mp3")

        subprocess.Popen(['python3', script])
        play_sound("game_start.mp3")
        return (True, None)
    except Exception as e:
        return (False, str(e))

def get_token_id_from_script():
    try:
        result = subprocess.run(['python3', 'get_id.py'], capture_output=True, text=True, timeout=10)
        output = result.stdout.strip()
        if "Token ID:" in output:
            token_id = int(output.split("Token ID:")[1].strip())
            return token_id
        print("Warning: get_id.py did not return a Token ID. Full output:", output)
        return None
    except Exception as e:
        print(f"Error reading token ID from get_id.py: {e}")
        return None

# --- Routes: UI ---------------------------------------------------------------

@app.route('/')
def index():
    return render_template('console.html')

# --- Routes: RFID -------------------------------------------------------------

@app.route('/scan_rfid')
def scan_rfid():
    token_id = get_token_id_from_script()
    print("Scanned token_id:", token_id)

    if not token_id:
        play_sound("rfid_error.mp3")
        return jsonify({'success': False, 'error': 'No token ID found or script failed'})

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT player_name FROM PlayerRegistrations WHERE token_id = ?", (token_id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        # Success chime when the name pops up
        play_sound("name and rfid pops up.mp3")
        play_sound("rfid_success.mp3")
        return jsonify({'success': True, 'name': row['player_name'], 'token_id': token_id})
    else:
        play_sound("rfid_error.mp3")
        return jsonify({'success': False, 'error': 'Token not registered to any player'})

@app.route('/write_rfid_token', methods=['POST'])
def write_rfid_token():
    data = request.get_json()
    token_id = data.get('token_id')
    if token_id is not None:
        try:
            with open(TOKEN_FILE, "w") as f:
                f.write(str(token_id))
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': f'Failed to write token file: {e}'})
    return jsonify({'success': False, 'error': 'No token_id provided'})

# --- Routes: Initialising screen flow ----------------------------------------

@app.route('/api/connection_check', methods=['POST'])
def api_connection_check():
    ok = run_connection_check()
    if ok:
        # Voice line for initialization screen
        play_sound("initialising drone and nodes before game.mp3")
    return jsonify({'success': ok})

@app.route('/api/start_game', methods=['POST'])
def api_start_game():
    data = request.get_json(force=True)
    game_number = int(data.get('game_number', 0))
    level_number = int(data.get('level_number', 0))

    success, err = start_game_process(game_number, level_number)
    if success:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': err or 'Failed to start game'})

# --- Back-compat endpoints ----------------------------------------------------

@app.route('/start_hue_game')
def start_hue_game():
    try:
        # Clear stale flag for legacy entry points too
        if os.path.exists(GAME_DONE_FLAG):
            os.remove(GAME_DONE_FLAG)
        # Write meta for legacy call (defaults: game 2, level 1)
        with open(GAME_META_FILE, "w") as m:
            json.dump({"game_number": 2, "level_number": 1}, m)

        # Button confirm + init line, keep existing start sound
        play_sound("button selection.mp3")
        play_sound("initialising drone and nodes before game.mp3")

        subprocess.Popen(['python3', '/home/devesh/gamescripts/huestheboss.py'])
        play_sound("game_start.mp3")
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/start_hover_game')
def start_hover_game():
    try:
        # Clear stale flag for legacy entry points too
        if os.path.exists(GAME_DONE_FLAG):
            os.remove(GAME_DONE_FLAG)
        # Write meta for legacy call (defaults: game 1, level 1)
        with open(GAME_META_FILE, "w") as m:
            json.dump({"game_number": 1, "level_number": 1}, m)

        # Button confirm + init line, keep existing start sound
        play_sound("button selection.mp3")
        play_sound("initialising drone and nodes before game.mp3")

        subprocess.Popen(['python3', '/home/devesh/gamescripts/hoverandseek.py'])
        play_sound("game_start.mp3")
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# --- Scores / Leaderboard -----------------------------------------------------

@app.route('/submit_score', methods=['POST'])
def submit_score():
    """
    Expects: token_id (int), game_number (int), level_number (int), score (int)
    Inserts a row in GamePlays and updates PlayerBests (manual upsert).
    """
    data = request.get_json()
    token_id = data.get('token_id')
    game_number = data.get('game_number')
    level_number = data.get('level_number')
    score = data.get('score')

    # Debug log
    print(f"[submit_score] token={token_id} game={game_number} level={level_number} score={score}")

    if token_id is None or game_number is None or level_number is None or score is None:
        return jsonify({'success': False, 'error': 'Missing token_id, game_number, level_number, or score'})

    try:
        token_id = int(token_id)
        game_number = int(game_number)
        level_number = int(level_number)
        score = int(score)
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid numeric fields'})

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        now_ts = int(datetime.now(tz=ZoneInfo("Asia/Kolkata")).timestamp())

        # 1) Insert raw play
        cursor.execute("""
            INSERT INTO GamePlays (token_id, game_number, level_number, score, begin_timestamp, end_timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (token_id, game_number, level_number, score, now_ts, now_ts))

        # 2) Manual upsert for PlayerBests
        cursor.execute("""
            SELECT player_best_id, highest_score
            FROM PlayerBests
            WHERE token_id = ? AND game_number = ? AND level_number = ?
            ORDER BY player_best_id LIMIT 1
        """, (token_id, game_number, level_number))
        row = cursor.fetchone()

        if row is None:
            cursor.execute("""
                INSERT INTO PlayerBests (token_id, game_number, level_number, highest_score, timestamp_achieved)
                VALUES (?, ?, ?, ?, ?)
            """, (token_id, game_number, level_number, score, now_ts))
        else:
            player_best_id = row['player_best_id']
            prev = row['highest_score'] or 0
            if score > prev:
                cursor.execute("""
                    UPDATE PlayerBests
                    SET highest_score = ?, timestamp_achieved = ?
                    WHERE player_best_id = ?
                """, (score, now_ts, player_best_id))

        conn.commit()
        # Sound for score reveal / scoreboard moment (keep existing submit sound)
        play_sound("final score display.mp3")
        play_sound("score_submit.mp3")
        return jsonify({'success': True, 'message': 'Score submitted and stats updated.'})

    except sqlite3.Error as e:
        conn.rollback()
        return jsonify({'success': False, 'error': f'Database error: {e}'})
    finally:
        conn.close()

@app.route('/get_leaderboard')
def get_leaderboard():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT
                pr.player_name,
                COALESCE(SUM(pb.highest_score), 0) AS total_score
            FROM PlayerBests AS pb
            JOIN PlayerRegistrations AS pr ON pb.token_id = pr.token_id
            GROUP BY pr.player_name
            ORDER BY total_score DESC
        """)
        rows = cursor.fetchall()
        leaderboard_data = [{'name': row['player_name'], 'score': row['total_score']} for row in rows]
        # Use the "final score display" sound when the leaderboard shows (keep existing)
        play_sound("final score display.mp3")
        play_sound("leaderboard.mp3")
        return jsonify({'success': True, 'leaderboard': leaderboard_data})
    except sqlite3.Error as e:
        print(f"Error fetching leaderboard data: {e}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        conn.close()

# --- Game done flag -----------------------------------------------------------

@app.route('/game_done')
def game_done():
    if os.path.exists(GAME_DONE_FLAG):
        os.remove(GAME_DONE_FLAG)
        # Play return-to-home audio cue when game completes
        play_sound("drone back to home.mp3")
        return jsonify({'done': True})
    else:
        return jsonify({'done': False})

# --- Main --------------------------------------------------------------------

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
