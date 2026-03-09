from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

from app.schemas import BlockCitation, EvidenceChunk

DEFAULT_COLLECTION_NAME = "evidence_chunks"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


class ChunkVectorStore:
    """Thin wrapper around Chroma for storing and retrieving evidence chunks."""

    def __init__(
        self,
        persist_directory: str | None = None,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        embedding_model: str | None = None,
    ) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required to initialize ChunkVectorStore.")

        base_url = os.getenv("OPENAI_BASE_URL")
        model = embedding_model or os.getenv("OPENAI_EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL
        storage_path = Path(persist_directory or ".chroma")
        storage_path.mkdir(parents=True, exist_ok=True)

        self._embeddings = OpenAIEmbeddings(
            api_key=api_key,
            base_url=base_url or None,
            model=model,
        )
        self._vectorstore = Chroma(
            collection_name=collection_name,
            persist_directory=str(storage_path),
            embedding_function=self._embeddings,
        )

    def add_chunks(self, chunks: list[EvidenceChunk]) -> list[str]:
        """Insert chunks into Chroma and return the stored chunk IDs."""

        if not chunks:
            return []

        documents = [self._chunk_to_document(chunk) for chunk in chunks]
        chunk_ids = [chunk.chunk_id for chunk in chunks]

        # Replace existing IDs so repeated ingests stay deterministic.
        self._vectorstore.delete(ids=chunk_ids)
        self._vectorstore.add_documents(documents=documents, ids=chunk_ids)

        return chunk_ids

    def similarity_search(
        self,
        query: str,
        k: int = 4,
        document_id: str | None = None,
    ) -> list[EvidenceChunk]:
        """Search similar chunks, optionally restricted to one document."""

        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must not be empty")
        if k <= 0:
            raise ValueError("k must be greater than 0")

        search_filter = self._build_filter(document_id)
        documents = self._vectorstore.similarity_search(
            query=normalized_query,
            k=k,
            filter=search_filter,
        )
        return [self._document_to_chunk(document) for document in documents]

    def _build_filter(self, document_id: str | None) -> dict[str, Any] | None:
        if not document_id:
            return None
        return {"document_id": document_id}

    def _chunk_to_document(self, chunk: EvidenceChunk) -> Document:
        metadata = {
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "file_name": chunk.file_name or "",
            "page_number": chunk.page_number,
            "citation": self._serialize_citation(chunk.citation),
            "contains_table": chunk.contains_table,
            "section_title": chunk.section_title or "",
            "block_types": json.dumps(chunk.block_types),
        }
        return Document(page_content=chunk.text, metadata=metadata)

    def _document_to_chunk(self, document: Document) -> EvidenceChunk:
        metadata = document.metadata
        citation = self._deserialize_citation(metadata["citation"])

        return EvidenceChunk(
            chunk_id=str(metadata["chunk_id"]),
            document_id=str(metadata["document_id"]),
            file_name=self._empty_string_to_none(metadata.get("file_name")),
            page_number=int(metadata["page_number"]),
            block_index=citation.block_index,
            text=document.page_content,
            block_types=self._deserialize_block_types(metadata.get("block_types")),
            section_title=self._empty_string_to_none(metadata.get("section_title")),
            contains_table=bool(metadata.get("contains_table", False)),
            citation=citation,
        )

    def _serialize_citation(self, citation: BlockCitation) -> str:
        payload = {
            "document_id": citation.document_id,
            "file_name": citation.file_name,
            "page_number": citation.page_number,
            "block_index": citation.block_index,
            "chunk_id": citation.chunk_id,
            "quote_text": citation.quote_text,
        }
        return json.dumps(payload, separators=(",", ":"))

    def _deserialize_citation(self, payload: str) -> BlockCitation:
        data = json.loads(payload)
        return BlockCitation(
            document_id=str(data["document_id"]),
            file_name=self._empty_string_to_none(data.get("file_name")),
            page_number=int(data["page_number"]),
            block_index=self._optional_int(data.get("block_index")),
            chunk_id=self._empty_string_to_none(data.get("chunk_id")),
            quote_text=self._empty_string_to_none(data.get("quote_text")),
        )

    def _deserialize_block_types(self, payload: Any) -> list[str]:
        if not payload:
            return []

        if isinstance(payload, list):
            return [str(value) for value in payload]

        return [str(value) for value in json.loads(str(payload))]

    def _empty_string_to_none(self, value: Any) -> str | None:
        if value is None:
            return None

        text = str(value)
        return text or None

    def _optional_int(self, value: Any) -> int | None:
        if value is None or value == "":
            return None
        return int(value)
