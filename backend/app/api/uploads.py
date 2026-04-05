"""
uploads.py – ingest session-scoped PDF uploads for retrieval.
"""
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.config import get_settings
from app.models.database import AsyncSessionLocal
from app.models.schemas import PdfUploadResponse
from app.services.pdf_ingestion import store_uploaded_pdf

router = APIRouter()
settings = get_settings()


@router.post("/api/v1/uploads/pdfs", response_model=PdfUploadResponse, tags=["uploads"])
async def upload_pdfs(
    session_id: str = Form(...),
    files: list[UploadFile] = File(...),
):
    """Upload up to five PDFs totaling at most 40 MB for session-scoped retrieval."""
    if not files:
        raise HTTPException(status_code=400, detail="At least one PDF is required.")
    if len(files) > settings.max_pdf_upload_files:
        raise HTTPException(
            status_code=400,
            detail=f"You can upload at most {settings.max_pdf_upload_files} PDFs at a time.",
        )

    uploaded = []
    total_bytes = 0
    file_payloads: list[tuple[str, bytes]] = []

    for file in files:
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF files are supported.")

        content = await file.read()
        total_bytes += len(content)
        if total_bytes > settings.max_pdf_upload_bytes:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Combined upload size exceeds {settings.max_pdf_upload_bytes // (1024 * 1024)} MB."
                ),
            )
        file_payloads.append((file.filename, content))
        await file.close()

    async with AsyncSessionLocal() as db:
        for file_name, content in file_payloads:
            try:
                uploaded.append(await store_uploaded_pdf(db, session_id, file_name, content))
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

    return PdfUploadResponse(session_id=session_id, uploaded=uploaded)
