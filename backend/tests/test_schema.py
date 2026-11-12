"""The Main Database schema holds what the contracts say it holds (ON-11).

These run against a throwaway SQLite database so the unit suite stays
offline and fast. What they check is behaviour the schema itself must
guarantee — not what the application remembers to do — so every assertion
here is about a constraint the database would enforce even if every line of
service code were wrong.

`test_migrations.py` proves the migration produces this same schema, and
`test_schema_postgres.py` proves PostgreSQL agrees.
"""

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app.db import Base, ChatLog, Document, Escalation, Feedback, Section, User

# The six rows of the Interface Contracts' data table.
EXPECTED_TABLES = {
    "users",
    "documents",
    "sections",
    "chat_logs",
    "feedback",
    "escalations",
}


@pytest.fixture
def engine():
    """An empty database with foreign keys actually enforced.

    SQLite ignores foreign keys unless asked, and a test suite that silently
    skips every cascade and RESTRICT rule would pass no matter what the
    schema said.
    """
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enforce_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine):
    with Session(engine) as session:
        yield session


def _employee(session: Session, email: str = "ada@example.com") -> User:
    user = User(
        email=email,
        full_name="Ada Employee",
        password_hash="argon2:not-a-real-hash",
        role="employee",
    )
    session.add(user)
    session.flush()
    return user


def _document(session: Session, owner: User) -> Document:
    document = Document(
        filename="handbook.pdf",
        content_type="pdf",
        stored_path="backend/storage/documents/1-handbook.pdf",
        size_bytes=2048,
        uploaded_by=owner,
    )
    session.add(document)
    session.flush()
    return document


# --- the tables themselves ---------------------------------------------


def test_the_schema_has_the_six_tables_the_contracts_name(engine):
    assert set(inspect(engine).get_table_names()) == EXPECTED_TABLES


# --- users: a hashed password and one of two roles ----------------------


def test_a_user_holds_a_hashed_password_and_a_role(session):
    user = _employee(session)

    assert user.password_hash == "argon2:not-a-real-hash"
    assert user.role == "employee"


def test_there_is_nowhere_to_put_a_plain_password(engine):
    """The column is named for what it holds, and it is the only one."""
    columns = {column["name"] for column in inspect(engine).get_columns("users")}

    assert "password_hash" in columns
    assert not {name for name in columns if "password" in name} - {"password_hash"}


@pytest.mark.parametrize("role", ["employee", "hr_administrator"])
def test_both_roles_the_contracts_define_are_accepted(session, role):
    session.add(
        User(
            email=f"{role}@example.com",
            full_name="Someone",
            password_hash="hash",
            role=role,
        )
    )
    session.flush()


def test_the_orm_will_not_write_a_role_the_contracts_do_not_define(session):
    session.add(User(email="x@example.com", full_name="X", password_hash="hash", role="superuser"))

    with pytest.raises(StatementError):
        session.flush()


def test_the_database_itself_will_not_hold_a_third_role(session):
    """Written as raw SQL on purpose.

    The ORM refuses the value first, so going through it proves only that
    SQLAlchemy is configured. Auth Check decides what a request may reach
    from this column, so the guarantee has to survive code that bypasses the
    ORM entirely.
    """
    with pytest.raises(IntegrityError):
        session.execute(
            text(
                "INSERT INTO users (email, full_name, password_hash, role) "
                "VALUES ('x@example.com', 'X', 'hash', 'superuser')"
            )
        )


def test_two_users_cannot_share_an_email(session):
    _employee(session)
    session.add(
        User(
            email="ada@example.com",
            full_name="Someone Else",
            password_hash="hash",
            role="hr_administrator",
        )
    )

    with pytest.raises(IntegrityError):
        session.flush()


# --- documents and sections --------------------------------------------


def test_each_section_references_its_document(session):
    user = _employee(session)
    document = _document(session, user)
    section = Section(document=document, position=0, text="Paid time off is 15 days.")
    session.add(section)
    session.flush()

    assert section.document_id == document.id
    assert document.sections == [section]


def test_a_section_cannot_exist_without_a_document(session):
    session.add(Section(document_id=999, position=0, text="orphan"))

    with pytest.raises(IntegrityError):
        session.flush()


def test_deleting_a_document_deletes_its_sections(session):
    """DELETE /api/documents/{id} must not leave citable text behind."""
    user = _employee(session)
    document = _document(session, user)
    session.add_all(
        [
            Section(document=document, position=0, text="first"),
            Section(document=document, position=1, text="second"),
        ]
    )
    session.flush()

    session.delete(document)
    session.flush()

    assert session.query(Section).count() == 0


def test_a_position_is_used_once_within_a_document(session):
    """A re-run of the upload must not quietly duplicate a section."""
    user = _employee(session)
    document = _document(session, user)
    session.add_all(
        [
            Section(document=document, position=0, text="first"),
            Section(document=document, position=0, text="first again"),
        ]
    )

    with pytest.raises(IntegrityError):
        session.flush()


def test_a_file_type_outside_pdf_and_txt_is_rejected(session):
    """The contracts allow PDF and TXT uploads and nothing else."""
    user = _employee(session)

    with pytest.raises(IntegrityError):
        session.execute(
            text(
                "INSERT INTO documents (filename, content_type, stored_path, "
                "size_bytes, uploaded_by_id) "
                "VALUES ('payroll.xlsx', 'xlsx', '/tmp/payroll.xlsx', 10, :user)"
            ),
            {"user": user.id},
        )


# --- chat logs and feedback --------------------------------------------


def test_a_chat_log_keeps_the_answer_and_its_citations(session):
    user = _employee(session)
    log = ChatLog(
        user=user,
        question="How much paid time off do I get?",
        answer="15 days per year.",
        citations=[{"document_id": 1, "section": 4}],
        fallback=False,
    )
    session.add(log)
    session.flush()
    session.expire(log)

    assert log.citations == [{"document_id": 1, "section": 4}]
    assert log.fallback is False


def test_a_fallback_is_recorded_as_one(session):
    """ON-24 measures how often this happens, so it has to be a column."""
    user = _employee(session)
    log = ChatLog(
        user=user,
        question="What is the policy on moon leave?",
        answer="Please contact HR.",
        citations=[],
        fallback=True,
    )
    session.add(log)
    session.flush()

    assert log.fallback is True


def test_one_rating_per_person_per_answer(session):
    user = _employee(session)
    log = ChatLog(user=user, question="q", answer="a", citations=[], fallback=False)
    session.add(log)
    session.flush()
    session.add_all(
        [
            Feedback(chat_log=log, user_id=user.id, rating="up"),
            Feedback(chat_log=log, user_id=user.id, rating="down"),
        ]
    )

    with pytest.raises(IntegrityError):
        session.flush()


def test_a_rating_is_thumbs_up_or_thumbs_down(session):
    user = _employee(session)
    log = ChatLog(user=user, question="q", answer="a", citations=[], fallback=False)
    session.add(log)
    session.flush()

    with pytest.raises(IntegrityError):
        session.execute(
            text(
                "INSERT INTO feedback (chat_log_id, user_id, rating) "
                "VALUES (:log, :user, 'five stars')"
            ),
            {"log": log.id, "user": user.id},
        )


def test_deleting_a_chat_log_deletes_its_feedback(session):
    user = _employee(session)
    log = ChatLog(user=user, question="q", answer="a", citations=[], fallback=False)
    session.add(log)
    session.flush()
    session.add(Feedback(chat_log=log, user_id=user.id, rating="up"))
    session.flush()

    session.delete(log)
    session.flush()

    assert session.query(Feedback).count() == 0


# --- escalations --------------------------------------------------------


def test_an_escalation_is_saved_open(session):
    """E2: the question is saved as an open escalation."""
    user = _employee(session)
    escalation = Escalation(user_id=user.id, question="What is the policy on moon leave?")
    session.add(escalation)
    session.flush()
    session.expire(escalation)

    assert escalation.status == "open"
    assert escalation.hr_reply is None
    assert escalation.resolved_at is None


def test_hr_resolves_an_escalation_with_a_reply(session):
    """E3: HR replies and marks it resolved; E4 shows the reply in the chat."""
    from datetime import UTC, datetime

    employee = _employee(session)
    hr = User(
        email="hr@example.com",
        full_name="Hiram R",
        password_hash="hash",
        role="hr_administrator",
    )
    session.add(hr)
    session.flush()
    escalation = Escalation(user_id=employee.id, question="q")
    session.add(escalation)
    session.flush()

    escalation.status = "resolved"
    escalation.hr_reply = "There is no moon leave."
    escalation.resolved_by_id = hr.id
    escalation.resolved_at = datetime.now(UTC)
    session.flush()

    assert escalation.status == "resolved"


def test_an_escalation_status_outside_open_and_resolved_is_rejected(session):
    user = _employee(session)

    with pytest.raises(IntegrityError):
        session.execute(
            text("INSERT INTO escalations (user_id, question, status) VALUES (:u, 'q', 'pending')"),
            {"u": user.id},
        )


def test_an_escalation_outlives_the_chat_log_it_came_from(session):
    """The question HR must answer is on the escalation, not borrowed."""
    user = _employee(session)
    log = ChatLog(user=user, question="q", answer="Please contact HR.", citations=[], fallback=True)
    session.add(log)
    session.flush()
    escalation = Escalation(user_id=user.id, chat_log=log, question="q")
    session.add(escalation)
    session.flush()

    session.delete(log)
    session.flush()
    session.expire(escalation)

    assert escalation.chat_log_id is None
    assert escalation.question == "q"


# --- what must not be deletable ----------------------------------------


def test_a_user_cannot_be_deleted_while_the_history_points_at_them(session):
    """Chat logs and escalations are the audit trail; they must not dangle."""
    user = _employee(session)
    session.add(ChatLog(user=user, question="q", answer="a", citations=[], fallback=False))
    session.flush()

    with pytest.raises(IntegrityError):
        session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})
