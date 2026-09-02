# gmail-archive – agent guide

This file describes how an AI agent should use the mail archive and how a
coding agent should work on this repository.

## What this is

A read-mostly archive of one Gmail mailbox in SQLite. New mail is pulled by
IMAP twice a day. Agents access the archive through:

- **MCP** (preferred): streamable HTTP at `http://<host>:8001/mcp`
- **REST**: `http://<host>:8000`, OpenAPI docs at `/docs`

The archive is the source of truth for reading. Gmail itself is only touched
for syncing and for moving mails to the trash.

## Using the archive as an agent

### Tools (MCP) / endpoints (REST)

| MCP tool        | REST                       | Purpose                                             |
|-----------------|----------------------------|-----------------------------------------------------|
| `archive_stats` | `GET /stats`               | Number of mails, newest date, last sync             |
| `list_mails`    | `GET /mails`               | Newest first; `limit`, `offset`, `since=YYYY-MM-DD` |
| `search_mails`  | `GET /search?q=`           | Full-text search over subject, sender, body         |
| `get_mail`      | `GET /mails/{uid}`         | One mail including plain-text body                  |
| –               | `POST /mails/trash`        | Move mails to Gmail trash (purged after 30 days)    |

Every mail has a stable integer `uid`. Use it to refer to mails between calls.
Lists and search results contain headers only (`uid`, `date`, `sender`,
`recipients`, `subject`, `labels`); the body is only returned by `get_mail`.

### Working with a small context window

1. Start with `archive_stats` to learn the date range.
2. Narrow first: `search_mails` with a specific query, or `list_mails` with
   `since`. Ask for 10–20 results, not hundreds.
3. Fetch bodies one at a time with `get_mail` and only for mails you actually
   need. Bodies of newsletters can be long; summarise and move on.
4. Do not page through the whole archive. If a question needs aggregation
   over many mails, say so and suggest a batch job instead.

### Search syntax

`search_mails` uses SQLite FTS5:

- `sparkasse rechnung` – both words
- `sparkasse OR volksbank`
- `"kündigung zum"` – phrase
- `rechn*` – prefix
- `sender:zillow` – restrict to a column (`subject`, `sender`, `body_text`)

Dates are ISO 8601 in UTC, e.g. `2026-09-01T08:00:00+00:00`.

### Deleting

`POST /mails/trash` with `{"ids": [uid, "<message-id>", ...]}` moves mails to
Gmail's trash. Google deletes them permanently after 30 days; the archive keeps
its copy and sets `trashed_at`. The MCP server does not expose this on purpose.
Only call it when the user explicitly asks to delete specific mails, and list
the affected mails before doing so.

### Privacy

The archive contains private correspondence. Do not quote more of a mail than
the task requires, and never send mail content to third-party services.

## Working on the repository

Layout:

```
src/gmail_archive/
  db.py          schema, migrations, queries – shared by API and MCP
  gmail.py       IMAP connection, trash folder lookup, trash()
  sync.py        incremental fetch (batched UID FETCH) into SQLite
  api.py         FastAPI app
  mcp_server.py  MCP server (mcp>=2, MCPServer)
compose.yaml     three services (sync, api, mcp) sharing the `data` volume
```

Conventions:

- Python 3.13, managed with `uv`. `uv sync`, then `uv run gmail-archive-<sync|api|mcp>`.
- Put queries in `db.py`; `api.py` and `mcp_server.py` stay thin wrappers.
- The IMAP connection is opened read-only everywhere except `gmail.trash()`.
- Schema changes go into `SCHEMA` plus an idempotent migration in `db.connect()`;
  existing databases must keep working.
- Never store credentials in the repo. Configuration is environment only, see
  `.env.example`.
- Test with a scratch database: `GMAIL_ARCHIVE_DB=/tmp/t.sqlite`, mock
  `gmail.connect` for sync tests, `fastapi.testclient` for the API.
- Verify `docker build .` succeeds before committing.
