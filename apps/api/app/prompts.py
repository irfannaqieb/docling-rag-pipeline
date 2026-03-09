from __future__ import annotations

from app.schemas import BlockCitation, DocumentAnalysis, EvidenceChunk, NormalizedDocument


def build_document_extraction_prompt(
    doc: NormalizedDocument,
    chunks: list[EvidenceChunk],
    instructions: str | None = None,
) -> str:
    """Build a grounded extraction prompt from one document and its evidence chunks."""

    prompt_instructions = """
You are analyzing one document using only the evidence chunks provided below.

Rules:
- Use only the provided evidence.
- Every factual claim must cite one or more chunk IDs from the provided evidence.
- Separate directly observed facts from inference where possible.
- Prefer table-derived evidence when it is relevant to the claim.
- If the evidence is uncertain, incomplete, or ambiguous, say uncertain.
- Do not perform cross-document synthesis.
- For possible_links_to_other_documents, provide only grounded hints about what other document may be useful, based solely on this document.
- Do not invent chunk IDs, values, dates, diagnoses, or relationships.
- If nothing supports a field, leave it empty rather than guessing.

Return structured output that matches the requested schema.
""".strip()

    chunk_sections: list[str] = []
    for chunk in chunks:
        section_title = chunk.section_title or "None"
        citation = _format_citation(chunk)
        chunk_sections.append(
            "\n".join(
                [
                    f"Chunk ID: {chunk.chunk_id}",
                    f"Page Number: {chunk.page_number}",
                    f"Citation: {citation}",
                    f"Section Title: {section_title}",
                    f"Contains Table: {'yes' if chunk.contains_table else 'no'}",
                    "Text:",
                    chunk.text,
                ]
            )
        )

    evidence_body = "\n\n---\n\n".join(chunk_sections)
    instruction_block = _format_optional_instructions(instructions)

    return "\n\n".join(
        [
            prompt_instructions,
            instruction_block,
            f"Document ID: {doc.document_id}",
            f"File Name: {doc.file_name}",
            f"Page Count: {doc.page_count}",
            "Evidence Chunks:",
            evidence_body,
        ]
    )


def _format_citation(chunk: EvidenceChunk) -> str:
    citation = chunk.citation
    quote_text = citation.quote_text or ""
    quote_suffix = f' | Quote: "{quote_text}"' if quote_text else ""
    return (
        f"{citation.file_name or chunk.file_name or 'Unknown file'}, "
        f"Page {citation.page_number}, "
        f"Chunk {citation.chunk_id or chunk.chunk_id}"
        f"{quote_suffix}"
    )


def build_cross_document_synthesis_prompt(
    document_analyses: list[DocumentAnalysis],
    instructions: str | None = None,
) -> str:
    """Build a grounded synthesis prompt from multiple document analyses."""

    prompt_instructions = """
You are synthesizing findings across multiple documents.

Rules:
- Compare documents against each other instead of summarizing them independently.
- Use only the grounded information and citations provided below.
- Surface only cross-document insights that require combining documents.
- Look for corroborations, contradictions, repeated entities, repeated metrics, timeline clues, recommendation or follow-up relationships, and meaningful gaps.
- Every insight must cite supporting citation keys from the provided evidence.
- Prefer insights supported by at least two documents.
- A gap may use one source only if the absence or incompleteness becomes meaningful in the multi-document context.
- Do not invent document IDs, citation keys, diagnoses, measurements, or relationships.
- If the evidence is weak or partial, lower confidence and say so in the description.

Return structured output that matches the requested schema.
""".strip()

    document_sections: list[str] = []
    for analysis in document_analyses:
        summary = analysis.summary or "None"
        document_sections.append(
            "\n".join(
                [
                    f"Document ID: {analysis.document.document_id}",
                    f"File Name: {analysis.document.file_name or 'Unknown file'}",
                    f"Summary: {summary}",
                    "Extracted Facts:",
                    _format_fact_entries(analysis),
                    "Risks Or Anomalies:",
                    _format_risk_entries(analysis),
                    "Open Questions:",
                    _format_open_question_entries(analysis),
                    "Possible Links To Other Documents:",
                    _format_possible_link_entries(analysis),
                ]
            )
        )

    instruction_block = _format_optional_instructions(instructions)

    return "\n\n".join(
        [
            prompt_instructions,
            instruction_block,
            "Document Analyses:",
            "\n\n---\n\n".join(document_sections),
        ]
    )


def _format_fact_entries(analysis: DocumentAnalysis) -> str:
    if not analysis.extracted_facts:
        return "- None"

    entries: list[str] = []
    for fact in analysis.extracted_facts:
        citations = _format_citation_list(fact.citations)
        rationale = fact.rationale or "None"
        entries.append(
            "\n".join(
                [
                    f"- Fact ID: {fact.fact_id}",
                    f"  Type: {fact.fact_type}",
                    f"  Label: {fact.label}",
                    f"  Value: {fact.value}",
                    f"  Unit: {fact.unit or 'None'}",
                    f"  Confidence: {_format_confidence(fact.confidence)}",
                    f"  Rationale: {rationale}",
                    f"  Citations: {citations}",
                ]
            )
        )
    return "\n".join(entries)


def _format_risk_entries(analysis: DocumentAnalysis) -> str:
    if not analysis.risks_or_anomalies:
        return "- None"

    entries: list[str] = []
    for risk in analysis.risks_or_anomalies:
        citations = _format_citation_list(risk.citations)
        entries.append(
            "\n".join(
                [
                    f"- Risk ID: {risk.risk_id}",
                    f"  Title: {risk.title}",
                    f"  Severity: {risk.severity}",
                    f"  Confidence: {_format_confidence(risk.confidence)}",
                    f"  Description: {risk.description}",
                    f"  Citations: {citations}",
                ]
            )
        )
    return "\n".join(entries)


def _format_open_question_entries(analysis: DocumentAnalysis) -> str:
    if not analysis.open_questions:
        return "- None"

    entries: list[str] = []
    for question in analysis.open_questions:
        citations = _format_citation_list(question.citations)
        entries.append(
            "\n".join(
                [
                    f"- Question ID: {question.question_id}",
                    f"  Question: {question.question}",
                    f"  Reason: {question.reason}",
                    f"  Citations: {citations}",
                ]
            )
        )
    return "\n".join(entries)


def _format_possible_link_entries(analysis: DocumentAnalysis) -> str:
    if not analysis.possible_links_to_other_documents:
        return "- None"

    entries: list[str] = []
    for link in analysis.possible_links_to_other_documents:
        citations = _format_citation_list(link.citations)
        entries.append(
            "\n".join(
                [
                    f"- Link ID: {link.link_id}",
                    f"  Description: {link.description}",
                    f"  Linked Document Hint: {link.linked_document_hint}",
                    f"  Confidence: {_format_confidence(link.confidence)}",
                    f"  Citations: {citations}",
                ]
            )
        )
    return "\n".join(entries)


def _format_citation_list(citations: list[BlockCitation]) -> str:
    if not citations:
        return "None"
    return "; ".join(_format_block_citation(citation) for citation in citations)


def _format_block_citation(citation: BlockCitation) -> str:
    citation_key = build_citation_key(citation)
    quote_text = citation.quote_text or ""
    quote_suffix = f' | Quote: "{quote_text}"' if quote_text else ""
    return (
        f"{citation_key} => "
        f"{citation.file_name or 'Unknown file'}, "
        f"Page {citation.page_number}"
        f"{quote_suffix}"
    )


def build_citation_key(citation: BlockCitation) -> str:
    chunk_id = citation.chunk_id or "no_chunk"
    block_index = citation.block_index if citation.block_index is not None else "na"
    return f"{citation.document_id}::{chunk_id}/p{citation.page_number}/b{block_index}"


def _format_confidence(value: float | None) -> str:
    if value is None:
        return "None"
    return f"{value:.2f}"


def _format_optional_instructions(value: str | None) -> str:
    if value is None:
        return "Additional Instructions: None"

    normalized = value.strip()
    if not normalized:
        return "Additional Instructions: None"

    return f"Additional Instructions:\n{normalized}"
