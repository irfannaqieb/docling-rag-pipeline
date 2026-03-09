from __future__ import annotations

from pydantic import BaseModel, Field

from app.prompts import build_citation_key, build_cross_document_synthesis_prompt
from app.schemas import (
    BlockCitation,
    CrossDocumentAnalysis,
    CrossDocumentInsight,
    DocumentAnalysis,
    DocumentReference,
)


class _CrossDocumentInsightPayload(BaseModel):
    title: str
    description: str
    insight_type: str
    confidence: float | None = None
    involved_document_ids: list[str] = Field(default_factory=list)
    citation_keys: list[str] = Field(default_factory=list)


class _CrossDocumentSynthesisResponse(BaseModel):
    summary: str | None = None
    insights: list[_CrossDocumentInsightPayload] = Field(default_factory=list)


def synthesize_across_documents(
    document_analyses: list[DocumentAnalysis],
    llm,
    instructions: str | None = None,
) -> CrossDocumentAnalysis:
    """Synthesize grounded insights across multiple analyzed documents."""

    warnings: list[str] = []
    base_analysis = CrossDocumentAnalysis(insights=[], summary=None, warnings=warnings)

    if len(document_analyses) < 2:
        warnings.append("At least two document analyses are required for cross-document synthesis.")
        return base_analysis

    if not hasattr(llm, "with_structured_output"):
        raise TypeError("llm must support with_structured_output(...) for structured synthesis.")

    prompt = build_cross_document_synthesis_prompt(document_analyses, instructions)
    structured_llm = llm.with_structured_output(_CrossDocumentSynthesisResponse)
    response = structured_llm.invoke(prompt)

    document_lookup = _build_document_lookup(document_analyses)
    citation_lookup = _build_citation_lookup(document_analyses)

    base_analysis.summary = _normalize_optional_text(response.summary)
    base_analysis.insights = _map_insights(
        response.insights,
        document_lookup,
        citation_lookup,
        warnings,
    )
    return base_analysis


def _build_document_lookup(
    document_analyses: list[DocumentAnalysis],
) -> dict[str, DocumentReference]:
    return {
        analysis.document.document_id: analysis.document.model_copy(deep=True)
        for analysis in document_analyses
    }


def _build_citation_lookup(
    document_analyses: list[DocumentAnalysis],
) -> dict[str, BlockCitation]:
    lookup: dict[str, BlockCitation] = {}

    for analysis in document_analyses:
        citation_groups = [
            [citation for fact in analysis.extracted_facts for citation in fact.citations],
            [citation for risk in analysis.risks_or_anomalies for citation in risk.citations],
            [citation for question in analysis.open_questions for citation in question.citations],
            [
                citation
                for link in analysis.possible_links_to_other_documents
                for citation in link.citations
            ],
        ]

        for citations in citation_groups:
            for citation in citations:
                key = build_citation_key(citation)
                if key not in lookup:
                    lookup[key] = citation.model_copy(deep=True)

    return lookup


def _map_insights(
    payloads: list[_CrossDocumentInsightPayload],
    document_lookup: dict[str, DocumentReference],
    citation_lookup: dict[str, BlockCitation],
    warnings: list[str],
) -> list[CrossDocumentInsight]:
    results: list[CrossDocumentInsight] = []

    for index, payload in enumerate(payloads, start=1):
        citations = _resolve_citations(payload.citation_keys, citation_lookup, warnings)
        if not citations:
            warnings.append(f"Dropped cross-document insight #{index} because it had no valid citations.")
            continue

        involved_documents = _resolve_documents(
            payload.involved_document_ids,
            document_lookup,
            warnings,
        )
        if not involved_documents:
            warnings.append(
                f"Dropped cross-document insight #{index} because it had no valid involved documents."
            )
            continue

        distinct_document_ids = {document.document_id for document in involved_documents}
        normalized_type = payload.insight_type.strip().lower()

        if normalized_type != "gap" and len(distinct_document_ids) < 2:
            warnings.append(
                f"Dropped cross-document insight #{index} because non-gap insights must involve at least two documents."
            )
            continue

        if normalized_type == "gap" and len(distinct_document_ids) < 2:
            warnings.append(
                f"Accepted gap insight #{index} with one supporting document because gaps may be single-source."
            )

        results.append(
            CrossDocumentInsight(
                insight_id=f"cross_insight_{index}",
                title=payload.title.strip(),
                description=payload.description.strip(),
                insight_type=normalized_type,
                involved_documents=involved_documents,
                confidence=payload.confidence,
                citations=citations,
            )
        )

    return results


def _resolve_citations(
    citation_keys: list[str],
    citation_lookup: dict[str, BlockCitation],
    warnings: list[str],
) -> list[BlockCitation]:
    citations: list[BlockCitation] = []
    seen: set[str] = set()

    for citation_key in citation_keys:
        normalized_key = citation_key.strip()
        if not normalized_key or normalized_key in seen:
            continue

        citation = citation_lookup.get(normalized_key)
        if citation is None:
            warnings.append(f"LLM returned unknown citation key: {normalized_key}")
            continue

        seen.add(normalized_key)
        citations.append(citation.model_copy(deep=True))

    return citations


def _resolve_documents(
    document_ids: list[str],
    document_lookup: dict[str, DocumentReference],
    warnings: list[str],
) -> list[DocumentReference]:
    documents: list[DocumentReference] = []
    seen: set[str] = set()

    for document_id in document_ids:
        normalized_id = document_id.strip()
        if not normalized_id or normalized_id in seen:
            continue

        document = document_lookup.get(normalized_id)
        if document is None:
            warnings.append(f"LLM returned unknown involved document_id: {normalized_id}")
            continue

        seen.add(normalized_id)
        documents.append(document.model_copy(deep=True))

    return documents


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    return normalized or None
