import re
import secrets
import shutil
import tempfile
from pathlib import Path

from fastapi import UploadFile


_SAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def generate_document_id() -> str:
    return f"doc_{secrets.token_hex(6)}"


def create_temp_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="docling_"))


def sanitize_filename(name: str) -> str:
    candidate = Path(name or "").name
    candidate = _SAFE_FILENAME_CHARS.sub("_", candidate).strip("._")
    return candidate or "upload.pdf"


def save_upload_file(upload: UploadFile, target: Path) -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    upload.file.seek(0)
    with target.open("wb") as output:
        shutil.copyfileobj(upload.file, output)
    return target.stat().st_size


def cleanup_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
        return
    path.unlink(missing_ok=True)
