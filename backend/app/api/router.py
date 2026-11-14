"""Mounts the four API groups under the /api base path.

The Interface Contracts define exactly nine endpoints across these four
groups. The groups are declared here so every later ticket adds its
endpoint in one agreed place; the endpoints themselves arrive with their
own tickets.

Auth Check (ON-14) is attached here rather than to any endpoint. Every
request that reaches `/api` passes through it before the endpoint runs,
which is what the architecture diagram's step 2 says, and it means an
endpoint added next week is checked whether or not whoever adds it
remembers to ask for it.
"""

from fastapi import APIRouter, Depends

from app.api import auth, chat, documents, escalations
from app.api.auth_check import auth_check

api_router = APIRouter(prefix="/api", dependencies=[Depends(auth_check)])

api_router.include_router(auth.router)
api_router.include_router(documents.router)
api_router.include_router(chat.router)
api_router.include_router(escalations.router)
