from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RawDoclingBlock(BaseModel):
    """A single block returned by the raw Docling parser."""

    block_type: str = Field(description="The block label reported by Docling.")
    text: str = Field(description="The extracted text for this block.")


class RawDoclingPage(BaseModel):
    """A single page from the raw Docling parser output."""

    page_number: int = Field(description="The 1-based page number in the source PDF.")
    text: str = Field(description="The full page text assembled by the parser.")
    blocks: list[RawDoclingBlock] = Field(
        default_factory=list,
        description="The raw blocks detected on this page.",
    )


class RawDoclingMeta(BaseModel):
    """Metadata produced by the Docling parsing step."""

    parser: str = Field(description="The parser name used to produce the payload.")
    warnings: list[str] = Field(
        default_factory=list,
        description="Warnings emitted during parsing.",
    )
    artifact_keys: list[str] = Field(
        default_factory=list,
        description="Names of artifacts available in the payload.",
    )
    page_count: int = Field(description="The total number of pages in the document.")
    docling_meta: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional parser-specific metadata from Docling.",
    )
    content_type: str | None = Field(
        default=None,
        description="The uploaded file content type when known.",
    )
    file_size: int | None = Field(
        default=None,
        description="The uploaded file size in bytes when known.",
    )


class RawDoclingArtifacts(BaseModel):
    """Top-level artifacts exported by Docling for a document."""

    model_config = ConfigDict(populate_by_name=True)

    markdown: str | None = Field(
        default=None,
        description="Markdown representation of the parsed document.",
    )
    text: str | None = Field(
        default=None,
        description="Plain text representation of the parsed document.",
    )
    json_payload: dict[str, Any] = Field(
        default_factory=dict,
        alias="json",
        serialization_alias="json",
        description="Structured Docling JSON payload.",
    )


class RawDoclingDocument(BaseModel):
    """The full raw document payload returned by the Docling parsing pipeline."""

    ok: bool = Field(description="Whether the parsing step completed successfully.")
    document_id: str = Field(description="The API-assigned document identifier.")
    file_name: str = Field(description="The original uploaded file name.")
    source_path: str = Field(description="The temporary or source path used for parsing.")
    artifacts: RawDoclingArtifacts = Field(description="Artifacts exported by Docling.")
    pages: list[RawDoclingPage] = Field(
        default_factory=list,
        description="Per-page parser output.",
    )
    meta: RawDoclingMeta = Field(description="Metadata for the parsed document.")


class DocumentReference(BaseModel):
    """A lightweight reference to a source document."""

    document_id: str = Field(description="The unique document identifier.")
    file_name: str | None = Field(
        default=None,
        description="The document file name when available.",
    )


class BlockCitation(BaseModel):
    """A precise citation pointing to a page and optional block or chunk."""

    document_id: str = Field(description="The cited document identifier.")
    file_name: str | None = Field(
        default=None,
        description="The cited document file name when available.",
    )
    page_number: int = Field(description="The cited 1-based page number.")
    block_index: int | None = Field(
        default=None,
        description="The zero-based block index on the page when known.",
    )
    chunk_id: str | None = Field(
        default=None,
        description="The chunk identifier when the citation points to chunked evidence.",
    )
    quote_text: str | None = Field(
        default=None,
        description="A short quoted span that supports the citation.",
    )


class NormalizedBlock(BaseModel):
    """A cleaned block shape used by downstream extraction steps."""

    block_id: str | None = Field(
        default=None,
        description="A stable block identifier assigned by the pipeline.",
    )
    page_number: int = Field(description="The 1-based page number for this block.")
    block_index: int = Field(description="The zero-based block index on the page.")
    block_type: str = Field(description="The normalized block type.")
    text: str = Field(description="The normalized block text.")
    section_title: str | None = Field(
        default=None,
        description="The section heading that this block belongs to when known.",
    )
    heading_level: int | None = Field(
        default=None,
        description="The heading depth when the block is a heading.",
    )
    contains_table: bool = Field(
        default=False,
        description="Whether this block contains table content.",
    )


class NormalizedPage(BaseModel):
    """A normalized page ready for chunking and extraction."""

    page_number: int = Field(description="The 1-based page number.")
    text: str = Field(description="The normalized page text.")
    citation: str = Field(description="The page-level citation string.")
    blocks: list[NormalizedBlock] = Field(
        default_factory=list,
        description="Normalized blocks found on the page.",
    )
    contains_table: bool = Field(
        default=False,
        description="Whether this page contains any table content.",
    )


class NormalizedDocument(BaseModel):
    """A normalized document used for later analysis stages."""

    document_id: str = Field(description="The unique document identifier.")
    file_name: str = Field(description="The source file name.")
    source_path: str = Field(description="The source path for the document.")
    page_count: int = Field(description="The total page count after normalization.")
    text: str = Field(description="The normalized full-document text.")
    pages: list[NormalizedPage] = Field(
        default_factory=list,
        description="Normalized pages for the document.",
    )
    contains_table: bool = Field(
        default=False,
        description="Whether any part of the document contains table content.",
    )
    source_meta: RawDoclingMeta | None = Field(
        default=None,
        description="Optional raw parser metadata kept for reference.",
    )


class EvidenceChunk(BaseModel):
    """A chunk of evidence that can support facts, risks, or insights."""

    chunk_id: str = Field(description="The unique chunk identifier.")
    document_id: str = Field(description="The source document identifier.")
    file_name: str | None = Field(
        default=None,
        description="The source file name when available.",
    )
    page_number: int = Field(description="The page number where the chunk came from.")
    block_index: int | None = Field(
        default=None,
        description="The block index where the chunk originated when known.",
    )
    text: str = Field(description="The chunk text used as evidence.")
    block_types: list[str] = Field(
        default_factory=list,
        description="The normalized block types that contributed to this chunk.",
    )
    section_title: str | None = Field(
        default=None,
        description="The heading or section title associated with this chunk when known.",
    )
    contains_table: bool = Field(
        default=False,
        description="Whether the chunk includes table content.",
    )
    citation: BlockCitation = Field(
        description="The citation pointing back to the source location.",
    )


class ExtractedFact(BaseModel):
    """A structured fact extracted from one document."""

    fact_id: str = Field(description="The unique identifier for this fact.")
    source_document_id: str = Field(description="The document that produced the fact.")
    fact_type: str = Field(description="The category of fact, such as lab_result or date.")
    label: str = Field(description="The human-readable fact label.")
    value: str = Field(description="The extracted fact value.")
    unit: str | None = Field(
        default=None,
        description="The measurement unit when the fact has one.",
    )
    confidence: float | None = Field(
        default=None,
        description="The model confidence score for the fact when available.",
    )
    rationale: str | None = Field(
        default=None,
        description="A short explanation for why the fact was extracted.",
    )
    citations: list[BlockCitation] = Field(
        default_factory=list,
        description="Citations that support this fact.",
    )


class RiskOrAnomaly(BaseModel):
    """A possible risk, outlier, or anomaly found in one document."""

    risk_id: str = Field(description="The unique identifier for this risk or anomaly.")
    source_document_id: str = Field(description="The document that produced the finding.")
    title: str = Field(description="A short label for the finding.")
    description: str = Field(description="A plain-language description of the finding.")
    severity: str = Field(description="The severity level for the finding.")
    confidence: float | None = Field(
        default=None,
        description="The confidence score for this finding when available.",
    )
    citations: list[BlockCitation] = Field(
        default_factory=list,
        description="Citations that support this finding.",
    )


class OpenQuestion(BaseModel):
    """A question that remains unresolved after reviewing one document."""

    question_id: str = Field(description="The unique identifier for this open question.")
    source_document_id: str = Field(description="The document that produced the question.")
    question: str = Field(description="The unresolved question.")
    reason: str = Field(description="Why the question remains open.")
    citations: list[BlockCitation] = Field(
        default_factory=list,
        description="Citations that explain why the question remains open.",
    )


class PossibleDocumentLink(BaseModel):
    """A grounded hint that another document may be relevant."""

    link_id: str = Field(description="The unique identifier for this possible link.")
    source_document_id: str = Field(description="The document that produced the link.")
    description: str = Field(description="Why another document may be relevant.")
    linked_document_hint: str = Field(
        description="A plain-language hint about the kind of related document to look for.",
    )
    confidence: float | None = Field(
        default=None,
        description="The confidence score for this possible link when available.",
    )
    citations: list[BlockCitation] = Field(
        default_factory=list,
        description="Citations that support this possible link.",
    )


class DocumentAnalysis(BaseModel):
    """The full analysis output for a single document."""

    document: DocumentReference = Field(description="The document that was analyzed.")
    normalized_document: NormalizedDocument | None = Field(
        default=None,
        description="The normalized representation used for extraction.",
    )
    evidence_chunks: list[EvidenceChunk] = Field(
        default_factory=list,
        description="Evidence chunks created from the document.",
    )
    extracted_facts: list[ExtractedFact] = Field(
        default_factory=list,
        description="Structured facts found in the document.",
    )
    risks_or_anomalies: list[RiskOrAnomaly] = Field(
        default_factory=list,
        description="Potential risks or anomalies found in the document.",
    )
    open_questions: list[OpenQuestion] = Field(
        default_factory=list,
        description="Questions that remain unresolved after reviewing the document.",
    )
    possible_links_to_other_documents: list[PossibleDocumentLink] = Field(
        default_factory=list,
        description="Grounded hints about other documents that may be relevant.",
    )
    summary: str | None = Field(
        default=None,
        description="A short summary of the document analysis.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Warnings produced during analysis.",
    )


class CrossDocumentInsight(BaseModel):
    """A finding that depends on comparing more than one document."""

    insight_id: str = Field(description="The unique identifier for this insight.")
    title: str = Field(description="A short title for the cross-document insight.")
    description: str = Field(description="A plain-language description of the insight.")
    insight_type: str = Field(description="The category for this cross-document insight.")
    involved_documents: list[DocumentReference] = Field(
        default_factory=list,
        description="Documents that contribute to this insight.",
    )
    confidence: float | None = Field(
        default=None,
        description="The confidence score for this insight when available.",
    )
    citations: list[BlockCitation] = Field(
        default_factory=list,
        description="Citations that support this insight.",
    )


class CrossDocumentAnalysis(BaseModel):
    """Analysis output produced by comparing multiple documents."""

    insights: list[CrossDocumentInsight] = Field(
        default_factory=list,
        description="Cross-document insights found across the request.",
    )
    summary: str | None = Field(
        default=None,
        description="A short summary of the cross-document analysis.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Warnings produced during cross-document analysis.",
    )


class AnalyzeRequest(BaseModel):
    """Request payload for the analysis pipeline."""

    request_id: str | None = Field(
        default=None,
        description="An optional client-provided request identifier.",
    )
    instructions: str | None = Field(
        default=None,
        description="Optional plain-text instructions for the analysis pipeline.",
    )
    documents: list[RawDoclingDocument] = Field(
        default_factory=list,
        description="Raw parsed documents to analyze.",
    )


class AnalyzeResponse(BaseModel):
    """Response payload returned by the analysis pipeline."""

    ok: bool = Field(description="Whether the analysis pipeline completed successfully.")
    request_id: str | None = Field(
        default=None,
        description="The request identifier when one was provided.",
    )
    analyses: list[DocumentAnalysis] = Field(
        default_factory=list,
        description="Per-document analysis results.",
    )
    cross_document_analysis: CrossDocumentAnalysis | None = Field(
        default=None,
        description="Cross-document analysis results when more than one document is provided.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Top-level warnings returned by the pipeline.",
    )


class AnalysisStats(BaseModel):
    """Simple pipeline statistics returned by the orchestration layer."""

    document_count: int = Field(description="The number of raw input documents.")
    normalized_document_count: int = Field(
        description="The number of documents normalized by the pipeline."
    )
    chunk_count: int = Field(description="The total number of evidence chunks created.")
    document_analysis_count: int = Field(
        description="The number of per-document analyses returned."
    )
    cross_document_insight_count: int = Field(
        description="The number of cross-document insights returned."
    )


class AnalyzePipelineResponse(BaseModel):
    """Response payload returned by the `/analyze` orchestration endpoint."""

    ok: bool = Field(description="Whether the analysis pipeline completed successfully.")
    document_analyses: list[DocumentAnalysis] = Field(
        default_factory=list,
        description="Per-document analyses produced by the pipeline.",
    )
    cross_document_analysis: CrossDocumentAnalysis = Field(
        description="Cross-document analysis produced across all input documents.",
    )
    report_markdown: str = Field(
        description="The final executive intelligence report in markdown format.",
    )
    stats: AnalysisStats = Field(description="Basic orchestration statistics.")
    warnings: list[str] = Field(
        default_factory=list,
        description="Aggregated parser, analysis, and synthesis warnings.",
    )


class ReportDocumentSummary(BaseModel):
    """Compact per-document summary returned by the report-generation endpoint."""

    document_id: str = Field(description="The unique document identifier.")
    file_name: str = Field(description="The source file name.")
    page_count: int = Field(description="The normalized page count.")
    contains_table: bool = Field(
        default=False,
        description="Whether the document included table content.",
    )
    summary: str | None = Field(
        default=None,
        description="A short grounded summary of the document.",
    )
    extracted_facts: list[ExtractedFact] = Field(
        default_factory=list,
        description="Structured facts surfaced for the document.",
    )
    risks_or_anomalies: list[RiskOrAnomaly] = Field(
        default_factory=list,
        description="Grounded risks or anomalies for the document.",
    )
    open_questions: list[OpenQuestion] = Field(
        default_factory=list,
        description="Open questions that remain for the document.",
    )
    possible_links_to_other_documents: list[PossibleDocumentLink] = Field(
        default_factory=list,
        description="Grounded hints about related documents.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Warnings tied to this document.",
    )


class GenerateReportResponse(BaseModel):
    """Response payload returned by the `/reports/generate` endpoint."""

    ok: bool = Field(description="Whether report generation completed successfully.")
    report_markdown: str = Field(
        description="The final executive intelligence report in markdown format.",
    )
    documents: list[ReportDocumentSummary] = Field(
        default_factory=list,
        description="Compact per-document analysis summaries.",
    )
    cross_document_analysis: CrossDocumentAnalysis = Field(
        description="Cross-document synthesis results for the request.",
    )
    stats: AnalysisStats = Field(description="Basic orchestration statistics.")
    warnings: list[str] = Field(
        default_factory=list,
        description="Aggregated parser, analysis, and synthesis warnings.",
    )
