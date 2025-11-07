import os
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .processing import init_gemini, process_single_file

from dotenv import load_dotenv
load_dotenv()

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
    init_gemini()

@app.get("/api/health")
def health():
    return {"ok": True}

@app.post("/api/generate")
async def generate(file: UploadFile = File(...), max_stories: int = 3):
    if file.size and file.size > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (>10MB)")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        result = process_single_file(content, file.filename, max_stories=max_stories)
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))