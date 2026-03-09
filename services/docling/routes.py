from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from parser import DoclingParseError, parse_with_docling
from schemas import ParseResponse
from utils import (
    cleanup_path,
    create_temp_dir,
    generate_document_id,
    sanitize_filename,
    save_upload_file,
)


router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/parse", response_model=ParseResponse)
async def parse(file: UploadFile = File(...)) -> ParseResponse:
    if not file.filename or not file.filename.strip():
        raise HTTPException(status_code=400, detail="File not provided")

    safe_name = sanitize_filename(file.filename)
    content_type = file.content_type or "application/octet-stream"
    if Path(safe_name).suffix.lower() != ".pdf" and content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    temp_dir = create_temp_dir()
    source_path = temp_dir / safe_name

    try:
        file_size = save_upload_file(file, source_path)
        parsed = parse_with_docling(str(source_path))
        meta = dict(parsed["meta"])
        meta["content_type"] = content_type
        meta["file_size"] = file_size

        return ParseResponse(
            ok=True,
            document_id=generate_document_id(),
            file_name=safe_name,
            source_path=str(source_path),
            artifacts=parsed["artifacts"],
            pages=parsed["pages"],
            meta=meta,
        )
    except DoclingParseError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        cleanup_path(temp_dir)
