import sqlite3

con = sqlite3.connect("noospire.db")
cur = con.cursor()
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(f"Total tables: {len(tables)}")
for t in sorted(tables):
    cnt = cur.execute(f"SELECT count(*) FROM [{t}]").fetchone()[0]
    print(f"  {t}: {cnt} records")
con.close()
