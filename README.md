# gmail-archive

Pulls a Gmail mailbox into a local SQLite database via IMAP and exposes it
to local tooling (for example a self-hosted LLM) through a small REST API and
an MCP server. No OAuth, no browser: authentication uses a Gmail app password,
so it runs fine on a headless server.

## Components

| Service | What it does                                        | Port |
|---------|-----------------------------------------------------|------|
| `sync`  | Fetches new messages twice a day (incremental, by UID) | –    |
| `api`   | FastAPI: `/mails`, `/mails/{uid}`, `/search`, `/stats` | 8000 |
| `mcp`   | MCP server (streamable HTTP) with the same operations as tools | 8001 |

All three share one SQLite file with FTS5 full-text search.

## Setup

1. Enable 2-step verification in your Google account and create an
   **app password** (Google account → Security → App passwords). This is the
   only step that needs a browser and can be done on any device.
2. Copy `.env.example` to `.env` and fill in user and app password.
   German accounts need `GMAIL_MAILBOX=[Gmail]/Alle Nachrichten`.
3. Start everything:

   ```sh
   docker compose up -d --build
   ```

The first run downloads the whole mailbox; afterwards only new messages are
fetched. The sync interval is set in `compose.yaml` (`GMAIL_SYNC_INTERVAL`,
seconds; default 43200 = twice a day). Messages are fetched in batches of
`GMAIL_FETCH_BATCH` (default 50) per IMAP round trip.

## Running without Docker

```sh
uv sync
cp .env.example .env            # then edit
set -a; . ./.env; set +a
export GMAIL_ARCHIVE_DB=./mails.sqlite
uv run gmail-archive-sync       # one-off sync (GMAIL_SYNC_INTERVAL unset)
uv run gmail-archive-api        # http://localhost:8000/docs
uv run gmail-archive-mcp        # http://localhost:8001/mcp
```

## REST API

```
GET /mails?limit=50&offset=0&since=2026-01-01&body=false
GET /mails/{uid}
GET /search?q=invoice+AND+2026&limit=20
GET /stats
POST /mails/trash        {"ids": [123, "<message-id@example.com>"]}
```

`POST /mails/trash` moves the given mails (by UID or Message-ID) into Gmail's
trash, where Google purges them automatically after 30 days. The local copy is
kept and marked with `trashed_at`. This is the only write operation; the MCP
server stays read-only.

Interactive docs at `/docs`.

## MCP

The MCP server speaks streamable HTTP at `http://<host>:8001/mcp` and offers
the tools `list_mails`, `get_mail`, `search_mails` and `archive_stats`.
For stdio clients set `MCP_TRANSPORT=stdio`.

Example client configuration:

```json
{
  "mcpServers": {
    "gmail-archive": { "url": "http://localhost:8001/mcp" }
  }
}
```

## Notes

- The API and MCP server have no authentication. Keep the ports on a
  private network or put a reverse proxy in front of them.
- `GMAIL_STORE_RAW=1` additionally stores the complete RFC822 message
  (including attachments) in the `raw` column.
- The database lives in the `data` volume at `/data/mails.sqlite`.

## License

MIT
