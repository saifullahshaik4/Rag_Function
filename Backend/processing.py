import os
import io
import re
import json
import logging
import numpy as np
from typing import List, Dict, Tuple

import google.generativeai as genai
import pdfplumber
from docx import Document as Docx
from PIL import Image
import pytesseract

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('backend_errors.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

GEN_MODEL = os.getenv("GEN_MODEL", "gemini-2.5-flash")
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-004")

def init_gemini():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.error("GOOGLE_API_KEY is not set in environment variables")
        raise RuntimeError("GOOGLE_API_KEY is not set. Put it in .env")
    logger.info("Gemini API initialized successfully")
    genai.configure(api_key=api_key)

def extract_text(file_bytes: bytes, filename: str) -> str:
    name = filename.lower()
    logger.info(f"Extracting text from file: {filename} ({len(file_bytes)} bytes)")
    
    try:
        if name.endswith(".pdf"):
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                pages = [(p.extract_text() or "") for p in pdf.pages]
            text = "\n\n".join(p.strip() for p in pages if p and p.strip())
            logger.info(f"Extracted {len(text)} characters from PDF with {len(pages)} pages")
            return text
        
        if name.endswith(".docx"):
            bio = io.BytesIO(file_bytes)
            doc = Docx(bio)
            text = "\n".join(p.text for p in doc.paragraphs)
            logger.info(f"Extracted {len(text)} characters from DOCX")
            return text
        
        if name.endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff")):
            img = Image.open(io.BytesIO(file_bytes))
            text = pytesseract.image_to_string(img)
            logger.info(f"Extracted {len(text)} characters from image using OCR")
            return text
        
        # default: treat as text
        try:
            text = file_bytes.decode("utf-8", errors="ignore")
            logger.info(f"Extracted {len(text)} characters from text file")
            return text
        except Exception as e:
            logger.warning(f"Failed to decode file as UTF-8: {str(e)}")
            return ""
    
    except Exception as e:
        logger.error(f"Error extracting text from {filename}: {str(e)}", exc_info=True)
        return ""

def chunk_text(text: str, max_words: int = 350) -> List[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks, buf, count = [], [], 0
    for s in sentences:
        w = len(s.split())
        if count and count + w > max_words:
            chunks.append(" ".join(buf).strip())
            buf, count = [s], w
        else:
            buf.append(s); count += w
    if buf:
        chunks.append(" ".join(buf).strip())
    return [c for c in chunks if c]

def embed_texts(texts: List[str]) -> np.ndarray:
    """
    Robust wrapper over genai.embed_content that supports both
    object and dict-style responses across SDK versions.
    Always returns an L2-normalized [n, d] float32 array.
    """
    logger.info(f"Embedding {len(texts)} text chunks")
    vectors: List[np.ndarray] = []
    B = 64
    
    try:
        for i in range(0, len(texts), B):
            batch = texts[i:i+B]
            logger.debug(f"Embedding batch {i//B + 1}/{(len(texts)-1)//B + 1}")
            resp = genai.embed_content(model=EMBED_MODEL, content=batch)

            # Case A: object with .embeddings, each has .values
            if hasattr(resp, "embeddings"):
                vectors.extend([np.array(e.values, dtype="float32") for e in resp.embeddings])

            # Case B: dict with "embeddings": [{"values":[...]}]
            elif isinstance(resp, dict) and "embeddings" in resp:
                vectors.extend([np.array(e["values"], dtype="float32") for e in resp["embeddings"]])

            # Case C: list of dicts with "embedding" (older behavior)
            elif isinstance(resp, list) and resp and isinstance(resp[0], dict) and "embedding" in resp[0]:
                vectors.extend([np.array(e["embedding"], dtype="float32") for e in resp])

            # Case D: dict with single "embedding" (when a single string was sent)
            elif isinstance(resp, dict) and "embedding" in resp:
                vectors.append(np.array(resp["embedding"], dtype="float32"))

            else:
                logger.error(f"Unexpected embedding response shape: {type(resp)}")
                raise RuntimeError(f"Unexpected embedding response shape: {type(resp)} -> {resp}")

        arr = np.vstack(vectors).astype("float32")
        # L2-normalize so dot product == cosine
        norms = np.linalg.norm(arr, axis=1, keepdims=True) + 1e-9
        logger.info(f"Successfully embedded {len(texts)} texts with shape {arr.shape}")
        return arr / norms
    
    except Exception as e:
        logger.error(f"Error during text embedding: {str(e)}", exc_info=True)
        raise

def top_k_chunks(query: str, chunks: List[str], k: int = 6) -> List[Tuple[str, float]]:
    if not chunks:
        return []
    # embed chunks + query
    chunk_vecs = embed_texts(chunks)          # [n, d]
    qv = embed_texts([query])[0]              # [d]
    scores = chunk_vecs @ qv                  # cosine because vectors are normalized
    idx = np.argsort(-scores)[:k]
    return [(chunks[i], float(scores[i])) for i in idx]

CRITERIA_TEXT = """
Must include persona, goal, benefit. INVEST. Gherkin acceptance criteria (3–7 items).
Keep testable behavior; avoid implementation detail.
"""
STYLE_EXAMPLE = """Title: Example format
As a <persona>, I want <capability>, so that <benefit>.

Acceptance Criteria
- Given ..., When ..., Then ...
- Given ..., When ..., Then ...
"""

USER_STORY_SYSTEM = "You are a senior product analyst. Produce INVEST-quality user stories with strict structure."
USER_STORY_PROMPT = """Context (retrieved):
{context}

Style example (follow structure and tone):
{style_example}

Checklist:
{criteria}

Task:
- Write ONE user story with title.
- Use "As a <persona>, I want <capability>, so that <benefit>."
- Add 3–7 acceptance criteria in Gherkin.
- Include non-functional tags if implied.
- Priority: Must | Should | Could

Return JSON only:
{{
  "title": "...",
  "story": "...",
  "acceptance_criteria": ["...", "..."],
  "non_functional": ["..."],
  "priority": "Must|Should|Could",
  "tags": ["..."],
  "rationale": "1–2 lines"
}}
"""

def call_llm(context: str, style_example: str = STYLE_EXAMPLE, criteria: str = CRITERIA_TEXT, max_retries: int = 3) -> Dict:
    logger.info(f"Calling LLM with context length: {len(context)} characters")
    gmodel = genai.GenerativeModel(GEN_MODEL, system_instruction=USER_STORY_SYSTEM)
    prompt = USER_STORY_PROMPT.format(context=context[:8000], style_example=style_example, criteria=criteria)
    
    generation_config = {
        "temperature": 0.2, 
        "max_output_tokens": 2048,
        "response_mime_type": "application/json"
    }
    
    last_error = None
    for attempt in range(max_retries):
        try:
            logger.info(f"LLM attempt {attempt + 1}/{max_retries} with temperature {generation_config['temperature']}")
            resp = gmodel.generate_content(prompt, generation_config=generation_config)
            
            # Check if response was blocked
            if not resp.candidates or not resp.candidates[0].content.parts:
                finish_reason = resp.candidates[0].finish_reason if resp.candidates else None
                logger.error(f"LLM response blocked or empty. Finish reason: {finish_reason}")
                raise RuntimeError(f"Response blocked or empty. Finish reason: {finish_reason}")
            
            txt = resp.text.strip()
            logger.debug(f"Raw LLM response length: {len(txt)} characters")
            
            # Clean up potential markdown code blocks
            if txt.startswith("```json"):
                txt = txt[7:]
            if txt.startswith("```"):
                txt = txt[3:]
            if txt.endswith("```"):
                txt = txt[:-3]
            txt = txt.strip()
            
            # Try to parse JSON
            result = json.loads(txt)
            logger.info("Successfully parsed LLM response as JSON")
            return result
            
        except json.JSONDecodeError as e:
            last_error = e
            logger.error(f"JSON parsing error on attempt {attempt + 1}: {str(e)}")
            logger.error(f"Malformed JSON (first 500 chars): {txt[:500]}")
            
            # If it's the last attempt, try to salvage what we can
            if attempt == max_retries - 1:
                logger.warning("All retry attempts exhausted. Returning error structure.")
                # Return a fallback error structure
                return {
                    "title": "Error: Unable to parse LLM response",
                    "story": f"JSON parsing failed: {str(e)}",
                    "acceptance_criteria": ["Unable to generate criteria due to malformed response"],
                    "non_functional": [],
                    "priority": "Should",
                    "tags": ["error"],
                    "rationale": f"The LLM generated invalid JSON. Raw response preview: {txt[:200]}..."
                }
            # Otherwise, increase temperature slightly and retry
            generation_config["temperature"] = min(0.8, generation_config["temperature"] + 0.2)
            logger.info(f"Retrying with increased temperature: {generation_config['temperature']}")
        
        except Exception as e:
            logger.error(f"Unexpected error during LLM call: {str(e)}", exc_info=True)
            raise
    
    # Should never reach here due to fallback above, but just in case
    logger.error(f"Failed to get valid JSON after {max_retries} attempts")
    raise RuntimeError(f"Failed to get valid JSON after {max_retries} attempts: {last_error}")

def process_single_file(file_bytes: bytes, filename: str, max_stories: int = 3) -> Dict:
    """
    Minimal pipeline:
    - Extract text
    - Chunk
    - For N themes (simple heuristic: queries), retrieve top-k chunks
    - Generate stories
    """
    logger.info(f"Starting processing for file: {filename}")
    logger.info(f"Configured to generate {max_stories} user stories")
    
    try:
        text = extract_text(file_bytes, filename)
        if not text.strip():
            logger.warning(f"No text extracted from {filename}")
            return {"stories": [], "meta": {"chunks": 0, "message": "No text found"}}

        chunks = chunk_text(text)
        logger.info(f"Text chunked into {len(chunks)} chunks")
        
        # naive "themes": seed queries you can adjust or make dynamic
        seed_queries = [
            "key requirements and capabilities",
            "user goals and outcomes",
            "compliance, security, or performance constraints",
            "data flows and API behavior",
            "business rules and edge cases",
        ][:max_stories]

        stories = []
        for idx, q in enumerate(seed_queries, 1):
            logger.info(f"Processing story {idx}/{len(seed_queries)}: {q}")
            try:
                ctx = top_k_chunks(q, chunks, k=6)
                logger.info(f"Retrieved {len(ctx)} relevant chunks for query: {q}")
                
                stitched = "\n---\n".join([f"[score {s:.2f}] {c}" for c, s in ctx])
                story = call_llm(stitched)
                
                stories.append({
                    "query": q,
                    "title": story.get("title","").strip(),
                    "story": story.get("story","").strip(),
                    "acceptance_criteria": story.get("acceptance_criteria", []),
                    "non_functional": story.get("non_functional", []),
                    "priority": story.get("priority", "Should"),
                    "tags": story.get("tags", []),
                    "rationale": story.get("rationale",""),
                    "sources": [{"score": s} for _, s in ctx],
                })
                logger.info(f"Successfully generated story: {story.get('title', 'Untitled')}")
                
            except Exception as e:
                logger.error(f"Error generating story for query '{q}': {str(e)}", exc_info=True)
                stories.append({"query": q, "error": str(e)})

        logger.info(f"Completed processing {filename}. Generated {len(stories)} stories.")
        return {"stories": stories, "meta": {"chunks": len(chunks)}}
    
    except Exception as e:
        logger.error(f"Fatal error processing file {filename}: {str(e)}", exc_info=True)
        return {
            "stories": [],
            "meta": {
                "chunks": 0,
                "message": f"Processing failed: {str(e)}"
            }
        }