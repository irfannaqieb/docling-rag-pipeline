import json
import os

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx

app = FastAPI(title="AI Doc Parser API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MINERU_BASE_URL = os.getenv("MINERU_BASE_URL", "http://mineru:8001")

# check
@app.get("/")
def root():
    return {"message": "API is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/documents/parse")
async def parse_document(file: UploadFile = File(...)):
    if not file.filename or not file.filename.strip():
        return JSONResponse(status_code=400, content={"error": "File not provided"})

    content = await file.read()

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            files = {
                "file": (file.filename, content, file.content_type or "application/pdf")
            }
            response = await client.post(f"{MINERU_BASE_URL}/parse", files=files)
    except httpx.RequestError:
        return JSONResponse(
            status_code=502,
            content={"error": "Docling service unavailable"},
        )

    if response.status_code != 200:
        try:
            error_payload = response.json()
        except json.JSONDecodeError:
            error_payload = {"error": response.text or "MinerU request failed"}
        return JSONResponse(status_code=response.status_code, content=error_payload)

    return response.json()
