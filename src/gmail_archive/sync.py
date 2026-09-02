import email
import os
import time
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime

from . import db, gmail

STORE_RAW = os.environ.get("GMAIL_STORE_RAW", "0") == "1"
INTERVAL = int(os.environ.get("GMAIL_SYNC_INTERVAL", "0"))  # seconds, 0 = run once


def _hdr(msg, name):
    value = msg.get(name, "")
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _body_text(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", "replace")
        return ""
    payload = msg.get_payload(decode=True)
    return payload.decode(msg.get_content_charset() or "utf-8", "replace") if payload else ""


def sync_once():
    conn = db.connect()
    row = conn.execute("SELECT value FROM state WHERE key='last_uid'").fetchone()
    last_uid = int(row[0]) if row else 0

    imap = gmail.connect(readonly=True)

    _, data = imap.uid("SEARCH", None, f"UID {last_uid + 1}:*")
    uids = [u for u in data[0].split() if int(u) > last_uid]
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} fetching {len(uids)} new messages", flush=True)

    for uid in uids:
        _, parts = imap.uid("FETCH", uid, "(X-GM-LABELS RFC822)")
        raw = parts[0][1]
        labels = parts[0][0].decode(errors="replace")
        msg = email.message_from_bytes(raw)
        try:
            date = parsedate_to_datetime(msg["Date"]).astimezone(timezone.utc).isoformat()
        except Exception:
            date = msg.get("Date", "")
        conn.execute(
            "INSERT OR IGNORE INTO mails VALUES (?,?,?,?,?,?,?,?,?)",
            (int(uid), msg.get("Message-ID"), date, _hdr(msg, "From"), _hdr(msg, "To"),
             _hdr(msg, "Subject"), _body_text(msg), labels, raw if STORE_RAW else None),
        )
        conn.execute("INSERT OR REPLACE INTO state VALUES ('last_uid', ?)", (str(int(uid)),))
        conn.commit()

    conn.execute("INSERT OR REPLACE INTO state VALUES ('last_sync', ?)",
                 (datetime.now(timezone.utc).isoformat(),))
    conn.commit()
    imap.logout()
    conn.close()


def main():
    while True:
        try:
            sync_once()
        except Exception as e:  # keep the loop alive on transient IMAP errors
            print(f"sync failed: {e}", flush=True)
        if INTERVAL <= 0:
            break
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
