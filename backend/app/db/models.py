"""The Main Database schema (ON-11).

Six tables, one per row of the Interface Contracts' data table: users,
documents, sections, chat logs, feedback and escalations. Nothing here
invents a concept the contracts do not name; where the contracts describe
contents rather than columns, the columns are the smallest set that holds
those contents.

Two conventions run through the file:

* Enumerated values are stored as text with a check constraint
  (`native_enum=False`) rather than as a PostgreSQL enum type. A native enum
  cannot be altered inside a transaction on older servers and does not exist
  in the SQLite the unit tests run against, so the same schema would not be
  testable on both.
* Times are stored with their time zone and defaulted by the database, so a
  row written by a backend running in one zone still reads correctly from
  another.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.session import Base

# The two roles the contracts define. Auth Check reads this to decide
# whether a request may reach an HR-only endpoint.
ROLES = ("employee", "hr_administrator")

# The contracts allow PDF and TXT uploads and nothing else.
DOCUMENT_TYPES = ("pdf", "txt")

# "Thumbs up or thumbs down on an answer."
RATINGS = ("up", "down")

# An escalation is saved open (E2) and later marked resolved with HR's
# reply (E3).
ESCALATION_STATUSES = ("open", "resolved")


def _enum(*values: str, name: str) -> Enum:
    """A text column constrained to `values`, portable across backends.

    `create_constraint` has defaulted to False since SQLAlchemy 1.4, so
    without it a non-native enum is an unconstrained VARCHAR and the
    database would accept any string at all for a role or a status.
    """
    return Enum(
        *values,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
    )


def _now() -> Mapped[datetime]:
    """A creation timestamp the database fills in."""
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class User(Base):
    """An Employee or an HR administrator.

    The password is only ever stored hashed; the Auth Service (ON-36) owns
    the hashing, this table only guarantees there is nowhere to put a plain
    one.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(_enum(*ROLES, name="user_role"), nullable=False)
    created_at: Mapped[datetime] = _now()

    documents: Mapped[list[Document]] = relationship(back_populates="uploaded_by")
    chat_logs: Mapped[list[ChatLog]] = relationship(back_populates="user")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.id} {self.email} {self.role}>"


class Document(Base):
    """A PDF or TXT file an HR administrator uploaded.

    The original file is kept in File Storage (U2); `stored_path` is where.
    The extracted text lives in `sections`.
    """

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(
        _enum(*DOCUMENT_TYPES, name="document_type"), nullable=False
    )
    stored_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    uploaded_at: Mapped[datetime] = _now()

    uploaded_by: Mapped[User] = relationship(back_populates="documents")
    # DELETE /api/documents/{id} removes the document; its sections are part
    # of it and go with it, or retrieval would cite text no longer approved.
    sections: Mapped[list[Section]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Document {self.id} {self.filename}>"


class Section(Base):
    """A piece of a document's extracted text.

    Its vector lives in the Vector Database under this row's id, so the id
    must stay stable for as long as the section does.
    """

    __tablename__ = "sections"
    __table_args__ = (
        # The order the Document Upload Service split the text in. Unique so
        # a re-run cannot quietly duplicate a section.
        UniqueConstraint("document_id", "position", name="document_position"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    heading: Mapped[str | None] = mapped_column(String(500), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _now()

    document: Mapped[Document] = relationship(back_populates="sections")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Section {self.id} of document {self.document_id}>"


class ChatLog(Base):
    """One saved question and answer, written by the Logging Service (step 9).

    `fallback` records whether the employee got the HR fallback rather than
    an answer, which is the signal ON-24 measures and the reason a "Send to
    HR" button appears.
    """

    __tablename__ = "chat_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    # The citations the LLM Gateway accepted, as they were returned.
    citations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = _now()

    user: Mapped[User] = relationship(back_populates="chat_logs")
    feedback: Mapped[list[Feedback]] = relationship(
        back_populates="chat_log", cascade="all, delete-orphan", passive_deletes=True
    )
    escalations: Mapped[list[Escalation]] = relationship(back_populates="chat_log")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ChatLog {self.id} fallback={self.fallback}>"


class Feedback(Base):
    """Thumbs up or thumbs down on an answer.

    Logged for manual review and never used for automatic retraining, which
    is why nothing here feeds back into retrieval or the prompt.
    """

    __tablename__ = "feedback"
    __table_args__ = (
        # One verdict per person per answer; sending it again changes it.
        UniqueConstraint("chat_log_id", "user_id", name="one_rating_per_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_log_id: Mapped[int] = mapped_column(
        ForeignKey("chat_logs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    rating: Mapped[str] = mapped_column(_enum(*RATINGS, name="feedback_rating"), nullable=False)
    created_at: Mapped[datetime] = _now()

    chat_log: Mapped[ChatLog] = relationship(back_populates="feedback")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Feedback {self.id} {self.rating}>"


class Escalation(Base):
    """A question sent to HR, saved open (E2) and later resolved (E3).

    `chat_log_id` is the fallback answer the employee clicked "Send to HR"
    on, so the Chat Page can show HR's reply against the right message (E4).
    """

    __tablename__ = "escalations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    chat_log_id: Mapped[int | None] = mapped_column(
        ForeignKey("chat_logs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        _enum(*ESCALATION_STATUSES, name="escalation_status"),
        nullable=False,
        default="open",
        server_default="open",
        index=True,
    )
    hr_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = _now()
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    chat_log: Mapped[ChatLog | None] = relationship(back_populates="escalations")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Escalation {self.id} {self.status}>"


__all__ = [
    "DOCUMENT_TYPES",
    "ESCALATION_STATUSES",
    "RATINGS",
    "ROLES",
    "ChatLog",
    "Document",
    "Escalation",
    "Feedback",
    "Section",
    "User",
]
