import sys
import time
import sqlite3
from smartcard.System import readers
from smartcard.Exceptions import CardConnectionException, NoCardException
from smartcard.util import toHexString

DB_NAME = 'flycamp_framework.db'

def get_token_id(uid):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT token_id FROM RFIDTokens WHERE rfid_uid = ?", (uid,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def main():
    print("Waiting for NFC tap...")

    r = readers()
    if len(r) == 0:
        print("No NFC readers found.")
        sys.exit()

    reader = r[0]
    connection = reader.createConnection()

    try:
        while True:
            try:
                connection.connect()
                GET_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]
                data, sw1, sw2 = connection.transmit(GET_UID)

                if sw1 == 0x90 and sw2 == 0x00:
                    uid = toHexString(data).replace(" ", "")
                    token_id = get_token_id(uid)
                    if token_id:
                        print(f"[?] UID: {uid} | Token ID: {token_id}")
                    else:
                        print(f"[!] UID {uid} not found in database.")
                    # wait until card is removed before next read
                    while True:
                        try:
                            connection.connect()
                        except NoCardException:
                            break
                        time.sleep(0.2)
            except (CardConnectionException, NoCardException):
                pass

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n[?] Exiting on user interrupt.")
        sys.exit()

if __name__ == "__main__":
    main()
