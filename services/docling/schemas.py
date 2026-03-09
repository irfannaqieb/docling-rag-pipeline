from typing import Any

from pydantic import BaseModel, Field


class PageBlockResponse(BaseModel):
    block_type: str
    text: str


class PageResponse(BaseModel):
    page_number: int
    text: str
    blocks: list[PageBlockResponse] = Field(default_factory=list)


class ParseResponse(BaseModel):
    ok: bool
    document_id: str
    file_name: str
    source_path: str
    artifacts: dict[str, Any] = Field(default_factory=dict)
    pages: list[PageResponse] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
