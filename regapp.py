from flask import Flask, render_template, request, jsonify, send_from_directory
import sqlite3
import subprocess
import re
# MODIFIED: Added imports for timestamp and timezone handling
from datetime import datetime
from zoneinfo import ZoneInfo

app = Flask(__name__, static_folder='static', template_folder='templates')
# MODIFIED: Using the full path you provided in your cronjob for consistency
DB_PATH = '/home/devesh/Console/fly_camp_console/flycamp_framework.db'

# MODIFIED: Added a helper function to get a DB connection to reduce repeated code.
# This also lets us access columns by name, which is cleaner.
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def reg_page():
    return render_template('reg.html')

@app.route('/view-players')
def view_players():
    return render_template('players.html')

# --- THIS IS THE CORRECTED VERSION ---
@app.route('/players/full')
def get_players():
    """
    Endpoint to get all registered pilots for the display table.
    It fetches the integer token_id and the player's name.
    """
    conn = get_db_connection()
    
    # --- CHANGE 1: Simplified SQL Query ---
    # We only need the data from PlayerRegistrations for this page.
    # We select the integer `token_id` and the `player_name`.
    cursor = conn.execute(
        'SELECT token_id, player_name FROM PlayerRegistrations ORDER BY registration_timestamp'
    )
    pilots_from_db = cursor.fetchall()
    conn.close()
    
    # --- CHANGE 2: Correct JSON Structure ---
    # Create a list of dictionaries with the keys 'token_id' and 'name'
    # to exactly match what the JavaScript in players.html expects (p.token_id and p.name).
    players_list = []
    for pilot in pilots_from_db:
        players_list.append({
            'token_id': pilot['token_id'],
            'name': pilot['player_name']
        })
        
    return jsonify(players_list)

@app.route('/queue-count')
def queue_count():
    # MODIFIED: The "queue" is now the number of rows in PlayerRegistrations.
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM PlayerRegistrations")
    count = cursor.fetchone()[0]
    conn.close()
    return jsonify({'count': count})

@app.route('/check_name', methods=['POST'])
def check_name():
    # MODIFIED: Check for names in the new PlayerRegistrations table.
    data = request.get_json()
    name = data.get('name')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM PlayerRegistrations WHERE player_name = ?", (name,))
    exists = cursor.fetchone() is not None
    conn.close()
    return jsonify({'exists': exists})

@app.route('/register', methods=['POST'])
def register_player():
    # MODIFIED: This entire function is updated to use the new, safer registration logic.
    data = request.get_json()
    name = data.get('name')
    # This is the integer token_id from the RFIDTokens table, provided by get_id.py
    token_id = data.get('token_id')

    if not name or not token_id:
        return jsonify({'status': 'error', 'message': 'Missing name or token ID'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Check 1: Is the name already taken?
        cursor.execute("SELECT 1 FROM PlayerRegistrations WHERE player_name = ?", (name,))
        if cursor.fetchone():
            return jsonify({'status': 'exists', 'message': 'Name already taken'})

        # Check 2: Is the token already registered?
        cursor.execute("SELECT 1 FROM PlayerRegistrations WHERE token_id = ?", (token_id,))
        if cursor.fetchone():
            return jsonify({'status': 'exists', 'message': 'Token already used'})
            
        # Check 3: Does this token_id even exist in our master list?
        cursor.execute("SELECT rfid_uid FROM RFIDTokens WHERE token_id = ?", (token_id,))
        token_row = cursor.fetchone()
        if not token_row:
            return jsonify({'status': 'error', 'message': 'Invalid Token ID. This token is not in the system.'})
        
        rfid_uid = token_row['rfid_uid']

        # All checks passed, proceed with registration in a transaction
        kolkata_now_ts = int(datetime.now(tz=ZoneInfo("Asia/Kolkata")).timestamp())

        # Log the interaction
        cursor.execute(
            "INSERT INTO InteractionLog (rfid_uid, interaction_type, timestamp) VALUES (?, ?, ?)",
            (rfid_uid, 'REGISTRATION', kolkata_now_ts)
        )

        # Create the player registration
        cursor.execute(
            "INSERT INTO PlayerRegistrations (token_id, player_name, registration_timestamp) VALUES (?, ?, ?)",
            (token_id, name, kolkata_now_ts)
        )
        
        conn.commit()
        return jsonify({'status': 'registered', 'message': f"Successfully registered {name}."})

    except sqlite3.Error as e:
        conn.rollback() # Undo changes if any error occurs
        return jsonify({'status': 'error', 'message': f'Database error: {e}'}), 500
    finally:
        conn.close()


@app.route('/scan_uid', methods=['GET'])
def scan_uid():
    # This endpoint's logic does not need to change, as it relies on the output
    # of the external 'get_id.py' script. As long as 'get_id.py' is updated
    # to work with the new schema, this endpoint will function correctly.
    try:
        # It is recommended to use a timeout to prevent the request from hanging forever.
        result = subprocess.run(['python3', 'get_id.py'],
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  timeout=10) # 10-second timeout
        output = result.stdout.decode('utf-8')

        # This regex correctly looks for the integer Token ID.
        match = re.search(r'Token ID: (\d+)', output)
        if match:
            token_id = int(match.group(1))
            return jsonify({'status': 'success', 'token_id': token_id})
        elif "UID" in output:
            # This handles the case where get_id.py finds a UID but it's not in the DB
            return jsonify({'status': 'unlinked_uid', 'message': output.strip()})
        else:
            # This handles other cases, like no card found.
            return jsonify({'status': 'not_found', 'output': output.strip()})
    except subprocess.TimeoutExpired:
        return jsonify({'status': 'timeout', 'message': 'No card scanned in time.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'An error occurred: {e}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
