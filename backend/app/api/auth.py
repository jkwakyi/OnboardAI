"""Login API.

Contract: POST /api/auth/login. Implemented in ON-13 / ON-36.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])
