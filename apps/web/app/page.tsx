"use client";

import { ChangeEvent, ReactNode, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import remarkGfm from "remark-gfm";

type DocumentReference = {
  document_id: string;
  file_name: string | null;
};

type Citation = {
  document_id: string;
  file_name: string | null;
  page_number: number;
  block_index: number | null;
  chunk_id: string | null;
  quote_text: string | null;
};

type ExtractedFact = {
  fact_id: string;
  source_document_id: string;
  fact_type: string;
  label: string;
  value: string;
  unit: string | null;
  confidence: number | null;
  rationale: string | null;
  citations: Citation[];
};

type RiskOrAnomaly = {
  risk_id: string;
  source_document_id: string;
  title: string;
  description: string;
  severity: "low" | "medium" | "high" | string;
  confidence: number | null;
  citations: Citation[];
};

type OpenQuestion = {
  question_id: string;
  source_document_id: string;
  question: string;
  reason: string;
  citations: Citation[];
};

type PossibleLink = {
  link_id: string;
  source_document_id: string;
  description: string;
  linked_document_hint: string;
  confidence: number | null;
  citations: Citation[];
};

type ReportDocumentSummary = {
  document_id: string;
  file_name: string;
  page_count: number;
  contains_table: boolean;
  summary: string | null;
  extracted_facts: ExtractedFact[];
  risks_or_anomalies: RiskOrAnomaly[];
  open_questions: OpenQuestion[];
  possible_links_to_other_documents: PossibleLink[];
  warnings: string[];
};

type CrossDocumentInsight = {
  insight_id: string;
  title: string;
  description: string;
  insight_type: string;
  involved_documents: DocumentReference[];
  confidence: number | null;
  citations: Citation[];
};

type AnalysisStats = {
  document_count: number;
  normalized_document_count: number;
  chunk_count: number;
  document_analysis_count: number;
  cross_document_insight_count: number;
};

type GenerateReportResponse = {
  ok: boolean;
  report_markdown: string;
  documents: ReportDocumentSummary[];
  cross_document_analysis: {
    summary: string | null;
    insights: CrossDocumentInsight[];
    warnings: string[];
  };
  stats: AnalysisStats;
  warnings: string[];
};

type ErrorResponse = {
  detail?: string;
};

type FactGroup = {
  key: string;
  title: string;
  description: string;
  facts: ExtractedFact[];
};

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ??
  "http://localhost:8000";

const DEFAULT_INSTRUCTIONS = `Produce an Executive Intelligence Report, not a generic summary.

Priorities:
- treat tables and structured values as first-class evidence
- connect facts across documents only when citations support the inference
- highlight corroborations, contradictions, timeline links, and meaningful gaps
- keep every material claim grounded with document/page citations
- do not invent diagnoses, entities, dates, or relationships`;

const FACT_TYPE_META: Record<string, { title: string; description: string }> = {
  lab_result: {
    title: "Lab results",
    description: "Measurements and values extracted from the document.",
  },
  patient_identifier: {
    title: "Patient identifiers",
    description: "Names and identifiers tied to the patient record.",
  },
  patient_demographics: {
    title: "Patient profile",
    description: "Demographic details such as age and sex.",
  },
  document_metadata: {
    title: "Document metadata",
    description: "File-level details inferred from the source report.",
  },
  administrative_identifier: {
    title: "Administrative IDs",
    description: "Operational identifiers such as MRN or lab number.",
  },
  encounter_location: {
    title: "Encounter context",
    description: "Location and encounter details tied to the report.",
  },
  report_timing: {
    title: "Report timing",
    description: "Timestamps associated with report generation.",
  },
  specimen_timing: {
    title: "Specimen timing",
    description: "Timing information tied to receipt or collection.",
  },
  care_team: {
    title: "Care team",
    description: "Clinicians or departments referenced by the report.",
  },
};

const FACT_TYPE_ORDER = [
  "lab_result",
  "patient_identifier",
  "administrative_identifier",
  "patient_demographics",
  "report_timing",
  "specimen_timing",
  "encounter_location",
  "care_team",
  "document_metadata",
];

const reportMarkdownComponents: Components = {
  h1: ({ children }) => (
    <header className="report-header">
      <p className="report-kicker">Executive Report</p>
      <h3>{children}</h3>
    </header>
  ),
  h2: ({ children }) => <h2 className="report-markdown-heading">{children}</h2>,
  h3: ({ children }) => (
    <h3 className="report-markdown-subheading">{children}</h3>
  ),
  p: ({ children }) => <p className="report-paragraph">{children}</p>,
  ol: ({ children }) => (
    <ol className="report-list report-list-ordered">{children}</ol>
  ),
  ul: ({ children }) => (
    <ul className="report-list report-list-unordered">{children}</ul>
  ),
  li: ({ children }) => <li className="report-list-item">{children}</li>,
  table: ({ children }) => (
    <div className="report-table-wrap">
      <table className="report-table">{children}</table>
    </div>
  ),
  blockquote: ({ children }) => (
    <blockquote className="report-blockquote">{children}</blockquote>
  ),
};

export default function Home() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [instructions, setInstructions] = useState(DEFAULT_INSTRUCTIONS);
  const [result, setResult] = useState<GenerateReportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  function handleFileSelection(event: ChangeEvent<HTMLInputElement>) {
    const selectedFiles = Array.from(event.target.files ?? []).filter((file) =>
      file.name.toLowerCase().endsWith(".pdf"),
    );

    setFiles((currentFiles) => {
      const seen = new Set(
        currentFiles.map(
          (file) => `${file.name}:${file.size}:${file.lastModified}`,
        ),
      );
      const nextFiles = [...currentFiles];

      for (const file of selectedFiles) {
        const key = `${file.name}:${file.size}:${file.lastModified}`;
        if (!seen.has(key)) {
          seen.add(key);
          nextFiles.push(file);
        }
      }

      return nextFiles;
    });

    setError(null);
    event.target.value = "";
  }

  function removeFile(indexToRemove: number) {
    setFiles((currentFiles) =>
      currentFiles.filter((_, index) => index !== indexToRemove),
    );
  }

  async function handleSubmit() {
    if (files.length === 0) {
      setError("Pick at least one PDF before generating the report.");
      return;
    }

    const formData = new FormData();
    for (const file of files) {
      formData.append("files", file);
    }

    const trimmedInstructions = instructions.trim();
    if (trimmedInstructions) {
      formData.append("instructions", trimmedInstructions);
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/reports/generate`, {
        method: "POST",
        body: formData,
      });

      const payload = (await response.json()) as
        | GenerateReportResponse
        | ErrorResponse;

      if (!response.ok) {
        const message =
          "detail" in payload && typeof payload.detail === "string"
            ? payload.detail
            : "Report generation failed.";
        throw new Error(message);
      }

      if (!isGenerateReportResponse(payload)) {
        throw new Error("Unexpected report response.");
      }

      setResult(payload);
    } catch (submissionError) {
      setResult(null);
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "Report generation failed.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen px-4 py-8 md:px-8 md:py-10">
      <div className="mx-auto flex w-full max-w-[100rem] flex-col gap-6">
        <section className="hero-panel rounded-4xl border border-white/60 p-6 md:p-10">
          <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
            <div className="space-y-4">
              <p className="text-sm font-semibold uppercase tracking-[0.28em] text-(--accent-strong)">
                N1 Care / Web
              </p>
              <div className="space-y-3">
                <h1 className="max-w-4xl text-4xl font-semibold tracking-tight text-(--ink-strong) md:text-6xl">
                  Review medical PDF output without fighting the interface.
                </h1>
                <p className="max-w-2xl text-base leading-7 text-(--ink-soft) md:text-lg">
                  Upload one or more PDFs, generate the backend report, then
                  read the output as a narrative first, with grouped evidence
                  and risks beneath it.
                </p>
              </div>
            </div>

            <div className="glass-panel rounded-[1.75rem] p-5">
              <div className="grid grid-cols-2 gap-4">
                <MetricCard
                  label="Selected PDFs"
                  value={String(files.length)}
                />
                <MetricCard
                  label="API Endpoint"
                  value={API_BASE_URL.replace(/^https?:\/\//, "")}
                  small
                />
                <MetricCard
                  label="Cross-doc Insights"
                  value={String(
                    result?.stats.cross_document_insight_count ?? 0,
                  )}
                />
                <MetricCard
                  label="Processing Notes"
                  value={String(result?.warnings.length ?? 0)}
                />
              </div>
            </div>
          </div>
        </section>

        <section className="space-y-6">
          <div className="grid gap-6 xl:grid-cols-2">
            <div className="glass-panel rounded-[1.75rem] p-5 md:p-6">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-xl font-semibold text-(--ink-strong)">
                    PDF Picker
                  </h2>
                  <p className="text-sm leading-6 text-(--ink-soft)">
                    Add PDFs to the batch. Files are sent as repeated `files`
                    fields in one request.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="rounded-full bg-(--accent) px-4 py-2 text-sm font-medium text-white transition hover:bg-(--accent-strong)"
                >
                  Add PDFs
                </button>
              </div>

              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="upload-zone flex w-full flex-col items-center justify-center rounded-3xl border border-dashed border-(--line-strong) px-6 py-10 text-center"
              >
                <span className="text-lg font-semibold text-(--ink-strong)">
                  Pick multiple PDF files
                </span>
                <span className="mt-2 max-w-md text-sm leading-6 text-(--ink-soft)">
                  Use Ctrl or Shift in the dialog, or reopen the picker to
                  append more files.
                </span>
              </button>

              <input
                ref={fileInputRef}
                type="file"
                accept="application/pdf,.pdf"
                multiple
                className="hidden"
                onChange={handleFileSelection}
              />

              <div className="mt-4 space-y-3">
                {files.length === 0 ? (
                  <p className="rounded-2xl border border-(--line) bg-(--paper) px-4 py-3 text-sm text-(--ink-soft)">
                    No PDFs selected yet.
                  </p>
                ) : (
                  files.map((file, index) => (
                    <div
                      key={`${file.name}:${file.size}:${file.lastModified}`}
                      className="flex items-center justify-between gap-3 rounded-2xl border border-(--line) bg-(--paper) px-4 py-3"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-(--ink-strong)">
                          {file.name}
                        </p>
                        <p className="text-xs text-(--ink-soft)">
                          {formatFileSize(file.size)}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => removeFile(index)}
                        className="rounded-full border border-(--line) px-3 py-1 text-xs font-medium text-(--ink-soft) transition hover:border-(--accent) hover:text-(--accent-strong)"
                      >
                        Remove
                      </button>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="glass-panel rounded-[1.75rem] p-5 md:p-6">
              <div className="mb-3">
                <h2 className="text-xl font-semibold text-(--ink-strong)">
                  Instructions
                </h2>
                <p className="text-sm leading-6 text-(--ink-soft)">
                  Override the default prompt when you need a different
                  synthesis style.
                </p>
              </div>
              <textarea
                value={instructions}
                onChange={(event) => setInstructions(event.target.value)}
                rows={10}
                className="w-full rounded-[1.25rem] border border-(--line) bg-(--paper) px-4 py-3 text-sm leading-6 text-(--ink-strong) outline-none transition focus:border-(--accent)"
              />
              <div className="mt-4 flex items-center justify-between gap-3">
                <p className="text-sm leading-6 text-(--ink-soft)">
                  {files.length > 1
                    ? "Multiple PDFs will be analyzed together."
                    : "Add more PDFs to unlock cross-document synthesis."}
                </p>
                <button
                  type="button"
                  onClick={handleSubmit}
                  disabled={isSubmitting}
                  className="rounded-full bg-(--ink-strong) px-5 py-2.5 text-sm font-medium text-white transition hover:bg-(--ink-stronger) disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isSubmitting ? "Generating..." : "Generate Report"}
                </button>
              </div>
              {error ? (
                <p className="mt-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {error}
                </p>
              ) : null}
            </div>
          </div>

          <div className="space-y-6">
            <section className="report-shell rounded-[1.75rem] p-5 md:p-6">
              {result ? (
                <div className="report-stage">
                  <div className="space-y-4">
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div className="max-w-3xl">
                        <p className="text-sm font-semibold uppercase tracking-[0.24em] text-white/55">
                          Report Output
                        </p>
                        <h2 className="mt-2 text-2xl font-semibold text-white">
                          Generated review
                        </h2>
                        <p className="mt-2 text-sm leading-6 text-white/70">
                          Read the narrative first, then use the structured side
                          rail and document breakdowns to verify what the
                          backend actually grounded.
                        </p>
                      </div>

                      <div className="grid min-w-[18rem] gap-3 sm:grid-cols-2">
                        <MetricCard
                          label="Documents"
                          value={String(result.stats.document_count)}
                          dark
                        />
                        <MetricCard
                          label="Chunks"
                          value={String(result.stats.chunk_count)}
                          dark
                        />
                        <MetricCard
                          label="Doc Analyses"
                          value={String(result.stats.document_analysis_count)}
                          dark
                        />
                        <MetricCard
                          label="Insights"
                          value={String(
                            result.stats.cross_document_insight_count,
                          )}
                          dark
                        />
                      </div>
                    </div>

                    <ReportMarkdownView markdown={result.report_markdown} />
                  </div>

                  <ReportSideRail result={result} />
                </div>
              ) : (
                <div className="report-empty">
                  <p className="report-kicker">Report Output</p>
                  <h2>No report yet.</h2>
                  <p>
                    Submit at least one PDF to populate the markdown report and
                    structured evidence panels.
                  </p>
                </div>
              )}
            </section>

            {result?.documents.map((document) => (
              <DocumentCard key={document.document_id} document={document} />
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}

function ReportSideRail({ result }: { result: GenerateReportResponse }) {
  return (
    <aside className="report-side-rail">
      <AsideCard title="Batch overview" eyebrow="Structured snapshot">
        <div className="pill-list">
          <SummaryPill
            label={`${result.documents.length} document${result.documents.length === 1 ? "" : "s"}`}
          />
          <SummaryPill label={`${countTotalFacts(result.documents)} facts`} />
          <SummaryPill label={`${countTotalRisks(result.documents)} risks`} />
          <SummaryPill
            label={`${countTotalQuestions(result.documents)} open questions`}
          />
        </div>

        <div className="aside-stack mt-4">
          {result.documents.map((document) => (
            <article key={document.document_id} className="aside-item">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-semibold text-white">
                    {cleanText(document.file_name)}
                  </p>
                  <p className="mt-1 text-sm leading-6 text-white/68">
                    {document.page_count} page
                    {document.page_count === 1 ? "" : "s"}
                    {document.contains_table ? " • contains tables" : ""}
                  </p>
                </div>
                <span className="rounded-full border border-white/10 bg-white/6 px-2.5 py-1 text-xs font-semibold text-white/72">
                  {document.extracted_facts.length} facts
                </span>
              </div>
            </article>
          ))}
        </div>
      </AsideCard>

      <AsideCard title="Cross-document synthesis" eyebrow="Comparison layer">
        <p className="text-sm leading-7 text-white/80">
          {cleanText(
            result.cross_document_analysis.summary ||
              (result.documents.length > 1
                ? "No grounded cross-document summary was returned."
                : "One document was analyzed, so cross-document synthesis is naturally limited."),
          )}
        </p>

        {result.cross_document_analysis.insights.length > 0 ? (
          <div className="aside-stack mt-4">
            {result.cross_document_analysis.insights.map((insight) => (
              <CrossDocumentInsightCard
                key={insight.insight_id}
                insight={insight}
              />
            ))}
          </div>
        ) : null}

        {result.cross_document_analysis.warnings.length > 0 ? (
          <TextList
            className="mt-4"
            title="Cross-document notes"
            items={result.cross_document_analysis.warnings}
            dark
          />
        ) : null}
      </AsideCard>

      {result.warnings.length > 0 ? (
        <AsideCard title="Processing notes" eyebrow="Pipeline">
          <TextList items={result.warnings} dark />
        </AsideCard>
      ) : null}
    </aside>
  );
}

function CrossDocumentInsightCard({
  insight,
}: {
  insight: CrossDocumentInsight;
}) {
  const confidenceLabel = formatConfidence(insight.confidence);

  return (
    <article className="aside-item">
      <div className="flex flex-wrap items-center gap-2">
        <p className="font-semibold text-white">{cleanText(insight.title)}</p>
        {confidenceLabel ? (
          <ConfidenceBadge label={confidenceLabel} dark />
        ) : null}
      </div>
      <p className="mt-2 text-sm leading-6 text-white/78">
        {cleanText(insight.description)}
      </p>
      {insight.involved_documents.length > 0 ? (
        <p className="mt-3 text-xs font-medium uppercase tracking-[0.18em] text-white/48">
          {insight.involved_documents.map(formatDocumentReference).join(" • ")}
        </p>
      ) : null}
      {insight.citations.length > 0 ? (
        <InlineEvidenceSummary
          className="mt-3"
          citations={insight.citations}
          dark
        />
      ) : null}
    </article>
  );
}

function DocumentCard({ document }: { document: ReportDocumentSummary }) {
  const factGroups = groupFactsByType(document.extracted_facts);
  const headlineFacts = getHeadlineFacts(document.extracted_facts);

  return (
    <section className="glass-panel rounded-[1.75rem] p-5 md:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <p className="text-sm font-semibold uppercase tracking-[0.24em] text-(--accent-strong)">
            Document Review
          </p>
          <h2 className="mt-2 text-2xl font-semibold text-(--ink-strong)">
            {cleanText(document.file_name)}
          </h2>
          <p className="mt-2 text-sm leading-6 text-(--ink-soft)">
            {document.page_count} page{document.page_count === 1 ? "" : "s"}
            {document.contains_table ? " • contains tables" : ""}
          </p>
          {headlineFacts.length > 0 ? (
            <div className="mt-4 flex flex-wrap gap-2">
              {headlineFacts.map((fact) => (
                <SummaryPill key={fact} label={fact} subtle />
              ))}
            </div>
          ) : null}
        </div>

        <div className="grid min-w-[18rem] gap-3 sm:grid-cols-2">
          <MetricCard
            label="Facts"
            value={String(document.extracted_facts.length)}
          />
          <MetricCard
            label="Risks"
            value={String(document.risks_or_anomalies.length)}
          />
          <MetricCard
            label="Questions"
            value={String(document.open_questions.length)}
          />
          <MetricCard
            label="Related Docs"
            value={String(document.possible_links_to_other_documents.length)}
          />
        </div>
      </div>

      <div className="mt-5 grid gap-6 xl:grid-cols-[1.3fr_0.7fr]">
        <div className="space-y-6">
          <SectionCard
            title="Grounded summary"
            subtitle="Short narrative pulled from the per-document analysis."
          >
            <p className="text-sm leading-7 text-(--ink-soft)">
              {cleanText(document.summary || "No summary returned.")}
            </p>
          </SectionCard>

          <SectionCard
            title="Extracted facts"
            subtitle="Grouped by fact type so values read more like a dossier than a stack of cards."
          >
            {factGroups.length > 0 ? (
              <div className="fact-group-stack">
                {factGroups.map((group) => (
                  <FactGroupTable key={group.key} group={group} />
                ))}
              </div>
            ) : (
              <EmptyState label="No facts returned for this document." />
            )}
          </SectionCard>
        </div>

        <div className="space-y-6">
          <SectionCard
            title="Risks and anomalies"
            subtitle="Issues the backend flagged while staying grounded in the source."
          >
            {document.risks_or_anomalies.length > 0 ? (
              <div className="signal-stack">
                {document.risks_or_anomalies.map((risk) => (
                  <RiskCard key={risk.risk_id} risk={risk} />
                ))}
              </div>
            ) : (
              <EmptyState label="No risks or anomalies returned." />
            )}
          </SectionCard>

          <SectionCard
            title="Open questions"
            subtitle="Unresolved ambiguities that still need a clearer source document."
          >
            {document.open_questions.length > 0 ? (
              <div className="signal-stack">
                {document.open_questions.map((question) => (
                  <QuestionCard
                    key={question.question_id}
                    question={question}
                  />
                ))}
              </div>
            ) : (
              <EmptyState label="No open questions returned." />
            )}
          </SectionCard>

          <SectionCard
            title="Possible linked documents"
            subtitle="Hints about adjacent records that could resolve gaps or add context."
          >
            {document.possible_links_to_other_documents.length > 0 ? (
              <div className="signal-stack">
                {document.possible_links_to_other_documents.map((link) => (
                  <LinkCard key={link.link_id} link={link} />
                ))}
              </div>
            ) : (
              <EmptyState label="No related-document hints returned." />
            )}
          </SectionCard>

          {document.warnings.length > 0 ? (
            <WarningList
              title="Document warnings"
              warnings={document.warnings}
            />
          ) : null}
        </div>
      </div>
    </section>
  );
}

function SectionCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-3xl border border-(--line) bg-white/72 px-5 py-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-(--ink-strong)">{title}</h3>
          {subtitle ? (
            <p className="mt-1 text-sm leading-6 text-(--ink-soft)">
              {subtitle}
            </p>
          ) : null}
        </div>
      </div>
      <div className="mt-4">{children}</div>
    </div>
  );
}

function FactGroupTable({ group }: { group: FactGroup }) {
  return (
    <section className="fact-group">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h4 className="text-base font-semibold text-(--ink-strong)">
            {group.title}
          </h4>
          <p className="mt-1 text-sm leading-6 text-(--ink-soft)">
            {group.description}
          </p>
        </div>
        <span className="rounded-full bg-(--accent-muted) px-2.5 py-1 text-xs font-semibold text-(--accent-strong)">
          {group.facts.length} item{group.facts.length === 1 ? "" : "s"}
        </span>
      </div>

      <div className="mt-4 fact-table">
        {group.facts.map((fact) => (
          <FactRow key={fact.fact_id} fact={fact} />
        ))}
      </div>
    </section>
  );
}

function FactRow({ fact }: { fact: ExtractedFact }) {
  const confidenceLabel = formatConfidence(fact.confidence);

  return (
    <article className="fact-row">
      <div>
        <p className="text-sm font-semibold text-(--ink-strong)">
          {cleanText(fact.label)}
        </p>
        {fact.rationale ? (
          <p className="mt-1 text-sm leading-6 text-(--ink-soft)">
            {cleanText(fact.rationale)}
          </p>
        ) : null}
      </div>

      <div className="fact-value-cell">
        <p className="text-base font-semibold text-(--ink-stronger)">
          {cleanText(fact.value)}
          {fact.unit ? (
            <span className="ml-2 text-sm font-medium text-(--ink-soft)">
              {cleanText(fact.unit)}
            </span>
          ) : null}
        </p>
        {confidenceLabel ? <ConfidenceBadge label={confidenceLabel} /> : null}
      </div>

      <EvidenceDetails citations={fact.citations} />
    </article>
  );
}

function RiskCard({ risk }: { risk: RiskOrAnomaly }) {
  const confidenceLabel = formatConfidence(risk.confidence);

  return (
    <article className="signal-card">
      <div className="flex flex-wrap items-center gap-2">
        <p className="font-semibold text-(--ink-strong)">
          {cleanText(risk.title)}
        </p>
        <SeverityBadge severity={risk.severity} />
        {confidenceLabel ? (
          <ConfidenceBadge label={confidenceLabel} muted />
        ) : null}
      </div>
      <p className="mt-2 text-sm leading-6 text-(--ink-soft)">
        {cleanText(risk.description)}
      </p>
      <EvidenceDetails className="mt-3" citations={risk.citations} />
    </article>
  );
}

function QuestionCard({ question }: { question: OpenQuestion }) {
  return (
    <article className="signal-card">
      <p className="font-semibold text-(--ink-strong)">
        {cleanText(question.question)}
      </p>
      <p className="mt-2 text-sm leading-6 text-(--ink-soft)">
        {cleanText(question.reason)}
      </p>
      <EvidenceDetails className="mt-3" citations={question.citations} />
    </article>
  );
}

function LinkCard({ link }: { link: PossibleLink }) {
  const confidenceLabel = formatConfidence(link.confidence);

  return (
    <article className="signal-card">
      <div className="flex flex-wrap items-center gap-2">
        <p className="font-semibold text-(--ink-strong)">
          Linked document hint
        </p>
        {confidenceLabel ? (
          <ConfidenceBadge label={confidenceLabel} muted />
        ) : null}
      </div>
      <p className="mt-2 text-sm leading-6 text-(--ink-soft)">
        {cleanText(link.description)}
      </p>
      <p className="mt-3 rounded-xl border border-(--line) bg-white/80 px-3 py-3 text-sm font-medium leading-6 text-(--ink-strong)">
        {cleanText(link.linked_document_hint)}
      </p>
      <EvidenceDetails className="mt-3" citations={link.citations} />
    </article>
  );
}

function EvidenceDetails({
  citations,
  className = "",
}: {
  citations: Citation[];
  className?: string;
}) {
  if (citations.length === 0) {
    return (
      <p className={`text-sm leading-6 text-(--ink-soft) ${className}`.trim()}>
        No citation returned for this item.
      </p>
    );
  }

  const visibleCitations = citations.slice(0, 3);

  return (
    <details className={`evidence-disclosure ${className}`.trim()}>
      <summary>
        <span>Evidence</span>
        <span className="evidence-count">
          {citations.length} citation{citations.length === 1 ? "" : "s"}
        </span>
      </summary>

      <div className="evidence-list">
        {visibleCitations.map((citation, index) => (
          <article
            key={`${citation.document_id}-${citation.page_number}-${citation.chunk_id ?? index}`}
            className="evidence-item"
          >
            <p className="evidence-meta">{formatCitationLocation(citation)}</p>
            {citation.quote_text ? (
              <p className="evidence-quote">
                {truncate(cleanText(citation.quote_text), 340)}
              </p>
            ) : null}
            {citation.chunk_id || citation.block_index !== null ? (
              <p className="text-xs text-(--ink-soft)">
                {citation.chunk_id ? `Chunk ${citation.chunk_id}` : ""}
                {citation.chunk_id && citation.block_index !== null
                  ? " • "
                  : ""}
                {citation.block_index !== null
                  ? `Block ${citation.block_index}`
                  : ""}
              </p>
            ) : null}
          </article>
        ))}

        {citations.length > visibleCitations.length ? (
          <p className="text-xs text-(--ink-soft)">
            Showing the first {visibleCitations.length} citations.
          </p>
        ) : null}
      </div>
    </details>
  );
}

function InlineEvidenceSummary({
  citations,
  className = "",
  dark = false,
}: {
  citations: Citation[];
  className?: string;
  dark?: boolean;
}) {
  return (
    <p
      className={`text-xs font-medium uppercase tracking-[0.18em] ${
        dark ? "text-white/48" : "text-(--ink-soft)"
      } ${className}`.trim()}
    >
      {citations.length} citation{citations.length === 1 ? "" : "s"} supporting
      this finding
    </p>
  );
}

function WarningList({
  title,
  warnings,
  className = "",
}: {
  title: string;
  warnings: string[];
  className?: string;
}) {
  return (
    <div
      className={`rounded-2xl border border-amber-200 bg-amber-50 px-4 py-4 ${className}`.trim()}
    >
      <p className="text-sm font-semibold text-amber-900">{title}</p>
      <ul className="mt-2 space-y-2 text-sm leading-6 text-amber-800">
        {warnings.map((warning) => (
          <li key={warning}>{cleanText(warning)}</li>
        ))}
      </ul>
    </div>
  );
}

function TextList({
  title,
  items,
  dark = false,
  className = "",
}: {
  title?: string;
  items: string[];
  dark?: boolean;
  className?: string;
}) {
  const textClassName = dark ? "text-white/76" : "text-(--ink-soft)";

  return (
    <div className={className}>
      {title ? (
        <p
          className={`text-sm font-semibold ${dark ? "text-white" : "text-(--ink-strong)"}`}
        >
          {title}
        </p>
      ) : null}
      <ul className={`mt-2 space-y-2 text-sm leading-6 ${textClassName}`}>
        {items.map((item) => (
          <li key={item}>{cleanText(item)}</li>
        ))}
      </ul>
    </div>
  );
}

function EmptyState({ label }: { label: string }) {
  return (
    <p className="rounded-2xl border border-(--line) bg-(--paper) px-4 py-4 text-sm text-(--ink-soft)">
      {label}
    </p>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const normalized = severity.toLowerCase();
  const className =
    normalized === "high"
      ? "bg-red-100 text-red-700"
      : normalized === "medium"
        ? "bg-amber-100 text-amber-800"
        : "bg-emerald-100 text-emerald-700";

  return (
    <span
      className={`rounded-full px-2.5 py-1 text-xs font-semibold uppercase ${className}`}
    >
      {severity}
    </span>
  );
}

function ConfidenceBadge({
  label,
  muted = false,
  dark = false,
}: {
  label: string;
  muted?: boolean;
  dark?: boolean;
}) {
  const className = dark
    ? "border border-white/10 bg-white/8 text-white/78"
    : muted
      ? "bg-(--surface-muted) text-(--ink-soft)"
      : "bg-(--accent-muted) text-(--accent-strong)";

  return (
    <span
      className={`rounded-full px-2.5 py-1 text-xs font-semibold ${className}`}
    >
      {label}
    </span>
  );
}

function SummaryPill({
  label,
  subtle = false,
}: {
  label: string;
  subtle?: boolean;
}) {
  return (
    <span
      className={`rounded-full border px-3 py-1.5 text-xs font-medium ${
        subtle
          ? "border-(--line) bg-white/72 text-(--ink-soft)"
          : "border-white/10 bg-white/8 text-white/78"
      }`}
    >
      {cleanText(label)}
    </span>
  );
}

function AsideCard({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="report-aside-card">
      <p className="report-aside-kicker">{eyebrow}</p>
      <h3>{title}</h3>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function MetricCard({
  label,
  value,
  small = false,
  dark = false,
}: {
  label: string;
  value: string;
  small?: boolean;
  dark?: boolean;
}) {
  return (
    <div
      className={`rounded-[1.25rem] border px-4 py-4 ${
        dark ? "border-white/10 bg-white/6" : "border-white/50 bg-white/55"
      }`}
    >
      <p
        className={`text-xs uppercase tracking-[0.25em] ${dark ? "text-white/48" : "text-(--ink-soft)"}`}
      >
        {label}
      </p>
      <p
        className={`mt-2 font-semibold ${dark ? "text-white" : "text-(--ink-strong)"} ${
          small ? "break-all text-sm" : "text-3xl"
        }`}
      >
        {value}
      </p>
    </div>
  );
}

function ReportMarkdownView({ markdown }: { markdown: string }) {
  return (
    <article className="report-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={reportMarkdownComponents}
      >
        {markdown}
      </ReactMarkdown>
    </article>
  );
}

function isGenerateReportResponse(
  value: unknown,
): value is GenerateReportResponse {
  if (!value || typeof value !== "object") {
    return false;
  }

  return (
    "report_markdown" in value &&
    typeof value.report_markdown === "string" &&
    "documents" in value &&
    Array.isArray(value.documents)
  );
}

function countTotalFacts(documents: ReportDocumentSummary[]) {
  return documents.reduce(
    (total, document) => total + document.extracted_facts.length,
    0,
  );
}

function countTotalRisks(documents: ReportDocumentSummary[]) {
  return documents.reduce(
    (total, document) => total + document.risks_or_anomalies.length,
    0,
  );
}

function countTotalQuestions(documents: ReportDocumentSummary[]) {
  return documents.reduce(
    (total, document) => total + document.open_questions.length,
    0,
  );
}

function getHeadlineFacts(facts: ExtractedFact[]) {
  return facts
    .filter((fact) => fact.fact_type === "lab_result")
    .slice(0, 3)
    .map((fact) =>
      cleanText(
        `${fact.label}: ${fact.value}${fact.unit ? ` ${cleanText(fact.unit)}` : ""}`,
      ),
    );
}

function groupFactsByType(facts: ExtractedFact[]): FactGroup[] {
  const groups = new Map<string, ExtractedFact[]>();

  for (const fact of facts) {
    const key = fact.fact_type || "other";
    const current = groups.get(key) ?? [];
    current.push(fact);
    groups.set(key, current);
  }

  return Array.from(groups.entries())
    .sort(([left], [right]) => compareFactTypeOrder(left, right))
    .map(([key, groupFacts]) => {
      const meta = FACT_TYPE_META[key] ?? {
        title: humanizeToken(key),
        description: "Other grounded details extracted from the document.",
      };

      return {
        key,
        title: meta.title,
        description: meta.description,
        facts: groupFacts,
      };
    });
}

function compareFactTypeOrder(left: string, right: string) {
  const leftIndex = FACT_TYPE_ORDER.indexOf(left);
  const rightIndex = FACT_TYPE_ORDER.indexOf(right);

  if (leftIndex === -1 && rightIndex === -1) {
    return left.localeCompare(right);
  }

  if (leftIndex === -1) {
    return 1;
  }

  if (rightIndex === -1) {
    return -1;
  }

  return leftIndex - rightIndex;
}

function formatDocumentReference(reference: DocumentReference) {
  return cleanText(reference.file_name || reference.document_id);
}

function formatCitationLocation(citation: Citation) {
  return [
    cleanText(citation.file_name || citation.document_id),
    `p.${citation.page_number}`,
  ].join(" • ");
}

function humanizeToken(value: string) {
  return cleanText(value.replaceAll("_", " ")).replace(/\b\w/g, (character) =>
    character.toUpperCase(),
  );
}

function formatFileSize(sizeInBytes: number) {
  if (sizeInBytes < 1024 * 1024) {
    return `${(sizeInBytes / 1024).toFixed(1)} KB`;
  }

  return `${(sizeInBytes / (1024 * 1024)).toFixed(2)} MB`;
}

function formatConfidence(confidence: number | null | undefined) {
  if (typeof confidence !== "number") {
    return null;
  }

  return `${Math.round(confidence * 100)}% confidence`;
}

function truncate(value: string, maxLength: number) {
  if (value.length <= maxLength) {
    return value;
  }

  return `${value.slice(0, maxLength - 3).trimEnd()}...`;
}

function cleanText(value: string | null | undefined) {
  return (value || "")
    .replaceAll("â€”", "-")
    .replaceAll("â€¢", "-")
    .replaceAll("Âµ", "u")
    .replaceAll("â€™", "'")
    .replaceAll("â€˜", "'")
    .replaceAll("â€œ", '"')
    .replaceAll("â€\u009d", '"')
    .replaceAll("â€", '"')
    .replaceAll("â—„", "")
    .replaceAll("ï¿½", "")
    .replace(/\s+/g, " ")
    .trim();
}
