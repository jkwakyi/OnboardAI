"""The Logging Service (ON-47).

The component the contracts describe as "saves chats and feedback for
manual review", called by the QA Controller's caller to save the chat
(step 9) and by the Chat API for feedback.

Named `logs` rather than `logging`, which would shadow the standard
library module every other file in this package imports. The contracts'
name for the component is in this docstring instead, where it cannot
confuse an import.

Feedback arrives with the Feedback epic; `chat.py` is the chat half.
"""

from app.services.logs.chat import citation_rows, save_chat

__all__ = ["citation_rows", "save_chat"]
