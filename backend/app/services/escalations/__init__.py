"""The Escalation Service (ON-20).

The component the contracts describe as "sends unanswered questions to
HR", called by the Escalations API. `service.py` is E1 to E2 — saving a
fallback question as an open escalation. Replying and resolving (E3) and
showing the reply back in the chat (E4) are ON-21 and ON-22.
"""

from app.services.escalations.service import (
    EscalationRefused,
    NoSuchAnswer,
    NotAFallback,
    open_escalation,
)

__all__ = ["EscalationRefused", "NoSuchAnswer", "NotAFallback", "open_escalation"]
