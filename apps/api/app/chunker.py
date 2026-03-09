from __future__ import annotations

from collections.abc import Iterable

from app.schemas import (
    BlockCitation,
    EvidenceChunk,
    NormalizedBlock,
    NormalizedDocument,
    NormalizedPage,
)

MERGEABLE_BLOCK_TYPES = {
    "caption",
    "footnote",
    "list",
    "list_item",
    "paragraph",
    "text",
}
HEADING_BLOCK_TYPES = {
    "header",
    "heading",
    "section_header",
    "section_title",
    "subheading",
    "subtitle",
    "title",
}
MAX_MERGED_TEXT_LENGTH = 900
MAX_SINGLE_BLOCK_LENGTH = 600
MAX_QUOTE_TEXT_LENGTH = 240


def chunk_document(doc: NormalizedDocument) -> list[EvidenceChunk]:
    chunks: list[EvidenceChunk] = []

    for page in doc.pages:
        page_chunks = _chunk_page(doc, page)
        chunks.extend(page_chunks)

    return chunks


def _chunk_page(doc: NormalizedDocument, page: NormalizedPage) -> list[EvidenceChunk]:
    usable_blocks = [block for block in page.blocks if _has_meaningful_text(block.text)]
    if not usable_blocks:
        fallback_chunk = _build_page_fallback_chunk(doc, page, chunk_number=1)
        return [fallback_chunk] if fallback_chunk is not None else []

    chunks: list[EvidenceChunk] = []
    pending_blocks: list[NormalizedBlock] = []
    current_section_title: str | None = None
    chunk_number = 1

    for block in usable_blocks:
        section_title = _resolve_section_title(block, current_section_title)

        if _is_heading_block(block):
            if pending_blocks:
                chunks.append(
                    _build_chunk(
                        doc=doc,
                        page=page,
                        chunk_number=chunk_number,
                        blocks=pending_blocks,
                        section_title=current_section_title,
                    )
                )
                chunk_number += 1
                pending_blocks = []

            current_section_title = _clean_text(block.text)
            continue

        if _is_table_block(block):
            if pending_blocks:
                chunks.append(
                    _build_chunk(
                        doc=doc,
                        page=page,
                        chunk_number=chunk_number,
                        blocks=pending_blocks,
                        section_title=current_section_title,
                    )
                )
                chunk_number += 1
                pending_blocks = []

            chunks.append(
                _build_chunk(
                    doc=doc,
                    page=page,
                    chunk_number=chunk_number,
                    blocks=[block],
                    section_title=section_title,
                )
            )
            chunk_number += 1
            continue

        if pending_blocks and not _should_merge_blocks(pending_blocks, block):
            chunks.append(
                _build_chunk(
                    doc=doc,
                    page=page,
                    chunk_number=chunk_number,
                    blocks=pending_blocks,
                    section_title=current_section_title,
                )
            )
            chunk_number += 1
            pending_blocks = []

        pending_blocks.append(block)
        current_section_title = section_title

    if pending_blocks:
        chunks.append(
            _build_chunk(
                doc=doc,
                page=page,
                chunk_number=chunk_number,
                blocks=pending_blocks,
                section_title=current_section_title,
            )
        )
        chunk_number += 1

    if not chunks:
        heading_only_chunk = _build_heading_only_chunk(
            doc=doc,
            page=page,
            chunk_number=chunk_number,
            blocks=usable_blocks,
        )
        if heading_only_chunk is not None:
            return [heading_only_chunk]

        fallback_chunk = _build_page_fallback_chunk(doc, page, chunk_number=chunk_number)
        return [fallback_chunk] if fallback_chunk is not None else []

    return chunks


def _build_page_fallback_chunk(
    doc: NormalizedDocument,
    page: NormalizedPage,
    chunk_number: int,
) -> EvidenceChunk | None:
    text = _clean_text(page.text)
    if not text:
        return None

    chunk_id = _build_chunk_id(doc.document_id, page.page_number, chunk_number)
    citation = BlockCitation(
        document_id=doc.document_id,
        file_name=doc.file_name,
        page_number=page.page_number,
        block_index=None,
        chunk_id=chunk_id,
        quote_text=_quote_text(text),
    )
    return EvidenceChunk(
        chunk_id=chunk_id,
        document_id=doc.document_id,
        file_name=doc.file_name,
        page_number=page.page_number,
        block_index=None,
        text=text,
        block_types=[],
        section_title=None,
        contains_table=page.contains_table,
        citation=citation,
    )


def _build_heading_only_chunk(
    doc: NormalizedDocument,
    page: NormalizedPage,
    chunk_number: int,
    blocks: list[NormalizedBlock],
) -> EvidenceChunk | None:
    heading_blocks = [block for block in blocks if _is_heading_block(block)]
    if not heading_blocks:
        return None

    return _build_chunk(
        doc=doc,
        page=page,
        chunk_number=chunk_number,
        blocks=heading_blocks,
        section_title=_clean_text(heading_blocks[0].text),
    )


def _build_chunk(
    doc: NormalizedDocument,
    page: NormalizedPage,
    chunk_number: int,
    blocks: list[NormalizedBlock],
    section_title: str | None,
) -> EvidenceChunk:
    text = "\n\n".join(_clean_text(block.text) for block in blocks if _has_meaningful_text(block.text))
    first_block = blocks[0]
    chunk_id = _build_chunk_id(doc.document_id, page.page_number, chunk_number)

    citation = BlockCitation(
        document_id=doc.document_id,
        file_name=doc.file_name,
        page_number=page.page_number,
        block_index=first_block.block_index,
        chunk_id=chunk_id,
        quote_text=_quote_text(text),
    )

    return EvidenceChunk(
        chunk_id=chunk_id,
        document_id=doc.document_id,
        file_name=doc.file_name,
        page_number=page.page_number,
        block_index=first_block.block_index,
        text=text,
        block_types=_unique_preserving_order(block.block_type for block in blocks),
        section_title=section_title,
        contains_table=any(block.contains_table for block in blocks),
        citation=citation,
    )


def _should_merge_blocks(
    pending_blocks: list[NormalizedBlock],
    next_block: NormalizedBlock,
) -> bool:
    if _is_table_block(next_block) or _is_heading_block(next_block):
        return False

    if not all(_is_mergeable_text_block(block) for block in pending_blocks):
        return False

    if not _is_mergeable_text_block(next_block):
        return False

    current_text = "\n\n".join(_clean_text(block.text) for block in pending_blocks)
    next_text = _clean_text(next_block.text)

    if len(next_text) > MAX_SINGLE_BLOCK_LENGTH:
        return False

    return len(current_text) + len(next_text) + 2 <= MAX_MERGED_TEXT_LENGTH


def _resolve_section_title(
    block: NormalizedBlock,
    current_section_title: str | None,
) -> str | None:
    if block.section_title:
        return _clean_text(block.section_title)
    if _is_heading_block(block):
        return _clean_text(block.text)
    return current_section_title


def _is_table_block(block: NormalizedBlock) -> bool:
    return block.contains_table or block.block_type.strip().lower() == "table"


def _is_heading_block(block: NormalizedBlock) -> bool:
    block_type = block.block_type.strip().lower()
    if block.heading_level is not None:
        return True
    return block_type in HEADING_BLOCK_TYPES


def _is_mergeable_text_block(block: NormalizedBlock) -> bool:
    if _is_table_block(block) or _is_heading_block(block):
        return False

    block_type = block.block_type.strip().lower()
    return block_type in MERGEABLE_BLOCK_TYPES or block_type.startswith("text")


def _build_chunk_id(document_id: str, page_number: int, chunk_number: int) -> str:
    return f"{document_id}_p{page_number}_c{chunk_number}"


def _has_meaningful_text(text: str) -> bool:
    return bool(_clean_text(text))


def _clean_text(text: str) -> str:
    return "\n".join(line.strip() for line in text.splitlines() if line.strip()).strip()


def _quote_text(text: str) -> str | None:
    normalized = _clean_text(text)
    if not normalized:
        return None
    if len(normalized) <= MAX_QUOTE_TEXT_LENGTH:
        return normalized
    return normalized[: MAX_QUOTE_TEXT_LENGTH - 3].rstrip() + "..."


def _unique_preserving_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)

    return result
