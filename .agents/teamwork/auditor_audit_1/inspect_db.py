import sqlite3

conn = sqlite3.connect('noospire.db')
cursor = conn.cursor()

wal = cursor.execute('PRAGMA journal_mode;').fetchone()
print(f"PRAGMA journal_mode: {wal[0]}")

tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;").fetchall()
print(f"\nTotal tables: {len(tables)}")
for (tname,) in tables:
    count = cursor.execute(f"SELECT count(*) FROM [{tname}];").fetchone()[0]
    cols = [col[1] for col in cursor.execute(f"PRAGMA table_info([{tname}]);").fetchall()]
    print(f"  {tname} ({count} records): {cols[:6]}...")

print("\n--- Assets sample ---")
for row in cursor.execute("SELECT * FROM assets LIMIT 3;").fetchall():
    print(" ", row)

print("\n--- Scans sample ---")
for row in cursor.execute("SELECT * FROM scans LIMIT 3;").fetchall():
    print(" ", row)

print("\n--- Findings sample ---")
for row in cursor.execute("SELECT * FROM findings LIMIT 3;").fetchall():
    print(" ", row)

conn.close()
