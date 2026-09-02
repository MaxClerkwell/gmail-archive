import email
import os
import re
import time
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime

from . import db, gmail

STORE_RAW = os.environ.get("GMAIL_STORE_RAW", "0") == "1"
INTERVAL = int(os.environ.get("GMAIL_SYNC_INTERVAL", "0"))  # seconds, 0 = run once
BATCH = int(os.environ.get("GMAIL_FETCH_BATCH", "50"))


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


def _parse_fetch(parts):
    """Yield (uid, labels, raw) from a multi-message FETCH response."""
    for item in parts:
        if not isinstance(item, tuple):
            continue
        meta = item[0].decode(errors="replace")
        uid = re.search(r"UID (\d+)", meta)
        labels = re.search(r"X-GM-LABELS \((.*?)\)", meta)
        if uid:
            yield int(uid.group(1)), labels.group(1) if labels else "", item[1]


def _store(conn, uid, labels, raw):
    msg = email.message_from_bytes(raw)
    try:
        date = parsedate_to_datetime(msg["Date"]).astimezone(timezone.utc).isoformat()
    except Exception:
        date = msg.get("Date", "")
    conn.execute(
        "INSERT OR IGNORE INTO mails (uid, message_id, date, sender, recipients, subject, "
        "body_text, labels, raw) VALUES (?,?,?,?,?,?,?,?,?)",
        (uid, msg.get("Message-ID"), date, _hdr(msg, "From"), _hdr(msg, "To"),
         _hdr(msg, "Subject"), _body_text(msg), labels, raw if STORE_RAW else None),
    )


def sync_once():
    conn = db.connect()
    row = conn.execute("SELECT value FROM state WHERE key='last_uid'").fetchone()
    last_uid = int(row[0]) if row else 0

    imap = gmail.connect(readonly=True)

    _, data = imap.uid("SEARCH", None, f"UID {last_uid + 1}:*")
    uids = sorted(int(u) for u in data[0].split() if int(u) > last_uid)
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} fetching {len(uids)} new messages", flush=True)

    done = 0
    for i in range(0, len(uids), BATCH):
        chunk = uids[i:i + BATCH]
        _, parts = imap.uid("FETCH", ",".join(map(str, chunk)), "(X-GM-LABELS RFC822)")
        for uid, labels, raw in _parse_fetch(parts):
            _store(conn, uid, labels, raw)
        conn.execute("INSERT OR REPLACE INTO state VALUES ('last_uid', ?)", (str(chunk[-1]),))
        conn.commit()
        done += len(chunk)
        if done % 1000 < BATCH:
            print(f"  {done}/{len(uids)}", flush=True)

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
