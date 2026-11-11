"""Documents API.

Contract: POST /api/documents, GET /api/documents,
DELETE /api/documents/{id}. Implemented in ON-15 / ON-39.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/documents", tags=["documents"])
