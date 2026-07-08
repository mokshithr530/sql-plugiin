# SQL AI Plugin

An enterprise-style natural language SQL assistant built with React, FastAPI, SQLite, and Gemini.

The goal of this project is simple: upload a database, ask a question in plain English, and get a safe SQL-backed answer without writing SQL manually.

## Features

- Floating React chat widget
- Database upload for `.db`, `.sqlite`, and `.sql` files
- MySQL-style `.sql` dump cleanup before SQLite import
- Database metadata chip with table and column counts
- FastAPI backend with clean upload, chat, status, and clear endpoints
- Schema reading for tables, columns, and foreign keys
- Gemini-powered SQL generation
- SQL validation before execution
- Retry pipeline for invalid or failed SQL
- Safe query execution with automatic row limits
- Natural-language answer generation from query results
- Multi-key Gemini fallback using `GEMINI_API_KEYS`
- Config-based LLM provider/model setup for future MCP or model switching

## Tech Stack

Frontend:

- React
- TypeScript
- Vite
- Tailwind CSS
- Lucide React

Backend:

- FastAPI
- SQLite
- Pandas
- Gemini API
- python-dotenv

## Project Structure

```text
src/
  components/
  hooks/
  services/
  types/

backend/
  main.py
  config.py
  database_manager.py
  sql_importer.py
  schema_reader.py
  validator.py
  sql_executor.py
  session_memory.py
  llm.py
  chat_pipeline.py
```

## Setup

Install frontend dependencies:

```bash
npm install
```

Install backend dependencies:

```bash
pip install fastapi uvicorn pandas python-dotenv google-generativeai python-multipart
```

Create a backend environment file:

```bash
copy backend\.env.example backend\.env
```

Add your Gemini key or keys:

```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_API_KEYS=your_primary_key,your_backup_key
GEMINI_MODEL=gemini-2.5-flash
LLM_PROVIDER=gemini
QUERY_ROW_LIMIT=100
```

`GEMINI_API_KEYS` is optional, but useful on free tier. The backend tries the configured keys in order and falls back when a quota/rate/auth style error happens.

## Running Locally

Start the backend:

```bash
cd backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Start the frontend:

```bash
npm run dev
```

Open the Vite URL, upload a database, and ask questions in the chat widget.

## API Endpoints

`POST /upload`

Uploads a database file, connects it, reads the schema, and stores the active session.

`POST /chat`

Receives a natural-language question, generates SQL, validates it, executes it safely, and returns a natural-language answer.

`GET /status`

Returns backend status, active database state, supported uploads, and LLM configuration summary.

`POST /clear`

Clears the active session and disconnects the database.

## Supported Databases

Currently supported:

- SQLite `.db`
- SQLite `.sqlite`
- SQL dump `.sql`

MySQL-style dump files are partially supported by normalizing common MySQL syntax into SQLite-compatible SQL before import.

Live MySQL server connections are not implemented yet. The database layer is structured so MySQL, PostgreSQL, or SQL Server can be added later without changing the frontend chat flow.

## Safety

The backend validates generated SQL before execution:

- Only `SELECT` and `WITH` queries are allowed
- Dangerous keywords are blocked
- Multiple SQL statements are blocked
- Tables and columns are checked against the active schema
- Query output is limited by `QUERY_ROW_LIMIT` unless the generated SQL already contains a limit

The frontend never talks directly to Gemini. All LLM calls happen through FastAPI.

## Testing

Frontend:

```bash
npm run build
npm run lint
```

Backend syntax check:

```bash
python -m compileall backend
```

The upload and chat pipeline has been tested with:

- no database connected
- unsupported upload extensions
- SQLite upload
- MySQL-style `.sql` dump upload
- missing Gemini key
- mocked full chat success
- unsafe SQL blocking

## Roadmap

- Real Gemini end-to-end testing with production keys
- Provider interface for MCP server integration
- Live MySQL/PostgreSQL connection support
- SQL parser validation with `sqlglot`
- Result table preview in the chat UI
- CSV and Excel export
- Chart generation
- Authentication and multi-session support
- Docker deployment

## Author

Mokshith Reddy Nallaballe
