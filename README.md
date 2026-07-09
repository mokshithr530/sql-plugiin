# SQL Assistant POC

A small proof-of-concept app for asking questions about an uploaded SQL database in natural language.

You upload a `.db`, `.sqlite`, or `.sql` file. The backend reads the schema, asks the configured LLM to generate SQL, validates the SQL, runs it safely, and returns a short answer.

## Stack

- Frontend: React, TypeScript, Vite, Tailwind CSS
- Backend: FastAPI, SQLite, Pandas
- LLM: configured through `backend/.env`

## Architecture

High-level structure:

```text
Browser
  |
  v
React UI
  |
  v
src/services/api.ts
  |
  v
FastAPI backend
  |
  +--> Upload / schema / session
  |
  +--> Chat pipeline
          |
          +--> LLM provider layer
          |
          +--> SQL validator
          |
          +--> SQL executor
          |
          v
        Answer returned to UI
```

Upload flow:

```text
User uploads database
  |
  v
POST /upload
  |
  v
Validate file type
  |
  v
Save file in backend/uploads
  |
  v
Connect SQLite database
  |
  v
Read tables, columns, foreign keys
  |
  v
Store active database in session memory
```

Chat flow:

```text
User asks question
  |
  v
POST /chat
  |
  v
Read active schema
  |
  v
LLM generates SQL
  |
  v
Validate SQL safety
  |
  v
Execute SQL
  |
  v
LLM explains result
  |
  v
Return answer + SQL + rows
```

LLM and MCP design:

```text
chat_pipeline.py
  |
  v
LLMService
  |
  v
Provider
  |
  +--> Gemini
  |
  +--> Anthropic
  |
  +--> OpenAI-compatible APIs

MCP client (Claude Desktop, Claude Code, or another host)
  |
  v
backend/mcp_server.py
  |
  +--> inspect_schema
  |
  +--> execute_read_query (read-only)
```

The frontend never calls the LLM directly. All provider calls happen inside the FastAPI backend.

## First-Time Setup

Run these commands from the project root:

```powershell
npm install
pip install -r requirements.txt
```

Create your private environment file:

```powershell
copy backend\.env.example backend\.env
```

Open `backend/.env` and replace the placeholder key:

```env
LLM_PROVIDER=auto
LLM_API_KEYS=paste_your_real_api_key_here
LLM_MODEL=
LLM_FALLBACK_MODELS=gemini-2.5-flash-lite,gemini-2.0-flash
GEMINI_TIMEOUT_SECONDS=20
QUERY_ROW_LIMIT=100
```

`auto` recognizes Gemini (`AIza...`), Anthropic (`sk-ant-...`), and OpenAI
(`sk-...`) keys. Set `LLM_PROVIDER` explicitly for unusual key formats. For an
OpenAI-compatible service, also set `LLM_BASE_URL`.

## MCP Server

Set an absolute SQLite path in `backend/.env`:

```env
MCP_DATABASE_PATH=C:\absolute\path\to\database.sqlite
```

Start the stdio MCP server with:

```powershell
python backend\mcp_server.py
```

Configure your MCP host to run that command from this project directory. MCP is
independent of the LLM provider, so Claude, OpenAI, Gemini, or another MCP host
can use the same tools.

## Redis Cache

Redis is optional. To cache repeated answers:

```env
REDIS_URL=redis://localhost:6379/0
CACHE_TTL_SECONDS=3600
```

When Redis is unavailable or `REDIS_URL` is blank, the app continues without
caching. Cache entries are separated by question, database fingerprint,
provider, and model.

Important:

- Put real keys only in `backend/.env`.
- Do not put real keys in `backend/.env.example`.
- `backend/.env` is ignored by Git.

## How To Run

Open two terminals.

**Terminal 1: backend**

```powershell
cd backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Check backend status:

```text
http://127.0.0.1:8000/status
```

**Terminal 2: frontend**

From the project root:

```powershell
npm run dev
```

Open the Vite URL shown in the terminal. Usually:

```text
http://localhost:5173
```

Then:

1. Click the chat button.
2. Upload a `.db`, `.sqlite`, or `.sql` file.
3. Ask a question about the database.

Example:

```text
How many orders are there?
```

## Tests

Run backend tests:

```powershell
python -m pytest -q
```

Run frontend checks:

```powershell
npm run build
npm run lint
```

Optional backend syntax check:

```powershell
python -m compileall backend
```

## Common Errors

**`LLM API key is not configured`**

Fix:

- Make sure `backend/.env` exists.
- Make sure it contains `LLM_API_KEYS=your_real_key`.
- Restart the backend after editing `.env`.

**`503 UNAVAILABLE` or model high demand**

This means the LLM provider is temporarily busy.

Fix:

- Try again after a short wait.
- Keep fallback models in `LLM_FALLBACK_MODELS`.

**Frontend opens, but chat cannot connect**

Fix:

- Make sure the backend is running on `http://127.0.0.1:8000`.
- Open `http://127.0.0.1:8000/status` and confirm it says `backend: online`.

**`127.0.0.1:5173` does not open**

Vite may be listening on `localhost`.

Fix:

- Open `http://localhost:5173`.
- Or restart frontend with:

```powershell
npm run dev -- --host 127.0.0.1
```

**Uploaded database disappeared**

The active database is stored in memory.

Fix:

- Re-upload the database after restarting the backend.

**SSL or certificate error when calling the LLM**

Fix:

```powershell
pip install -r requirements.txt
```

The project includes `python-certifi-win32` and `truststore` so Python can use trusted Windows certificates.

**Port 8000 already in use**

Fix:

- Stop the old backend terminal.
- Or run the backend on another port and update `src/services/api.ts`.

## Notes

- The frontend never calls the LLM directly.
- Only the FastAPI backend talks to the LLM provider.
- Gemini, Anthropic, and OpenAI-compatible providers are supported.
- MCP exposes the database tools and is intentionally separate from provider selection.

## Author

Mokshith Reddy Nallaballe
