# ORBIT Architecture & Migration Notes

## Existing architecture inspected

The supplied repository contains a compact Python 3.10+ / Streamlit application backed by SQLite. It is deliberately local and simulation-only.

| Module | Existing responsibility |
|---|---|
| `app.py` | Single-page Streamlit dashboard, sample-case selection, workflow history, evidence, approval and audit views |
| `pipeline.py` | Supervisor orchestration, stage persistence, failure recovery, approval-gated simulated actions |
| `agents.py` | Deterministic Research, Analysis, Validation and Action agents |
| `storage.py` | SQLite schema, sample-data seeding, persistence and read helpers |
| `sample_data.py` | Six simulated shipment records and four local example policies |
| `evaluation.py` | Small six-case baseline comparison and safety/recovery checks |
| `tests/` | Authentication, schema migration, workflow, ownership, approval and recovery tests |
| `auth.py` | Local password authentication, User/Administrator roles, and admin promotion |

### Existing capabilities retained

- Shipment-claim classification for delay, damage, lost and delivery-dispute examples.
- Evidence collection from local sample records and local example policy rules.
- Persisted agent events, audit entries, decisions, approvals and simulated actions.
- Human approval gate for sensitive simulated actions.
- Resume after a persisted stage failure.
- Existing evaluation and test suite.

### Technical limitations found

- The supplied implementation is deterministic; it does not contain an LLM integration, live carrier API, external document retrieval, or production claim adjudication.
- The existing dashboard is a single dark-themed Streamlit application, not a multi-page enterprise application.
- Original workflow stages were mostly linear and always included Research, Analysis, Validation and Action.
- No persistent reviewer-feedback table, explicit debate record, support-score rubric, or decision graph existed.
- Existing sample policies are educational local examples, not official carrier policy.
- Existing evaluation covers six cases and cannot establish real-world predictive calibration.
- Authentication is local and intended for a single-machine demonstration, not production identity management.

## ORBIT incremental architecture

The existing pipeline remains the source of truth. The new `orbit_intelligence.py` module adds deterministic, inspectable intelligence derived from actual workflow state:

1. **Adaptive plan** — selects investigation and debate when required documents are missing, a delivery dispute/high-exposure signal is present, or complaint text indicates a conflict. It records selected and skipped agents with reasons.
2. **Debate trace** — creates a bounded, two-round challenge record from the Analysis and Validation outputs. It does not pretend that independent LLM agents ran; it labels the rule-derived positions and unresolved evidence gaps.
3. **Uncertainty engine** — calculates a configurable-style weighted support heuristic from completeness, reliability, consistency, policy clarity and historical similarity. It explicitly does not call the score a probability or calibrated confidence.
4. **Decision graph** — persists inspectable nodes and links for claim, shipment, evidence, policy, findings, debate, uncertainty, validation and recommendation.
5. **Feedback memory** — stores reviewer feedback in a separate SQLite table with versions, reviewer, rationale and deletion support. Feedback never rewrites policy.
6. **Adversarial lab inventory** — supplies clearly labeled simulated scenario categories. This is a scenario catalog, not yet a full automated adversarial benchmark runner.

### Data flow

`Claim → Existing Research → Existing Analysis → Existing Validation → Adaptive plan / Debate / Uncertainty / Decision graph → Existing approval-gated Action`

The existing sample shipment records remain the only shipment source. Every sample record and action remains simulation-only.

## Migration strategy

- Keep Python + Streamlit + SQLite; no new runtime dependencies are required.
- Preserve existing workflow behavior and function call compatibility while adding optional ownership and authorization context.
- Add the intelligence module and one additive `orbit_feedback` table.
- Add a role column to the existing account database and an owner column to workflow runs. Existing accounts default to User; ownerless historical runs are visible to Administrators.
- Persist new derived state inside each run's existing `state_json`.
- Keep human approval and simulation-only action semantics, requiring a persisted Administrator role for decisions.
- Filter user claim history and feedback by the signed-in account; Administrators can review all accounts' records.
- Add UI workbench panels without removing the original claim workflow and audit history.
- Run the existing unit tests after changes.

## New modules and artifacts

- `orbit_intelligence.py` — adaptive planning, bounded debate, uncertainty scoring, decision graph, feedback memory and scenario catalog.
- `auth.py` — salted password hashing, role migration, role lookup and local Administrator promotion.
- `ORBIT_ARCHITECTURE.md` — this architecture and migration record.

## Known gaps / production roadmap

- The plan is adaptive metadata over the current deterministic pipeline; it does not yet dynamically skip pipeline stages.
- Debate is a structured rule-derived challenge trace, not autonomous LLM-to-LLM deliberation.
- The reliability component is a conservative heuristic for local demo data, not source-authenticated carrier evidence.
- Historical feedback retrieval is exact shipment-ID matching, not semantic embeddings.
- The adversarial page currently catalogs scenarios; automated injection, expected-vs-actual scoring, and regression reporting remain future work.
- The dashboard is still Streamlit, with workbench tabs rather than a fully separate routed multi-page frontend.
- Replace local sign-in and the local admin-promotion command with a production identity provider before deployment. Add session hardening, encryption, retention configuration, secure document parsing, observability, rate limits, calibrated evaluation and external integrations before any production deployment.

## Safety and interpretation

ORBIT's support score is an explainable heuristic. It is not a probability, model confidence, or a claim outcome guarantee. A high support score does not bypass existing approval gates. No real shipment, refund, payment or support action is executed. Human feedback is stored as a historical observation and never changes official policy automatically.
