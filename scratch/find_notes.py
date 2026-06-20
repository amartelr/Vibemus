import sqlite3
import re
from collections import Counter

conn = sqlite3.connect("data/chordonomicon.db")
cursor = conn.cursor()
cursor.execute("SELECT chords FROM chord_progression LIMIT 1000")
rows = cursor.fetchall()

notes = Counter()
for row in rows:
    chords_str = row[0]
    chords_str = re.sub(r'<[^>]+>', ' ', chords_str)
    tokens = chords_str.split()
    for tok in tokens:
        # Extract root note: standard note optionally followed by s or b
        m = re.match(r'^([A-G][sb]?)', tok)
        if m:
            notes[m.group(1)] += 1

print(notes.most_common())
conn.close()
