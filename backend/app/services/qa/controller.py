"""The QA Controller (ON-46, steps 3 to 8).

The contracts give this component the job of running the RAG steps and
one decision of its own:

    Condition: the best match is below the relevance threshold.
    Result:    the QA Controller *skips the LLM* and returns
               `fallback: true` with a message directing the employee
               to HR.

That is the whole of ON-46, and the word that carries the weight is
*skips*. An assistant that always asks the model and hopes it says "I
don't know" is a different system from one that declines to ask: a model
given five irrelevant sections and a direct question will usually answer
it anyway, drawing on what it learnt in training rather than on an
approved HR document. That answer reads exactly like a good one. It is
the invented policy this whole design exists to prevent, and the only
thing standing in its way is this component not making the call.

So the test that matters here is not that a fallback comes back - it is
that the provider was never asked.

Why the threshold is a setting when the other numbers are constants
-------------------------------------------------------------------
The top-5 cut and the Gateway's 20 seconds are constants, because the
contracts fix them and a deployment quietly changing one would be running
a different design. This number is different: ON-46 says to "start with a
provisional threshold" and tune it in the evaluation story, so it is
expected to move, and it depends on the embedding model rather than on
the design. `RELEVANCE_THRESHOLD` is where it lives.

It is also **provider-specific**, which is the sharp edge. A threshold
measured against one embedding model means nothing to another: the scores
are cosine similarities, and two models put the same pair of texts at
quite different angles. The shipped default was measured against the mock
embedder, because the Embedding API account has no credit and the hosted
model's distribution has never been seen. See TD-30.

What this does not do
---------------------
It does not log the chat. The contracts have the Logging Service "called
by the Chat API for feedback and by the QA Controller to save the chat
(step 9)", and that is ON-47, which owns the endpoint and the chat log
together. This returns everything such a log needs - including the score
it decided on and the reason, which no employee ever sees - and writes
nothing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.services.llm import get_provider
from app.services.llm.gateway import (
    HR_FALLBACK_MESSAGE,
    Citation,
    GatewayResult,
    LLMGateway,
    PromptSection,
)
from app.services.retrieval import RetrievedSection, retrieve

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Answer:
    """What the Chat API (ON-47) turns into a response and a chat log.

    `answer`, `citations` and `fallback` are the contracts' own fields.
    The last three are for the log and for ON-24's measurements, and are
    never shown to an employee - who gets the same message whichever way
    the AI path declined to answer, because the difference between "the
    model timed out" and "nothing in the handbook covers this" is not
    theirs to act on. Either way the next step is to ask HR.
    """

    answer: str
    citations: list[Citation] = field(default_factory=list)
    fallback: bool = False
    #: Why, for the log. Never rendered.
    reason: str | None = None
    #: The best retrieval score seen, or None if nothing was retrieved.
    best_score: float | None = None
    #: How many sections retrieval returned.
    retrieved: int = 0


def to_prompt_sections(sections: list[RetrievedSection]) -> list[PromptSection]:
    """Retrieved sections, as the LLM Gateway wants them.

    This conversion lives here rather than in either neighbour on
    purpose. The Retrieval Service must not import the LLM package - it
    ranks sections and has no business knowing a model exists - and the
    Gateway must not import the database. The QA Controller is the one
    component the contracts give both, so the join is its job.
    """
    return [
        PromptSection(
            section_id=section.section_id,
            heading=section.heading,
            text=section.text,
            document=section.document,
        )
        for section in sections
    ]


class QAController:
    """Runs the RAG steps, and decides when not to."""

    def __init__(
        self,
        gateway: LLMGateway | None = None,
        threshold: float | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self.threshold = threshold if threshold is not None else self._settings.relevance_threshold
        self.gateway = gateway if gateway is not None else LLMGateway(get_provider(self._settings))

    def ask(self, question: str, session: Session) -> Answer:
        """Answer `question` from the approved documents, or send it to HR.

        Never raises for anything retrieval or the provider does. "A
        failure in the AI path returns the HR fallback instead of an
        error, so employees never see an invented policy" is the
        contracts' phrasing, and a traceback is not an invented policy but
        it is not an answer either.
        """
        try:
            sections = retrieve(question, session)
        except Exception as failure:  # noqa: BLE001 - never surfaced to an employee
            # The Embedding API being down, or the Vector Database. Worth
            # an exception trace in the log, because unlike the other
            # fallbacks this one is somebody's to fix.
            logger.exception("retrieval failed for a question")
            return self._fallback(f"retrieval failed: {type(failure).__name__}: {failure}")

        if not sections:
            return self._fallback("nothing was retrieved for the question", retrieved=0)

        best = sections[0].score
        if best < self.threshold:
            # The decision this component exists for. The provider is not
            # called, not asked to decline, and not given the chance to
            # answer from training data instead of from the handbook.
            return self._fallback(
                f"the best match scored {best:.3f}, below the threshold of {self.threshold:.3f}",
                best_score=best,
                retrieved=len(sections),
            )

        result = self.gateway.answer(question, to_prompt_sections(sections))
        return self._from_gateway(result, best_score=best, retrieved=len(sections))

    # --- the two ways an Answer gets built ------------------------------

    def _fallback(
        self,
        reason: str,
        best_score: float | None = None,
        retrieved: int = 0,
    ) -> Answer:
        logger.info("the HR fallback, because %s", reason)
        return Answer(
            answer=HR_FALLBACK_MESSAGE,
            citations=[],
            fallback=True,
            reason=reason,
            best_score=best_score,
            retrieved=retrieved,
        )

    @staticmethod
    def _from_gateway(result: GatewayResult, best_score: float, retrieved: int) -> Answer:
        """Carry the Gateway's verdict through without re-deciding it.

        Including when it fell back: the Gateway has already judged a
        timeout, a provider error or output that failed the JSON check,
        and the contracts give all three the same result. Second-guessing
        any of them here would be two components deciding one thing.
        """
        return Answer(
            answer=result.answer,
            citations=list(result.citations),
            fallback=result.fallback,
            reason=result.reason,
            best_score=best_score,
            retrieved=retrieved,
        )


__all__ = ["Answer", "QAController", "to_prompt_sections"]
