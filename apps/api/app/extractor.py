from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from app.prompts import build_document_extraction_prompt
from app.schemas import (
    BlockCitation,
    DocumentAnalysis,
    DocumentReference,
    EvidenceChunk,
    ExtractedFact,
    NormalizedDocument,
    OpenQuestion,
    PossibleDocumentLink,
    RiskOrAnomaly,
)

logger = logging.getLogger(__name__)


class _ExtractedFactPayload(BaseModel):
    fact_type: str
    label: str
    value: str
    unit: str | None = None
    confidence: float | None = None
    rationale: str | None = None
    citation_chunk_ids: list[str] = Field(default_factory=list)


class _RiskOrAnomalyPayload(BaseModel):
    title: str
    description: str
    severity: str
    confidence: float | None = None
    citation_chunk_ids: list[str] = Field(default_factory=list)


class _OpenQuestionPayload(BaseModel):
    question: str
    reason: str
    citation_chunk_ids: list[str] = Field(default_factory=list)


class _PossibleDocumentLinkPayload(BaseModel):
    description: str
    linked_document_hint: str
    confidence: float | None = None
    citation_chunk_ids: list[str] = Field(default_factory=list)


class _DocumentExtractionResponse(BaseModel):
    summary: str | None = None
    extracted_facts: list[_ExtractedFactPayload] = Field(default_factory=list)
    risks_or_anomalies: list[_RiskOrAnomalyPayload] = Field(default_factory=list)
    open_questions: list[_OpenQuestionPayload] = Field(default_factory=list)
    possible_links_to_other_documents: list[_PossibleDocumentLinkPayload] = Field(
        default_factory=list
    )


def analyze_document(
    doc: NormalizedDocument,
    chunks: list[EvidenceChunk],
    llm,
    instructions: str | None = None,
) -> DocumentAnalysis:
    """Analyze one document using only the provided evidence chunks."""

    warnings: list[str] = []
    base_analysis = DocumentAnalysis(
        document=DocumentReference(document_id=doc.document_id, file_name=doc.file_name),
        normalized_document=doc,
        evidence_chunks=chunks,
        extracted_facts=[],
        risks_or_anomalies=[],
        open_questions=[],
        possible_links_to_other_documents=[],
        summary=None,
        warnings=warnings,
    )

    if not chunks:
        warnings.append("No evidence chunks were provided for document analysis.")
        logger.warning("Skipping analysis for document_id=%s because chunk_count=0", doc.document_id)
        return base_analysis

    if not hasattr(llm, "with_structured_output"):
        raise TypeError("llm must support with_structured_output(...) for structured extraction.")

    logger.info(
        "Starting structured extraction document_id=%s file=%s chunk_count=%s",
        doc.document_id,
        doc.file_name,
        len(chunks),
    )
    prompt = build_document_extraction_prompt(doc, chunks, instructions)
    structured_llm = llm.with_structured_output(_DocumentExtractionResponse)
    response = _coerce_extraction_response(structured_llm.invoke(prompt))
    logger.info(
        "Structured extraction completed document_id=%s summary_present=%s extracted_facts=%s risks=%s open_questions=%s links=%s",
        doc.document_id,
        bool(response.summary and response.summary.strip()),
        len(response.extracted_facts),
        len(response.risks_or_anomalies),
        len(response.open_questions),
        len(response.possible_links_to_other_documents),
    )

    chunk_lookup = {chunk.chunk_id: chunk for chunk in chunks}
    facts = _map_facts(doc.document_id, response.extracted_facts, chunk_lookup, warnings)
    risks = _map_risks(doc.document_id, response.risks_or_anomalies, chunk_lookup, warnings)
    open_questions = _map_open_questions(
        doc.document_id,
        response.open_questions,
        chunk_lookup,
        warnings,
    )
    possible_links = _map_possible_links(
        doc.document_id,
        response.possible_links_to_other_documents,
        chunk_lookup,
        warnings,
    )

    base_analysis.summary = _normalize_optional_text(response.summary)
    base_analysis.extracted_facts = facts
    base_analysis.risks_or_anomalies = risks
    base_analysis.open_questions = open_questions
    base_analysis.possible_links_to_other_documents = possible_links
    logger.info(
        "Mapped structured extraction document_id=%s facts=%s risks=%s open_questions=%s links=%s warnings=%s",
        doc.document_id,
        len(facts),
        len(risks),
        len(open_questions),
        len(possible_links),
        len(warnings),
    )

    return base_analysis


def _coerce_extraction_response(value: object) -> _DocumentExtractionResponse:
    if isinstance(value, _DocumentExtractionResponse):
        logger.info("Structured extraction returned direct response model.")
        return value

    parsed = getattr(value, "parsed", None)
    if isinstance(parsed, _DocumentExtractionResponse):
        logger.info("Structured extraction returned wrapper with parsed response model.")
        return parsed
    if isinstance(parsed, dict):
        logger.info("Structured extraction returned wrapper with parsed dict payload.")
        return _DocumentExtractionResponse.model_validate(parsed)

    if isinstance(value, dict):
        logger.info("Structured extraction returned raw dict payload.")
        return _DocumentExtractionResponse.model_validate(value)

    logger.error("Unexpected structured extraction payload type=%s", type(value).__name__)
    raise TypeError(
        "Structured extraction returned an unexpected payload type: "
        f"{type(value).__name__}"
    )


def _map_facts(
    document_id: str,
    payloads: list[_ExtractedFactPayload],
    chunk_lookup: dict[str, EvidenceChunk],
    warnings: list[str],
) -> list[ExtractedFact]:
    results: list[ExtractedFact] = []
    for index, payload in enumerate(payloads, start=1):
        citations = _resolve_citations(payload.citation_chunk_ids, chunk_lookup, warnings)
        if not citations:
            warnings.append(
                f"Dropped extracted fact #{index} because it did not include valid citations."
            )
            continue

        results.append(
            ExtractedFact(
                fact_id=_build_item_id(document_id, "fact", index),
                source_document_id=document_id,
                fact_type=payload.fact_type.strip(),
                label=payload.label.strip(),
                value=payload.value.strip(),
                unit=_normalize_optional_text(payload.unit),
                confidence=payload.confidence,
                rationale=_normalize_optional_text(payload.rationale),
                citations=citations,
            )
        )
    return results


def _map_risks(
    document_id: str,
    payloads: list[_RiskOrAnomalyPayload],
    chunk_lookup: dict[str, EvidenceChunk],
    warnings: list[str],
) -> list[RiskOrAnomaly]:
    results: list[RiskOrAnomaly] = []
    for index, payload in enumerate(payloads, start=1):
        citations = _resolve_citations(payload.citation_chunk_ids, chunk_lookup, warnings)
        if not citations:
            warnings.append(
                f"Dropped risk/anomaly #{index} because it did not include valid citations."
            )
            continue

        results.append(
            RiskOrAnomaly(
                risk_id=_build_item_id(document_id, "risk", index),
                source_document_id=document_id,
                title=payload.title.strip(),
                description=payload.description.strip(),
                severity=payload.severity.strip(),
                confidence=payload.confidence,
                citations=citations,
            )
        )
    return results


def _map_open_questions(
    document_id: str,
    payloads: list[_OpenQuestionPayload],
    chunk_lookup: dict[str, EvidenceChunk],
    warnings: list[str],
) -> list[OpenQuestion]:
    results: list[OpenQuestion] = []
    for index, payload in enumerate(payloads, start=1):
        citations = _resolve_citations(payload.citation_chunk_ids, chunk_lookup, warnings)
        if not citations:
            warnings.append(
                f"Dropped open question #{index} because it did not include valid citations."
            )
            continue

        results.append(
            OpenQuestion(
                question_id=_build_item_id(document_id, "question", index),
                source_document_id=document_id,
                question=payload.question.strip(),
                reason=payload.reason.strip(),
                citations=citations,
            )
        )
    return results


def _map_possible_links(
    document_id: str,
    payloads: list[_PossibleDocumentLinkPayload],
    chunk_lookup: dict[str, EvidenceChunk],
    warnings: list[str],
) -> list[PossibleDocumentLink]:
    results: list[PossibleDocumentLink] = []
    for index, payload in enumerate(payloads, start=1):
        citations = _resolve_citations(payload.citation_chunk_ids, chunk_lookup, warnings)
        if not citations:
            warnings.append(
                f"Dropped possible document link #{index} because it did not include valid citations."
            )
            continue

        results.append(
            PossibleDocumentLink(
                link_id=_build_item_id(document_id, "link", index),
                source_document_id=document_id,
                description=payload.description.strip(),
                linked_document_hint=payload.linked_document_hint.strip(),
                confidence=payload.confidence,
                citations=citations,
            )
        )
    return results


def _resolve_citations(
    citation_chunk_ids: list[str],
    chunk_lookup: dict[str, EvidenceChunk],
    warnings: list[str],
) -> list[BlockCitation]:
    citations: list[BlockCitation] = []
    seen: set[str] = set()

    for chunk_id in citation_chunk_ids:
        normalized_chunk_id = chunk_id.strip()
        if not normalized_chunk_id or normalized_chunk_id in seen:
            continue

        chunk = chunk_lookup.get(normalized_chunk_id)
        if chunk is None:
            warnings.append(f"LLM returned unknown citation chunk_id: {normalized_chunk_id}")
            continue

        seen.add(normalized_chunk_id)
        citations.append(chunk.citation.model_copy(deep=True))

    return citations


def _build_item_id(document_id: str, item_type: str, index: int) -> str:
    return f"{document_id}_{item_type}_{index}"


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    return normalized or None
