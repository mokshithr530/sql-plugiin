 # SQL AI Plugin
## Enterprise Natural Language SQL Assistant

Author: Mokshith Reddy Nallaballe

---

# Project Goal

The objective of this project is to build an enterprise-grade AI plugin that allows users to upload SQL databases and ask questions in natural language.

Example:

User uploads:

employees.sqlite

↓

User asks:

"Who are the top 10 highest paid employees?"

↓

The AI should:

1. Read the database schema.
2. Understand relationships.
3. Generate SQL using Gemini.
4. Validate the SQL.
5. Execute the SQL safely.
6. Explain the results in natural language.

The user should never need to write SQL manually.

---

# Current Tech Stack

## Frontend

- React
- TypeScript
- Vite
- Tailwind CSS
- Lucide React Icons

## Backend

- FastAPI
- SQLite
- Gemini API
- Pandas
- python-dotenv

---

# Project Architecture

Frontend

React

↓

Hooks

↓

Services

↓

FastAPI

↓

Database Layer

↓

Gemini

The frontend should NEVER directly talk to Gemini.

Only FastAPI communicates with Gemini.

---

# Folder Structure

Frontend

src/

components/

hooks/

services/

types/

assets/

App.tsx

main.tsx

Backend

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

uploads/

temp_databases/

---

# Frontend Progress

## Components

### ChatWidget

Purpose

Owns the overall chat window.

Responsibilities

- Floating button
- Open/close popup
- Owns database state
- Owns message state
- Owns loading state
- Passes props to children

Current Status

Needs refactoring to fully use hooks.

---

### ChatHeader

Completed.

Displays

- Plugin title
- Subtitle

---

### ChatMessages

Completed.

Displays

- User messages
- Assistant messages
- Loading animation

Future Improvements

- Markdown
- Code formatting
- SQL syntax highlighting

---

### ChatInput

Currently under refactoring.

Responsibilities

- Send messages
- Display attached database
- Upload database
- Enter key support

Database state should NOT be stored here.

It should receive

database

setDatabase

from ChatWidget.

---

### UploadDatabase

Uploads database to backend.

Current Behaviour

Uploads successfully.

Needs Improvement

Return full database object instead of filename only.

Current callback

onUploadSuccess(file.name)

Desired callback

onUploadSuccess(result.database)

---

### DatabaseChip

Purpose

Shows current connected database.

Desired UI

🗄 employees.sqlite

SQLite Database

8 Tables • 54 Columns

Future

Allow removing current database.

---

# Hooks

useChat

Purpose

Manage

- Messages
- Loading
- AI requests

Should eventually call

sendMessage()

from services/api.ts

---

useUpload

Purpose

Manage

- Upload loading
- Upload state
- Connected database

Should store

DatabaseInfo

instead of only filename.

---

# Services

api.ts

Contains ALL backend communication.

Functions

uploadDatabase()

sendMessage()

clearSession()

getStatus()

No component should use fetch() directly.

Always use api.ts.

---

# Types

chat.ts

Contains

Message

ChatResponse

database.ts

Contains

DatabaseInfo

UploadResponse

Never duplicate interfaces.

Always import them.

---

# Backend Progress

database_manager.py

Completed

Responsibilities

- Connect SQLite
- Convert SQL dumps
- Store connection
- Return active connection

Supports

.db

.sqlite

.sql

Future

MySQL

PostgreSQL

SQL Server

---

sql_importer.py

Completed

Purpose

Convert SQL dumps into temporary SQLite databases.

Stores converted files inside

temp_databases/

---

schema_reader.py

Completed

Features

Read Tables

Read Columns

Read Foreign Keys

Generate Schema Prompt

Count Tables

Count Columns

Check Table Exists

Get Column Names

IMPORTANT

This file should return NORMAL Python objects.

It should NOT return HTTP responses.

---

validator.py

Completed

Checks

Dangerous SQL

DROP

DELETE

ALTER

UPDATE

INSERT

CREATE

Only SELECT and WITH allowed.

Future

Use sqlglot parser instead of string matching.

---

sql_executor.py

Completed

Purpose

Safely execute SQL.

Returns

Pandas DataFrame

Future

Execution timing

Row limits

Streaming

---

session_memory.py

Completed

Stores

Current Database

Current Schema

Chat History

Last SQL

Last Result

Retry Count

Future

Conversation summarization

Persistent sessions

---

llm.py

Completed

Functions

_generate()

generate_sql()

generate_answer()

rewrite_failed_sql()

summarize_schema()

suggest_followup()

Future

Few-shot prompting

Prompt templates

Model switching

---

config.py

Completed

Contains

Gemini Model

API Key

Upload Folder

Temp Folder

Blocked Keywords

Retry Count

Supported Extensions

Should contain ALL configuration values.

Never hardcode values elsewhere.

---

main.py

Part 1

Completed

FastAPI

Imports

CORS

Folders

---

Part 2

Completed

POST /upload

Flow

Validate File

↓

Save File

↓

Connect Database

↓

Read Schema

↓

Store Session

↓

Return Database Metadata

Current Status

Working

---

Still Remaining

Part 3

POST /chat

Flow

Receive Question

↓

Get Current Schema

↓

Generate SQL

↓

Validate SQL

↓

Retry if invalid

↓

Execute SQL

↓

Generate Natural Language Answer

↓

Update Session Memory

↓

Return Response

---

Part 4

Retry Pipeline

Question

↓

LLM

↓

Validator

↓

Invalid?

↓

Rewrite SQL

↓

Validator

↓

Execute

↓

Answer

---

Current API

POST

/upload

Completed

POST

/chat

Not implemented

GET

/status

Future

POST

/clear

Future

---

Current Frontend Status

Floating Chat

Completed

Popup

Completed

Header

Completed

Messages

Completed

Upload

Completed

Database Upload

Working

Database Chip

Needs integration

ChatInput

Needs state refactor

Suggested Questions

Removed intentionally

SQL Viewer

Removed intentionally

Copy SQL Button

Removed intentionally

---

Important Design Decisions

Database state belongs in ChatWidget.

ChatInput should receive database as props.

Components should ONLY render UI.

Hooks manage state.

Services perform API requests.

Backend services should return Python objects.

Only main.py should return HTTP JSON responses.

---

Future Features

Charts

Graphs

CSV Export

Excel Export

Authentication

Multiple Sessions

Multiple Databases

Conversation Memory

SQL Explanation

Streaming Responses

Deploy Backend

Deploy Frontend

Docker

---

Current Progress

Frontend

~75%

Backend

~90%

Overall

~82%

---

Coding Guidelines

- Keep components small.
- Do not duplicate interfaces.
- Use hooks for state.
- Use api.ts for all API calls.
- Keep business logic in backend.
- Never call Gemini from frontend.
- Never execute raw SQL without validation.
- Configuration must remain inside config.py.

---

Immediate Next Tasks

1. Finish ChatWidget refactor.
2. Finish DatabaseChip integration.
3. Finish UploadDatabase callback.
4. Implement POST /chat.
5. Connect Gemini.
6. Validate SQL.
7. Execute SQL.
8. Generate AI response.
9. Test complete upload → chat pipeline.
10. Polish UI.

---

Notes for Future AI/Codex Sessions

Before making architectural changes:

- Read this entire file.
- Preserve the current component hierarchy.
- Do not move business logic into React components.
- Do not duplicate API logic.
- Prefer reusable hooks and services.
- If refactoring is required, explain why before changing architecture.
- Keep the code modular and maintainable.
- Avoid introducing breaking changes without updating all dependent files.