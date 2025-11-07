import os
import logging
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .processing import init_gemini, process_single_file

from dotenv import load_dotenv
load_dotenv()

# Setup logger for main API
logger = logging.getLogger(__name__)

app = FastAPI(title="RAG User Story API", version="0.1")

# CORS for local static frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5500", "http://127.0.0.1:5500", "http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def _startup():
    logger.info("Application startup initiated")
    try:
        init_gemini()
        logger.info("Application startup completed successfully")
    except Exception as e:
        logger.error(f"Application startup failed: {str(e)}", exc_info=True)
        raise

@app.get("/api/health")
def health():
    logger.debug("Health check endpoint called")
    return {"ok": True}

@app.post("/api/generate")
async def generate(file: UploadFile = File(...), max_stories: int = 3):
    logger.info(f"Generate endpoint called - File: {file.filename}, Max stories: {max_stories}")
    
    # Check file size
    if file.size and file.size > 10 * 1024 * 1024:
        logger.warning(f"File rejected - too large: {file.size} bytes ({file.filename})")
        raise HTTPException(status_code=413, detail="File too large (>10MB)")
    
    logger.info(f"Reading file: {file.filename} ({file.size if file.size else 'unknown'} bytes)")

    content = await file.read()
    if not content:
        logger.error(f"Empty file uploaded: {file.filename}")
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        logger.info(f"Starting processing of {file.filename}")
        result = process_single_file(content, file.filename, max_stories=max_stories)
        
        # Log summary of results
        num_stories = len(result.get("stories", []))
        num_errors = sum(1 for s in result.get("stories", []) if "error" in s)
        logger.info(f"Processing completed - Generated {num_stories} stories ({num_errors} errors) for {file.filename}")
        
        return JSONResponse(result)
    except Exception as e:
        logger.error(f"Fatal error processing {file.filename}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))