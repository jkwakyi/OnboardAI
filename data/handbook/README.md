# The synthetic company handbook

The approved HR document set OnboardAI answers from. It is the input for the
evaluation question set (ON-23) and the alpha end-to-end smoke test (ON-26).

**Larkfield Systems is a fictional company.** Every name, figure, address and
policy here is invented for testing. No real employee, company or customer
data appears in this corpus, and every document carries a notice saying so.

## What is here

Eight documents, each provided as both TXT and PDF:

| # | Document | Covers |
| --- | --- | --- |
| 1 | Welcome and Company Overview | Founding, offices, headcount, leadership, departments, values, fiscal year, all-hands schedule |
| 2 | Employment Policies | Employment categories, introductory period, working hours, core hours, remote and hybrid rules, attendance, resignation notice |
| 3 | Compensation and Payroll | Pay schedule, salary bands, overtime, referral bonus, expense rules, meal allowance, payroll errors |
| 4 | Time Off and Leave | PTO accrual and carryover, sick leave, the 11 company holidays, parental leave, bereavement, unpaid leave |
| 5 | Benefits and Wellbeing | Enrolment, medical and dental cost share, 401(k) match, wellness stipend, employee assistance programme, equipment stipends |
| 6 | Code of Conduct | Harassment, reporting routes, non-retaliation, conflicts of interest, gifts, outside employment, confidentiality |
| 7 | IT Security and Acceptable Use | Multi-factor authentication, passwords, devices, the four data classification levels, acceptable use, incident reporting, training |
| 8 | Onboarding, Training and Performance | First week, onboarding buddy, 30/60/90 check-ins, review cycle, promotion, improvement plans, development budget |

`txt/` holds the source of truth. `pdf/` is generated from it by
`scripts/build_handbook_pdfs.py` — edit the TXT, never the PDF, then
regenerate.

Each fact lives in exactly one document. Documents cross-reference each other
by number rather than repeating a figure, so retrieval can never surface two
contradictory sources for the same question.

## Answerable questions

ON-23 needs 20 answerable questions. The corpus carries well over that number
of specific, checkable facts. A sample, one per document, with the section that
answers it:

| Question | Answer | Source |
| --- | --- | --- |
| When was the Portland office opened? | 2019 | 1.2 |
| How long is the introductory period? | 90 calendar days | 2.2 |
| What are the core hours? | 10:00–16:00 Eastern Time | 2.3 |
| How often are employees paid? | Semi-monthly, the 15th and the last business day | 3.1 |
| What is the referral bonus? | 2,000 US dollars | 3.4 |
| How long do I have to submit an expense claim? | 30 days | 3.5 |
| How much PTO do I accrue in my fourth year? | 20 days | 4.1 |
| How many PTO days can I carry over? | Five, used by 31 March | 4.2 |
| How many paid company holidays are there? | 11 | 4.4 |
| How much paid leave does a primary caregiver get? | 12 weeks at full pay | 4.5 |
| What is the 401(k) match? | 4 per cent of base salary, vesting immediately | 5.3 |
| What is the monthly wellness stipend? | 75 US dollars | 5.4 |
| How many counselling sessions does the assistance programme cover? | Six per year | 5.5 |
| What is the gift limit? | 100 US dollars | 6.6 |
| How quickly must I disclose a conflict of interest? | Within 10 business days | 6.5 |
| What is the minimum password length? | 14 characters | 7.2 |
| What are the four data classification levels? | Public, Internal, Confidential, Restricted | 7.4 |
| How quickly must a security incident be reported? | Within one hour | 7.7 |
| When are performance reviews held? | April and October | 8.5 |
| How long does a performance improvement plan run? | 60 days | 8.7 |
| What is the annual development budget? | 1,500 US dollars per fiscal year | 8.8 |

## Deliberate gaps

ON-23 also needs 10 questions the handbook **cannot** answer, so the HR
fallback path can be tested. These gaps are intentional — do not fill them
without updating ON-23.

Topics absent entirely:

1. Stock options, equity or an employee share scheme
2. Sales commission structure
3. Jury duty leave
4. Military and veteran leave
5. Relocation assistance
6. Severance or redundancy pay
7. Visa and immigration sponsorship
8. Commuter benefits and office parking
9. Sabbaticals
10. Childcare subsidy or backup care
11. Tuition reimbursement for a degree programme
12. Whether pets are allowed in the offices

Topics mentioned but deliberately left without figures, so a question about
the number has no answer in the corpus:

13. Medical and dental deductibles and co-payments (5.2 points at the benefits
    portal instead)
14. The dollar ranges of salary bands L1 to L6 (3.2 points at the intranet)
15. The detail of the approval process for working outside the United States
    (2.4 states only that approval is required)

## Regenerating the PDFs

From the repository root, with the backend virtual environment active:

```bash
python scripts/build_handbook_pdfs.py
```

The script is idempotent. `pytest -m handbook` from `backend/` checks that
every TXT has a matching PDF and that the PDFs are readable.
