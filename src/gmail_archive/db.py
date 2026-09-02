import os
import sqlite3

DB_PATH = os.environ.get("GMAIL_ARCHIVE_DB", "/data/mails.sqlite")

SCHEMA = """
CREATE TABLE IF NOT EXISTS mails (
    uid         INTEGER PRIMARY KEY,
    message_id  TEXT,
    date        TEXT,
    sender      TEXT,
    recipients  TEXT,
    subject     TEXT,
    body_text   TEXT,
    labels      TEXT,
    raw         BLOB,
    trashed_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_mails_date ON mails(date);
CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS mails_fts USING fts5(
    subject, sender, body_text, content='mails', content_rowid='uid'
);
CREATE TRIGGER IF NOT EXISTS mails_ai AFTER INSERT ON mails BEGIN
    INSERT INTO mails_fts(rowid, subject, sender, body_text)
    VALUES (new.uid, new.subject, new.sender, new.body_text);
END;
"""


def connect(path: str = DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(mails)")}
    if "trashed_at" not in cols:
        conn.execute("ALTER TABLE mails ADD COLUMN trashed_at TEXT")
    return conn


def row_to_dict(row: sqlite3.Row, with_body: bool = True) -> dict:
    d = {k: row[k] for k in row.keys() if k != "raw"}
    if not with_body:
        d.pop("body_text", None)
    return d


def list_mails(conn, limit=50, offset=0, since=None, with_body=False):
    sql = "SELECT * FROM mails"
    args: list = []
    if since:
        sql += " WHERE date >= ?"
        args.append(since)
    sql += " ORDER BY date DESC LIMIT ? OFFSET ?"
    args += [limit, offset]
    return [row_to_dict(r, with_body) for r in conn.execute(sql, args)]


def get_mail(conn, uid: int, with_body=True):
    row = conn.execute("SELECT * FROM mails WHERE uid = ?", (uid,)).fetchone()
    return row_to_dict(row, with_body) if row else None


def search_mails(conn, query: str, limit=20, with_body=False):
    rows = conn.execute(
        """SELECT m.* FROM mails_fts f JOIN mails m ON m.uid = f.rowid
           WHERE mails_fts MATCH ? ORDER BY rank LIMIT ?""",
        (query, limit),
    )
    return [row_to_dict(r, with_body) for r in rows]


def resolve_ids(conn, ids: list) -> tuple[list[int], list]:
    """Accept numeric UIDs or RFC Message-ID strings; return (found UIDs, unknown ids)."""
    uids, unknown = [], []
    for i in ids:
        if isinstance(i, int) or (isinstance(i, str) and i.isdigit()):
            row = conn.execute("SELECT uid FROM mails WHERE uid = ?", (int(i),)).fetchone()
        else:
            row = conn.execute("SELECT uid FROM mails WHERE message_id = ?", (i,)).fetchone()
        if row:
            uids.append(row["uid"])
        else:
            unknown.append(i)
    return uids, unknown


def mark_trashed(conn, uids: list[int]):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany("UPDATE mails SET trashed_at = ? WHERE uid = ?", [(now, u) for u in uids])
    conn.commit()


def stats(conn):
    total = conn.execute("SELECT COUNT(*) FROM mails").fetchone()[0]
    newest = conn.execute("SELECT MAX(date) FROM mails").fetchone()[0]
    last = conn.execute("SELECT value FROM state WHERE key='last_sync'").fetchone()
    return {"total": total, "newest": newest, "last_sync": last[0] if last else None}
