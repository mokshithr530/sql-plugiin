from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from config import (
    UPLOAD_FOLDER,
    SUPPORTED_DATABASES,
    SUPPORTED_DATABASE_NOTES,
    LLM_PROVIDER,
    LLM_MODEL,
    LLM_API_KEYS,
)
import os
import shutil
import logging
from database_manager import db_manager
from schema_reader import SchemaReader
from session_memory import session_memory
from chat_pipeline import chat_pipeline
from metrics import token_metrics
from active_database import (
    clear_session_database_path,
    get_session_database_path,
    save_session_database_path,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


class ChatRequest(BaseModel):
    question: str
    session_id: str


class SessionRequest(BaseModel):
    session_id: str

app = FastAPI(
    title="Enterprise SQL AI Plugin",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # tighten later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)
@app.get("/")
async def root():
    return RedirectResponse(url="/docs")

@app.post("/upload")
async def upload_database(
    file: UploadFile = File(...),
    session_id: str = Form(...),
):

    try:
        # Validate before using session_id as part of an upload path.
        get_session_database_path(session_id)

        # ---------------------------------
        # Validate File
        # ---------------------------------

        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail="Uploaded file must have a filename."
            )

        extension = Path(file.filename).suffix.lower()

        if extension not in SUPPORTED_DATABASES:

            raise HTTPException(
                status_code=400,
                detail="Unsupported database format."
            )

        # ---------------------------------
        # Save Uploaded File
        # ---------------------------------

        os.makedirs(
            UPLOAD_FOLDER,
            exist_ok=True
        )

        session_upload_folder = os.path.join(UPLOAD_FOLDER, session_id)
        os.makedirs(session_upload_folder, exist_ok=True)
        file_path = os.path.join(
            session_upload_folder,
            file.filename
        )

        with open(file_path, "wb") as buffer:

            shutil.copyfileobj(
                file.file,
                buffer
            )

        # ---------------------------------
        # Connect Database
        # ---------------------------------

        db_manager.connect(file_path)

        # ---------------------------------
        # Read Schema
        # ---------------------------------

        reader = SchemaReader()

        schema = reader.read_schema()

        summary = reader.get_database_summary()
        active_database_path = db_manager.database_path or file_path
        save_session_database_path(
            session_id,
            active_database_path,
            file.filename,
        )

        # ---------------------------------
        # Store Session
        # ---------------------------------

        session_memory.reset()

        session_memory.set_database(
            file.filename,
            file_path
        )

        session_memory.set_schema(schema)

        # ---------------------------------
        # Return Success
        # ---------------------------------

        return {
                "success": True,
                "database": {
                "name": file.filename,
                "type": db_manager.get_database_type().upper(),
                "tables": summary["tables"],
                "columns": summary["columns"]
                },
                "message": "Database uploaded successfully."
}

    except HTTPException:
        raise

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.post("/chat")
async def chat(request: ChatRequest):
    try:
        database_path = get_session_database_path(request.session_id)
        if not database_path or not Path(database_path).is_file():
            raise ValueError(
                "No database is available for this session. Upload a database first."
            )

        db_manager.connect(database_path)
        reader = SchemaReader()
        schema = reader.read_schema()
        session_memory.reset()
        session_memory.set_database(Path(database_path).name, database_path)
        session_memory.set_schema(schema)
        return chat_pipeline.ask(request.question)

    except ValueError as e:
        token_metrics.log_summary()
        raise HTTPException(status_code=400, detail=str(e))

    except RuntimeError as e:
        token_metrics.log_summary()
        raise HTTPException(status_code=503, detail=str(e))

    except Exception as e:
        token_metrics.log_summary()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/status")
async def status(session_id: str | None = None):
    database_path = (
        get_session_database_path(session_id)
        if session_id
        else None
    )

    return {
        "success": True,
        "backend": "online",
        "database_connected": bool(database_path),
        "database": {
            "database_name": Path(database_path).name if database_path else None,
            "database_path": database_path,
        },
        "schema_loaded": bool(database_path),
        "supported_uploads": SUPPORTED_DATABASE_NOTES,
        "llm": {
            "provider": LLM_PROVIDER,
            "model": LLM_MODEL or "provider default",
            "keys_configured": len(LLM_API_KEYS)
        }
    }


@app.post("/clear")
async def clear(request: SessionRequest):
    clear_session_database_path(request.session_id)
    session_memory.reset()
    db_manager.disconnect()

    return {
        "success": True,
        "message": "Session cleared."
    }
