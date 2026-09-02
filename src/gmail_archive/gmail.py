"""Shared IMAP helpers."""
import imaplib
import os
import re

MAILBOX = os.environ.get("GMAIL_MAILBOX", "[Gmail]/All Mail")


def connect(readonly: bool = True) -> imaplib.IMAP4_SSL:
    imap = imaplib.IMAP4_SSL("imap.gmail.com")
    imap.login(os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"])
    imap.select(f'"{MAILBOX}"', readonly=readonly)
    return imap


def trash_folder(imap: imaplib.IMAP4_SSL) -> str:
    """Find the folder flagged \\Trash (name depends on the account language)."""
    _, boxes = imap.list()
    for line in boxes:
        text = line.decode(errors="replace")
        if "\\Trash" in text:
            m = re.search(r'"([^"]+)"\s*$', text)
            if m:
                return m.group(1)
    return "[Gmail]/Trash"


def trash(uids: list[int]) -> list[int]:
    """Move messages to Gmail's trash (auto-purged after 30 days). Returns moved UIDs."""
    if not uids:
        return []
    imap = connect(readonly=False)
    try:
        folder = trash_folder(imap)
        moved = []
        for uid in uids:
            status, _ = imap.uid("COPY", str(uid), f'"{folder}"')
            if status == "OK":
                moved.append(uid)
        return moved
    finally:
        imap.logout()
