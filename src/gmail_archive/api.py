import os

import uvicorn
from fastapi import FastAPI, HTTPException, Query

from . import db

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


@app.get("/stats")
def stats():
    with db.connect() as conn:
        return db.stats(conn)


def main():
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
