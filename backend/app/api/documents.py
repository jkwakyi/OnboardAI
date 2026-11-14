"""Documents API.

Contract: POST /api/documents, GET /api/documents,
DELETE /api/documents/{id} - all three "Admin Upload Page (HR
administrator)", which Auth Check (ON-14) enforces from its own table
before any of this runs.

POST is ON-39: "A PDF or TXT document in. The original file is saved..."
The rest of that sentence - the text extracted, split into sections, and
turned into vectors - is ON-40 and ON-41, which will hang off the same
endpoint. GET and DELETE are ON-43.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.auth_check import current_claims
from app.config import get_settings
from app.db.models import Document, User
from app.db.session import get_session
from app.services.auth import TokenClaims
from app.services.documents import (
    DocumentTooLarge,
    UnreadableDocument,
    UnsupportedDocument,
    UnusableDocument,
    UploadRefused,
    delete_stored_file,
    index_document,
    save_upload,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

# Which refusal is which status code. The wording belongs to the service -
# it is what an HR administrator reads - and the code belongs here, because
# a status code is part of the HTTP contract rather than part of a message.
REFUSAL_STATUS: dict[type[UploadRefused], int] = {
    DocumentTooLarge: status.HTTP_413_CONTENT_TOO_LARGE,
    UnusableDocument: status.HTTP_400_BAD_REQUEST,
    UnsupportedDocument: status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    # A valid PDF with no text in it. The request was well formed and
    # the file is what it says it is; there is simply nothing in it to
    # answer questions from, which is what 422 is for.
    UnreadableDocument: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


class DocumentResponse(BaseModel):
    """An uploaded document, as the Admin Upload Page lists it.

    Built from the columns ON-11 defined, minus `stored_path`: where a file
    sits on the server's disk is the server's business, and a path in a
    response is a path somebody will eventually try to request.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    content_type: str
    size_bytes: int
    uploaded_at: datetime


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a PDF or TXT document",
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "The file was empty or unnamed."},
        status.HTTP_413_CONTENT_TOO_LARGE: {"description": "The file is too large."},
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {"description": "Only PDF and TXT."},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "No readable text, for example a scanned PDF."
        },
    },
)
def upload_document(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    claims: Annotated[TokenClaims, Depends(current_claims)],
    file: Annotated[UploadFile, File(description="The PDF or TXT document to upload.")],
) -> Document:
    """Save an uploaded document's original file and record it (U1, U2)."""
    settings = get_settings()

    # The token says who this is; the table says whether they still exist.
    # A token outlives the account it names (TD-19), and the documents row
    # has a foreign key that would fail far less legibly than this.
    uploader = session.get(User, claims.user_id)
    if uploader is None:
        logger.warning("token for user %s names an account that is gone", claims.user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This account no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        stored = save_upload(
            file.file,
            filename=file.filename,
            declared_content_type=file.content_type,
            directory=settings.storage_path,
            max_bytes=settings.max_upload_bytes,
        )
    except UploadRefused as refused:
        code = REFUSAL_STATUS.get(type(refused), status.HTTP_400_BAD_REQUEST)
        raise HTTPException(status_code=code, detail=str(refused)) from refused

    document = Document(
        filename=stored.filename,
        content_type=stored.content_type,
        stored_path=str(stored.path),
        size_bytes=stored.size_bytes,
        uploaded_by_id=uploader.id,
    )
    try:
        session.add(document)
        session.commit()
    except SQLAlchemyError:
        # The file is already on disk. Without this the two halves disagree
        # and File Storage slowly fills with documents no row points at -
        # which ON-40 would never index and nobody would ever find.
        session.rollback()
        delete_stored_file(stored.path)
        logger.exception("could not record %s; its stored file was removed", stored.filename)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The document could not be saved. Please try again.",
        ) from None

    # U3: the text is extracted, split into sections and saved. Done here
    # rather than in the background because the contracts show U1 to U4 as
    # one flow, and because an HR administrator who is told the upload
    # worked should be told at the same moment if it cannot be read.
    try:
        sections = index_document(session, document)
    except UploadRefused as refused:
        _discard(session, document, stored.path)
        code = REFUSAL_STATUS.get(type(refused), status.HTTP_400_BAD_REQUEST)
        raise HTTPException(status_code=code, detail=str(refused)) from refused
    except Exception:
        _discard(session, document, stored.path)
        logger.exception("could not index %s; the upload was discarded", stored.filename)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The document could not be read. Please try again.",
        ) from None

    logger.info(
        "user %s uploaded document %s (%s, %d bytes, %d sections)",
        uploader.id,
        document.id,
        document.content_type,
        document.size_bytes,
        len(sections),
    )
    return document


def _discard(session: Session, document: Document, path: Path) -> None:
    """Undo a half-finished upload: no row, no file, no sections.

    A document that was stored but never split is one retrieval can never
    find and the Admin Upload Page would still list - an HR administrator
    would see an approved document that cannot answer a single question.
    Better that the upload failed and they know it.
    """
    session.rollback()
    try:
        session.delete(document)
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        logger.exception("could not remove the record for %s", document.filename)
    delete_stored_file(path)
