"""Escalations API.

Contract: POST /api/escalations, GET /api/escalations,
PATCH /api/escalations/{id}. Implemented in the HR escalation epic.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/escalations", tags=["escalations"])
