from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from langchain_openai import ChatOpenAI
from pydantic import ValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.chunker import chunk_document
from app.extractor import analyze_document
from app.normalizer import normalize_document
from app.report_generator import generate_report_markdown
from app.schemas import (
    AnalysisStats,
    AnalyzePipelineResponse,
    AnalyzeRequest,
    CrossDocumentAnalysis,
    DocumentAnalysis,
    EvidenceChunk,
    GenerateReportResponse,
    NormalizedDocument,
    RawDoclingDocument,
    ReportDocumentSummary,
)
from app.synthesizer import synthesize_across_documents
from app.vectorstore import ChunkVectorStore

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Doc Parser API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MINERU_BASE_URL = os.getenv("MINERU_BASE_URL", "http://mineru:8001")
DEFAULT_CHAT_MODEL = "gpt-4o-mini"
MINERU_TIMEOUT_SECONDS = 300.0
DEFAULT_REPORT_INSTRUCTIONS = """
Produce an Executive Intelligence Report, not a generic summary.

Priorities:
- treat tables and structured values as first-class evidence
- connect facts across documents only when citations support the inference
- highlight corroborations, contradictions, timeline links, and meaningful gaps
- keep every material claim grounded with document/page citations
- do not invent diagnoses, entities, dates, or relationships
""".strip()


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "API is running"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/documents/parse", response_model=RawDoclingDocument)
async def parse_document(file: UploadFile = File(...)) -> RawDoclingDocument:
    logger.info(
        "Received /documents/parse request for file=%s content_type=%s",
        file.filename,
        file.content_type,
    )
    return await _parse_document_upload(file)


@app.post("/analyze", response_model=AnalyzePipelineResponse)
def analyze(request: AnalyzeRequest) -> AnalyzePipelineResponse:
    if not request.documents:
        raise HTTPException(status_code=400, detail="Request must include at least one document.")

    logger.info(
        "Received /analyze request with document_count=%s request_id=%s",
        len(request.documents),
        request.request_id,
    )

    try:
        pipeline = _run_analysis_pipeline(request.documents, request.instructions)
        logger.info(
            "Completed /analyze request with document_analyses=%s cross_document_insights=%s warnings=%s",
            len(pipeline["document_analyses"]),
            len(pipeline["cross_document_analysis"].insights),
            len(pipeline["warnings"]),
        )
        return AnalyzePipelineResponse(
            ok=True,
            document_analyses=pipeline["document_analyses"],
            cross_document_analysis=pipeline["cross_document_analysis"],
            report_markdown=pipeline["report_markdown"],
            stats=pipeline["stats"],
            warnings=pipeline["warnings"],
        )
    except ValueError as exc:
        logger.warning("Rejected /analyze request: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.exception("Runtime failure during /analyze")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled failure during /analyze")
        raise HTTPException(status_code=500, detail=f"Analysis pipeline failed: {exc}") from exc


@app.post("/reports/generate", response_model=GenerateReportResponse)
async def generate_report(
    files: list[UploadFile] = File(...),
    instructions: str | None = Form(None),
) -> GenerateReportResponse:
    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one PDF.")

    logger.info(
        "Received /reports/generate request with file_count=%s files=%s",
        len(files),
        [file.filename for file in files],
    )

    raw_documents = [await _parse_document_upload(file) for file in files]
    logger.info(
        "Parsed uploaded files successfully document_count=%s document_ids=%s",
        len(raw_documents),
        [document.document_id for document in raw_documents],
    )

    try:
        pipeline = _run_analysis_pipeline(
            raw_documents,
            _resolve_report_instructions(instructions),
        )
        logger.info(
            "Completed /reports/generate with report_length=%s document_analyses=%s cross_document_insights=%s warnings=%s",
            len(pipeline["report_markdown"]),
            len(pipeline["document_analyses"]),
            len(pipeline["cross_document_analysis"].insights),
            len(pipeline["warnings"]),
        )
        return GenerateReportResponse(
            ok=True,
            report_markdown=pipeline["report_markdown"],
            documents=_build_report_document_summaries(pipeline["document_analyses"]),
            cross_document_analysis=pipeline["cross_document_analysis"],
            stats=pipeline["stats"],
            warnings=pipeline["warnings"],
        )
    except ValueError as exc:
        logger.warning("Rejected /reports/generate request: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.exception("Runtime failure during /reports/generate")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled failure during /reports/generate")
        raise HTTPException(status_code=500, detail=f"Report generation failed: {exc}") from exc


@lru_cache(maxsize=1)
def _build_chat_model() -> ChatOpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY is missing; cannot build chat model.")
        raise RuntimeError("OPENAI_API_KEY is required to run /analyze.")

    model_name = os.getenv("OPENAI_CHAT_MODEL", DEFAULT_CHAT_MODEL)
    base_url = os.getenv("OPENAI_BASE_URL")
    logger.info("Building chat model model=%s base_url=%s", model_name, base_url or "<default>")
    return ChatOpenAI(
        api_key=api_key,
        base_url=base_url or None,
        model=model_name,
        temperature=0,
    )


def _run_analysis_pipeline(
    raw_documents: list[RawDoclingDocument],
    instructions: str | None,
) -> dict[str, Any]:
    logger.info(
        "Starting analysis pipeline raw_document_count=%s instructions_provided=%s",
        len(raw_documents),
        bool(instructions and instructions.strip()),
    )
    llm = _build_chat_model()
    vector_store = ChunkVectorStore()

    normalized_documents = [normalize_document(raw_doc) for raw_doc in raw_documents]
    logger.info(
        "Normalized documents count=%s page_counts=%s",
        len(normalized_documents),
        [document.page_count for document in normalized_documents],
    )
    chunks_by_document: dict[str, list[EvidenceChunk]] = {}
    all_chunks: list[EvidenceChunk] = []

    for normalized_document in normalized_documents:
        document_chunks = chunk_document(normalized_document)
        chunks_by_document[normalized_document.document_id] = document_chunks
        all_chunks.extend(document_chunks)
        logger.info(
            "Chunked document document_id=%s file=%s chunk_count=%s contains_table=%s",
            normalized_document.document_id,
            normalized_document.file_name,
            len(document_chunks),
            normalized_document.contains_table,
        )

    vector_store.add_chunks(all_chunks)
    logger.info("Added chunks to vector store total_chunk_count=%s", len(all_chunks))

    document_analyses: list[DocumentAnalysis] = []
    for normalized_document in normalized_documents:
        document_chunks = chunks_by_document.get(normalized_document.document_id, [])
        logger.info(
            "Analyzing document document_id=%s chunk_count=%s",
            normalized_document.document_id,
            len(document_chunks),
        )
        document_analyses.append(
            analyze_document(
                normalized_document,
                document_chunks,
                llm,
                instructions=instructions,
            )
        )
        latest_analysis = document_analyses[-1]
        logger.info(
            "Completed document analysis document_id=%s facts=%s risks=%s open_questions=%s links=%s warnings=%s",
            normalized_document.document_id,
            len(latest_analysis.extracted_facts),
            len(latest_analysis.risks_or_anomalies),
            len(latest_analysis.open_questions),
            len(latest_analysis.possible_links_to_other_documents),
            len(latest_analysis.warnings),
        )

    cross_document_analysis = synthesize_across_documents(
        document_analyses,
        llm,
        instructions=instructions,
    )
    report_markdown = generate_report_markdown(document_analyses, cross_document_analysis)
    stats = _build_stats(
        request_count=len(raw_documents),
        normalized_documents=normalized_documents,
        all_chunks=all_chunks,
        document_analyses=document_analyses,
        cross_document_analysis=cross_document_analysis,
    )
    warnings = _collect_pipeline_warnings(
        raw_documents,
        document_analyses,
        cross_document_analysis,
    )
    logger.info(
        "Finished analysis pipeline cross_document_insights=%s warnings=%s",
        len(cross_document_analysis.insights),
        len(warnings),
    )

    return {
        "document_analyses": document_analyses,
        "cross_document_analysis": cross_document_analysis,
        "report_markdown": report_markdown,
        "stats": stats,
        "warnings": warnings,
    }


def _build_stats(
    request_count: int,
    normalized_documents: list[NormalizedDocument],
    all_chunks: list[EvidenceChunk],
    document_analyses: list[DocumentAnalysis],
    cross_document_analysis: CrossDocumentAnalysis,
) -> AnalysisStats:
    return AnalysisStats(
        document_count=request_count,
        normalized_document_count=len(normalized_documents),
        chunk_count=len(all_chunks),
        document_analysis_count=len(document_analyses),
        cross_document_insight_count=len(cross_document_analysis.insights),
    )


async def _parse_document_upload(file: UploadFile) -> RawDoclingDocument:
    _validate_uploaded_pdf(file)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    logger.info(
        "Parsing upload file=%s size_bytes=%s content_type=%s mineru_url=%s",
        file.filename,
        len(content),
        file.content_type,
        MINERU_BASE_URL,
    )

    try:
        async with httpx.AsyncClient(timeout=MINERU_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{MINERU_BASE_URL}/parse",
                files={
                    "file": (
                        file.filename or "document.pdf",
                        content,
                        file.content_type or "application/pdf",
                    )
                },
            )
    except httpx.RequestError as exc:
        logger.exception("Docling request failed for file=%s", file.filename)
        raise HTTPException(status_code=502, detail="Docling service unavailable.") from exc

    if response.status_code != 200:
        logger.warning(
            "Docling returned non-200 status=%s for file=%s",
            response.status_code,
            file.filename,
        )
        raise HTTPException(
            status_code=response.status_code,
            detail=_extract_upstream_error_detail(response),
        )

    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        logger.exception("Docling returned invalid JSON for file=%s", file.filename)
        raise HTTPException(status_code=502, detail="Docling returned invalid JSON.") from exc

    try:
        document = RawDoclingDocument.model_validate(payload)
        logger.info(
            "Validated parsed document file=%s document_id=%s pages=%s parser=%s warnings=%s",
            document.file_name,
            document.document_id,
            len(document.pages),
            document.meta.parser,
            len(document.meta.warnings),
        )
        return document
    except ValidationError as exc:
        logger.exception("Docling returned unexpected payload for file=%s", file.filename)
        raise HTTPException(status_code=502, detail="Docling returned an unexpected payload.") from exc


def _validate_uploaded_pdf(file: UploadFile) -> None:
    if not file.filename or not file.filename.strip():
        raise HTTPException(status_code=400, detail="File not provided.")

    normalized_name = file.filename.strip().lower()
    content_type = (file.content_type or "").strip().lower()
    if content_type == "application/pdf" or normalized_name.endswith(".pdf"):
        return

    raise HTTPException(status_code=400, detail="Only PDF uploads are supported.")


def _extract_upstream_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return response.text.strip() or "Docling request failed."

    if isinstance(payload, dict):
        for key in ("detail", "error", "message"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return "Docling request failed."


def _resolve_report_instructions(value: str | None) -> str:
    normalized = value.strip() if value else ""
    return normalized or DEFAULT_REPORT_INSTRUCTIONS


def _build_report_document_summaries(
    document_analyses: list[DocumentAnalysis],
) -> list[ReportDocumentSummary]:
    summaries: list[ReportDocumentSummary] = []

    for analysis in document_analyses:
        normalized_document = analysis.normalized_document
        summaries.append(
            ReportDocumentSummary(
                document_id=analysis.document.document_id,
                file_name=analysis.document.file_name or "Unknown file",
                page_count=normalized_document.page_count if normalized_document is not None else 0,
                contains_table=(
                    normalized_document.contains_table if normalized_document is not None else False
                ),
                summary=analysis.summary,
                extracted_facts=analysis.extracted_facts,
                risks_or_anomalies=analysis.risks_or_anomalies,
                open_questions=analysis.open_questions,
                possible_links_to_other_documents=analysis.possible_links_to_other_documents,
                warnings=analysis.warnings,
            )
        )

    return summaries


def _collect_pipeline_warnings(
    raw_documents: list[RawDoclingDocument],
    document_analyses: list[DocumentAnalysis],
    cross_document_analysis: CrossDocumentAnalysis,
) -> list[str]:
    warnings: list[str] = []

    for raw_document in raw_documents:
        for warning in raw_document.meta.warnings:
            warnings.append(f"{raw_document.file_name}: {warning}")

    for analysis in document_analyses:
        file_name = analysis.document.file_name or analysis.document.document_id
        for warning in analysis.warnings:
            warnings.append(f"{file_name}: {warning}")

    warnings.extend(cross_document_analysis.warnings)

    if len(raw_documents) < 2:
        warnings.append(
            "Cross-document synthesis is limited with one document. Upload related PDFs to unlock comparative insights."
        )
    elif len(cross_document_analysis.insights) < 2:
        warnings.append(
            "Fewer than two grounded cross-document insights were generated. The challenge requirement is not fully met yet."
        )

    return _dedupe_strings(warnings)


def _dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()

    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)

    return deduped
