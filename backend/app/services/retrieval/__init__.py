"""The Retrieval Service (ON-43).

One of the components the architecture diagram names. It sits between the
QA Controller and the two databases: the question goes in, the five
closest approved sections come out, each with the text to answer from and
a score to judge it by.

It deliberately knows nothing about the LLM. The QA Controller decides
whether the best score clears the relevance threshold and, if it does,
hands the sections to the LLM Gateway; retrieval ranking and prompt
building are different jobs and the contracts keep them in different
components.
"""

from app.services.retrieval.service import (
    TOP_K,
    RetrievedSection,
    relevance,
    retrieve,
)

__all__ = ["TOP_K", "RetrievedSection", "relevance", "retrieve"]
