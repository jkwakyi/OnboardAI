"""The QA Controller (ON-46).

The component the architecture diagram puts in the middle of the ask
flow: the Chat API hands it a question (step 3), it asks the Retrieval
Service for matching sections (step 4), and it builds the prompt through
the LLM Gateway when - and only when - there is a good match (step 7).

The "only when" is the whole ticket. Below the relevance threshold the
LLM is skipped entirely and the employee gets the HR fallback, because a
model asked a direct question over five irrelevant sections will usually
answer it from training data and sound exactly as confident as it does
when it is right.
"""

from app.services.qa.controller import Answer, QAController, to_prompt_sections

__all__ = ["Answer", "QAController", "to_prompt_sections"]
