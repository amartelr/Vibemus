import sqlite3
import os

db_path = "data/chordonomicon.db"
if not os.path.exists(db_path):
    print("Database does not exist.")
else:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT chords FROM chord_progression LIMIT 10")
    rows = cursor.fetchall()
    for idx, row in enumerate(rows, 1):
        print(f"{idx}: {row[0][:200]}...")
    conn.close()
