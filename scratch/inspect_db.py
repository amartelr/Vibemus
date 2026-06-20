import sqlite3

conn = sqlite3.connect("data/chordonomicon.db")
cursor = conn.cursor()
cursor.execute("SELECT count(*) FROM chord_progression")
print("Total rows:", cursor.fetchone()[0])

cursor.execute("SELECT * FROM chord_progression LIMIT 10")
print("First 10 rows:")
for r in cursor.fetchall():
    print(r[0], r[1][:100] + "...")
conn.close()
