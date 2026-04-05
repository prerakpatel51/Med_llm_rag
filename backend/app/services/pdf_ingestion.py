"""
pdf_ingestion.py – store uploaded PDF documents as session-scoped retrieval data.
"""
from __future__ import annotations

from hashlib import sha1
from io import BytesIO
import re

from pypdf import PdfReader
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.chunker import make_chunks_for_document
from app.ingestion.embedder import embed_batch
from app.models.schemas import UploadedPdfSummary
from app.services.vector_store import save_chunks


def extract_pdf_text(content: bytes) -> str:
    """Extract normalized text from a PDF byte stream."""
    reader = PdfReader(BytesIO(content))
    pages: list[str] = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages.append(page_text.strip())
    text_content = "\n\n".join(pages)
    return re.sub(r"\s+\n", "\n", text_content).strip()


async def store_uploaded_pdf(
    db: AsyncSession,
    session_id: str,
    file_name: str,
    content: bytes,
) -> UploadedPdfSummary:
    """Store a PDF as a session-scoped document and return its summary."""
    digest = sha1(content).hexdigest()
    source_id = f"upload:{session_id}:{digest}"

    existing = await db.execute(
        text("""
            SELECT d.title, COUNT(c.id) AS chunk_count
            FROM documents d
            LEFT JOIN chunks c ON c.document_id = d.id
            WHERE d.source_id = :source_id
            GROUP BY d.id, d.title
        """),
        {"source_id": source_id},
    )
    row = existing.mappings().first()
    if row:
        return UploadedPdfSummary(
            file_name=file_name,
            source_id=source_id,
            chunk_count=row["chunk_count"] or 0,
            size_bytes=len(content),
            title=row["title"] or file_name,
        )

    extracted_text = extract_pdf_text(content)
    if not extracted_text:
        raise ValueError(
            f"'{file_name}' does not contain extractable text. Scanned PDFs without OCR are not supported."
        )

    insert_result = await db.execute(
        text("""
            INSERT INTO documents
                (source, source_id, title, authors, journal, doi, url,
                 published_at, publication_type, trust_score, ingested_at)
            VALUES
                ('upload', :source_id, :title, '', 'Uploaded PDF', '', '',
                 NULL, 'user_upload', 0.60, NOW())
            RETURNING id
        """),
        {
            "source_id": source_id,
            "title": file_name,
        },
    )
    document_id = insert_result.scalar_one()
    await db.commit()

    chunks = make_chunks_for_document(
        document_id=document_id,
        text=extracted_text,
        source="upload",
        source_id=source_id,
        trust_score=0.60,
    )

    if chunks:
        embeddings = embed_batch([chunk["content"] for chunk in chunks])
        for chunk, embedding in zip(chunks, embeddings):
            chunk["embedding"] = embedding
        await save_chunks(db, chunks)

    return UploadedPdfSummary(
        file_name=file_name,
        source_id=source_id,
        chunk_count=len(chunks),
        size_bytes=len(content),
        title=file_name,
    )
