"""Faults for the QA Controller (ON-46).

This component makes one decision, and the failure that matters is not
the obvious one. A controller that returned an answer where it should
have returned a fallback would be caught by almost anything. A controller
that returns the fallback *after* asking the model is indistinguishable
from a correct one in its output, and is a different system: it spends a
model call and up to twenty seconds on every unanswerable question, and
it hands the model a direct question over five irrelevant sections, which
is how a confident invented policy gets written. So several of these
faults leave the result untouched and change only whether the provider
was called.

Four are changes somebody would make on purpose:

* "the model is asked anyway and its answer thrown away below the
  threshold" looks like simpler control flow, and the output is identical.
  It is the fault this whole test file exists for.
* "the average score decides instead of the best" looks more robust than
  trusting one number. The top-5 cut returns five results whatever
  happens, so most of them are padding, and averaging them in refuses
  nearly every real question.
* "a retrieval failure is allowed to propagate" looks like not hiding
  errors. It shows an employee a 500 for a provider having a bad minute,
  when the contracts say that case returns the fallback.
* "the Gateway's fallback is re-judged here" looks like defensive
  programming. It is two components deciding one thing, and the second
  one has less to go on.
"""

TESTS = [
    "tests/test_qa_controller.py",
    "tests/test_config.py",
    "tests/test_llm_gateway.py",
    "tests/test_retrieval.py",
]

CONTROLLER = "app/services/qa/controller.py"
PACKAGE = "app/services/qa/__init__.py"
CONFIG = "app/config.py"

FAULTS = [
    # --- skipping the LLM, which is the whole ticket --------------------
    (
        # The quiet one: same answer, same fallback flag, same everything -
        # except the model was asked.
        "the model is asked anyway and its answer thrown away below the threshold",
        CONTROLLER,
        "        best = sections[0].score\n        if best < self.threshold:",
        "        best = sections[0].score\n        self.gateway.answer(question, to_prompt_sections(sections))\n        if best < self.threshold:",
    ),
    (
        "the threshold is not applied at all",
        CONTROLLER,
        "        if best < self.threshold:",
        "        if False:",
    ),
    (
        "the comparison is the wrong way round, so only good matches are refused",
        CONTROLLER,
        "        if best < self.threshold:",
        "        if best > self.threshold:",
    ),
    (
        "a score exactly on the threshold is refused",
        CONTROLLER,
        "        if best < self.threshold:",
        "        if best <= self.threshold:",
    ),
    (
        "the threshold is read once at import rather than from the instance",
        CONTROLLER,
        "        if best < self.threshold:",
        "        if best < 0.22:",
    ),
    # --- which score decides ---------------------------------------------
    (
        "the average score decides instead of the best",
        CONTROLLER,
        "        best = sections[0].score",
        "        best = sum(s.score for s in sections) / len(sections)",
    ),
    (
        "the worst of the five decides",
        CONTROLLER,
        "        best = sections[0].score",
        "        best = min(s.score for s in sections)",
    ),
    (
        "the distance is compared against the threshold rather than the score",
        CONTROLLER,
        "        best = sections[0].score",
        "        best = sections[0].distance",
    ),
    # --- nothing retrieved ------------------------------------------------
    (
        "an empty retrieval is passed to the Gateway rather than refused here",
        CONTROLLER,
        "        if not sections:\n            return self._fallback(\"nothing was retrieved for the question\", retrieved=0)",
        "        if False:\n            return self._fallback(\"nothing was retrieved for the question\", retrieved=0)",
    ),
    (
        "an empty retrieval reports a best score it never saw",
        CONTROLLER,
        '            return self._fallback("nothing was retrieved for the question", retrieved=0)',
        '            return self._fallback(\n                "nothing was retrieved for the question", best_score=0.0, retrieved=0\n            )',
    ),
    # --- a failure in the AI path -----------------------------------------
    (
        "a retrieval failure is allowed to propagate to the employee",
        CONTROLLER,
        "        except Exception as failure:  # noqa: BLE001 - never surfaced to an employee",
        "        except KeyboardInterrupt as failure:",
    ),
    (
        "a retrieval failure leaves nothing in the log for whoever has to fix it",
        CONTROLLER,
        '            logger.exception("retrieval failed for a question")',
        '            logger.debug("retrieval failed for a question")',
    ),
    (
        "the reason for a retrieval failure loses what actually went wrong",
        CONTROLLER,
        '            return self._fallback(f"retrieval failed: {type(failure).__name__}: {failure}")',
        '            return self._fallback("retrieval failed")',
    ),
    # --- the Gateway's verdict ---------------------------------------------
    (
        "the Gateway's fallback is re-judged here and reported as an answer",
        CONTROLLER,
        "            fallback=result.fallback,",
        "            fallback=False,",
    ),
    (
        "a fallback from the Gateway loses the score that got it there",
        CONTROLLER,
        "        result = self.gateway.answer(question, to_prompt_sections(sections))\n        return self._from_gateway(result, best_score=best, retrieved=len(sections))",
        "        result = self.gateway.answer(question, to_prompt_sections(sections))\n        return self._from_gateway(result, best_score=None, retrieved=len(sections))",
    ),
    (
        "the Gateway's citations are dropped on the way out",
        CONTROLLER,
        "            citations=list(result.citations),",
        "            citations=[],",
    ),
    (
        "the Gateway's own answer is replaced by the fallback message",
        CONTROLLER,
        "            answer=result.answer,",
        "            answer=HR_FALLBACK_MESSAGE,",
    ),
    (
        "the reason the Gateway gave is lost",
        CONTROLLER,
        "            reason=result.reason,",
        "            reason=None,",
    ),
    # --- what the employee reads -------------------------------------------
    (
        "the fallback tells the employee about the threshold",
        CONTROLLER,
        "        return Answer(\n            answer=HR_FALLBACK_MESSAGE,",
        "        return Answer(\n            answer=HR_FALLBACK_MESSAGE + ' ' + reason,",
    ),
    (
        "a refusal comes back carrying citations to the sections it refused",
        CONTROLLER,
        "            answer=HR_FALLBACK_MESSAGE,\n            citations=[],",
        "            answer=HR_FALLBACK_MESSAGE,\n            citations=[Citation(section_id=0, heading=None)],",
    ),
    (
        "a refusal is not marked as a fallback",
        CONTROLLER,
        "            citations=[],\n            fallback=True,",
        "            citations=[],\n            fallback=False,",
    ),
    (
        "the score and the threshold are not recorded in the reason",
        CONTROLLER,
        '                f"the best match scored {best:.3f}, below the threshold of {self.threshold:.3f}",',
        '                "the best match was not good enough",',
    ),
    # --- what the log and ON-24 need ----------------------------------------
    (
        "a below-threshold refusal does not say how many sections it saw",
        CONTROLLER,
        "                best_score=best,\n                retrieved=len(sections),",
        "                best_score=best,\n                retrieved=0,",
    ),
    (
        "a below-threshold refusal does not report the score it refused",
        CONTROLLER,
        "                best_score=best,\n                retrieved=len(sections),",
        "                best_score=None,\n                retrieved=len(sections),",
    ),
    (
        "an Answer can be rewritten after the Chat API has it",
        CONTROLLER,
        "@dataclass(frozen=True)\nclass Answer:",
        "@dataclass\nclass Answer:",
    ),
    # --- the join to the two neighbours --------------------------------------
    (
        "the ranking is lost on the way into the prompt",
        CONTROLLER,
        "    return [\n        PromptSection(",
        "    sections = sorted(sections, key=lambda s: s.section_id, reverse=True)\n    return [\n        PromptSection(",
    ),
    (
        "the prompt is built from the headings rather than the text",
        CONTROLLER,
        "            text=section.text,",
        "            text=section.heading or section.text,",
    ),
    (
        "a citation loses the document it came from",
        CONTROLLER,
        "            document=section.document,",
        "            document=None,",
    ),
    (
        "the section id the citation has to carry is the position instead",
        CONTROLLER,
        "            section_id=section.section_id,",
        "            section_id=section.position,",
    ),
    # --- configuration ---------------------------------------------------------
    (
        "the shipped threshold is not the one that was measured",
        CONFIG,
        "    relevance_threshold: float = 0.22",
        "    relevance_threshold: float = 0.5",
    ),
    (
        "a threshold no score could ever reach is accepted",
        CONFIG,
        "        if not -1.0 <= value <= 1.0:",
        "        if False:",
    ),
    (
        "only the upper end of the threshold is checked",
        CONFIG,
        "        if not -1.0 <= value <= 1.0:",
        "        if not value <= 1.0:",
    ),
    (
        "the controller ignores the configured threshold",
        CONTROLLER,
        "        self.threshold = threshold if threshold is not None else self._settings.relevance_threshold",
        "        self.threshold = threshold if threshold is not None else 0.22",
    ),
    (
        "the controller cannot build its own Gateway",
        CONTROLLER,
        "        self.gateway = gateway if gateway is not None else LLMGateway(get_provider(self._settings))",
        "        self.gateway = gateway",
    ),
    # --- what the package offers -------------------------------------------------
    (
        "the QA Controller stops exporting what the Chat API imports",
        PACKAGE,
        '__all__ = ["Answer", "QAController", "to_prompt_sections"]',
        '__all__ = ["QAController"]\ndel Answer, to_prompt_sections',
    ),
]
