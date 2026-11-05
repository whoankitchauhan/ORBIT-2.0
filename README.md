# ORBIT

**ORBIT** is a Delhivery-focused shipment-claim review application. A Supervisor coordinates four deterministic workflow agents—Research, Analysis, Validation, and Action—to review a complaint against local shipment records and claim policies. The optional AI Assistant uses retrieval-augmented generation (RAG) with local Ollama models to answer questions from those records.

> **Simulation notice:** Shipment records, tracking, documents, and policies are sample data. ORBIT has no Delhivery, payment, or support-system integration. Approving a sensitive action writes a simulated execution record only; it never changes a real shipment, issues a real refund, or creates a real ticket.

For a beginner-friendly setup, role, data-storage, and classroom walkthrough, see [PERSONAL.md](./PERSONAL.md).

## What it does

- Retrieves sample shipment, tracking, available-document, and policy evidence.
- Offers a chat assistant that embeds and retrieves relevant local shipment and policy records, then generates a cited answer with a locally running Ollama model.
- Identifies missing documents and evaluates visible thresholds for delay, damage, lost-shipment, and delivery-dispute claims.
- Validates each recommendation against its evidence and policy checks.
- Requires a recorded human decision before sensitive refund or claim-closure actions.
- Keeps workflow state, decisions, approvals, simulated action outcomes, agent events, and errors in SQLite.
- Resumes failed runs from the last successfully persisted agent result.
- Compares the same 21 sample cases with an intentionally simple “always eligible” baseline.
- Keeps chat inference and embeddings on the configured loopback Ollama service; it does not call a cloud AI API.

The rules and policy thresholds are educational examples, not official Delhivery policy or legal/financial guidance.

## Setup (Windows PowerShell)

Prerequisite: Python 3.10 or newer.

From the project folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

If PowerShell blocks activation, allow it for the current session:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Start the dashboard:

```powershell
python -m streamlit run app.py
```

Open the local URL printed by Streamlit (normally `http://localhost:8501`). Choose a sample case, review or edit the complaint, and select **Review claim**. A sensitive action remains pending until a reviewer submits an approval decision.

### Local AI Assistant (optional)

Install Ollama and make sure it is running. Download the models once:

```powershell
ollama pull qwen2.5:7b
ollama pull embeddinggemma:latest
ollama list
```

In ORBIT, open **AI Assistant** and ask a question about a shipment ID, tracking history, or claim policy. ORBIT embeds the current local shipment and policy records, retrieves the closest matching records, and sends only the question, recent chat turns, and retrieved context to the Ollama chat endpoint at `127.0.0.1`. Answers display their source IDs. The embedding index is held in that signed-in Streamlit session's memory; chat history is also session-only and is not saved to SQLite. The assistant reads shared shipment/policy source tables, not saved user claim history; all signed-in users can search the same current source rows.

Configure `ORBIT_OLLAMA_BASE_URL`, `ORBIT_OLLAMA_CHAT_MODEL`, `ORBIT_OLLAMA_EMBED_MODEL`, and `ORBIT_OLLAMA_TIMEOUT_SECONDS` in `.env` if needed. The application rejects non-loopback model URLs. Model downloads require an internet connection, but inference and embedding requests are local. Local inference by itself does not secure the Streamlit app, computer, database, or network. Because per-customer shipment authorization is not implemented, use only the supplied fictional data until approved source data and access controls are added.

`ORBIT_DB_PATH` in `.env` optionally selects the workflow SQLite database path. `ORBIT_AUTH_DB_PATH` selects the local account database. Relative paths resolve from this project directory; the defaults are `orbit_data.db` and `orbit_users.db`. Do not commit local databases or secrets.

## Evaluation and tests

The dashboard evaluation uses the same 21 representative sample cases for ORBIT and the baseline. The intentionally simple baseline marks every complaint eligible, retrieves no evidence, cannot resume a failure, and has no approval gate.

The dashboard reports metrics for the current 21-case dataset. Processing time varies by machine and load.

The dashboard recalculates decision accuracy, evidence completeness, and processing time. Its recovery and authorization checks use a temporary SQLite database.

Run the automated tests:

```powershell
python -m unittest discover -s tests -v
```

The tests cover representative decision outcomes, RAG retrieval and source attribution, input validation, evidence retrieval, account migration and password hashing, persisted theme preferences, administrator-guarded account listing and promotion, owner-scoped claim history, administrator-only approval, approval/rejection, prevention of execution before approval, persisted audit records, feedback ownership, and retry from a failed stage.

## Project layout

- `app.py` — Streamlit dashboard.
- `pipeline.py` — Supervisor workflow, persistence coordination, retry, and approval-gated simulated actions.
- `agents.py` — Research, Analysis, Validation, and Action agent logic.
- `local_rag.py` — Local document preparation, embedding retrieval, and Ollama answer generation.
- `storage.py` — SQLite schema, sample-data seeding, and read helpers.
- `auth.py` — Local account registration, password verification, role migration, theme preferences, and administrator-guarded account access.
- `sample_data.py` — Simulated Delhivery shipment cases and demo policy examples.
- `evaluation.py` — Same-dataset baseline comparison and safety/recovery checks.
- `tests/` — Standard-library automated tests.


## ORBIT intelligence workbench

The upgraded app adds a persisted adaptive execution plan, bounded evidence-linked debate trace, transparent decision-support heuristic, inspectable decision graph, reviewer feedback memory, and a simulated adversarial scenario catalog. These additions are implemented in `orbit_intelligence.py` and displayed in the ORBIT workbench.

The support score is a heuristic, not a probability or calibrated model confidence. Feedback is versioned separately and does not rewrite policy. The adversarial lab is currently a scenario inventory; automated benchmark execution remains future work. See `ORBIT_ARCHITECTURE.md` for the inspected baseline, migration notes and known limitations.


## Accounts and roles

Create accounts from the sign-in screen. New accounts—including accounts already present in an older database—have the **User** role. Users can create claims and access their own claim history and feedback. Only accounts with the **Administrator** role can view all users' claims or approve/reject sensitive simulated actions. Approval checks the role stored in the account database, not a name typed into the form.

Administrators also have a **User Access** page for searching the account directory and granting an existing User administrator access. The app verifies the signed-in administrator against the account database before listing accounts or changing a role. Role changes cannot be reversed from the app; there is no role-demotion control.

Choose **System**, **Light**, or **Dark** under **Appearance** in the sidebar. Signed-in accounts retain their selection; System follows the operating-system preference. The public home page also provides a theme selector.

To grant Administrator access, first create the account in the app, then run this command from the project folder:

```powershell
.\.venv\Scripts\python.exe auth.py promote-admin your-email@example.com
```

The app re-reads the role from the account database on each rerun; refresh the recipient's session after promotion. There are no built-in credentials or passwords. The command modifies the local SQLite account database; it should only be run by someone with trusted access to the project machine. User accounts and salted PBKDF2-HMAC-SHA256 password hashes are stored in `orbit_users.db` by default. This is a local demo identity system, not production identity management. Do not expose the app publicly without a proper identity provider, HTTPS, session hardening, rate limiting, and deployment security.

## ORBIT Command Center

After signing in, use the sidebar's **My Dashboard** (User) or **Admin Dashboard** (Administrator) for a compact, at-a-glance visual overview of the shipment-claim system. It shows persisted claim counts, the configured agent topology with statuses derived from recorded workflow events, the selected claim's decision/support details, recent claims, uncertainty components, and governance status. User accounts see their own records; administrators see all records. Use **New Claim** or **Claims & Approvals** to submit or review claims, and inspect detailed evidence, agent events, approvals, debate, decision graph, feedback, and adversarial scenarios. A user can submit and track a request; an administrator records the human approval or rejection. The dashboard does not invent live carrier activity; the project uses local simulated shipment records.
