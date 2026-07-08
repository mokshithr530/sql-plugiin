from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from config import (
    UPLOAD_FOLDER,
    SUPPORTED_DATABASES,
    SUPPORTED_DATABASE_NOTES,
    LLM_PROVIDER,
    GEMINI_MODEL,
    GEMINI_API_KEYS
)
import os
import shutil
from database_manager import db_manager
from schema_reader import SchemaReader
from session_memory import session_memory
from chat_pipeline import chat_pipeline


class ChatRequest(BaseModel):
    question: str

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
async def upload_database(file: UploadFile = File(...)):

    try:

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

        file_path = os.path.join(
            UPLOAD_FOLDER,
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
        return chat_pipeline.ask(request.question)

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=str(e)
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@app.get("/status")
async def status():
    database = session_memory.get_database()
    schema = session_memory.get_schema()

    return {
        "success": True,
        "backend": "online",
        "database_connected": bool(database["database_name"]),
        "database": database,
        "schema_loaded": schema is not None,
        "supported_uploads": SUPPORTED_DATABASE_NOTES,
        "llm": {
            "provider": LLM_PROVIDER,
            "model": GEMINI_MODEL,
            "keys_configured": len(GEMINI_API_KEYS)
        }
    }


@app.post("/clear")
async def clear():
    session_memory.reset()
    db_manager.disconnect()

    return {
        "success": True,
        "message": "Session cleared."
    }

