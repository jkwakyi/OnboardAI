# The evaluation question set

Thirty questions about the synthetic handbook in [`../handbook/`](../handbook/),
used to measure how well OnboardAI answers and, just as importantly, how well
it declines to answer.

`questions.json` is the file. ON-24 runs the assistant against it and tunes the
relevance threshold; ON-26 uses a subset for the alpha smoke test.

## Shape

Twenty questions are **answerable** from the corpus. Each carries the expected
answer, the document and the section that answers it, and a sentence quoted
from that section:

```json
{
  "id": "EVAL-06",
  "question": "How much is the employee referral bonus?",
  "answerable": true,
  "expected_fallback": false,
  "expected_answer": "2,000 US dollars.",
  "source_document": "03-compensation-and-payroll.txt",
  "source_section": "3.4",
  "supporting_text": "bonus of 2,000 US dollars."
}
```

Ten are **unanswerable**. The handbook genuinely does not cover them, so the
correct behaviour is the HR fallback — `fallback: true` and a message pointing
the employee at HR — rather than an invented policy. Each names the deliberate
gap in the corpus it relies on:

```json
{
  "id": "EVAL-26",
  "question": "How much severance would I receive if my role were eliminated?",
  "answerable": false,
  "expected_fallback": true,
  "gap": "severance"
}
```

An unanswerable question has no `expected_answer` and no `source_section`:
there is nothing to cite.

## The twenty answerable questions

| ID | Question | Source |
| --- | --- | --- |
| EVAL-01 | When did the Portland office open? | 1.2 |
| EVAL-02 | When does the fiscal year run? | 1.5 |
| EVAL-03 | How long is the introductory period for a new employee? | 2.2 |
| EVAL-04 | What are the core hours? | 2.3 |
| EVAL-05 | How often are employees paid? | 3.1 |
| EVAL-06 | How much is the employee referral bonus? | 3.4 |
| EVAL-07 | How many days of paid time off do I accrue in my fourth year? | 4.1 |
| EVAL-08 | How many paid company holidays are there each year? | 4.4 |
| EVAL-09 | How much paid parental leave does a primary caregiver receive? | 4.5 |
| EVAL-10 | What does the company match on the 401(k)? | 5.3 |
| EVAL-11 | What is the monthly wellness stipend? | 5.4 |
| EVAL-12 | How many counselling sessions does the Employee Assistance Programme cover? | 5.5 |
| EVAL-13 | What is the most a gift from a supplier may be worth for me to accept it? | 6.6 |
| EVAL-14 | How quickly must I disclose a conflict of interest? | 6.5 |
| EVAL-15 | What is the minimum password length? | 7.2 |
| EVAL-16 | What are the four data classification levels? | 7.4 |
| EVAL-17 | How quickly must I report a suspected security incident? | 7.7 |
| EVAL-18 | When are performance reviews held? | 8.5 |
| EVAL-19 | How long does a performance improvement plan run? | 8.7 |
| EVAL-20 | What is my annual professional development budget? | 8.8 |

All eight handbook documents are covered; a test fails if any document is
never asked about.

## The ten unanswerable questions

| ID | Question | Gap it relies on |
| --- | --- | --- |
| EVAL-21 | Do I get stock options or equity as part of my package? | stock options or equity |
| EVAL-22 | How is the sales commission structure calculated? | sales commission |
| EVAL-23 | Am I paid while serving jury duty? | jury duty |
| EVAL-24 | What is the military leave policy for reservists? | military leave |
| EVAL-25 | Does the company pay relocation assistance if I move for the job? | relocation assistance |
| EVAL-26 | How much severance would I receive if my role were eliminated? | severance |
| EVAL-27 | Does Larkfield Systems sponsor work visas? | visa sponsorship |
| EVAL-28 | Is there a commuter benefit or a parking allowance at the offices? | commuter benefits |
| EVAL-29 | Can I take a sabbatical after five years of service? | sabbatical |
| EVAL-30 | Is there a childcare subsidy or backup care benefit? | childcare subsidy |

Each gap is one the handbook tests assert stays empty, so these questions
cannot quietly become answerable.

## Why the tests matter

`backend/tests/test_evaluation_questions.py` checks the set against the
handbook itself rather than taking it on trust. For every answerable question
it verifies the source document exists, the section number exists in that
document, the quoted sentence really appears there, and every figure in the
expected answer appears in that document.

A wrong expected answer or a stale section number is worth catching here. If
it survived to ON-24 it would look like the assistant getting an answer wrong,
and the hunt would start in the wrong place.

Run them with:

```bash
cd backend && pytest tests/test_evaluation_questions.py
```
