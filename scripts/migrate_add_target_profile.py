import sqlite3

conn = sqlite3.connect("data/crime_analysis.db")
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cur.fetchall()
print("Tables:", tables)

cur.execute("PRAGMA table_info(cases)")
cols = cur.fetchall()
print("Cases columns:", [c[1] for c in cols])

# Add target_profile column if missing
col_names = [c[1] for c in cols]
if "target_profile" not in col_names:
    cur.execute("ALTER TABLE cases ADD COLUMN target_profile TEXT DEFAULT '{}'")
    conn.commit()
    print("Added target_profile column to cases table.")
else:
    print("target_profile column already exists.")

conn.close()
