"""The LLMProvider interface (ON-44).

The Interface Contracts are unusually specific here: "The one method
signature the diagram defines is generate(prompt) on the LLMProvider
interface, which the Real LLM Client and the Mock LLM both implement, so
the frontend team can build against the Mock LLM in Sprint 1 and switch to
the hosted model without changing the QA Controller."

So the interface is one method taking one argument. It is tempting to add
a temperature, a model name, a token limit, a timeout - and every one of
those would be a reason the QA Controller has to change when the provider
does, which is the single thing this interface exists to prevent. The
timeout in particular belongs to the LLM Gateway (ON-45), which the
contracts say "applies a 20-second timeout": the provider does not get to
decide how long it is allowed, and it does not get to be the thing that
enforces it either.

What `generate` returns
-----------------------
A string. The contracts say "the answer comes back as JSON with citations"
and that the LLM Gateway "checks the JSON output" - so what comes back here
is *meant* to be JSON and may well not be, and the provider must not be
the thing that decides. A provider that parsed its own output would have
to choose what to do with a malformed answer, and the contracts already say
what happens to one: the HR fallback, decided by the Gateway. So this
returns the text exactly as the model produced it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMError(Exception):
    """A provider could not produce an answer.

    The contracts treat "the provider returns an error" as one of the three
    conditions that produce the HR fallback, alongside a timeout and output
    that fails the JSON check. Raising one type for all of them means the
    Gateway has one thing to catch rather than a list that grows every time
    somebody adds a provider.
    """


class LLMProvider(ABC):
    """Something that can answer a prompt.

    An abstract base class rather than a Protocol, because the contracts
    say the Real LLM Client and the Mock LLM both *implement* this - and a
    class that forgets `generate` should fail when somebody tries to build
    it, not later when something asks it a question.
    """

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Answer `prompt`, returning the model's output as it came.

        Raises `LLMError` if the provider could not answer at all. It does
        not raise for an answer it dislikes: whether the output is usable
        is the LLM Gateway's judgement, not the provider's.
        """

    @property
    def name(self) -> str:
        """Which provider this is, for logs and for the refinement report.

        Not part of the contract's signature - it answers questions about
        the system rather than questions from an employee, and nothing in
        the answer path reads it.
        """
        return type(self).__name__


__all__ = ["LLMError", "LLMProvider"]
