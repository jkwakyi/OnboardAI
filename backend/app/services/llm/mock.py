"""The Mock LLM (ON-44).

"Fake answers for Sprint 1", in the contracts' words, and the reason the
whole design puts an interface in front of the model: the frontend team
can build against this, CI can run the answer path with no model and no
key, and a teammate without 8 GB of weights on their laptop can still run
the system. `LLM_PROVIDER=mock` is the default for exactly that reason
(TD-01).

It is not only a stand-in. The LLM Gateway (ON-45) has to behave correctly
when a provider times out, errors, or returns something that is not the
JSON it asked for - and those three conditions are what the contracts say
produce the HR fallback. A mock that can only succeed would leave all
three untested, so this one can be told to do any of them.

Where this touches ON-45
------------------------
Two things here are this ticket guessing at a decision that belongs to the
Gateway, and both are in one place each so that guess is cheap to correct:

* `ANSWER_SHAPE` - the JSON an answer comes back as. The contracts fix the
  shape of the *endpoint's* response, not of the exchange between the
  Gateway and a provider, so ON-45 owns this and may change it.
* `SECTION_MARKER` - how a retrieved section is labelled inside the prompt,
  which is what lets this mock cite the sections it was actually given
  rather than inventing titles. If ON-45 builds prompts a different way,
  the mock simply finds no markers and cites nothing, which is still valid
  output rather than a crash.
"""

from __future__ import annotations

import json
import logging
import re
import time

from app.services.llm.provider import LLMError, LLMProvider

logger = logging.getLogger(__name__)

# The JSON an answer comes back as. ON-45's to confirm - see the docstring.
ANSWER_SHAPE = ("answer", "citations")

# How a retrieved section is labelled in a prompt: "[section:42] 5.1 TITLE".
# The id is what a citation has to carry, because it is the only thing that
# identifies a section once the text has been through a model.
#
# The heading is whatever follows on the *same line*. Written as `\s*(.+)`
# it swallowed the newline and captured the section's first line of body
# text as its title, which is how a citation ends up titled with the middle
# of a sentence.
SECTION_MARKER = re.compile(r"\[section:(\d+)\][ \t]*([^\n]*)")

# What the mock says when it was given nothing to work from. Deliberately
# not a plausible HR answer: a fake answer that reads like a real one is
# one somebody eventually screenshots into a report.
NO_CONTEXT_ANSWER = (
    "This answer came from the Mock LLM, which does not read the handbook "
    "and does not know the answer. Set LLM_PROVIDER to a real provider to "
    "get a real one."
)


class MockLLM(LLMProvider):
    """A provider that answers from the prompt without a model.

    Every argument exists so the LLM Gateway can be tested against the
    conditions the contracts name:

    * `delay_seconds` - a provider slower than the Gateway's 20-second
      limit.
    * `fail_with` - a provider that errors.
    * `raw_response` - a provider that returns something that is not the
      JSON it was asked for.

    Left alone it answers, which is what the frontend and the demo need.
    """

    def __init__(
        self,
        *,
        delay_seconds: float = 0.0,
        fail_with: str | None = None,
        raw_response: str | None = None,
    ) -> None:
        self.delay_seconds = delay_seconds
        self.fail_with = fail_with
        self.raw_response = raw_response
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        """Answer `prompt`, or behave like a provider that cannot."""
        # Kept so a test can assert what the Gateway actually sent - above
        # all that the prompt was limited to the retrieved text, which the
        # contracts require and which only an inspectable provider can show.
        self.prompts.append(prompt)

        if self.delay_seconds:
            # A real sleep, because what ON-45 needs to test is a provider
            # that does not come back in time, and a fake clock would not
            # exercise whatever it uses to give up waiting.
            time.sleep(self.delay_seconds)

        if self.fail_with is not None:
            raise LLMError(self.fail_with)

        if self.raw_response is not None:
            return self.raw_response

        citations = self._citations_in(prompt)
        answer = self._answer_for(citations)
        return json.dumps({"answer": answer, "citations": citations}, indent=None)

    @staticmethod
    def _citations_in(prompt: str) -> list[dict[str, str | int]]:
        """The sections the prompt carried, as citations.

        Citing what it was given rather than inventing a title is the
        difference between a mock the frontend can build a citation chip
        against and one that makes every answer look broken.
        """
        citations: list[dict[str, str | int]] = []
        for match in SECTION_MARKER.finditer(prompt):
            section_id, heading = match.group(1), (match.group(2) or "").strip()
            citations.append(
                {
                    "section_id": int(section_id),
                    "heading": heading or f"Section {section_id}",
                }
            )
        return citations

    @staticmethod
    def _answer_for(citations: list[dict[str, str | int]]) -> str:
        if not citations:
            return NO_CONTEXT_ANSWER
        headings = ", ".join(str(citation["heading"]) for citation in citations)
        return (
            "This answer came from the Mock LLM, which does not read the "
            f"handbook. It was given {len(citations)} section(s): {headings}. "
            "Set LLM_PROVIDER to a real provider for a real answer."
        )

    @property
    def name(self) -> str:
        return "mock"


__all__ = ["ANSWER_SHAPE", "NO_CONTEXT_ANSWER", "SECTION_MARKER", "MockLLM"]
