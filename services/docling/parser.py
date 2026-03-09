from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any


class DoclingParseError(RuntimeError):
    pass


def safe_call(label: str, fn: Callable[[], Any]) -> tuple[Any | None, str | None]:
    try:
        return fn(), None
    except Exception as exc:  # noqa: BLE001
        return None, f"{label} export failed: {exc}"


def parse_with_docling(file_path: str) -> dict[str, Any]:
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as exc:
        raise DoclingParseError("Docling is not installed") from exc

    converter = DocumentConverter()
    result = converter.convert(file_path)
    doc = getattr(result, "document", result)

    artifacts, artifact_warnings = export_docling_artifacts(doc)
    pages, page_warnings = extract_pages(doc, artifacts)

    meta: dict[str, Any] = {
        "parser": "docling",
        "warnings": artifact_warnings + page_warnings,
        "artifact_keys": sorted(artifacts.keys()),
    }

    doc_meta = _extract_doc_meta(doc, result)
    if doc_meta:
        meta["docling_meta"] = doc_meta
    if pages:
        meta["page_count"] = len(pages)

    return {
        "artifacts": artifacts,
        "pages": pages,
        "meta": meta,
    }


def export_docling_artifacts(doc: Any) -> tuple[dict[str, Any], list[str]]:
    artifacts: dict[str, Any] = {}
    warnings: list[str] = []

    markdown = _try_export(
        doc,
        warnings,
        "markdown",
        ("export_to_markdown", "to_markdown"),
    )
    if isinstance(markdown, str) and markdown:
        artifacts["markdown"] = markdown

    json_artifact = _try_export(
        doc,
        warnings,
        "json",
        ("export_to_dict", "model_dump", "export_to_json", "to_dict"),
    )
    normalized_json = _normalize_json_artifact(json_artifact)
    if normalized_json is not None:
        artifacts["json"] = normalized_json

    text = _try_export(
        doc,
        warnings,
        "text",
        ("export_to_text", "to_text"),
    )
    if isinstance(text, str) and text:
        artifacts["text"] = text

    if not artifacts:
        raise DoclingParseError("Docling export failed for markdown, json, and text")

    return artifacts, warnings


def extract_pages(doc: Any, artifacts: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []

    json_artifact = artifacts.get("json")
    if isinstance(json_artifact, dict):
        pages = _extract_pages_from_json(json_artifact)
        if pages:
            return pages, warnings

    pages_from_doc = _extract_pages_from_doc(doc)
    if pages_from_doc:
        warnings.append("pages derived from document object fallback")
        return pages_from_doc, warnings

    fallback_text = artifacts.get("text")
    if not isinstance(fallback_text, str) or not fallback_text.strip():
        fallback_text = _markdown_to_text(artifacts.get("markdown"))

    warnings.append("pages derived from synthetic single-page fallback")
    return [
        {
            "page_number": 1,
            "text": fallback_text or "",
            "blocks": [],
        }
    ], warnings


def _try_export(
    doc: Any,
    warnings: list[str],
    label: str,
    method_names: tuple[str, ...],
) -> Any | None:
    last_value: Any | None = None
    for method_name in method_names:
        method = getattr(doc, method_name, None)
        if not callable(method):
            continue
        value, warning = safe_call(f"{label}:{method_name}", method)
        if warning:
            warnings.append(warning)
            continue
        last_value = value
        break
    return last_value


def _normalize_json_artifact(value: Any) -> dict[str, Any] | list[Any] | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, (dict, list)):
            return parsed
    return None


def _extract_pages_from_json(data: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = (
        data.get("pages"),
        data.get("document", {}).get("pages") if isinstance(data.get("document"), dict) else None,
    )
    for candidate in candidates:
        pages = _normalize_pages_candidate(candidate)
        if pages:
            return pages
    return []


def _normalize_pages_candidate(candidate: Any) -> list[dict[str, Any]]:
    if not isinstance(candidate, list):
        return []

    pages: list[dict[str, Any]] = []
    for index, raw_page in enumerate(candidate, start=1):
        if not isinstance(raw_page, dict):
            continue
        page_number = raw_page.get("page_number") or raw_page.get("page_no") or raw_page.get("number") or index
        page_text = _extract_text(raw_page) or ""
        raw_blocks = raw_page.get("blocks") or raw_page.get("items") or raw_page.get("children") or []
        blocks = _normalize_blocks(raw_blocks)
        if not page_text and blocks:
            page_text = "\n".join(block["text"] for block in blocks if block["text"]).strip()
        pages.append(
            {
                "page_number": int(page_number),
                "text": page_text,
                "blocks": blocks,
            }
        )
    return pages


def _extract_pages_from_doc(doc: Any) -> list[dict[str, Any]]:
    for attr_name in ("pages", "page_items"):
        candidate = getattr(doc, attr_name, None)
        if isinstance(candidate, list):
            pages: list[dict[str, Any]] = []
            for index, raw_page in enumerate(candidate, start=1):
                if isinstance(raw_page, dict):
                    page_number = raw_page.get("page_number") or raw_page.get("page_no") or index
                    page_text = _extract_text(raw_page) or ""
                    raw_blocks = raw_page.get("blocks") or raw_page.get("items") or []
                    blocks = _normalize_blocks(raw_blocks)
                else:
                    page_number = getattr(raw_page, "page_number", getattr(raw_page, "page_no", index))
                    page_text = _extract_text(raw_page) or ""
                    blocks = _normalize_blocks(getattr(raw_page, "blocks", getattr(raw_page, "items", [])))
                if not page_text and blocks:
                    page_text = "\n".join(block["text"] for block in blocks if block["text"]).strip()
                pages.append(
                    {
                        "page_number": int(page_number),
                        "text": page_text,
                        "blocks": blocks,
                    }
                )
            if pages:
                return pages
    return []


def _normalize_blocks(raw_blocks: Any) -> list[dict[str, str]]:
    if not isinstance(raw_blocks, list):
        return []

    blocks: list[dict[str, str]] = []
    for raw_block in raw_blocks:
        block_text = _extract_text(raw_block)
        if not block_text:
            continue
        blocks.append(
            {
                "block_type": _extract_block_type(raw_block),
                "text": block_text,
            }
        )
    return blocks


def _extract_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("text", "content", "raw_text", "markdown"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()
    else:
        for attr_name in ("text", "content", "raw_text", "markdown"):
            item = getattr(value, attr_name, None)
            if isinstance(item, str) and item.strip():
                return item.strip()
    return ""


def _extract_block_type(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("block_type", "type", "label", "name"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()
    else:
        for attr_name in ("block_type", "type", "label", "name"):
            item = getattr(value, attr_name, None)
            if isinstance(item, str) and item.strip():
                return item.strip()
    return "text"


def _markdown_to_text(markdown: Any) -> str:
    if not isinstance(markdown, str):
        return ""
    text = re.sub(r"[`*_>#-]+", " ", markdown)
    text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_doc_meta(doc: Any, result: Any) -> dict[str, Any]:
    meta: dict[str, Any] = {}

    for attr_name in ("meta", "metadata"):
        candidate = getattr(doc, attr_name, None)
        if isinstance(candidate, dict) and candidate:
            meta.update(candidate)
            break

    result_status = getattr(result, "status", None)
    if result_status is not None:
        meta["status"] = str(result_status)

    return meta
