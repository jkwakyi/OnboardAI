"""The Real LLM Client (ON-18).

The architecture's fourth LLM component, and the last one. It implements
`generate(prompt)` and nothing else, because that is the only method the
design fixes - the prompt was built by the LLM Gateway, the 20 seconds are
the Gateway's to enforce, and whether the output is usable is the
Gateway's to judge. This file's whole job is: take a string to a model,
bring a string back, and raise `LLMError` if it could not.

The model runs locally
----------------------
ON-18 says the model is one of the models already on the machine, served
by Ollama over HTTP on 127.0.0.1. That is a deliberate difference from the
Embedding API, which is a hosted service with a key: there is no key here,
nothing leaves the machine, and the handbook text in the prompt never
reaches a third party. It is also why the URL has no HTTPS requirement -
the Embedding Client has one, and applying it here would make the one
provider that keeps the data local the one that is refused.

**The Ollama service belongs to SentinelMesh and is off limits.** This
client calls the API at 127.0.0.1:11434 and does nothing else: it does not
start the service, stop it, pull models or change its configuration. A
model that is not there is a configuration error reported to a developer,
not something to fix by reaching for the service.

Why thinking is turned off
--------------------------
`qwen3` reasons before it answers, and with `format: json` those thinking
tokens are generated and then thrown away. Measured on this hardware the
same question took 18.6 seconds with thinking on and 4.0 with it off, for
the same answer and the same citation - 380 output tokens against 87. The
Gateway allows 20 seconds, so thinking on spends most of the contractual
budget producing text nobody reads, and a slightly longer answer breaches
it. It is a constant rather than a setting for the same reason the 20
seconds are: a deployment that turned it back on would be slower in a way
that only shows up as employees getting the HR fallback.

Models that do not reason ignore the flag, so it is safe to send always.

The timeout here is not *the* timeout
-------------------------------------
The contractual 20 seconds belong to the LLM Gateway, which enforces them
on a thread and stops the employee waiting. But the Gateway giving up does
not stop the call (TD-23): the thread stays until the provider returns. So
this client sets its own socket timeout, longer than the Gateway's limit,
purely to bound how long an abandoned call can sit there. It is a leak
bound, not a promise to anybody - by the time it fires, the employee has
had the HR fallback for ten seconds already.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable

from app.config import Settings, get_settings
from app.services.llm.provider import LLMError, LLMProvider

logger = logging.getLogger(__name__)

# How the request reaches the model server. Injected in the tests, so the
# suite needs no GPU, no 5 GB of weights and no Ollama; nothing in the
# application passes it.
Transport = Callable[[urllib.request.Request, float], bytes]

# Reasoning off. See the docstring - this is a performance decision with a
# measurement behind it, not a preference.
THINK = False

# One answer, deterministically. A model asked the same question twice
# should not cite different sections each time, and an HR assistant is not
# a place for sampling.
TEMPERATURE = 0.0

# A ceiling on the answer's length. The Gateway's 20 seconds are spent
# almost entirely generating tokens, so this is the one number that
# decides whether a long-winded answer times out. 400 is comfortably more
# than any answer measured here needed (the longest was 87 tokens) and
# still bounds the worst case.
MAX_ANSWER_TOKENS = 400


class RealLLMClient(LLMProvider):
    """Answers a prompt with a local model, through Ollama's HTTP API.

    Everything that can go wrong on the way - the service not running, an
    HTTP error, a body that is not JSON, a JSON body with no response in
    it - raises `LLMError`, which is the one thing the Gateway catches and
    turns into the HR fallback. Nothing here decides what an employee
    sees.
    """

    def __init__(self, settings: Settings | None = None, send: Transport | None = None) -> None:
        self._settings = settings or get_settings()
        self._send = send if send is not None else _send

    def generate(self, prompt: str) -> str:
        """Send `prompt` to the configured model and return its output.

        The output comes back exactly as the model produced it, including
        when it is not the JSON that was asked for. Checking that is the
        Gateway's job, and a provider that checked its own output would
        have to decide what to do with a bad answer - which the contracts
        already answer.
        """
        settings = self._settings
        body = json.dumps(
            {
                "model": settings.llm_model,
                "prompt": prompt,
                "stream": False,
                # The Gateway's prompt asks for JSON; this makes the model
                # constrain its output to it rather than hope.
                "format": "json",
                "think": THINK,
                "options": {
                    "temperature": TEMPERATURE,
                    "num_predict": MAX_ANSWER_TOKENS,
                },
                # Keep the model resident between questions. A cold load
                # of an 8B model measured 56 seconds here, which no
                # employee is going to wait through and the Gateway would
                # not let them - see TD-36.
                "keep_alive": settings.llm_keep_alive,
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            settings.llm_api_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            payload = json.loads(self._send(request, settings.llm_timeout_seconds))
        except urllib.error.HTTPError as refused:
            raise LLMError(self._describe(refused)) from None
        except urllib.error.URLError as unreachable:
            raise LLMError(
                f"could not reach the local model at {settings.llm_api_url}: {unreachable.reason}"
            ) from None
        except TimeoutError:
            raise LLMError(
                f"the local model did not answer within {settings.llm_timeout_seconds} seconds"
            ) from None
        except (json.JSONDecodeError, ValueError) as unreadable:
            raise LLMError(f"the model server's reply was not JSON: {unreadable}") from None

        return self._output_from(payload)

    @staticmethod
    def _output_from(payload: object) -> str:
        """The model's text, or a refusal naming what came instead.

        Ollama answers `{"response": "...", ...}`. An empty response is a
        failure rather than an empty answer: the Gateway would read it as
        output that is not valid JSON and fall back with a reason that
        points at the model's wording rather than at the model having said
        nothing at all.
        """
        if not isinstance(payload, dict):
            raise LLMError(
                f"the model server answered with {type(payload).__name__}, not an object"
            )

        output = payload.get("response")
        if output is None:
            raise LLMError("the model server's reply carried no 'response'")
        if not isinstance(output, str):
            raise LLMError(
                f"the model server's 'response' was {type(output).__name__}, not a string"
            )
        if not output.strip():
            raise LLMError("the model returned an empty answer")

        return output

    def _describe(self, refused: urllib.error.HTTPError) -> str:
        """An HTTP refusal, in the server's own words where it gave any.

        A 404 from Ollama means the model is not pulled, which is the
        mistake a teammate is most likely to make, so it is worth saying
        plainly rather than leaving as a status code.
        """
        detail = ""
        try:
            body = json.loads(refused.read() or b"{}")
            if isinstance(body, dict) and isinstance(body.get("error"), str):
                detail = f": {body['error']}"
        except (json.JSONDecodeError, ValueError, OSError):
            detail = ""

        if refused.code == 404:
            return (
                f"the local model {self._settings.llm_model!r} is not available "
                f"from {self._settings.llm_api_url}{detail}"
            )
        return f"the model server answered {refused.code}{detail}"

    @property
    def name(self) -> str:
        return f"real ({self._settings.llm_model})"


def _send(request: urllib.request.Request, timeout: float) -> bytes:
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


__all__ = [
    "MAX_ANSWER_TOKENS",
    "TEMPERATURE",
    "THINK",
    "RealLLMClient",
    "Transport",
]
