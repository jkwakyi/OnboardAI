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
from app.config import REPO_ROOT, get_settings
from app.db.models import Document, Section, User
from app.db.session import get_session
from app.main import create_app
from app.services.auth import ensure_account, issue_token

DOCUMENTS = "/api/documents"

# Real handbook documents rather than a stub PDF. Since ON-40 the endpoint
# reads what it stores, so a few bytes that merely begin "%PDF-" are no
# longer a document - they are a 422, correctly.
HANDBOOK = REPO_ROOT / "data" / "handbook"
PDF_BYTES = (HANDBOOK / "pdf" / "05-benefits-and-wellbeing.pdf").read_bytes()
TXT_BYTES = (HANDBOOK / "txt" / "05-benefits-and-wellbeing.txt").read_bytes()


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
def api(auth_env, db_session, storage, accounts, mock_embedding, collection):
    """The endpoint, with U4 pointed at a fake Vector Database.

    Since ON-41 the upload embeds its sections before answering, so without
    `mock_embedding` and `collection` every test here would try to reach
    the paid Embedding API and a running ChromaDB. Tests that care about
    the vectors take the `collection` fixture too and read it directly.
    """
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


# --- the text is extracted and split (ON-40, U3) -----------------------


def test_an_uploaded_document_is_split_into_sections(api, accounts, db_session):
    """U3. Until this, an upload was a file nothing could ever cite."""
    upload(api, accounts, TXT_BYTES, name="benefits.txt", kind="text/plain")

    document = db_session.scalars(select(Document)).one()
    sections = db_session.scalars(
        select(Section).where(Section.document_id == document.id).order_by(Section.position)
    ).all()

    assert len(sections) > 1
    assert [section.position for section in sections] == list(range(len(sections)))
    assert any(section.heading and section.heading.startswith("5.") for section in sections)
    assert all(section.text.strip() for section in sections)


def test_a_pdf_is_split_too(api, accounts, db_session):
    upload(api, accounts, PDF_BYTES, name="benefits.pdf")

    document = db_session.scalars(select(Document)).one()
    sections = db_session.scalars(select(Section)).all()

    assert sections
    assert all(section.document_id == document.id for section in sections)


def test_a_pdf_with_no_readable_text_is_a_422(api, accounts, db_session, storage, tmp_path):
    """A scan. The upload fails rather than succeeding uselessly: an HR
    administrator should not be told a document is approved when nothing
    can be read from it."""
    from reportlab.pdfgen import canvas

    path = tmp_path / "scan.pdf"
    page = canvas.Canvas(str(path))
    page.rect(100, 100, 200, 200, fill=0)
    page.save()

    response = upload(api, accounts, path.read_bytes(), name="scan.pdf")

    assert response.status_code == 422
    assert "text recognition" in response.json()["detail"]


def test_a_document_that_cannot_be_read_leaves_nothing_behind(
    api, accounts, db_session, storage, tmp_path
):
    """No row, no file, no sections. A document that was stored but never
    split is one retrieval can never find and the Admin Upload Page would
    still list."""
    from reportlab.pdfgen import canvas

    path = tmp_path / "scan.pdf"
    page = canvas.Canvas(str(path))
    page.rect(100, 100, 200, 200, fill=0)
    page.save()

    upload(api, accounts, path.read_bytes(), name="scan.pdf")

    assert db_session.scalars(select(Document)).all() == []
    assert db_session.scalars(select(Section)).all() == []
    assert not storage.exists() or list(storage.glob("*")) == []


def test_a_failed_split_leaves_nothing_behind(api, accounts, db_session, storage, monkeypatch):
    """Not only the refusals: an unexpected error in indexing must undo the
    upload too, or the two halves disagree."""

    def explode(*args, **kwargs):
        raise RuntimeError("the splitter fell over")

    monkeypatch.setattr("app.api.documents.index_document", explode)

    response = upload(api, accounts, PDF_BYTES)

    assert response.status_code == 500
    assert db_session.scalars(select(Document)).all() == []
    assert list(storage.glob("*")) == []


def test_every_kind_of_refusal_has_a_status_code():
    """A fifth refusal added without a row here would become a 400 by
    default, which is the wrong answer for most of the things it could be."""
    from app.api.documents import REFUSAL_STATUS
    from app.services.documents import UploadRefused

    kinds = set()
    pending = [UploadRefused]
    while pending:
        for subclass in pending.pop().__subclasses__():
            kinds.add(subclass)
            pending.append(subclass)

    assert kinds == set(REFUSAL_STATUS)


def test_a_document_of_nothing_but_separators_is_a_422(api, accounts, db_session, storage):
    """The reachable path into "no sections": a TXT file that is not empty
    as bytes but holds no text once the rule lines are dropped."""
    response = upload(api, accounts, b"-----\n=====\n-----\n", name="rules.txt", kind="text/plain")

    assert response.status_code == 422
    assert db_session.scalars(select(Document)).all() == []
    assert db_session.scalars(select(Section)).all() == []
    assert not storage.exists() or list(storage.glob("*")) == []


# --- the sections are embedded and stored (ON-41, U4) ------------------


def test_an_uploaded_document_has_a_vector_for_every_section(api, accounts, db_session, collection):
    response = upload(api, accounts, TXT_BYTES, name="handbook.txt", kind="text/plain")
    assert response.status_code == 201

    sections = db_session.scalars(select(Section)).all()
    assert len(sections) > 1
    assert set(collection.rows) == {str(section.id) for section in sections}


def test_a_stored_vector_names_the_document_it_came_from(api, accounts, db_session, collection):
    response = upload(api, accounts, TXT_BYTES, name="handbook.txt", kind="text/plain")
    document_id = response.json()["id"]

    assert all(
        collection.metadata_for(identifier)["document_id"] == document_id
        for identifier in collection.rows
    )


def test_the_vectors_have_the_configured_width(api, accounts, collection):
    # `mock_embedding` sets EMBEDDING_DIMENSIONS to 32. A collection built
    # for one width is the reason this has to be true of every vector.
    upload(api, accounts, TXT_BYTES, name="handbook.txt", kind="text/plain")

    assert {len(vector) for vector, _metadata in collection.rows.values()} == {32}


def test_a_document_that_cannot_be_embedded_is_refused(api, accounts, db_session, collection):
    # Without this the upload would answer 201 and the Admin Upload Page
    # would list an approved document that retrieval can never return -
    # which is exactly what ON-42's success message promises it is not.
    collection.fail_with = RuntimeError("the Vector Database is unreachable")

    response = upload(api, accounts, TXT_BYTES, name="handbook.txt", kind="text/plain")

    assert response.status_code == 500
    assert "prepared for search" in response.json()["detail"]


def test_a_document_that_cannot_be_embedded_leaves_nothing_behind(
    api, accounts, db_session, storage, collection
):
    collection.fail_with = RuntimeError("the Vector Database is unreachable")

    upload(api, accounts, TXT_BYTES, name="handbook.txt", kind="text/plain")

    assert db_session.scalars(select(Document)).all() == []
    assert db_session.scalars(select(Section)).all() == []
    assert not storage.exists() or list(storage.glob("*")) == []


def test_vectors_written_before_a_later_failure_are_cleaned_up(
    api, accounts, db_session, storage, collection, monkeypatch
):
    """The half-written case, which is the one that bites.

    U4 writes outside the SQL transaction (TD-28), so a failure after some
    batches have gone up leaves vectors for sections that are about to be
    deleted. Those are what retrieval searches, so they would be found and
    then cited as nothing at all.
    """
    import app.services.embedding.store as store

    monkeypatch.setattr(store, "MAX_WRITE_BATCH", 1)
    original = collection.upsert

    def fail_after_the_first(*args, **kwargs):
        original(*args, **kwargs)
        if len(collection.upsert_calls) >= 2:
            raise RuntimeError("the Vector Database went away mid-write")

    monkeypatch.setattr(collection, "upsert", fail_after_the_first)

    response = upload(api, accounts, TXT_BYTES, name="handbook.txt", kind="text/plain")

    assert response.status_code == 500
    assert db_session.scalars(select(Document)).all() == []
    assert collection.count() == 0


def test_the_refusal_does_not_leak_what_went_wrong_inside(api, accounts, collection):
    collection.fail_with = RuntimeError("psycopg: FATAL password authentication failed")

    response = upload(api, accounts, TXT_BYTES, name="handbook.txt", kind="text/plain")

    assert "password" not in response.text
