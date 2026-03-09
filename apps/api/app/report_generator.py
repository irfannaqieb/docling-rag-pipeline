from __future__ import annotations

from dataclasses import dataclass

from app.schemas import (
    BlockCitation,
    CrossDocumentAnalysis,
    CrossDocumentInsight,
    DocumentAnalysis,
    ExtractedFact,
    OpenQuestion,
    RiskOrAnomaly,
)

MAX_KEY_FINDINGS = 5
MAX_CROSS_INSIGHTS = 5
MAX_RISK_ITEMS = 8


@dataclass(frozen=True)
class _ReportClaim:
    text: str
    citations: list[BlockCitation]


@dataclass(frozen=True)
class _RankedItem:
    sort_key: tuple[float, float, float, str]
    label_key: str
    claim: _ReportClaim


def generate_report_markdown(
    document_analyses: list[DocumentAnalysis],
    cross_analysis: CrossDocumentAnalysis,
) -> str:
    """Render a deterministic executive markdown report from grounded analyses."""

    key_findings = _select_key_findings(document_analyses)[:MAX_KEY_FINDINGS]
    cross_insights = _select_cross_document_insights(cross_analysis)[:MAX_CROSS_INSIGHTS]
    risk_items = _select_risks_anomalies_and_gaps(document_analyses, cross_analysis)[:MAX_RISK_ITEMS]

    major_claims = [item.claim for item in key_findings]
    major_claims.extend(item.claim for item in cross_insights)
    major_claims.extend(item.claim for item in risk_items)

    executive_summary = _build_executive_summary(
        document_analyses=document_analyses,
        cross_analysis=cross_analysis,
        key_findings=key_findings,
        cross_insights=cross_insights,
        risk_items=risk_items,
    )

    sections = [
        "# Executive Intelligence Report",
        "",
        "## Executive Summary",
        executive_summary,
        "",
        "## Key Findings",
        *_render_numbered_section(key_findings, empty_message="No grounded findings available."),
        "",
        "## Cross-Document Insights",
        *_render_numbered_section(
            cross_insights,
            empty_message="No grounded cross-document insights available.",
        ),
        "",
        "## Risks, Anomalies, and Gaps",
        *_render_bulleted_section(
            risk_items,
            empty_message="No grounded risks, anomalies, or gaps available.",
        ),
        "",
        "## Evidence Appendix",
        *_render_evidence_appendix(major_claims),
    ]
    return "\n".join(sections).strip() + "\n"


def _build_executive_summary(
    document_analyses: list[DocumentAnalysis],
    cross_analysis: CrossDocumentAnalysis,
    key_findings: list[_RankedItem],
    cross_insights: list[_RankedItem],
    risk_items: list[_RankedItem],
) -> str:
    if cross_analysis.summary:
        return cross_analysis.summary.strip()

    document_count = len(document_analyses)
    insight_count = len(cross_insights)
    finding_count = len(key_findings)
    risk_count = len(risk_items)

    document_summaries = [
        analysis.summary.strip()
        for analysis in document_analyses
        if analysis.summary and analysis.summary.strip()
    ]

    if document_summaries:
        lead = document_summaries[0]
        return (
            f"{lead} Across {document_count} document(s), the grounded review surfaced "
            f"{finding_count} key finding(s), {insight_count} cross-document insight(s), and "
            f"{risk_count} risk, anomaly, or gap item(s)."
        )

    if document_count == 0:
        return "No grounded findings available because no document analyses were provided."

    return (
        f"Grounded review across {document_count} document(s) surfaced {finding_count} key finding(s), "
        f"{insight_count} cross-document insight(s), and {risk_count} risk, anomaly, or gap item(s)."
    )


def _select_key_findings(document_analyses: list[DocumentAnalysis]) -> list[_RankedItem]:
    ranked: list[_RankedItem] = []

    for analysis in document_analyses:
        for fact in analysis.extracted_facts:
            if not fact.citations:
                continue
            text = _format_fact_claim(fact, analysis.document.file_name)
            ranked.append(
                _RankedItem(
                    sort_key=_build_sort_key(
                        confidence=fact.confidence,
                        citation_count=len(fact.citations),
                        has_quote=_has_quote(fact.citations),
                        label=fact.label,
                    ),
                    label_key=_normalize_key(fact.label),
                    claim=_ReportClaim(text=text, citations=_dedupe_citations(fact.citations)),
                )
            )

        for risk in analysis.risks_or_anomalies:
            if not risk.citations:
                continue
            text = _format_risk_claim(risk, analysis.document.file_name)
            ranked.append(
                _RankedItem(
                    sort_key=_build_sort_key(
                        confidence=risk.confidence,
                        citation_count=len(risk.citations),
                        has_quote=_has_quote(risk.citations),
                        label=risk.title,
                    ),
                    label_key=_normalize_key(risk.title),
                    claim=_ReportClaim(text=text, citations=_dedupe_citations(risk.citations)),
                )
            )

    return _dedupe_ranked_items(ranked)


def _select_cross_document_insights(cross_analysis: CrossDocumentAnalysis) -> list[_RankedItem]:
    ranked: list[_RankedItem] = []

    for insight in cross_analysis.insights:
        if not insight.citations:
            continue
        text = _format_cross_insight_claim(insight)
        ranked.append(
            _RankedItem(
                sort_key=_build_sort_key(
                    confidence=insight.confidence,
                    citation_count=len(insight.citations),
                    has_quote=_has_quote(insight.citations),
                    label=insight.title,
                ),
                label_key=_normalize_key(insight.title),
                claim=_ReportClaim(text=text, citations=_dedupe_citations(insight.citations)),
            )
        )

    return _dedupe_ranked_items(ranked)


def _select_risks_anomalies_and_gaps(
    document_analyses: list[DocumentAnalysis],
    cross_analysis: CrossDocumentAnalysis,
) -> list[_RankedItem]:
    ranked: list[_RankedItem] = []

    for analysis in document_analyses:
        for risk in analysis.risks_or_anomalies:
            if not risk.citations:
                continue
            text = _format_risk_claim(risk, analysis.document.file_name)
            ranked.append(
                _RankedItem(
                    sort_key=_build_sort_key(
                        confidence=risk.confidence,
                        citation_count=len(risk.citations),
                        has_quote=_has_quote(risk.citations),
                        label=f"risk:{risk.title}",
                    ),
                    label_key=_normalize_key(f"risk:{risk.title}"),
                    claim=_ReportClaim(text=text, citations=_dedupe_citations(risk.citations)),
                )
            )

        for question in analysis.open_questions:
            if not question.citations:
                continue
            text = _format_open_question_claim(question, analysis.document.file_name)
            ranked.append(
                _RankedItem(
                    sort_key=_build_sort_key(
                        confidence=None,
                        citation_count=len(question.citations),
                        has_quote=_has_quote(question.citations),
                        label=f"question:{question.question}",
                    ),
                    label_key=_normalize_key(f"question:{question.question}"),
                    claim=_ReportClaim(text=text, citations=_dedupe_citations(question.citations)),
                )
            )

    for insight in cross_analysis.insights:
        if insight.insight_type != "gap" or not insight.citations:
            continue
        text = _format_cross_insight_claim(insight)
        ranked.append(
            _RankedItem(
                sort_key=_build_sort_key(
                    confidence=insight.confidence,
                    citation_count=len(insight.citations),
                    has_quote=_has_quote(insight.citations),
                    label=f"gap:{insight.title}",
                ),
                label_key=_normalize_key(f"gap:{insight.title}"),
                claim=_ReportClaim(text=text, citations=_dedupe_citations(insight.citations)),
            )
        )

    return _dedupe_ranked_items(ranked)


def _render_numbered_section(items: list[_RankedItem], empty_message: str) -> list[str]:
    if not items:
        return [empty_message]

    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        lines.append(f"{index}. {item.claim.text} {_render_inline_citations(item.claim.citations)}")
    return lines


def _render_bulleted_section(items: list[_RankedItem], empty_message: str) -> list[str]:
    if not items:
        return [f"- {empty_message}"]

    lines: list[str] = []
    for item in items:
        lines.append(f"- {item.claim.text} {_render_inline_citations(item.claim.citations)}")
    return lines


def _render_evidence_appendix(claims: list[_ReportClaim]) -> list[str]:
    unique_claims: list[_ReportClaim] = []
    seen: set[str] = set()

    for claim in claims:
        key = _normalize_key(claim.text)
        if key in seen:
            continue
        seen.add(key)
        unique_claims.append(claim)

    if not unique_claims:
        return ["- Claim: No grounded claims were included in the report body.", "  - Citations: None"]

    lines: list[str] = []
    for claim in unique_claims:
        lines.append(f"- Claim: {claim.text}")
        lines.append(f"  - Citations: {_render_citation_list(claim.citations)}")
    return lines


def _format_fact_claim(fact: ExtractedFact, file_name: str | None) -> str:
    unit_suffix = f" {fact.unit}" if fact.unit else ""
    source_suffix = f" in {file_name}" if file_name else ""
    rationale_suffix = f" {fact.rationale.strip()}" if fact.rationale and fact.rationale.strip() else ""
    return f"{fact.label}: {fact.value}{unit_suffix}{source_suffix}.{rationale_suffix}".strip()


def _format_risk_claim(risk: RiskOrAnomaly, file_name: str | None) -> str:
    severity = risk.severity.strip() if risk.severity else "unspecified"
    source_suffix = f" in {file_name}" if file_name else ""
    return f"{risk.title} ({severity}){source_suffix}: {risk.description}".strip()


def _format_open_question_claim(question: OpenQuestion, file_name: str | None) -> str:
    source_suffix = f" in {file_name}" if file_name else ""
    return f"Open question{source_suffix}: {question.question} Reason: {question.reason}".strip()


def _format_cross_insight_claim(insight: CrossDocumentInsight) -> str:
    documents = ", ".join(
        document.file_name or document.document_id for document in insight.involved_documents
    )
    document_suffix = f" Across {documents}." if documents else ""
    insight_type = insight.insight_type.replace("_", " ")
    return f"{insight.title} [{insight_type}]: {insight.description}{document_suffix}".strip()


def _render_inline_citations(citations: list[BlockCitation]) -> str:
    if not citations:
        return ""
    return f"({_render_citation_list(citations)})"


def _render_citation_list(citations: list[BlockCitation]) -> str:
    deduped = _dedupe_citations(citations)
    return "; ".join(_format_citation(citation) for citation in deduped) if deduped else "None"


def _format_citation(citation: BlockCitation) -> str:
    parts = [
        citation.file_name or citation.document_id,
        f"p.{citation.page_number}",
    ]
    if citation.chunk_id:
        parts.append(citation.chunk_id)
    if citation.quote_text:
        parts.append(f'"{_truncate_quote(citation.quote_text)}"')
    return ", ".join(parts)


def _dedupe_citations(citations: list[BlockCitation]) -> list[BlockCitation]:
    deduped: list[BlockCitation] = []
    seen: set[tuple[str, int, int | None, str | None]] = set()

    for citation in citations:
        key = (
            citation.document_id,
            citation.page_number,
            citation.block_index,
            citation.chunk_id,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(citation)

    return deduped


def _dedupe_ranked_items(items: list[_RankedItem]) -> list[_RankedItem]:
    deduped: list[_RankedItem] = []
    seen: set[str] = set()

    for item in sorted(items, key=lambda entry: entry.sort_key):
        if item.label_key in seen:
            continue
        seen.add(item.label_key)
        deduped.append(item)

    return deduped


def _build_sort_key(
    confidence: float | None,
    citation_count: int,
    has_quote: bool,
    label: str,
) -> tuple[float, float, float, str]:
    normalized_confidence = -(confidence if confidence is not None else -1.0)
    normalized_citations = -float(citation_count)
    normalized_quote = -1.0 if has_quote else 0.0
    return (normalized_confidence, normalized_citations, normalized_quote, _normalize_key(label))


def _has_quote(citations: list[BlockCitation]) -> bool:
    return any(bool(citation.quote_text and citation.quote_text.strip()) for citation in citations)


def _normalize_key(value: str) -> str:
    return " ".join(value.lower().split())


def _truncate_quote(value: str, max_length: int = 80) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 3].rstrip() + "..."
