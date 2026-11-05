# ORBIT: Personal Project Guide

This guide is for setting up, understanding, and presenting ORBIT on Windows. The project is a local demonstration: it does not connect to Delhivery or issue real refunds.

## What the project does

ORBIT takes a shipment complaint and checks it against a local sample shipment record and a local example policy. Its workflow has four steps:

1. **Research** collects the shipment, tracking, document, and policy information.
2. **Analysis** checks the information against the example policy.
3. **Validation** checks that the recommendation agrees with the evidence.
4. **Action** prepares a next step. A simulated refund or claim closure waits for an Administrator's approval.

In everyday language, ORBIT is like a digital checklist and filing cabinet: it gathers the information for a claim, shows how the checklist was applied, and saves the result for later review.

## Install and start the project

Open PowerShell in the project folder. Run these commands in order:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
python -m streamlit run app.py
```

Open the local address Streamlit prints (usually `http://localhost:8501`). If PowerShell refuses to activate the virtual environment, run this once in that PowerShell window and activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

To stop the app, focus the PowerShell window and press **Ctrl+C**. To run the automated checks instead:

```powershell
python -m unittest discover -s tests -v
```

## Register and sign in

1. Open ORBIT and select **Create account**.
2. Enter an email address and a password of at least eight characters.
3. Select **Create ORBIT account**, then use **Sign in** with that account.

Every new account starts with the **User** role. There are no default usernames or passwords. Users can submit claims and see their own claim history and feedback.

### Give an account Administrator access

First register the account in ORBIT. Then, from the project folder, run:

```powershell
.\.venv\Scripts\python.exe auth.py promote-admin your-email@example.com
```

Replace the example address with the registered account's email. The app re-reads roles from the account database on each rerun, so refresh the recipient's session after promotion. Only run this command on a computer you trust: someone with access to the project folder and terminal controls the local demo's Administrator accounts.

Administrators can see every account's claim records and approve or reject sensitive simulated actions. Approval checks the role saved in the account database; it is not granted by typing an administrator name into the app.

Administrators can also open **User Access** in the sidebar to search registered accounts and grant Administrator access. This action cannot be undone from the app; use it only for accounts that need organization-wide claim visibility and approval authority. Regular Users do not see this page.

Choose **System**, **Light**, or **Dark** under **Appearance** in the sidebar. Signed-in accounts retain their selection, and System follows the computer's appearance preference.

## Where the information is stored

The app uses local SQLite databases in the project folder by default:

- **`orbit_data.db`** contains the sample shipment and policy records, submitted complaints, workflow results, agent events, approval decisions, simulated action results, and audit history.
- **`orbit_users.db`** contains account email addresses, roles, salted password hashes, and account creation times. It does not store plain-text passwords.

The sample cases and example policies are defined in `sample_data.py`. When the app starts, `storage.py` copies them into the workflow database if they are not already there. Submitted claim details and review results are then saved to SQLite. New claims are attached to the signed-in account; a User sees only their own claims, while an Administrator can review all users' claims.

Both database paths can be changed in `.env` using `ORBIT_DB_PATH` and `ORBIT_AUTH_DB_PATH`. These are local files; do not share or commit them.

## Main features

- **Claim Workspace:** choose a sample shipment, enter a complaint, and run the review.
- **Evidence and policy:** inspect retrieved sample facts, missing documents, policy checks, and validation results.
- **Review history:** reopen saved claims. Failed workflows can resume from their last saved stage.
- **Approvals and actions:** an Administrator can approve/reject sensitive actions. A saved approval records a simulated result only; it does not contact a carrier, issue money, or create a ticket.
- **Command Center:** see counts and the selected claim. Counts and records are limited to the User's own data, or all data for an Administrator.
- **Decision workbench:** inspect the rule-derived debate, decision graph, support heuristic, reviewer feedback, and simulated scenario catalog. The support score is not a probability, and the scenario catalog is not an automated benchmark.
- **AI Assistant:** ask questions in plain language about a shipment ID, its tracking events, or a claim policy. ORBIT uses the locally installed Ollama embedding model to retrieve relevant local records, then asks the local chat model to answer with source IDs. Chat and embeddings are kept in the signed-in Streamlit session's memory, not persisted as chat history in SQLite.
- **Evaluation dashboard:** compare the local workflow with a deliberately simple baseline on the same 21 sample cases.

## A simple teacher demonstration

Prepare two accounts: one ordinary User and one Administrator. Use separate browser profiles (or sign out and back in) when showing the two roles.

1. Sign in as the User and submit **DLV-2401**, the sample nine-day delay. The workflow should find the shipment and policy information, recommend eligibility, and show that the sensitive action is waiting for human approval.
2. Sign in as the Administrator. Open the request from the Command Center or Claim Workspace, inspect its evidence and policy checks, and approve or reject it with a short note.
3. Reopen the request. Show the reviewer, saved decision, audit event, and simulated result. Explain that no real refund or shipment change happened.
4. Optionally submit **DLV-2403** to show how ORBIT identifies missing proof of delivery and requests more documents instead of automatically deciding the dispute.
5. Show the User view to demonstrate that it cannot see another account's claims or approve actions. Return to the Administrator view to show the broader review permissions.

## How to explain the project in one minute

“ORBIT is a local shipment-claim review application built with Python, Streamlit, and SQLite. A user submits a complaint about a shipment, and ORBIT gathers the matching local record and policy, checks the policy requirements, validates its recommendation, and saves the review. The separate AI Assistant lets users ask questions in plain language; it retrieves matching local shipment or policy records and uses Ollama on this computer to draft an answer with source IDs. Administrators review sensitive actions, which remain simulated and do not issue real refunds or update a carrier system.”

## Set up the local AI Assistant

The optional chat feature uses Ollama on this computer. Install Ollama, then download the chat and embedding models:

```powershell
ollama pull qwen2.5:7b
ollama pull embeddinggemma:latest
ollama list
```

Start Ollama and ORBIT, sign in, and select **AI Assistant** from the sidebar. Ask a question such as “What is the latest tracking update for DLV-2401?” or “What documents are needed for a delay claim?” ORBIT turns the local shipment and policy records into searchable text, asks the embedding model to represent them as vectors, compares the question vector with those records, and passes the most relevant records to the chat model. The answer includes source IDs so the user can see what information was retrieved.

The configured Ollama URL is restricted to this computer's loopback address. Model downloads need internet access, but normal chat and embedding requests go to the local Ollama service. Only retrieved context, recent turns in the current chat, and the question are included in the generation request. The vector index and chat history are held in the Streamlit session's memory; chat is not written to the workflow database. The assistant searches shared shipment and policy source tables, not saved claim history, and currently has no per-customer shipment authorization. Use only the fictional sample data until that access control is implemented. Local inference alone does not provide production access control, device security, network security, or confidentiality guarantees.

## Important limitations

The shipped shipment records and policy rules are fictional examples; workflow decisions are deterministic, and the app does not use a live carrier API. The AI Assistant is generative but can still make mistakes, so answers are informational and should be checked against the cited source records. Authentication and Administrator setup are local to this computer. Before using real customer or company data, replace the sample records with approved company sources, implement verified customer-to-shipment authorization, and complete security, privacy, and deployment reviews. Local Ollama inference does not by itself guarantee that company data cannot be accessed or exposed.

## Project ko bilkul simple Hinglish mein samjhein

ORBIT ko ek logistics company ke customer-complaint process ko aasaan banane ke liye banaya gaya local demo samjho. Socho ki pehle staff ko customer ki complaint phone par sunni padti thi, shipment ki details alag se dhoondhni padti thi, aur policy haath se padhkar decide karna padta tha ki case aage bhejna hai ya nahi. Is project ka idea hai ki in steps ko ek jagah par dikhaya aur organize kiya ja sake. Yeh company ke asli purane process ka verified record nahi hai; teacher ko ise proposed project scenario ke roop mein batana.

Customer app mein sign in karke ek supported sample shipment choose karta hai aur apni problem likhta hai—jaise parcel late hai, damaged mila, mila hi nahi, ya delivery par dispute hai. Demo mein shipment ID sample records mein honi chahiye; abhi user apne real parcel ko live tracking se search nahi kar sakta. Complaint submit karne ke baad ORBIT us sample case ka review shuru karta hai. Abhi alag se product-return process nahi bana hai; system supported shipment claims ka demo karta hai.

Pehle Research Agent us shipment ka local sample record, tracking updates, available documents aur us claim type ki example policy ikatthi karta hai. Phir Analysis Agent policy ke simple rules check karta hai—jaise delay kitne din ka hai, damage kitni jaldi report hua, ya lost parcel ka scan kitne din se nahi aaya. Aasaan bhaasha mein, yeh ek digital checklist ki tarah kaam karta hai; yeh official company policy ya kisi live delivery system ko check nahi karta.

Uske baad Validation Agent dekhta hai ki recommendation jama ki gayi information aur policy checks se match karti hai ya nahi. Agar zaroori invoice ya photo missing ho, system batata hai ki aur document chahiye. Agar delivery ka customer ke saath dispute ho, to case ko seedha final karne ke bajay human investigation ke liye rakha ja sakta hai. Isse reviewer ko samajh aata hai ki decision kis jaankari par based tha aur kya abhi missing hai.

Phir Action Agent agla step taiyaar karta hai. Sensitive kaam—jaise simulated refund ya claim close karna—automatic nahi hota: Administrator ko case dekhkar approve ya reject karna padta hai. Approve karne par bhi demo sirf database mein simulated result save karta hai; customer ko asli paise nahi bhejta aur carrier ko contact nahi karta. User apne cases dekh sakta hai, aur Administrator sabke cases review kar sakta hai.

Teacher ko company background ke liye sirf wahi baat fact ke roop mein batana jo aapke paas sach mein document ya proof se supported ho. Is code se yeh confirm nahi hota ki kisi company ne Letter of Intent diya hai, pehle sirf phone par complaints li jaati thi, ya uske paas online platform nahi tha. Is demo ke shipment records aur policies fictional examples hain. Seedhi baat: ORBIT customer ki complaint leta hai, sample shipment aur example policy se compare karta hai, missing information batata hai, decision ka reason dikhata hai, aur zaroori hone par human Administrator ko approval ke liye bhejta hai—lekin abhi yeh real company service nahi hai.
