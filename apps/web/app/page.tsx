"use client";

import { useState } from "react";
import type { ChangeEvent, FormEvent } from "react";

type PageBlock = {
  block_type: string;
  text: string;
};

type ParsedPage = {
  page_number: number;
  text: string;
  blocks: PageBlock[];
};

type ParseResponse = {
  ok: boolean;
  document_id: string;
  file_name: string;
  source_path: string;
  artifacts: {
    markdown?: string;
    text?: string;
    json?: unknown;
  };
  pages: ParsedPage[];
  meta: Record<string, unknown>;
};

type ErrorResponse = {
  detail?: string;
};

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function Home() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [result, setResult] = useState<ParseResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const warnings = getWarnings(result?.meta);
  const responsePreview = getSnippet(result, 4000);

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const nextFile = event.target.files?.[0] ?? null;
    setSelectedFile(nextFile);
    setError(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!selectedFile) {
      setError("Select a PDF before uploading.");
      return;
    }

    const formData = new FormData();
    formData.append("file", selectedFile);

    setIsSubmitting(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/documents/parse`, {
        method: "POST",
        body: formData,
      });

      const payload: unknown = await response.json();

      if (!response.ok) {
        const message = getErrorMessage(payload);
        throw new Error(message);
      }

      if (!isParseResponse(payload)) {
        throw new Error("API returned an unexpected response shape.");
      }

      setResult(payload);
    } catch (submitError) {
      const message =
        submitError instanceof Error
          ? submitError.message
          : "Unexpected error while parsing the PDF.";
      setResult(null);
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen px-5 py-8 sm:px-8 lg:px-12">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-8">
        <section className="hero-panel overflow-hidden rounded-4xl border border-white/50">
          <div className="grid gap-8 p-6 sm:p-8 lg:grid-cols-[1.15fr_0.85fr] lg:p-10">
            <div className="space-y-5">
              <p className="text-xs font-semibold uppercase tracking-[0.35em] text-[var(--accent-strong)]">
                Docling Parser Lab
              </p>
              <div className="space-y-4">
                <h1 className="max-w-3xl text-4xl font-semibold tracking-[-0.05em] text-[var(--ink-strong)] sm:text-5xl lg:text-6xl">
                  Upload one PDF and inspect exactly what the parser extracted.
                </h1>
                <p className="max-w-2xl text-sm leading-7 text-[var(--ink-soft)] sm:text-base">
                  This screen sends the file to your API, waits for the Docling
                  wrapper response, then renders raw artifacts, page text, block
                  slices, and parser metadata side by side.
                </p>
              </div>
              <div className="flex flex-wrap gap-3 text-xs font-medium text-[var(--ink-soft)]">
                <span className="rounded-full border border-[var(--line)] bg-white/70 px-3 py-2">
                  API: {API_BASE_URL}
                </span>
                <span className="rounded-full border border-[var(--line)] bg-white/70 px-3 py-2">
                  Accepted: PDF only
                </span>
              </div>
            </div>

            <form
              onSubmit={handleSubmit}
              className="glass-panel flex flex-col gap-5 rounded-[1.75rem] p-5 sm:p-6"
            >
              <div className="space-y-2">
                <p className="text-sm font-semibold uppercase tracking-[0.25em] text-[var(--accent-strong)]">
                  Upload
                </p>
                <h2 className="text-2xl font-semibold tracking-[-0.03em] text-[var(--ink-strong)]">
                  Send a sample PDF
                </h2>
              </div>

              <label className="upload-zone cursor-pointer rounded-[1.5rem] border border-dashed border-[var(--accent)] p-5 text-left transition-transform duration-200 hover:-translate-y-0.5">
                <input
                  type="file"
                  accept="application/pdf,.pdf"
                  className="hidden"
                  onChange={handleFileChange}
                />
                <span className="mb-3 inline-flex rounded-full bg-[var(--accent)]/12 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--accent-strong)]">
                  Choose file
                </span>
                <p className="text-lg font-medium text-[var(--ink-strong)]">
                  {selectedFile ? selectedFile.name : "Drop in a PDF or browse"}
                </p>
                <p className="mt-2 text-sm text-[var(--ink-soft)]">
                  {selectedFile
                    ? `${Math.max(selectedFile.size / 1024, 1).toFixed(1)} KB selected`
                    : "The parser returns markdown, text, JSON, pages, and metadata."}
                </p>
              </label>

              <button
                type="submit"
                disabled={isSubmitting}
                className="rounded-full bg-[var(--ink-strong)] px-5 py-3 text-sm font-semibold text-white transition duration-200 hover:bg-[var(--accent-strong)] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isSubmitting ? "Parsing PDF..." : "Upload and parse"}
              </button>

              {error ? (
                <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
                  {error}
                </div>
              ) : null}

              {warnings.length > 0 ? (
                <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                  <p className="font-semibold">Warnings</p>
                  <ul className="mt-2 space-y-1">
                    {warnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </form>
          </div>
        </section>

        <section className="grid gap-6 lg:grid-cols-[0.95fr_1.05fr]">
          <div className="space-y-6">
            <article className="glass-panel rounded-[1.75rem] p-5 sm:p-6">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.28em] text-[var(--accent-strong)]">
                    Summary
                  </p>
                  <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-[var(--ink-strong)]">
                    Parse result
                  </h2>
                </div>
                <span className="rounded-full border border-[var(--line)] bg-white/70 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.18em] text-[var(--ink-soft)]">
                  {result?.ok ? "Success" : "Waiting"}
                </span>
              </div>

              {result ? (
                <dl className="mt-5 grid gap-3 text-sm text-[var(--ink-soft)]">
                  <MetaRow label="Document ID" value={result.document_id} />
                  <MetaRow label="File" value={result.file_name} />
                  <MetaRow label="Pages" value={String(result.pages.length)} />
                  <MetaRow
                    label="Artifacts"
                    value={Object.keys(result.artifacts).join(", ") || "None"}
                  />
                </dl>
              ) : (
                <p className="mt-5 text-sm leading-7 text-[var(--ink-soft)]">
                  Upload a PDF to populate parsed metadata and extracted
                  content.
                </p>
              )}
            </article>

            <article className="glass-panel rounded-[1.75rem] p-5 sm:p-6">
              <p className="text-xs font-semibold uppercase tracking-[0.28em] text-[var(--accent-strong)]">
                Pages
              </p>
              <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-[var(--ink-strong)]">
                Extracted page slices
              </h2>

              <div className="mt-5 space-y-4">
                {result?.pages.length ? (
                  result.pages.map((page) => (
                    <article
                      key={page.page_number}
                      className="rounded-[1.4rem] border border-[var(--line)] bg-white/72 p-4"
                    >
                      <div className="flex items-center justify-between gap-4">
                        <h3 className="text-base font-semibold text-[var(--ink-strong)]">
                          Page {page.page_number}
                        </h3>
                        <span className="text-xs uppercase tracking-[0.18em] text-[var(--ink-soft)]">
                          {page.blocks.length} blocks
                        </span>
                      </div>
                      <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-[var(--ink-soft)]">
                        {page.text || "No page text returned."}
                      </p>
                      {page.blocks.length > 0 ? (
                        <div className="mt-4 flex flex-col gap-2">
                          {page.blocks.slice(0, 8).map((block, index) => (
                            <div
                              key={`${page.page_number}-${index}-${block.block_type}`}
                              className="rounded-2xl bg-[var(--paper)] px-3 py-3"
                            >
                              <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-[var(--accent-strong)]">
                                {block.block_type}
                              </p>
                              <p className="mt-1 text-sm leading-6 text-[var(--ink-soft)]">
                                {block.text}
                              </p>
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </article>
                  ))
                ) : (
                  <p className="text-sm leading-7 text-[var(--ink-soft)]">
                    No extracted pages yet.
                  </p>
                )}
              </div>
            </article>
          </div>

          <div className="space-y-6">
            <ArtifactPanel
              title="Parse response"
              description="Snippet of the full JSON payload returned by the API."
              content={responsePreview}
              emptyLabel="The returned parse response will appear here."
            />
            <ArtifactPanel
              title="Metadata"
              description="Parser metadata, warnings, and artifact inventory."
              content={result?.meta ? JSON.stringify(result.meta, null, 2) : ""}
              emptyLabel="Metadata will appear here."
            />
            <ArtifactPanel
              title="Markdown"
              description="Raw markdown exported by Docling."
              content={result?.artifacts.markdown ?? ""}
              emptyLabel="Markdown output will appear here."
            />
            <ArtifactPanel
              title="Plain text"
              description="Text export from the parser boundary."
              content={result?.artifacts.text ?? ""}
              emptyLabel="Plain text output will appear here."
            />
            <ArtifactPanel
              title="Raw JSON"
              description="Structured export returned by the parser."
              content={
                result?.artifacts.json
                  ? JSON.stringify(result.artifacts.json, null, 2)
                  : ""
              }
              emptyLabel="JSON export will appear here."
            />
          </div>
        </section>
      </div>
    </main>
  );
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-2xl bg-white/70 px-4 py-3">
      <dt className="font-medium text-[var(--ink-strong)]">{label}</dt>
      <dd className="max-w-[60%] text-right text-[var(--ink-soft)]">{value}</dd>
    </div>
  );
}

function ArtifactPanel({
  title,
  description,
  content,
  emptyLabel,
}: {
  title: string;
  description: string;
  content: string;
  emptyLabel: string;
}) {
  return (
    <article className="glass-panel rounded-[1.75rem] p-5 sm:p-6">
      <p className="text-xs font-semibold uppercase tracking-[0.28em] text-[var(--accent-strong)]">
        {title}
      </p>
      <p className="mt-2 text-sm leading-6 text-[var(--ink-soft)]">
        {description}
      </p>
      <pre className="code-panel mt-4 overflow-x-auto rounded-[1.25rem] p-4 text-xs leading-6 text-white">
        {content || emptyLabel}
      </pre>
    </article>
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isParseResponse(value: unknown): value is ParseResponse {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.ok === "boolean" &&
    typeof value.document_id === "string" &&
    typeof value.file_name === "string" &&
    typeof value.source_path === "string" &&
    isRecord(value.artifacts) &&
    Array.isArray(value.pages) &&
    isRecord(value.meta)
  );
}

function getErrorMessage(payload: unknown): string {
  if (!isRecord(payload)) {
    return "Upload failed.";
  }

  const detail = (payload as ErrorResponse).detail;
  return typeof detail === "string" && detail.trim()
    ? detail
    : "Upload failed.";
}

function getWarnings(meta: Record<string, unknown> | undefined): string[] {
  const candidate = meta?.warnings;
  if (!Array.isArray(candidate)) {
    return [];
  }

  return candidate.filter(
    (warning): warning is string => typeof warning === "string",
  );
}

function getSnippet(value: unknown, maxLength: number): string {
  if (value === null || value === undefined) {
    return "";
  }

  const serialized = JSON.stringify(value, null, 2);
  if (!serialized) {
    return "";
  }

  if (serialized.length <= maxLength) {
    return serialized;
  }

  return `${serialized.slice(0, maxLength)}\n... [truncated ${serialized.length - maxLength} chars]`;
}
