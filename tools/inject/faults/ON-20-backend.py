"""Faults for the Escalation Service and POST /api/escalations (ON-20).

ON-20 spans both stacks, so it has two faults files: this one and
`ON-20-frontend.py`. The injector takes one `ROOT` and one `RUNNER` per
file, and splitting them is more honest than a file that pretends a
Python test run and a vitest run are the same pass.

This endpoint is the first one an employee can use to write something
another person will read, which makes its failure modes different from
everything before it. A chat log wrong in the database is an answer
nobody sees again; an escalation wrong in the database is a question in
front of an HR administrator, indistinguishable from a real one, that
somebody will act on.

Four are changes somebody would make on purpose:

* "the question comes from the request" is the obvious way to write this
  endpoint, and it is what almost every tutorial does. It lets a caller
  put any words at all into HR's inbox, attached to a chat log that says
  something else.
* "any answer can be escalated" removes a check that looks redundant,
  because the button only appears on a fallback. A button that is absent
  is not a rule.
* "the answer only has to exist" drops the ownership test, which looks
  like a lookup that is already doing its job. It lets an employee
  escalate a colleague's question - and read HR's reply to it, because
  E4 shows the reply against the chat it belongs to.
* "asking twice makes two escalations" is what you get by simply not
  thinking about a double click. It is the most likely of the four to
  happen in a demo.
"""

TESTS = [
    "tests/test_escalations_api.py",
    "tests/test_escalation_service.py",
    "tests/test_chat_api.py",
    "tests/test_auth_check.py",
    "tests/test_schema.py",
]

SERVICE = "app/services/escalations/service.py"
API = "app/api/escalations.py"
PACKAGE = "app/services/escalations/__init__.py"

# One fault was written and removed as proving nothing: "the endpoint
# takes the question from the caller" added an unused `question` field
# to the request model. Pydantic ignores what nothing reads, so it
# changed no behaviour at all. What it was reaching for is covered by
# the first fault below, and by a test that sends an extra `question`
# and watches it be ignored.

FAULTS = [
    # --- whose words end up in HR's inbox -------------------------------
    (
        # The quiet one: a 201, a real row, and a question nobody asked.
        "the question comes from the request rather than the chat log",
        SERVICE,
        "        question=chat_log.question,",
        "        question=getattr(chat_log, 'answer', ''),",
    ),
    (
        "the escalation records no question at all",
        SERVICE,
        "        question=chat_log.question,",
        '        question="",',
    ),
    # --- whose answer is it ------------------------------------------------
    (
        "a colleague's answer can be escalated",
        SERVICE,
        "    if chat_log is None or chat_log.user_id != user_id:",
        "    if chat_log is None:",
    ),
    (
        "the escalation is recorded against the wrong person",
        SERVICE,
        "        user_id=user_id,\n        chat_log_id=chat_log_id,",
        "        user_id=chat_log.user_id if False else 1,\n        chat_log_id=chat_log_id,",
    ),
    (
        "a missing answer and somebody else's are told apart",
        SERVICE,
        '        raise NoSuchAnswer("That answer could not be found.")',
        "        raise NoSuchAnswer(\n            'That answer could not be found.'\n            if chat_log is None\n            else 'That answer belongs to another employee.'\n        )",
    ),
    # --- only a fallback ------------------------------------------------------
    (
        "any answer can be escalated, not only a fallback",
        SERVICE,
        "    if not chat_log.fallback:",
        "    if False:",
    ),
    (
        "the check is inverted, so only answered questions can be sent",
        SERVICE,
        "    if not chat_log.fallback:",
        "    if chat_log.fallback:",
    ),
    (
        "the refusal uses our word for it rather than the employee's",
        SERVICE,
        '        raise NotAFallback("That question was answered, so there is nothing to send to HR.")',
        '        raise NotAFallback("That chat log is not a fallback.")',
    ),
    # --- asking twice -----------------------------------------------------------
    (
        "asking twice puts the same question in HR's inbox twice",
        SERVICE,
        "    if existing is not None:",
        "    if False:",
    ),
    (
        "an escalation already resolved is handed back as the open one",
        SERVICE,
        '            Escalation.status == "open",',
        "            Escalation.id > 0,",
    ),
    (
        "one person's escalation is handed back to another",
        SERVICE,
        "            Escalation.user_id == user_id,",
        "            Escalation.id > 0,",
    ),
    (
        "two different questions collapse into one escalation",
        SERVICE,
        "            Escalation.chat_log_id == chat_log_id,",
        "            Escalation.id > 0,",
    ),
    # --- what gets saved ---------------------------------------------------------
    (
        "the escalation is saved already resolved",
        SERVICE,
        '        status="open",',
        '        status="resolved",',
    ),
    (
        "the escalation does not point back at the answer it came from",
        SERVICE,
        "        chat_log_id=chat_log_id,",
        "        chat_log_id=None,",
    ),
    (
        "the row is never flushed, so it has no id to return",
        SERVICE,
        "    session.add(escalation)\n    session.flush()",
        "    session.add(escalation)",
    ),
    (
        "the service commits the caller's transaction for it",
        SERVICE,
        "    session.add(escalation)\n    session.flush()",
        "    session.add(escalation)\n    session.commit()",
    ),
    (
        "the endpoint never commits, so nothing survives the request",
        API,
        "        session.commit()\n    except NoSuchAnswer as missing:",
        "        pass\n    except NoSuchAnswer as missing:",
    ),
    (
        "a failed save leaves its half-written row behind",
        API,
        "        session.rollback()\n        logger.exception",
        "        logger.exception",
    ),
    # --- the status codes -----------------------------------------------------------
    (
        "an answer that is not the caller's is reported as a server error",
        API,
        "        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(missing)) from missing",
        "        raise HTTPException(status_code=500, detail=str(missing)) from missing",
    ),
    (
        "an already-answered question is reported as not found",
        API,
        "        raise HTTPException(\n            status_code=status.HTTP_409_CONFLICT, detail=str(answered)\n        ) from answered",
        "        raise HTTPException(\n            status_code=status.HTTP_404_NOT_FOUND, detail=str(answered)\n        ) from answered",
    ),
    (
        "a created escalation does not answer 201",
        API,
        "    status_code=status.HTTP_201_CREATED,",
        "    status_code=status.HTTP_200_OK,",
    ),
    # --- validation -------------------------------------------------------------------
    (
        "an id of zero reaches the database",
        API,
        "        gt=0,",
        "        ge=0,",
    ),
    (
        "a token naming an account that is gone is allowed through",
        API,
        "    if asker is None:",
        "    if False:",
    ),
    # --- what comes back ----------------------------------------------------------------
    (
        "the response carries fields that are always empty",
        API,
        "    status: str\n    created_at: datetime",
        "    status: str\n    created_at: datetime\n    hr_reply: str | None = None\n    resolved_at: datetime | None = None",
    ),
    (
        "the response does not say which answer it belongs to",
        API,
        "    chat_log_id: int | None\n    question: str",
        "    question: str",
    ),
    # --- what the package offers -----------------------------------------------------------
    (
        "the Escalation Service stops exporting what the API imports",
        PACKAGE,
        '__all__ = ["EscalationRefused", "NoSuchAnswer", "NotAFallback", "open_escalation"]',
        '__all__ = ["open_escalation"]\ndel EscalationRefused, NoSuchAnswer, NotAFallback',
    ),
]
