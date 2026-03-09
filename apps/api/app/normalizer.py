from __future__ import annotations

from app.schemas import (
    NormalizedBlock,
    NormalizedDocument,
    NormalizedPage,
    RawDoclingDocument,
)


def format_page_citation(file_name: str, page_number: int) -> str:
    return f"{file_name}, Page {page_number}"


def page_text_contains_table(text: str) -> bool:
    stripped_text = text.strip()
    if not stripped_text:
        return False

    lines = [line.strip() for line in stripped_text.splitlines() if line.strip()]
    has_table_row = any(line.startswith("|") and line.endswith("|") for line in lines)
    has_separator_row = any(set(line) <= {"|", "-", ":", " "} and "|" in line for line in lines)
    return has_table_row and has_separator_row


def normalize_document(raw_doc: RawDoclingDocument) -> NormalizedDocument:
    # Pages are the source of truth for normalized content.
    normalized_pages: list[NormalizedPage] = []
    document_contains_table = False

    for raw_page in raw_doc.pages:
        normalized_blocks: list[NormalizedBlock] = []
        page_contains_table = page_text_contains_table(raw_page.text)

        # Preserve the original raw block index for later citations.
        for raw_block_index, raw_block in enumerate(raw_page.blocks):
            if not raw_block.text.strip():
                continue

            contains_table = raw_block.block_type == "table"
            if contains_table:
                page_contains_table = True

            normalized_blocks.append(
                NormalizedBlock(
                    block_id=f"{raw_doc.document_id}_p{raw_page.page_number}_b{raw_block_index + 1}",
                    page_number=raw_page.page_number,
                    block_index=raw_block_index,
                    block_type=raw_block.block_type,
                    text=raw_block.text,
                    contains_table=contains_table,
                )
            )

        normalized_pages.append(
            NormalizedPage(
                page_number=raw_page.page_number,
                text=raw_page.text,
                citation=format_page_citation(raw_doc.file_name, raw_page.page_number),
                blocks=normalized_blocks,
                contains_table=page_contains_table,
            )
        )

        if page_contains_table:
            document_contains_table = True

    document_text = "\n\n".join(page.text for page in normalized_pages if page.text)

    return NormalizedDocument(
        document_id=raw_doc.document_id,
        file_name=raw_doc.file_name,
        source_path=raw_doc.source_path,
        page_count=len(normalized_pages),
        text=document_text,
        pages=normalized_pages,
        contains_table=document_contains_table,
        source_meta=raw_doc.meta,
    )
