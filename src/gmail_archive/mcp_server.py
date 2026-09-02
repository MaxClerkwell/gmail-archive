import os

from mcp.server.mcpserver import MCPServer

from . import db

mcp = MCPServer("gmail-archive", version="0.1.0")


@mcp.tool()
def list_mails(limit: int = 20, offset: int = 0, since: str | None = None) -> list[dict]:
    """List archived mails, newest first. `since` is an ISO date like 2026-01-31."""
    with db.connect() as conn:
        return db.list_mails(conn, min(limit, 200), offset, since)


@mcp.tool()
def get_mail(uid: int) -> dict:
    """Return one mail including its plain-text body."""
    with db.connect() as conn:
        return db.get_mail(conn, uid) or {"error": "not found"}


@mcp.tool()
def search_mails(query: str, limit: int = 20) -> list[dict]:
    """Full-text search over subject, sender and body (SQLite FTS5 syntax)."""
    with db.connect() as conn:
        return db.search_mails(conn, query, min(limit, 100))


@mcp.tool()
def archive_stats() -> dict:
    """Number of archived mails, newest date and last sync time."""
    with db.connect() as conn:
        return db.stats(conn)


def main():
    if os.environ.get("MCP_TRANSPORT", "streamable-http") == "stdio":
        mcp.run("stdio")
    else:
        mcp.run("streamable-http", host="0.0.0.0", port=int(os.environ.get("PORT", "8001")),
                stateless_http=True)


if __name__ == "__main__":
    main()
