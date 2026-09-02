import os

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from . import db, gmail

app = FastAPI(title="gmail-archive", version="0.1.0")


@app.get("/mails")
def mails(limit: int = Query(50, le=500), offset: int = 0, since: str | None = None,
          body: bool = False):
    with db.connect() as conn:
        return db.list_mails(conn, limit, offset, since, body)


@app.get("/mails/{uid}")
def mail(uid: int):
    with db.connect() as conn:
        m = db.get_mail(conn, uid)
    if not m:
        raise HTTPException(404, "not found")
    return m


@app.get("/search")
def search(q: str, limit: int = Query(20, le=200), body: bool = False):
    with db.connect() as conn:
        return db.search_mails(conn, q, limit, body)


class TrashRequest(BaseModel):
    ids: list[int | str]


@app.post("/mails/trash")
def trash_mails(req: TrashRequest):
    """Move mails to Gmail's trash (purged after 30 days). Accepts UIDs or Message-IDs."""
    with db.connect() as conn:
        uids, unknown = db.resolve_ids(conn, req.ids)
        if not uids:
            raise HTTPException(404, "no matching mails")
        try:
            moved = gmail.trash(uids)
        except Exception as e:
            raise HTTPException(502, f"imap error: {e}")
        db.mark_trashed(conn, moved)
    return {"trashed": moved, "not_found": unknown}


@app.get("/stats")
def stats():
    with db.connect() as conn:
        return db.stats(conn)


def main():
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
