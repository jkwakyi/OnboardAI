"""Chat API.

Contract: POST /api/chat/ask, POST /api/chat/feedback.
Implemented in ON-17 and the Feedback epic.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/chat", tags=["chat"])
