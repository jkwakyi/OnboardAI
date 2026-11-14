"""Faults for the LLM Gateway (ON-45).

Nineteen single edits, each one a plausible mistake rather than a random
mutation: the kind of thing somebody tidying this file might do, or the
kind the first draft actually did.
"""

TESTS = "tests/test_llm_gateway.py"

GATEWAY = "app/services/llm/gateway.py"

FAULTS = [
    # The one the first draft of this component really got wrong.
    (
        "the timeout joins the thread it gave up on",
        GATEWAY,
        "        worker.join(self.timeout_seconds)",
        "        worker.join()",
    ),
    (
        "the timeout is never applied",
        GATEWAY,
        "        if worker.is_alive():",
        "        if False:",
    ),
    (
        "the contractual 20 seconds becomes something else",
        GATEWAY,
        "TIMEOUT_SECONDS = 20.0",
        "TIMEOUT_SECONDS = 120.0",
    ),
    (
        "a provider error escapes instead of becoming the fallback",
        GATEWAY,
        "        except LLMError as failed:",
        "        except LLMError as failed:\n            raise failed\n        except ValueError as failed:",
    ),
    (
        "an unexpected provider exception escapes",
        GATEWAY,
        "        except Exception as unexpected:",
        "        except KeyboardInterrupt as unexpected:",
    ),
    (
        "invalid JSON is passed on instead of refused",
        GATEWAY,
        '            return hr_fallback("the output was not valid JSON")',
        "            return GatewayResult(answer=output, citations=[], fallback=False)",
    ),
    (
        "a JSON array counts as an answer",
        GATEWAY,
        "        if not isinstance(parsed, dict):",
        "        if False:",
    ),
    (
        "an empty answer is accepted",
        GATEWAY,
        "        if not isinstance(answer, str) or not answer.strip():",
        "        if False:",
    ),
    (
        "a missing citations list is accepted",
        GATEWAY,
        "        if not isinstance(raw_citations, list):",
        "        if False:",
    ),
    (
        "an invented citation is kept",
        GATEWAY,
        "            if section is None:",
        "            if False:",
    ),
    (
        "an answer with no verifiable citation is let through",
        GATEWAY,
        "        if not citations:",
        "        if False:",
    ),
    (
        "the citation heading comes from the model",
        GATEWAY,
        "                    heading=section.heading,",
        '                    heading=raw.get("heading"),',
    ),
    (
        "the same section is cited twice",
        GATEWAY,
        "            if section_id in seen:",
        "            if False:",
    ),
    (
        "the question is not bounded",
        GATEWAY,
        "        asked = question.strip()[: self.max_question_characters]",
        "        asked = question.strip()",
    ),
    (
        "the retrieved text is left out of the prompt",
        GATEWAY,
        "            blocks.append(section.text.strip())",
        "            pass",
    ),
    (
        "the section markers are left out of the prompt",
        GATEWAY,
        "            blocks.append(",
        "            _unused = (",
    ),
    (
        "the model is asked even with nothing retrieved",
        GATEWAY,
        "        if not sections:",
        "        if False:",
    ),
    (
        "the fallback stops saying it is a fallback",
        GATEWAY,
        "fallback=True, reason=reason",
        "fallback=False, reason=reason",
    ),
    (
        "every fallback gets the same reason",
        GATEWAY,
        '    logger.warning("returning the HR fallback: %s", reason)',
        '    reason = "something went wrong"\n    logger.warning("returning the HR fallback: %s", reason)',
    ),
]
