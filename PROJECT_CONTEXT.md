# SQL Assistant POC - Project Context

Author: Mokshith Reddy Nallaballe

---

## Project Goal

This project is a proof-of-concept natural language SQL assistant.

The user uploads a SQL database file, asks a question in plain English, and receives a safe SQL-backed answer. The user does not need to write SQL manually.

Example flow:

1. User uploads `employees.sqlite`.
2. User asks: `Who are the top 10 highest paid employees?`
3. Backend reads the database schema.
4. Backend asks the configured LLM to generate SQL.
5. Backend validates the SQL.
6. Backend executes the SQL safely.
7. Backend returns a natural-language answer with the result.

---

## Current Status

The POC is working end to end.

Completed:

- Frontend POC workspace.
- Floating chat widget.
- Database upload from UI.
- Database metadata chip.
- Backend upload endpoint.
- Backend chat endpoint.
- SQLite database connection.
- `.sql` dump import into temporary SQLite.
- Schema reading.
- SQL generation using the configured LLM provider.
- SQL validation before execution.
- Safe SQL execution.
- Natural-language answer generation.
- Deterministic ecommerce product/category analysis for common manager questions.
- Deterministic revenue-at-risk analysis for loss/risk questions when cost data is unavailable.
- In-memory session state.
- Real Gemini end-to-end test.
- Provider-ready LLM layer for future MCP or other providers.
- Backend tests.
- GitHub Actions test workflow.
- Short README with setup, run steps, and troubleshooting.

Still left:

- Connect and verify the MCP server in the manager's chosen MCP host.
- Browser end-to-end automated tests.
- More tests for `.sql` import and retry behavior.
- Generalize deterministic business-analysis templates beyond Olist-style ecommerce schemas.
- Persistent sessions.
- Better result display/export in the UI.
- Authentication and deployment setup.

---

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
- python-dotenv
- google-genai

Testing:

- pytest
- FastAPI TestClient
- npm build/lint

---

## Architecture

The frontend never talks directly to the LLM.

Current request flow:

```text
React UI
-> src/services/api.ts
-> FastAPI backend
-> chat_pipeline.py
-> llm.py / provider layer
-> configured LLM provider
-> SQL validator
-> SQL executor
-> response back to UI
```

Important design decision:

```text
Frontend = UI only
Backend = schema, SQL generation, validation, execution, LLM calls
```

This keeps API keys and database logic out of the browser.

---

## Provider / LLM Design

The project is no longer hardcoded directly around Gemini in the app flow.

Current structure:

- `chat_pipeline.py` calls `llm.generate_sql()`, `llm.rewrite_failed_sql()`, and `llm.generate_answer()`.
- `llm.py` owns prompt construction and provider calls.
- `GeminiProvider` is currently implemented.
- Gemini, Anthropic, and OpenAI-compatible provider adapters are implemented.
- Provider auto-detection handles common API-key prefixes.
- `config.py` supports generic `LLM_*` environment variables.

Current working provider:

```text
LLM_PROVIDER=gemini
```

Supported generic environment variables:

```env
LLM_PROVIDER=gemini
LLM_API_KEYS=paste_your_real_api_key_here
LLM_MODEL=gemini-2.5-flash
LLM_FALLBACK_MODELS=gemini-2.5-flash-lite,gemini-2.0-flash
```

Backward-compatible Gemini-specific variables are still supported:

```env
GEMINI_API_KEY=...
GEMINI_API_KEYS=...
GEMINI_MODEL=...
GEMINI_FALLBACK_MODELS=...
```

Important clarification:

- Generic `LLM_*` naming is supported.
- Only Gemini is implemented today.
- Other providers will need their own provider class in `backend/llm.py`.
- MCP can be added by implementing `MCPProvider`.

---

## MCP Server

MCP is a tool protocol, not an LLM provider. The implemented path is:

```text
MCP host
-> backend/mcp_server.py
-> inspect_schema / execute_read_query
-> read-only SQLite connection
```

Files that should usually not need major changes for MCP:

- `main.py`
- `chat_pipeline.py`
- frontend components
- `sql_executor.py`
- `validator.py`

The server is provider-independent and can be used by Claude or any other
MCP-compatible host. SQL connections use SQLite read-only mode and results are
bounded by `QUERY_ROW_LIMIT`.

Redis response caching is optional. When `REDIS_URL` is configured, successful
answers are cached using the normalized question, database file fingerprint,
provider, and model. A Redis outage does not stop the application.

Do not put MCP logic into React components. Keep provider-specific logic inside the backend provider layer.

---

## Important Files

Frontend:

- `src/App.tsx` - POC workspace page.
- `src/components/ChatWidget.tsx` - floating chat container and database state.
- `src/components/ChatInput.tsx` - message input and upload control.
- `src/components/UploadDatabase.tsx` - database upload UI.
- `src/components/DatabaseChip.tsx` - connected database display.
- `src/components/ChatMessages.tsx` - chat transcript.
- `src/services/api.ts` - all frontend backend API calls.
- `src/types/` - shared frontend TypeScript types.

Backend:

- `backend/main.py` - FastAPI app and HTTP endpoints.
- `backend/chat_pipeline.py` - upload-to-answer orchestration.
- `backend/chat_pipeline.py` also contains POC business-analysis shortcuts for common ecommerce questions such as best product/category and revenue at risk.
- `backend/llm.py` - LLM service and provider layer.
- `backend/config.py` - environment/config values.
- `backend/database_manager.py` - database connection management.
- `backend/sql_importer.py` - `.sql` dump conversion.
- `backend/schema_reader.py` - schema extraction.
- `backend/validator.py` - SQL safety checks.
- `backend/sql_executor.py` - safe SQL execution.
- `backend/session_memory.py` - in-memory active session state.

Tests:

- `tests/test_api.py`
- `tests/test_sql_executor.py`
- `tests/test_validator.py`
- `tests/conftest.py`

---

## API Endpoints

`POST /upload`

Uploads a database file, validates the extension, connects the database, reads schema, stores session state, and returns database metadata.

`POST /chat`

Receives a natural-language question, generates SQL, validates it, executes it safely, generates an answer, and returns the answer, SQL, and result payload.

`GET /status`

Returns backend status, active database state, supported uploads, provider name, model name, and configured key count.

`POST /clear`

Clears session memory and disconnects the active database.

---

## Supported Uploads

Currently supported:

- `.db`
- `.sqlite`
- `.sql`

Notes:

- `.db` and `.sqlite` are opened directly as SQLite databases.
- `.sql` dumps are converted into temporary SQLite databases.
- Live MySQL, PostgreSQL, and SQL Server connections are not implemented yet.

---

## Security / SQL Safety

The backend validates LLM-generated SQL before execution.

Current protections:

- Only `SELECT` and `WITH` queries are allowed.
- Dangerous keywords are blocked.
- Multiple SQL statements are blocked.
- Referenced tables are checked against schema.
- Referenced columns are checked against schema.
- Row limit is added when generated SQL has no `LIMIT`.
- Aggregate expressions such as `SUM(...)`, `AVG(...)`, and `COUNT(DISTINCT ...)` are allowed for analytical queries.

Blocked SQL keywords include:

- `DROP`
- `DELETE`
- `UPDATE`
- `INSERT`
- `ALTER`
- `CREATE`
- `TRUNCATE`
- `ATTACH`
- `DETACH`
- `REPLACE`
- `PRAGMA`

Future improvement:

- Replace regex/string-based validation with a SQL parser such as `sqlglot`.

---

## Environment Files

`backend/.env.example`

- Safe template.
- Committed to the repo.
- Does not contain real keys.
- Shows what variables are needed.

`backend/.env`

- Private local file.
- Contains real API keys.
- Must not be committed.
- Ignored by `.gitignore`.

Setup:

```powershell
copy backend\.env.example backend\.env
```

Then edit `backend/.env` and set:

```env
LLM_PROVIDER=gemini
LLM_API_KEYS=your_real_key_here
LLM_MODEL=gemini-2.5-flash
LLM_FALLBACK_MODELS=gemini-2.5-flash-lite,gemini-2.0-flash
GEMINI_TIMEOUT_SECONDS=20
QUERY_ROW_LIMIT=100
```

---

## Problems Found And Fixed

Missing API key in UI:

- Problem: UI showed that the Gemini/LLM key was not configured.
- Cause: backend process was stale or config was not loading `backend/.env` reliably.
- Fix: `config.py` now loads `backend/.env` by absolute path based on the backend directory.

SSL certificate failure:

- Problem: live Gemini calls failed with `CERTIFICATE_VERIFY_FAILED`.
- Cause: Windows trusted the connection, but Python did not trust the local certificate chain. Avast SSL scanning was present.
- Fix: added `python-certifi-win32` and `truststore`, and configured the backend to use trusted certificates before creating the LLM client.

Deprecated Google SDK:

- Problem: old `google.generativeai` package showed a deprecation warning.
- Fix: migrated to the current `google-genai` package and `google.genai` client.

Gemini model high demand:

- Problem: provider returned `503 UNAVAILABLE` when the selected model was busy.
- Fix: fallback model config was added through `LLM_FALLBACK_MODELS` / `GEMINI_FALLBACK_MODELS`.

Product analysis query failed:

- Problem: questions like `which product was sold the most?` could fail because the LLM had to infer several ecommerce joins and the validator rejected some aggregate expressions.
- Cause: the Olist schema needs joins across `order_items`, `products`, and `product_category_name_translation`; the validator also mishandled aggregate SQL in some cases.
- Fix: added a deterministic ecommerce product/category SQL path in `chat_pipeline.py`, improved aggregate validation, and fixed duplicate `LIMIT` handling in `sql_executor.py`.

Loss / risk management question needed better handling:

- Problem: questions like `what is the loss and how should I manage it?` are business-analysis questions, not simple lookup questions.
- Cause: the Olist database does not contain true cost, margin, or refund-cost fields, so true profit/loss cannot be calculated directly.
- Fix: added a deterministic revenue-at-risk SQL path using canceled/unavailable orders from `orders` joined with `order_items`. The answer explains that this is a proxy, not true loss, and suggests management actions.

Confusing `.env` setup:

- Problem: unclear whether real keys should go in `.env` or `.env.example`.
- Fix: `.env.example` and README now clearly say real keys go only in `backend/.env`.

Outdated project context:

- Problem: old context said `/chat` was not implemented and included GitHub setup instructions.
- Fix: this file now reflects the current implementation and removes the GitHub section.

UI looked too decorative:

- Problem: first UI version felt like a generic landing page.
- Fix: UI was simplified into a crisp POC workspace with a cleaner chat widget.

---

## Testing Done

Commands run successfully:

```powershell
python -m pytest -q
npm run build
npm run lint
python -m compileall backend
```

Current pytest coverage:

- validator blocks unsafe SQL.
- validator accepts valid SELECT queries.
- validator rejects unknown tables/columns.
- SQL executor returns dataframe payloads.
- SQL executor applies default row limits.
- SQL executor returns failure for bad SQL.
- API upload works with a temporary SQLite DB.
- API chat works with mocked LLM behavior.
- Chat rejects questions when no database is uploaded.

Real provider test:

- A real temporary SQLite database was uploaded.
- Real Gemini call generated SQL.
- SQL was validated and executed.
- Natural-language answer was returned successfully.

Business analysis tests run manually against `olist.sqlite`:

- `which product was sold the most?` returns `bed_bath_table` as the top category by units sold and includes revenue context.
- `what product should I focus on more?` recommends `health_beauty` based on revenue and volume.
- `what is the loss how should i manage it?` reports canceled/unavailable orders as revenue-at-risk and explains how to manage the issue.

---

## How To Run

Install dependencies:

```powershell
npm install
pip install -r requirements.txt
```

Create `.env`:

```powershell
copy backend\.env.example backend\.env
```

Start backend:

```powershell
cd backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Start frontend from project root:

```powershell
npm run dev
```

Open:

```text
http://localhost:5173
```

Backend status:

```text
http://127.0.0.1:8000/status
```

---

## Known Limitations

- Sessions are stored in memory only.
- Uploaded database must be re-uploaded after backend restart.
- Only one active database/session is supported.
- Provider key auto-detection depends on common key prefixes; unusual providers
  should set `LLM_PROVIDER`, `LLM_MODEL`, and optionally `LLM_BASE_URL`.
- MCP currently supports `.db` and `.sqlite`; `.sql` dumps should first be
  imported through the web application.
- SQL validation is conservative and regex-based.
- POC business-analysis shortcuts currently target Olist-style ecommerce schemas.
- True profit/loss requires cost, margin, refund, or expense data. If those fields are missing, the app reports revenue at risk instead.
- UI does not yet show rich result tables or charts.
- No authentication.
- No production deployment configuration.

---

## Recommended Next Work

High priority:

- Implement actual `MCPProvider` when MCP server/tool contract is known.
- Add tests for provider fallback behavior.
- Add tests for `.sql` dump import.
- Add automated tests for product/category and revenue-at-risk analysis paths.
- Add browser-level workflow test.
- Rotate any real API keys if they were ever exposed outside `backend/.env`.

Medium priority:

- Add result table display in the chat UI.
- Add SQL preview/copy option if needed for demos.
- Add persistent session storage.
- Improve logging around provider calls and retry decisions.

Later:

- Add OpenAI/Anthropic providers if required.
- Add live database connections for PostgreSQL/MySQL.
- Add authentication.
- Add Docker/deployment setup.

---

## Rules For Future Changes

- Do not call the LLM directly from the frontend.
- Do not put provider-specific logic in React components.
- Keep all backend API calls inside `src/services/api.ts`.
- Keep SQL validation before SQL execution.
- Do not execute write queries from LLM output.
- Keep real secrets out of Git.
- Add new LLM providers inside `backend/llm.py` or a dedicated provider module.
- Prefer config values in `backend/config.py` instead of hardcoding.
