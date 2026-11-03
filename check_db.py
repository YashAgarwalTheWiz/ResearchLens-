# check_db.py — look inside the local database. Run from the project root:
#   python check_db.py                      -> list sessions
#   python check_db.py delete <session_id>  -> delete one session (and its chunks)
import sys

from services.db import get_connection, init_db

init_db()
conn = get_connection()

cols = [r[1] for r in conn.execute("PRAGMA table_info(rpa_sessions)")]
print("columns:", cols)

rows = conn.execute("""
    SELECT s.session_id, s.pdf_name, s.created_at,
           s.extracted IS NOT NULL AS has_extracted,
           s.positioning IS NOT NULL AS has_positioning,
           (SELECT COUNT(*) FROM rpa_chunks c WHERE c.session_id = s.session_id) AS chunks
    FROM rpa_sessions s ORDER BY s.created_at DESC
""").fetchall()
for row in rows:
    print(row)

if len(sys.argv) == 3 and sys.argv[1] == "delete":
    sid = sys.argv[2]
    conn.execute("DELETE FROM rpa_chunks WHERE session_id = ?", (sid,))
    conn.execute("DELETE FROM rpa_sessions WHERE session_id = ?", (sid,))
    conn.commit()
    print("deleted", sid)

conn.close()