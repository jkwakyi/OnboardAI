"""Mounts the four API groups under the /api base path.

The Interface Contracts define exactly nine endpoints across these four
groups. The groups are declared here so every later ticket adds its endpoint
in one agreed place; the endpoints themselves arrive with their own tickets.
"""

from fastapi import APIRouter

from app.api import auth, chat, documents, escalations

api_router = APIRouter(prefix="/api")

api_router.include_router(auth.router)
api_router.include_router(documents.router)
api_router.include_router(chat.router)
api_router.include_router(escalations.router)
