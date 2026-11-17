"""Faults for the Real LLM Client (ON-18).

This is the component that makes the system stop being a demo, and its
failure modes split cleanly in two.

Half are about *not answering*: a model server that is down, a model that
was never pulled, a reply that is not what Ollama sends. None of those
may reach an employee as an error, so each has to raise `LLMError` and be
turned into the HR fallback by the Gateway. A client that raised
something else, or returned a string anyway, breaks that.

The other half are about *answering too slowly or too freely*, and those
are the quiet ones. Thinking left on, the token cap removed, the model
unloaded between questions - none of them changes a single answer. They
change how long the answer takes, and the only visible symptom is an
employee getting the HR fallback for a question the handbook covers,
intermittently, with a timeout in a log nobody reads.

Five are changes somebody would make on purpose:

* "reasoning is left on" is the default, and the obvious thing to do is
  nothing. It triples the generated tokens for an identical answer and
  spends most of the Gateway's twenty seconds on text the JSON check
  throws away.
* "the client parses the model's output" is what anybody writes who has
  not read the Gateway. It looks like validation. It moves the decision
  the contracts gave the Gateway into a component that cannot make it,
  and an answer the Gateway would have refused comes back looking fine.
* "the socket timeout becomes the contractual one" looks like removing a
  confusing duplicate number. The employee's wait silently becomes 30
  seconds instead of 20.
* "the model is unloaded between questions" looks like being a good
  citizen with somebody else's VRAM. It adds a 56-second load to the
  first question after any pause, which the Gateway will not wait for.
* "an empty answer is passed on" looks like faithfully returning what the
  model said. It arrives at the Gateway as "the output was not valid
  JSON", which sends whoever is debugging it to look at the model's
  wording rather than at the model having said nothing.
"""

TESTS = [
    "tests/test_llm_real.py",
    "tests/test_llm_provider.py",
    "tests/test_llm_gateway.py",
    "tests/test_config.py",
    "tests/test_qa_controller.py",
]

REAL = "app/services/llm/real.py"
PACKAGE = "app/services/llm/__init__.py"
CONFIG = "app/config.py"

FAULTS = [
    # --- how long an answer is allowed to take -------------------------
    (
        # The quiet one. Same answer, same citation, three times the
        # tokens, and the Gateway's budget gone.
        "reasoning is left on, so most of the 20 seconds go on discarded tokens",
        REAL,
        "THINK = False",
        "THINK = True",
    ),
    (
        "the think flag is not sent at all, so the model's default decides",
        REAL,
        '                "think": THINK,\n',
        "",
    ),
    (
        "nothing caps how long an answer may run",
        REAL,
        '                    "num_predict": MAX_ANSWER_TOKENS,\n',
        "",
    ),
    (
        "the answer cap is raised past what 20 seconds can generate",
        REAL,
        "MAX_ANSWER_TOKENS = 400",
        "MAX_ANSWER_TOKENS = 4000",
    ),
    (
        "the model is unloaded between questions, so the next one pays the load",
        REAL,
        '                "keep_alive": settings.llm_keep_alive,\n',
        "",
    ),
    (
        "the model answers differently each time it is asked",
        REAL,
        "TEMPERATURE = 0.0",
        "TEMPERATURE = 1.0",
    ),
    # --- the request ----------------------------------------------------
    (
        "the prompt the Gateway built is not what gets sent",
        REAL,
        '                "prompt": prompt,',
        '                "prompt": prompt[:200],',
    ),
    (
        "a model other than the configured one answers",
        REAL,
        '                "model": settings.llm_model,',
        '                "model": "llama3.2:latest",',
    ),
    (
        "the model is not asked to constrain its output to JSON",
        REAL,
        '                "format": "json",\n',
        "",
    ),
    (
        "the reply is streamed, so it arrives as a run of JSON objects",
        REAL,
        '                "stream": False,',
        '                "stream": True,',
    ),
    (
        "it is sent somewhere other than the configured URL",
        REAL,
        "            settings.llm_api_url,",
        '            "http://127.0.0.1:11434/api/chat",',
    ),
    (
        "it is sent as a GET, which carries no prompt",
        REAL,
        '            method="POST",',
        '            method="GET",',
    ),
    (
        # There is no key for a local model, and a header that looks like
        # one is a thing somebody later tries to fill in.
        "a credential header is sent to a local model",
        REAL,
        '            headers={"Content-Type": "application/json"},',
        '            headers={"Content-Type": "application/json", "Authorization": "Bearer key"},',
    ),
    # --- the wait ---------------------------------------------------------
    (
        "the socket timeout quietly becomes the employee's wait",
        CONFIG,
        "    llm_timeout_seconds: float = 30.0",
        "    llm_timeout_seconds: float = 20.0",
    ),
    (
        "a timeout shorter than the Gateway's is accepted",
        CONFIG,
        "        if value <= GATEWAY_TIMEOUT_SECONDS:",
        "        if False:",
    ),
    (
        "config's copy of the Gateway limit drifts from the Gateway's",
        CONFIG,
        "GATEWAY_TIMEOUT_SECONDS = 20.0",
        "GATEWAY_TIMEOUT_SECONDS = 60.0",
    ),
    (
        "the call is made with no timeout at all",
        REAL,
        "            payload = json.loads(self._send(request, settings.llm_timeout_seconds))",
        "            payload = json.loads(self._send(request, None))",
    ),
    # --- a provider that cannot answer --------------------------------------
    (
        "a model server that is not running raises something the Gateway does not catch",
        REAL,
        "        except urllib.error.URLError as unreachable:\n            raise LLMError(",
        "        except urllib.error.URLError as unreachable:\n            raise RuntimeError(",
    ),
    (
        "an HTTP refusal raises something the Gateway does not catch",
        REAL,
        "        except urllib.error.HTTPError as refused:\n            raise LLMError(self._describe(refused)) from None",
        "        except urllib.error.HTTPError as refused:\n            raise RuntimeError(self._describe(refused)) from None",
    ),
    (
        "a timeout raises something the Gateway does not catch",
        REAL,
        "        except TimeoutError:\n            raise LLMError(",
        "        except TimeoutError:\n            raise RuntimeError(",
    ),
    (
        "the refusal does not say which URL was tried",
        REAL,
        '                f"could not reach the local model at {settings.llm_api_url}: {unreachable.reason}"',
        '                "could not reach the local model"',
    ),
    (
        "a model that was never pulled is reported as an ordinary failure",
        REAL,
        "        if refused.code == 404:",
        "        if False:",
    ),
    (
        "the refusal does not name the model that is missing",
        REAL,
        '                f"the local model {self._settings.llm_model!r} is not available "',
        '                "the local model is not available "',
    ),
    (
        "the server's own words are dropped from the refusal",
        REAL,
        '                detail = f": {body[\'error\']}"',
        '                detail = ""',
    ),
    (
        "a reply that is not JSON raises something the Gateway does not catch",
        REAL,
        "        except (json.JSONDecodeError, ValueError) as unreadable:\n            raise LLMError(",
        "        except (json.JSONDecodeError, ValueError) as unreadable:\n            raise RuntimeError(",
    ),
    # --- what comes back ------------------------------------------------------
    (
        # The one that moves a decision out of the Gateway.
        "the client parses the model's output rather than passing it on",
        REAL,
        "        return self._output_from(payload)",
        "        return json.dumps(json.loads(self._output_from(payload)))",
    ),
    (
        "the output is trimmed here rather than left to the Gateway",
        REAL,
        "        return output",
        "        return output.strip()",
    ),
    (
        "a reply that is not an object is read as one anyway",
        REAL,
        "        if not isinstance(payload, dict):",
        "        if False and not isinstance(payload, dict):",
    ),
    (
        "a reply carrying no response is answered with nothing",
        REAL,
        "        if output is None:\n            raise LLMError(\"the model server's reply carried no 'response'\")",
        '        if output is None:\n            return ""',
    ),
    (
        "a response that is not a string is forced into one",
        REAL,
        "        if not isinstance(output, str):",
        "        output = str(output)\n        if False:",
    ),
    (
        "an empty answer is passed on as though the model had answered",
        REAL,
        '        if not output.strip():\n            raise LLMError("the model returned an empty answer")\n',
        "",
    ),
    (
        "it reads a field Ollama does not send",
        REAL,
        '        output = payload.get("response")',
        '        output = payload.get("text")',
    ),
    # --- selection ---------------------------------------------------------------
    (
        "the real provider cannot be selected",
        PACKAGE,
        'PROVIDERS: dict[str, type[LLMProvider]] = {"mock": MockLLM, "real": RealLLMClient}',
        'PROVIDERS: dict[str, type[LLMProvider]] = {"mock": MockLLM}',
    ),
    (
        "the real provider becomes the default, so CI needs a GPU",
        CONFIG,
        '    llm_provider: str = "mock"',
        '    llm_provider: str = "real"',
    ),
    (
        "an unknown provider quietly becomes the mock",
        PACKAGE,
        "    try:\n        provider = PROVIDERS[name]\n    except KeyError:",
        "    try:\n        provider = PROVIDERS[name]\n    except KeyError:\n        return MockLLM()\n    if False:",
    ),
    (
        "selecting the mock no longer says so",
        PACKAGE,
        '        logger.warning(\n            "LLM_PROVIDER=mock: answering with the Mock LLM, which does not "',
        '        logger.debug(\n            "LLM_PROVIDER=mock: answering with the Mock LLM, which does not "',
    ),
    (
        "the configured model is not part of the provider's name",
        REAL,
        '        return f"real ({self._settings.llm_model})"',
        '        return "real"',
    ),
    (
        "building the client reaches for the model",
        REAL,
        "        self._send = send if send is not None else _send",
        "        self._send = send if send is not None else _send\n        self.generate('warm up')",
    ),
]
