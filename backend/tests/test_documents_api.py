"""POST /api/documents (ON-39).

The endpoint through a real HTTP client, against a throwaway database and
a throwaway File Storage directory. The role rule itself belongs to Auth
Check and is tested in `test_auth_check.py`; what is checked here is that
this endpoint sits behind it, and that a file and its row either both
exist or neither does.
"""

import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.api.auth_check import BEARER
from app.config import get_settings
from app.db.models import Document, User
from app.db.session import get_session
from app.main import create_app
from app.services.auth import ensure_account, issue_token

DOCUMENTS = "/api/documents"
PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n%%EOF\n"
TXT_BYTES = b"Employees are enrolled in the medical plan on their first day.\n"


@pytest.fixture
def storage(tmp_path, monkeypatch):
    directory = tmp_path / "documents"
    monkeypatch.setenv("FILE_STORAGE_DIR", str(directory))
    get_settings.cache_clear()
    yield directory
    get_settings.cache_clear()


@pytest.fixture
def accounts(auth_env, db_session):
    for email, name, role in (
        ("employee@onboardai.example", "Alex Rivera", "employee"),
        ("hr@onboardai.example", "Jordan Blake", "hr_administrator"),
    ):
        ensure_account(
            db_session, email=email, full_name=name, role=role, password="a development password"
        )
    return {user.role: user for user in db_session.scalars(select(User)).all()}


@pytest.fixture
def api(auth_env, db_session, storage, accounts):
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as client:
        yield client


def headers_for(accounts, role: str) -> dict[str, str]:
    user = accounts[role]
    token = issue_token(user.id, email=user.email, full_name=user.full_name, role=user.role)
    return {"Authorization": f"{BEARER} {token}"}


def upload(
    api,
    accounts,
    data: bytes,
    *,
    name="handbook.pdf",
    kind="application/pdf",
    role="hr_administrator",
):
    return api.post(
        DOCUMENTS,
        files={"file": (name, io.BytesIO(data), kind)},
        headers=headers_for(accounts, role),
    )


# --- the happy path ----------------------------------------------------


def test_an_hr_administrator_can_upload_a_pdf(api, accounts, db_session, storage):
    response = upload(api, accounts, PDF_BYTES)

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "handbook.pdf"
    assert body["content_type"] == "pdf"
    assert body["size_bytes"] == len(PDF_BYTES)
    assert body["id"] > 0

    document = db_session.scalars(select(Document)).one()
    assert document.uploaded_by_id == accounts["hr_administrator"].id


def test_the_original_file_is_in_file_storage(api, accounts, db_session, storage):
    """U2: the original is kept, byte for byte."""
    upload(api, accounts, PDF_BYTES)

    document = db_session.scalars(select(Document)).one()
    from pathlib import Path

    assert Path(document.stored_path).read_bytes() == PDF_BYTES


def test_a_text_document_can_be_uploaded_too(api, accounts):
    response = upload(api, accounts, TXT_BYTES, name="policy.txt", kind="text/plain")

    assert response.status_code == 201
    assert response.json()["content_type"] == "txt"


def test_the_response_does_not_say_where_the_file_is_on_disk(api, accounts):
    """A path in a response is a path somebody will eventually request."""
    body = upload(api, accounts, PDF_BYTES).json()

    assert set(body) == {"id", "filename", "content_type", "size_bytes", "uploaded_at"}


def test_two_uploads_are_two_documents(api, accounts, db_session):
    upload(api, accounts, PDF_BYTES)
    upload(api, accounts, PDF_BYTES)

    assert len(db_session.scalars(select(Document)).all()) == 2


# --- who may upload ----------------------------------------------------


def test_an_employee_cannot_upload(api, accounts, db_session):
    response = upload(api, accounts, PDF_BYTES, role="employee")

    assert response.status_code == 403
    assert db_session.scalars(select(Document)).all() == []


def test_an_upload_with_no_token_is_refused(api):
    response = api.post(
        DOCUMENTS, files={"file": ("h.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}
    )

    assert response.status_code == 401


def test_a_token_naming_an_account_that_is_gone_is_refused(api, accounts, db_session, storage):
    """A token outlives the account it names (TD-19). The foreign key would
    catch it too, far less legibly and after the file was written."""
    token = issue_token(
        9999, email="ghost@onboardai.example", full_name="Ghost", role="hr_administrator"
    )

    response = api.post(
        DOCUMENTS,
        files={"file": ("handbook.pdf", io.BytesIO(PDF_BYTES), "application/pdf")},
        headers={"Authorization": f"{BEARER} {token}"},
    )

    assert response.status_code == 401
    assert db_session.scalars(select(Document)).all() == []
    assert not storage.exists() or list(storage.glob("*")) == []


# --- refusals ----------------------------------------------------------


def test_a_file_that_is_not_a_pdf_or_txt_is_a_415(api, accounts, db_session):
    response = upload(api, accounts, b"\x89PNG\r\n\x1a\n", name="logo.png", kind="image/png")

    assert response.status_code == 415
    assert "PDF and TXT" in response.json()["detail"]
    assert db_session.scalars(select(Document)).all() == []


def test_a_file_pretending_to_be_a_pdf_is_a_415(api, accounts):
    response = upload(api, accounts, b"not a pdf at all", name="handbook.pdf")

    assert response.status_code == 415
    assert "does not contain one" in response.json()["detail"]


def test_an_empty_file_is_a_400(api, accounts):
    assert upload(api, accounts, b"", name="empty.txt", kind="text/plain").status_code == 400


def test_a_file_over_the_limit_is_a_413(api, accounts, monkeypatch, db_session):
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "1024")
    get_settings.cache_clear()

    response = upload(api, accounts, b"x" * 4096, name="big.txt", kind="text/plain")

    assert response.status_code == 413
    assert db_session.scalars(select(Document)).all() == []


def test_a_request_with_no_file_at_all_is_a_422(api, accounts):
    response = api.post(DOCUMENTS, headers=headers_for(accounts, "hr_administrator"))

    assert response.status_code == 422


# --- the file and the row agree ----------------------------------------


def test_a_failed_insert_takes_the_stored_file_with_it(
    api, accounts, db_session, storage, monkeypatch
):
    """Otherwise File Storage fills with documents no row points at, which
    ON-40 would never index and nobody would ever find."""

    def refuse():
        raise OperationalError("INSERT", {}, Exception("no room at the inn"))

    monkeypatch.setattr(db_session, "commit", refuse)

    response = upload(api, accounts, PDF_BYTES)

    assert response.status_code == 500
    assert list(storage.glob("*")) == []


def test_a_refused_upload_leaves_file_storage_empty(api, accounts, storage):
    upload(api, accounts, b"\x89PNG\r\n\x1a\n", name="logo.png", kind="image/png")

    assert not storage.exists() or list(storage.glob("*")) == []


# --- the name -----------------------------------------------------------


def test_the_uploaded_name_is_kept_for_display_but_not_used_as_a_path(api, accounts, db_session):
    upload(api, accounts, PDF_BYTES, name="../../etc/passwd.pdf")

    document = db_session.scalars(select(Document)).one()
    assert document.filename == "passwd.pdf"
    assert ".." not in document.stored_path
