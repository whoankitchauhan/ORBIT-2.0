"""Streamlit dashboard for ORBIT's simulated Delhivery shipment-claim workflow."""

from __future__ import annotations

import sqlite3
from typing import Any

import streamlit as st

from auth import authenticate_user, get_user, initialize_auth_database, register_user
from evaluation import run_evaluation
from local_rag import (
    LocalModelError,
    LocalRAGAssistant,
    OllamaSettings,
    build_retrieval_corpus,
)
from pipeline import (
    WorkflowError,
    decide_approval,
    resume_claim_workflow,
    start_claim_workflow,
)
from orbit_intelligence import list_feedback, save_feedback, delete_feedback, simulated_scenarios, similar_feedback
from storage import (
    get_db_path,
    get_run_details,
    initialize_database,
    list_runs,
    list_policies,
    list_shipments,
)

st.set_page_config(
    page_title="ORBIT | Delhivery Claims",
    page_icon="◉",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
      --orbit-bg: #f3f5f7;
      --orbit-surface: #ffffff;
      --orbit-ink: #172633;
      --orbit-muted: #637586;
      --orbit-line: #e0e6eb;
      --orbit-accent: #087e83;
      --orbit-accent-soft: #e8f4f3;
      --orbit-sidebar: #14232d;
      --primary-color: #087e83;
      --primaryColor: #087e83;
    }
    html, body, [class*="css"] { font-family: Inter, "Segoe UI", sans-serif; }
    .stApp, [data-testid="stAppViewContainer"] { background:var(--orbit-bg); color:var(--orbit-ink); }
    [data-testid="stHeader"] { background:rgba(243,245,247,.92); }
    [data-testid="stMain"] > div { padding-top:1.6rem; }
    [data-testid="stSidebar"] { background:var(--orbit-sidebar); border-right:1px solid #263944; }
    [data-testid="stSidebar"] > div:first-child { padding-top:1.3rem; }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color:#bdc9d1; }
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color:#98aab6; }
    [data-testid="stSidebar"] [data-testid="stRadio"] label { color:#e4ebef; }
    .orbit-brand { font:800 1.65rem 'Segoe UI',sans-serif; letter-spacing:.18em; color:#48b8ad; }
    .orbit-kicker { color:var(--orbit-muted); font-size:.7rem; letter-spacing:.15em; text-transform:uppercase; }
    [data-testid="stSidebar"] .orbit-kicker { color:#91a5b2; }
    .orbit-topbar { display:flex; justify-content:space-between; align-items:center; gap:1rem; padding:.7rem 1rem; margin-bottom:1rem; background:var(--orbit-surface); border:1px solid var(--orbit-line); border-radius:10px; color:var(--orbit-muted); font-size:.72rem; letter-spacing:.06em; }
    .orbit-topbar b { color:var(--orbit-accent); }
    .orbit-hero { position:relative; overflow:hidden; background:var(--orbit-surface); border:1px solid var(--orbit-line); border-radius:14px; padding:1.5rem 1.65rem; margin:.2rem 0 1rem; box-shadow:0 8px 26px rgba(24,43,56,.045); }
    .orbit-hero h1 { font:700 1.85rem 'Segoe UI',sans-serif; margin:.45rem 0 .45rem; color:var(--orbit-ink); letter-spacing:-.025em; }
    .orbit-hero p { color:var(--orbit-muted); margin:0; max-width:760px; line-height:1.65; }
    .orbit-pill { display:inline-block; border:1px solid #cce5e2; color:#176d6c; background:var(--orbit-accent-soft); border-radius:999px; padding:.3rem .65rem; font-size:.66rem; font-weight:700; letter-spacing:.08em; }
    .orbit-panel { background:var(--orbit-surface); border:1px solid var(--orbit-line); border-radius:12px; padding:1rem; min-height:120px; }
    .orbit-panel-title { color:var(--orbit-muted); font-size:.68rem; font-weight:700; letter-spacing:.1em; text-transform:uppercase; }
    .orbit-glow { color:var(--orbit-accent); }
    div.stButton > button, div.stFormSubmitButton > button { border-radius:8px; min-height:2.55rem; font-weight:600; transition:background-color .16s ease, border-color .16s ease, transform .16s ease; }
    button[data-testid*="BaseButton-primary"] { background:var(--orbit-accent) !important; border:1px solid var(--orbit-accent) !important; color:white !important; }
    button[data-testid*="BaseButton-primary"]:hover { background:#066d71 !important; border-color:#066d71 !important; color:white !important; transform:translateY(-1px); }
    button[data-testid*="BaseButton-secondary"] { border:1px solid var(--orbit-line) !important; background:var(--orbit-surface) !important; color:var(--orbit-ink) !important; }
    div[data-testid="stMetric"] { background:var(--orbit-surface); border:1px solid var(--orbit-line); border-radius:10px; padding:.8rem .95rem; box-shadow:0 3px 12px rgba(24,43,56,.025); }
    div[data-testid="stMetricLabel"], div[data-testid="stMetricLabel"] * {
      color:var(--orbit-muted) !important;
    }
    div[data-testid="stMetricValue"], div[data-testid="stMetricValue"] * {
      color:var(--orbit-ink) !important;
    }
    .stTabs [role="tablist"] { gap:.25rem; background:#e9edf0; border-radius:9px; padding:.25rem; }
    .stTabs [role="tab"] { color:var(--orbit-muted) !important; border-radius:7px; }
    .stTabs [role="tab"][aria-selected="true"] { background:var(--orbit-surface); color:var(--orbit-accent) !important; box-shadow:0 1px 3px rgba(24,43,56,.08); }
    [data-testid="stExpander"] { background:var(--orbit-surface); border:1px solid var(--orbit-line); border-radius:9px; }
    [data-testid="stVerticalBlockBorderWrapper"] { background:var(--orbit-surface); border-color:var(--orbit-line); border-radius:12px; }
    [data-testid="stForm"] { background:var(--orbit-surface); border:1px solid var(--orbit-line); border-radius:10px; padding:1rem; }
    .st-key-auth-card,
    .st-key-command-agents-card,
    .st-key-command-case-card,
    .st-key-command-inspector-card,
    .st-key-command-queue-card,
    .st-key-command-risk-card,
    .st-key-command-governance-card {
      background:var(--orbit-surface);
      border:1px solid var(--orbit-line);
      border-radius:11px;
      padding:.85rem;
    }
    [data-testid="stWidgetLabel"] { color:var(--orbit-ink) !important; }
    [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] * { color:var(--orbit-muted) !important; }
    .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"], .stNumberInput input {
      background:var(--orbit-surface); color:var(--orbit-ink); border-color:#cdd7de; border-radius:7px;
    }
    [data-testid="stSelectbox"] [role="combobox"] {
      background:var(--orbit-surface) !important;
      color:var(--orbit-ink) !important;
      border:1px solid #cdd7de !important;
      border-radius:7px;
    }
    [data-testid="stSelectbox"] [role="combobox"] * { color:var(--orbit-ink) !important; }
    [data-baseweb="popover"] { background:var(--orbit-surface); border:1px solid var(--orbit-line); }
    [data-baseweb="popover"] [role="option"] { color:var(--orbit-ink) !important; }
    .stTextInput input::placeholder, .stTextArea textarea::placeholder { color:#718293; opacity:1; }
    input[type="checkbox"], input[type="radio"] { accent-color:var(--orbit-accent); }
    [data-testid="stRadioOption"][data-selected="true"] > div > div:first-child {
      background:var(--orbit-accent) !important;
      border-color:var(--orbit-accent) !important;
    }
    [data-testid="stAlert"] { border:1px solid var(--orbit-line); }
    [data-testid="stAlert"] p { color:var(--orbit-ink) !important; }
    [data-testid="stAlertContainer"] { border-radius:9px; }
    [data-testid="stAlertContentInfo"] { background:#edf4f7 !important; }
    [data-testid="stAlertContentSuccess"] { background:#edf6f1 !important; }
    [data-testid="stAlertContentWarning"] { background:#fff6e8 !important; }
    [data-testid="stAlertContentError"] { background:#fff0f0 !important; }
    [data-testid="stBottom"] { background:rgba(243,245,247,.97); border-top:1px solid var(--orbit-line); }
    [data-testid="stBottom"] > div { background:var(--orbit-bg) !important; }
    [data-testid="stBottomBlockContainer"] { background:transparent; }
    [data-testid="stChatInputTextArea"] {
      background:var(--orbit-surface) !important;
      color:var(--orbit-ink) !important;
      border:1px solid #cdd7de !important;
      border-radius:8px;
    }
    [data-testid="stChatInput"] > div {
      background:var(--orbit-surface) !important;
      border:1px solid var(--orbit-line) !important;
    }
    [data-testid="stChatInputTextArea"]::placeholder { color:#718293; opacity:1; }
    [data-testid="stChatInputSubmitButton"] {
      background:var(--orbit-accent) !important;
      color:white !important;
      border-radius:7px;
    }
    code { color:#375267; background:#edf1f4; border-radius:4px; padding:.1rem .25rem; }
    [data-testid="stDataFrame"], [data-testid="stTable"] { border:1px solid var(--orbit-line); border-radius:9px; overflow:hidden; }
    [data-testid="stCaptionContainer"] { color:var(--orbit-muted); }
    button:focus-visible, input:focus-visible, textarea:focus-visible, [role="combobox"]:focus-visible {
      outline:2px solid #087e83; outline-offset:2px;
    }
    .auth-brand { color:var(--orbit-accent); font-size:.76rem; font-weight:700; letter-spacing:.15em; text-transform:uppercase; }
    .auth-heading { margin:.75rem 0 .8rem; color:var(--orbit-ink); font-size:2.6rem; font-weight:700; line-height:1.12; letter-spacing:-.04em; }
    .auth-copy { max-width:32rem; color:var(--orbit-muted); font-size:1rem; line-height:1.7; }
    .auth-detail { margin-top:1.7rem; padding-top:1.2rem; border-top:1px solid var(--orbit-line); color:var(--orbit-muted); font-size:.88rem; line-height:1.7; }
    .auth-card-title { margin:0; color:var(--orbit-ink); font-size:1.35rem; font-weight:700; letter-spacing:-.02em; }
    .stApp:has(.st-key-auth-home) { background:#f7f8f6; }
    .stApp:has(.st-key-auth-home) [data-testid="stHeader"] { display:none; }
    .stApp:has(.st-key-auth-home) [data-testid="stMain"] > div {
      max-width:1320px;
      padding:0 2.5rem 2.25rem;
    }
    .st-key-auth-home { animation:auth-rise .65s cubic-bezier(.2,.7,.25,1) both; }
    .auth-nav {
      display:flex; align-items:center; gap:.7rem; color:#1e343e;
      font-size:.86rem; font-weight:700; letter-spacing:.01em;
    }
    .auth-nav-mark {
      display:grid; width:2.35rem; height:2.35rem; place-items:center;
      border-radius:11px; background:#15313a; color:#8ce0d4;
      box-shadow:0 4px 12px rgba(19,46,54,.14);
    }
    .auth-nav-name { font-size:1.05rem; letter-spacing:.12em; }
    .auth-nav-context {
      margin-left:.45rem; padding-left:.9rem; border-left:1px solid #dfe5e2;
      color:#76858a; font-size:.77rem; font-weight:500; letter-spacing:0;
    }
    .auth-main { align-items:center; padding-top:1.2rem; }
    .auth-copy-column { padding:1.2rem .8rem 1rem 0; }
    .auth-eyebrow {
      display:inline-flex; align-items:center; gap:.55rem; margin-bottom:1.35rem;
      color:#43716c; font-size:.68rem; font-weight:700; letter-spacing:.13em;
      text-transform:uppercase;
    }
    .auth-eyebrow:before {
      content:""; width:1.65rem; height:1px; background:#70aaa0;
    }
    .auth-home-heading {
      max-width:650px; margin:0; color:#162c35;
      font-family:Georgia,"Times New Roman",serif !important;
      font-size:clamp(2.8rem,4.7vw,4rem) !important;
      font-weight:600 !important; line-height:1.04 !important;
      letter-spacing:-.052em !important;
    }
    .auth-home-heading em {
      color:#147e79; font-family:inherit !important; font-weight:500 !important;
    }
    .auth-home-copy {
      max-width:535px; margin:1.3rem 0 0; color:#63747a;
      font-size:1rem; line-height:1.8;
    }
    .auth-cta-row { display:flex; align-items:center; gap:.8rem; margin-top:1.45rem; }
    .auth-points {
      display:flex; flex-wrap:wrap; gap:.55rem 1.15rem; margin-top:1.25rem;
      color:#63747a; font-size:.76rem;
    }
    .auth-points span { display:inline-flex; align-items:center; gap:.4rem; }
    .auth-points span:before {
      content:""; width:.36rem; height:.36rem; border-radius:50%;
      background:#3a9183; box-shadow:0 0 0 3px #e4f0eb;
    }
    .auth-visual {
      position:relative; isolation:isolate; overflow:hidden; min-height:340px;
      margin-top:1.35rem; padding:1.15rem; border:1px solid #29434a;
      border-radius:17px; color:#edf5f2;
      background:linear-gradient(145deg,#17313a 0%,#1b3439 55%,#263b3b 100%);
      box-shadow:0 18px 38px rgba(30,58,58,.12);
    }
    .auth-visual:before, .auth-visual:after {
      position:absolute; z-index:-1; content:""; pointer-events:none;
      border:1px solid rgba(151,218,201,.09); border-radius:50%;
    }
    .auth-visual:before { width:330px; height:330px; right:-130px; top:-195px; }
    .auth-visual:after { width:250px; height:250px; right:-90px; top:-155px; }
    .auth-visual-top {
      display:flex; align-items:center; justify-content:space-between; gap:.6rem;
      color:#b6c8c4; font-size:.61rem; font-weight:700; letter-spacing:.1em;
      text-transform:uppercase;
    }
    .auth-visual-brand { display:flex; align-items:center; gap:.5rem; }
    .auth-visual-brand svg { color:#85d7c6; }
    .auth-local-tag {
      padding:.35rem .55rem; border:1px solid rgba(180,222,204,.2);
      border-radius:999px; color:#b8d7c8; font-size:.56rem; letter-spacing:.08em;
    }
    .auth-review-card {
      max-width:440px; margin:1.4rem auto 0; padding:1.2rem 1.25rem;
      border:1px solid rgba(255,255,255,.72); border-radius:12px;
      background:#f9fbf9; color:#1b3039;
      box-shadow:0 15px 34px rgba(5,20,24,.2);
    }
    .auth-review-top {
      display:flex; align-items:center; justify-content:space-between; gap:.5rem;
      color:#718087; font-size:.58rem; font-weight:700; letter-spacing:.09em;
    }
    .auth-review-status {
      display:inline-flex; align-items:center; gap:.35rem; color:#267867;
    }
    .auth-review-status:before {
      content:""; width:.38rem; height:.38rem; border-radius:50%; background:#4d9d7c;
    }
    .auth-review-title {
      margin:.85rem 0 .3rem; color:#1c3139;
      font:600 1.2rem Georgia,"Times New Roman",serif; letter-spacing:-.02em;
    }
    .auth-review-subtitle { margin:0; color:#75848a; font-size:.72rem; line-height:1.55; }
    .auth-flow { position:relative; display:grid; gap:.55rem; margin-top:1.05rem; }
    .auth-flow:before {
      position:absolute; left:1rem; top:1.75rem; bottom:1.75rem; width:1px;
      background:#dbe8e2; content:"";
    }
    .auth-flow-item {
      position:relative; display:flex; align-items:center; gap:.7rem;
      min-height:2.35rem; padding:.38rem .55rem; border:1px solid #e8eeea;
      border-radius:8px; background:#fff; font-size:.71rem;
    }
    .auth-flow-icon {
      display:grid; width:1.35rem; height:1.35rem; flex:none; place-items:center;
      border:1px solid #cfe4dc; border-radius:50%; background:#eef6f1;
      color:#307b6b; font-size:.58rem; font-weight:700;
    }
    .auth-flow-label { flex:1; color:#334b51; font-weight:600; }
    .auth-flow-state { color:#778880; font-size:.62rem; }
    .auth-review-foot {
      display:flex; justify-content:space-between; gap:.75rem; margin-top:.85rem;
      padding-top:.7rem; border-top:1px solid #e7ece9; color:#6c7d7e;
      font-size:.62rem; line-height:1.45;
    }
    .auth-review-foot b { color:#287767; font-weight:600; }
    .auth-visual-caption {
      margin:.8rem .1rem 0; color:#b2c5c0; font-size:.64rem;
      letter-spacing:.02em; text-align:center;
    }
    .st-key-auth-access-card {
      padding:1.35rem 1.35rem 1.1rem; border:1px solid #e1e7e4;
      border-radius:14px; background:rgba(255,255,255,.93);
      box-shadow:0 12px 35px rgba(26,53,55,.07);
      animation:auth-rise .72s .1s cubic-bezier(.2,.7,.25,1) both;
    }
    .auth-access-kicker {
      margin-bottom:.45rem; color:#438178; font-size:.62rem;
      font-weight:700; letter-spacing:.12em; text-transform:uppercase;
    }
    .auth-access-title {
      margin:0; color:#1b3038; font:600 1.55rem Georgia,"Times New Roman",serif;
      letter-spacing:-.025em;
    }
    .auth-access-copy { margin:.35rem 0 1rem; color:#728187; font-size:.78rem; }
    .st-key-auth-access-card [data-testid="stRadio"] > label { display:none; }
    .st-key-auth-access-card [data-testid="stRadio"] > div {
      gap:.35rem; padding:.25rem; border-radius:8px; background:#f0f3f1;
    }
    .st-key-auth-access-card [data-testid="stRadioOption"] {
      flex:1; justify-content:center; padding:.42rem .5rem; border-radius:6px;
      color:#68787b;
    }
    .st-key-auth-access-card [data-testid="stRadioOption"][data-selected="true"] {
      background:#fff; color:#176f6c;
      box-shadow:0 1px 3px rgba(29,55,56,.1);
    }
    .st-key-auth-access-card [data-testid="stForm"] {
      padding:0; border:0; background:transparent;
    }
    .st-key-auth-access-card [data-testid="stWidgetLabel"] { font-size:.77rem; font-weight:600; }
    .st-key-auth-access-card [data-testid="stTextInput"] input { min-height:2.7rem; }
    .auth-access-note {
      margin-top:.8rem; padding-top:.8rem; border-top:1px solid #edf0ee;
      color:#7a888b; font-size:.66rem; line-height:1.6;
    }
    .st-key-auth-hero-create button {
      min-height:2.8rem; padding:0 1.15rem; border-radius:8px;
    }
    .st-key-auth-hero-signin button, .st-key-auth-nav-signin button {
      min-height:2.8rem; padding:0 1rem; border-radius:8px;
      border-color:#dbe3df !important; background:rgba(255,255,255,.65) !important;
    }
    .st-key-auth-nav-row { padding:.85rem 0; border-bottom:1px solid #e8ece9; }
    .st-key-auth-nav-row [data-testid="stHorizontalBlock"] { align-items:center; }
    .st-key-auth-nav-row [data-testid="stButton"] { display:flex; justify-content:flex-end; }
    @keyframes auth-rise {
      from { opacity:0; transform:translateY(12px); }
      to { opacity:1; transform:translateY(0); }
    }
    @media (prefers-reduced-motion: reduce) {
      .st-key-auth-home, .st-key-auth-access-card { animation:none; }
      .st-key-auth-access-card button, .auth-nav-mark { transition:none; }
    }
    @media (max-width: 900px) {
      .stApp:has(.st-key-auth-home) [data-testid="stHorizontalBlock"]:has(.st-key-auth-copy-column) {
        flex-wrap:wrap !important;
      }
      .stApp:has(.st-key-auth-home) [data-testid="stHorizontalBlock"]:has(.st-key-auth-copy-column) > .stColumn {
        flex:1 1 100% !important;
        width:100% !important;
        min-width:100% !important;
      }
    }
    .cc-top { display:flex; justify-content:space-between; align-items:center; gap:1rem; padding:1rem 1.2rem; border:1px solid var(--orbit-line); border-radius:11px; background:var(--orbit-surface); margin-bottom:1rem; }
    .cc-brand { font:800 19px 'Segoe UI',sans-serif; letter-spacing:4px; color:var(--orbit-accent); }
    .cc-sub { font-size:11px; letter-spacing:1px; color:var(--orbit-muted); }
    .cc-status { font-size:11px; color:#227c67; letter-spacing:.06em; }
    .cc-panel { background:var(--orbit-surface); border:1px solid var(--orbit-line); border-radius:11px; padding:1rem; height:100%; min-height:150px; }
    .cc-label { font-size:11px; letter-spacing:.08em; color:var(--orbit-muted); text-transform:uppercase; font-weight:700; margin-bottom:9px; }
    .cc-big { font:700 24px 'Segoe UI',sans-serif; color:var(--orbit-ink); }
    .cc-muted { font-size:12px; color:var(--orbit-muted); line-height:1.55; }
    .cc-chip { display:inline-block; border:1px solid #cce5e2; background:var(--orbit-accent-soft); border-radius:20px; padding:4px 8px; color:#176d6c; font-size:10px; margin:3px; }
    .cc-agent { display:flex; justify-content:space-between; gap:8px; border-bottom:1px solid #edf0f2; padding:8px 0; font-size:12px; color:var(--orbit-ink); }
    .cc-kpi { background:var(--orbit-surface); border:1px solid var(--orbit-line); border-radius:9px; padding:11px 13px; height:100%; }
    .cc-kpi small { font-size:10px; letter-spacing:.08em; color:var(--orbit-muted); }
    .cc-kpi b { display:block; font:700 18px 'Segoe UI',sans-serif; color:var(--orbit-ink); margin-top:3px; white-space:nowrap; }
    @media (max-width: 760px) {
      [data-testid="stMain"] > div { padding:1rem .75rem 2rem; }
      [data-testid="stHorizontalBlock"] { flex-wrap:wrap; gap:.65rem; }
      [data-testid="stHorizontalBlock"] > [data-testid="column"] { flex:1 1 100%; min-width:100% !important; }
      .stApp:has(.st-key-auth-home) [data-testid="stMain"] > div { padding:0 .9rem 1.5rem; }
      .orbit-hero { padding:1.1rem; }
      .orbit-hero h1 { font-size:1.5rem; }
      .orbit-topbar, .cc-top { align-items:flex-start; flex-direction:column; gap:.45rem; }
      .auth-heading { font-size:2rem; }
      .cc-sub { font-size:10px; line-height:1.5; }
      .st-key-auth-nav-row [data-testid="stHorizontalBlock"] { flex-wrap:nowrap !important; gap:.35rem !important; }
      .st-key-auth-nav-row [data-testid="stHorizontalBlock"] > .stColumn:first-child {
        min-width:0 !important; flex:1 1 auto !important;
      }
      .st-key-auth-nav-row [data-testid="stHorizontalBlock"] > .stColumn:last-child {
        min-width:0 !important; flex:0 0 5.2rem !important;
      }
      .auth-nav-context { display:none; }
      .auth-main { padding-top:.5rem; }
      .auth-copy-column { padding:.9rem 0 0; }
      .auth-home-heading { max-width:100%; font-size:clamp(2.65rem,12vw,3.55rem) !important; }
      .auth-home-copy { margin-top:.9rem; font-size:.92rem; }
      .auth-cta-row { gap:.5rem; margin-top:1rem; }
      .auth-visual { min-height:0; margin-top:.9rem; padding:.85rem; }
      .auth-review-card { margin-top:1rem; padding:1rem; }
      .st-key-auth-access-card { padding:1.1rem; }
    }
    hr { border-color:var(--orbit-line); }
    </style>
    """,
    unsafe_allow_html=True,
)


try:
    initialize_database()
    initialize_auth_database()
except (OSError, sqlite3.Error) as error:
    st.error(f"ORBIT could not open its local database: {error}")
    st.stop()

if "orbit_user" not in st.session_state:
    st.session_state.orbit_user = None

account = (
    get_user(st.session_state.orbit_user)
    if st.session_state.orbit_user
    else None
)
if st.session_state.orbit_user and account is None:
    st.session_state.orbit_user = None

def _set_auth_mode(mode: str) -> None:
    st.session_state["auth_mode"] = mode


if not st.session_state.orbit_user:
    st.session_state.setdefault("auth_mode", "Create account")
    with st.container(key="auth-home"):
        with st.container(key="auth-nav-row"):
            nav_brand, nav_action = st.columns([5, 1], gap="small")
            with nav_brand:
                st.markdown(
                    '<div class="auth-nav">'
                    '<span class="auth-nav-mark"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">'
                    '<circle cx="12" cy="12" r="8.5" stroke="currentColor" stroke-width="1.5"/>'
                    '<circle cx="12" cy="12" r="3" fill="currentColor"/>'
                    '<path d="M12 1.8v3.1M22.2 12h-3.1M12 22.2v-3.1M1.8 12h3.1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>'
                    '</svg></span><span class="auth-nav-name">ORBIT</span>'
                    '<span class="auth-nav-context">Decision intelligence for shipment claims</span>'
                    '</div>',
                    unsafe_allow_html=True,
                )
            with nav_action:
                st.button(
                    "Sign in",
                    key="auth-nav-signin",
                    on_click=_set_auth_mode,
                    args=("Sign in",),
                    width="stretch",
                )

        auth_intro, auth_panel = st.columns([1.12, .88], gap="large")
        with auth_intro:
            with st.container(key="auth-copy-column"):
                st.markdown(
                    '<div class="auth-eyebrow">A more considered claim review</div>'
                    '<h1 class="auth-home-heading">Every claim deserves<br>'
                    '<em>a clearer answer.</em></h1>'
                    '<p class="auth-home-copy">Bring shipment evidence, policy guidance, '
                    'and human judgment into one calm, explainable review. ORBIT helps '
                    'your team see what matters before deciding what comes next.</p>',
                    unsafe_allow_html=True,
                )
                create_cta, signin_cta = st.columns([1.2, 1], gap="small")
                with create_cta:
                    st.button(
                        "Create your account",
                        key="auth-hero-create",
                        type="primary",
                        on_click=_set_auth_mode,
                        args=("Create account",),
                        width="stretch",
                    )
                with signin_cta:
                    st.button(
                        "I already have an account",
                        key="auth-hero-signin",
                        on_click=_set_auth_mode,
                        args=("Sign in",),
                        width="stretch",
                    )
                st.markdown(
                    '<div class="auth-points"><span>Evidence-led reviews</span>'
                    '<span>Human-gated actions</span><span>Local-first by design</span></div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    '<div class="auth-visual">'
                    '<div class="auth-visual-top"><span class="auth-visual-brand">'
                    '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden="true">'
                    '<circle cx="12" cy="12" r="8.5" stroke="currentColor" stroke-width="1.5"/>'
                    '<circle cx="12" cy="12" r="3" fill="currentColor"/>'
                    '</svg>ORBIT REVIEW</span><span class="auth-local-tag">ILLUSTRATIVE WORKFLOW</span></div>'
                    '<div class="auth-review-card"><div class="auth-review-top">'
                    '<span>CLAIM REVIEW</span><span class="auth-review-status">READY FOR REVIEW</span></div>'
                    '<div class="auth-review-title">A clearer view of the case.</div>'
                    '<p class="auth-review-subtitle">A guided path from available evidence '
                    'to a human decision.</p><div class="auth-flow">'
                    '<div class="auth-flow-item"><span class="auth-flow-icon">01</span>'
                    '<span class="auth-flow-label">Shipment evidence</span>'
                    '<span class="auth-flow-state">Collected</span></div>'
                    '<div class="auth-flow-item"><span class="auth-flow-icon">02</span>'
                    '<span class="auth-flow-label">Policy checks</span>'
                    '<span class="auth-flow-state">Explained</span></div>'
                    '<div class="auth-flow-item"><span class="auth-flow-icon">03</span>'
                    '<span class="auth-flow-label">Reviewer decision</span>'
                    '<span class="auth-flow-state">Human-led</span></div>'
                    '</div><div class="auth-review-foot"><span>Next step</span>'
                    '<b>Action stays gated until approved</b></div></div>'
                    '<div class="auth-visual-caption">Sample records · No live carrier connection</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )
        with auth_panel:
            with st.container(key="auth-access-card"):
                st.markdown(
                    '<div class="auth-access-kicker">Your secure workspace</div>'
                    '<div class="auth-access-title">'
                    + (
                        "Welcome back"
                        if st.session_state["auth_mode"] == "Sign in"
                        else "Get started with ORBIT"
                    )
                    + '</div><div class="auth-access-copy">Sign in or create an account '
                    'to continue to your claim workspace.</div>',
                    unsafe_allow_html=True,
                )
                st.radio(
                    "Access your workspace",
                    ["Create account", "Sign in"],
                    horizontal=True,
                    label_visibility="collapsed",
                    key="auth_mode",
                )
                if st.session_state["auth_mode"] == "Sign in":
                    with st.form("orbit_login_form"):
                        login_email = st.text_input(
                            "Email address",
                            placeholder="you@example.com",
                        )
                        login_password = st.text_input(
                            "Password",
                            type="password",
                        )
                        login_submit = st.form_submit_button(
                            "Sign in to ORBIT",
                            type="primary",
                            width="stretch",
                        )
                    if login_submit:
                        account = authenticate_user(login_email, login_password)
                        if account:
                            st.session_state.orbit_user = account["email"]
                            st.rerun()
                        else:
                            st.error("Email or password is incorrect.")
                else:
                    with st.form("orbit_signup_form"):
                        signup_email = st.text_input(
                            "Email address",
                            key="signup_email",
                            placeholder="you@example.com",
                        )
                        signup_password = st.text_input(
                            "Password",
                            type="password",
                            key="signup_password",
                            help="Use at least 8 characters.",
                        )
                        signup_confirm = st.text_input(
                            "Confirm password",
                            type="password",
                        )
                        signup_submit = st.form_submit_button(
                            "Create your account",
                            type="primary",
                            width="stretch",
                        )
                    if signup_submit:
                        if signup_password != signup_confirm:
                            st.error("Passwords do not match.")
                        else:
                            ok, message = register_user(
                                signup_email,
                                signup_password,
                            )
                            (st.success if ok else st.error)(message)
                st.markdown(
                    '<div class="auth-access-note">Passwords are stored as salted hashes '
                    'in the local account database. New accounts receive User access; '
                    'an administrator can promote an account.</div>',
                    unsafe_allow_html=True,
                )
    st.stop()

user_email = account["email"]
is_admin = account["role"] == "admin"


def _case_label(case: dict[str, Any]) -> str:
    return (
        f"{case['shipment_id']}  ·  {case['claim_type'].replace('_', ' ').title()}  ·  "
        f"{case['origin']} → {case['destination']}"
    )


def _format_duration(milliseconds: float) -> str:
    if milliseconds < 0.001:
        return f"{milliseconds * 1000:.2f} μs"
    return f"{milliseconds:.2f} ms"


def _load_selected_case() -> None:
    case = next(
        item
        for item in st.session_state["shipment_cases"]
        if item["shipment_id"] == st.session_state["selected_case_id"]
    )
    st.session_state["shipment_id_input"] = case["shipment_id"]
    st.session_state["complaint_input"] = case["complaint"]


def _on_history_change() -> None:
    st.session_state["current_run_id"] = st.session_state["history_selection"]


def _render_evaluation() -> None:
    report = run_evaluation()
    st.subheader("Evaluation snapshot")
    st.caption(
        f"Same {report['case_count']}-case simulated dataset. "
        "Baseline: always approve, with no evidence retrieval or safety controls."
    )
    columns = st.columns(4)
    columns[0].metric(
        "Decision accuracy",
        f"{report['orbit_accuracy']:.0f}%",
        f"{report['orbit_accuracy'] - report['baseline_accuracy']:+.0f} pp vs baseline",
    )
    columns[1].metric(
        "Evidence completeness",
        f"{report['orbit_evidence_completeness']:.0f}%",
        f"{report['orbit_evidence_completeness'] - report['baseline_evidence_completeness']:+.0f} pp",
    )
    columns[2].metric(
        "Mean processing",
        _format_duration(report["orbit_mean_processing_ms"]),
        f"Baseline {_format_duration(report['baseline_mean_processing_ms'])}",
        delta_color="off",
    )
    columns[3].metric(
        "Failure recovery",
        report["orbit_recovery"],
        f"Baseline {report['baseline_recovery']}",
        delta_color="off",
    )
    st.caption(
        "Unauthorized-action attempts blocked: "
        f"ORBIT {report['orbit_unauthorized_block']} · "
        f"baseline {report['baseline_unauthorized_block']}. "
        "The baseline has no approval gate. Recovery and authorization checks use a temporary database."
    )
    with st.expander("Per-case comparison and metric definitions"):
        st.markdown(
            "- **Evidence completeness:** simulated records, available documents, tracking events, and the applicable policy retrieved by Research.\n"
            "- **Baseline:** always marks a complaint eligible, with no evidence, retry, or approval gate.\n"
            "- **Processing time:** measured local agent-processing time; excludes human approval wait time."
        )
        st.dataframe(
            [
                {
                    "Shipment": case["shipment_id"],
                    "Expected": case["expected"].replace("_", " ").title(),
                    "ORBIT": case["orbit_decision"].replace("_", " ").title(),
                    "Baseline": case["baseline_decision"].title(),
                    "Evidence": f"{case['evidence_found']}/{case['evidence_expected']}",
                    "Validation": "Passed" if case["recommendation_validated"] else "Blocked",
                    "Prepared action": case["prepared_action"].replace("_", " "),
                }
                for case in report["cases"]
            ],
            hide_index=True,
            width="stretch",
        )


def _render_local_assistant() -> None:
    st.markdown(
        """
        <div class="orbit-topbar"><span><b>ORBIT / LOCAL AI ASSISTANT</b></span>
        <span>OLLAMA ON THIS COMPUTER · RETRIEVAL-AUGMENTED ANSWERS</span></div>
        <section class="orbit-hero">
          <div class="orbit-kicker">Ask about shipment records and claim policies</div>
          <h1>How can I help with your shipment?</h1>
          <p>Ask in plain language. ORBIT searches local records first, then asks the
          configured Ollama model to answer using the retrieved sources.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )
    st.info(
        "This assistant searches the shared local shipment and policy records, "
        "not saved claim history. The supplied records are fictional examples. "
        "Do not load customer-specific company records until per-customer shipment "
        "access controls are implemented. Ollama must be running on this computer; "
        "answers are informational and do not approve claims, process returns, "
        "or issue refunds."
    )
    settings = OllamaSettings.from_environment()
    corpus = build_retrieval_corpus(list_shipments(), list_policies())
    corpus_signature = tuple((item.source_id, item.text) for item in corpus)
    assistant_key = (
        corpus_signature,
        settings.base_url,
        settings.chat_model,
        settings.embedding_model,
        settings.timeout_seconds,
    )
    if st.session_state.get("local_rag_assistant_key") != assistant_key:
        st.session_state["local_rag_assistant"] = LocalRAGAssistant(
            corpus, settings
        )
        st.session_state["local_rag_assistant_key"] = assistant_key

    st.caption(
        f"Local chat model: `{settings.chat_model}` · "
        f"Local embedding model: `{settings.embedding_model}` · "
        "No cloud AI service is configured."
    )
    if "local_ai_history" not in st.session_state:
        st.session_state["local_ai_history"] = []
    if st.button("Clear conversation", key="clear_local_ai_history"):
        st.session_state["local_ai_history"] = []
        st.rerun()

    for item in st.session_state["local_ai_history"]:
        with st.chat_message(item["role"]):
            st.markdown(item["content"])
            if item.get("sources"):
                with st.expander("Retrieved local sources"):
                    for source in item["sources"]:
                        st.markdown(
                            f"**[{source['source_id']}]** · "
                            f"relevance {source['score']:.2f}"
                        )
                        st.caption(source["text"])

    question = st.chat_input(
        "Ask about a shipment ID, tracking update, or claim policy",
        max_chars=1000,
        key="local_ai_question",
    )
    if question:
        prior_messages = [
            {"role": item["role"], "content": item["content"]}
            for item in st.session_state["local_ai_history"]
        ]
        st.session_state["local_ai_history"].append({
            "role": "user",
            "content": question,
        })
        try:
            with st.spinner("Searching local records and asking Ollama..."):
                result = st.session_state["local_rag_assistant"].answer(
                    question, prior_messages
                )
            st.session_state["local_ai_history"].append({
                "role": "assistant",
                "content": result["answer"],
                "sources": result["sources"],
            })
            st.rerun()
        except (LocalModelError, ValueError, OSError) as error:
            st.error(f"Could not answer from local records: {error}")


with st.sidebar:
    st.markdown('<div class="orbit-brand">ORBIT</div>', unsafe_allow_html=True)
    st.markdown('<div class="orbit-kicker">Local claim review workspace</div>', unsafe_allow_html=True)
    st.caption(f"Signed in: {user_email}")
    st.caption(f"Role: {'Administrator' if is_admin else 'User'}")
    st.caption(
        "You can review every claim."
        if is_admin else "You can review and manage only the claims you submit."
    )
    if st.button("Sign out", width="stretch"):
        st.session_state.orbit_user = None
        st.rerun()
    st.divider()
    st.markdown("**NAVIGATION**")
    orbit_page = st.radio(
        "Workspace",
        ["Command Center", "Claim Workspace", "AI Assistant"],
        index=0,
        label_visibility="collapsed",
        key="orbit_page",
    )
    st.divider()
    st.markdown("**MISSION WORKFLOW**")
    for name, detail in (
        ("01  Research", "Retrieve simulated shipment and policy evidence"),
        ("02  Analysis", "Check evidence, documents, and policy thresholds"),
        ("03  Validation", "Cross-check recommendation against evidence"),
        ("04  Action", "Prepare a gated next step"),
    ):
        st.markdown(f"**{name}**")
        st.caption(detail)
    st.divider()
    st.markdown("**SYSTEM STATUS**")
    st.success("Local demo data · no carrier integration")
    st.caption(f"SQLite: `{get_db_path().name}`")
    st.caption("Sensitive actions are simulation-only and require a recorded human decision.")
    if st.button("Refresh dashboard", width="stretch"):
        st.rerun()

# Dedicated, at-a-glance visual command center. All operational counts and
# selected-case details below are read from persisted SQLite workflow records.
selected_page = st.session_state.get("orbit_page", "Command Center")
if selected_page == "Command Center":
    all_runs = list_runs(
        limit=500, owner_email=user_email, is_admin=is_admin
    )
    selected_run_id = st.session_state.get("current_run_id")
    if selected_run_id not in [item["run_id"] for item in all_runs] and all_runs:
        selected_run_id = all_runs[0]["run_id"]
    selected_run = (
        get_run_details(
            selected_run_id, owner_email=user_email, is_admin=is_admin
        )
        if selected_run_id else None
    )
    total = len(all_runs)
    completed = sum(x.get("status") == "completed" for x in all_runs)
    awaiting = sum(x.get("status") == "awaiting_approval" for x in all_runs)
    failed = sum(x.get("status") == "failed" for x in all_runs)
    st.markdown(
        '<div class="cc-top"><div><div class="cc-brand">ORBIT</div>'
        '<div class="cc-sub">DECISION INTELLIGENCE / COMMAND CENTER</div></div>'
        '<div class="cc-status">● LOCAL SYSTEM · ADAPTIVE MODE · SIMULATION</div></div>',
        unsafe_allow_html=True,
    )
    k = st.columns(4)
    claim_label = "CLAIMS PROCESSED" if is_admin else "MY CLAIMS"
    for col, label, value in zip(
        k,
        [claim_label, "COMPLETED", "HUMAN REVIEW", "FAILED RUNS"],
        [total, completed, awaiting, failed],
    ):
        col.markdown(
            f'<div class="cc-kpi"><small>{label}</small><b>{value}</b></div>',
            unsafe_allow_html=True,
        )
    st.markdown("<div style='height:8px'></div>",unsafe_allow_html=True)
    left, center, right = st.columns([1.05, 1.4, 1.05], gap="small")
    with left:
        with st.container(border=True, key="command-agents-card"):
            st.markdown(
                '<div class="cc-label">Agent network / execution map</div>',
                unsafe_allow_html=True,
            )
            statuses = {}
            if selected_run:
                for event in selected_run.get("events", []):
                    statuses[event.get("agent", "Agent")] = event.get(
                        "status", "completed"
                    )
            agent_names = [
                "Research Agent",
                "Analysis Agent",
                "Validation Agent",
                "Action Agent",
            ]
            for name in agent_names:
                status = next(
                    (
                        value
                        for agent, value in statuses.items()
                        if name.lower() in agent.lower()
                    ),
                    "idle",
                )
                color = {
                    "completed": "#227c67",
                    "running": "#a96b15",
                    "failed": "#bd4054",
                    "idle": "#758494",
                }.get(status, "#758494")
                st.markdown(
                    f'<div class="cc-agent"><span>{name.removesuffix(" Agent")}</span>'
                    f'<span style="color:{color}">● {status.upper()}</span></div>',
                    unsafe_allow_html=True,
                )
            st.markdown(
                '<div class="cc-muted" style="padding-top:8px">'
                "Statuses come from saved workflow events. Debate and support scoring "
                "are derived from those results, not separate live agents.</div>",
                unsafe_allow_html=True,
            )
    with center:
        with st.container(border=True, key="command-case-card"):
            st.markdown(
                '<div class="cc-label">ORBIT central command / case status</div>',
                unsafe_allow_html=True,
            )
            if selected_run:
                st.markdown(
                    f'<div class="cc-big">{selected_run["shipment_id"]}</div>'
                    '<div class="cc-muted">SELECTED SHIPMENT CLAIM</div>'
                    f'<div style="margin:9px"><span class="cc-chip">'
                    f'{selected_run["status"].replace("_", " ").upper()}</span>'
                    f'<span class="cc-chip">'
                    f'{(selected_run.get("decision") or "PENDING").upper()}</span></div>',
                    unsafe_allow_html=True,
                )
                st.write(
                    selected_run.get("recommendation")
                    or "Workflow has not produced a recommendation yet."
                )
                state = selected_run.get("state", {})
                uncertainty = state.get("uncertainty", {})
                support_score = uncertainty.get("decision_support_score")
                evidence_score = uncertainty.get("evidence_completeness")
                support_value = f"{support_score}/100" if support_score is not None else "—"
                evidence_value = f"{evidence_score}%" if evidence_score is not None else "—"
                support_column, evidence_column, processing_column = st.columns(3)
                support_column.metric("Support", support_value)
                evidence_column.metric("Evidence", evidence_value)
                processing_column.metric(
                    "Processing", f'{selected_run.get("processing_ms", 0)} ms'
                )
            else:
                st.markdown(
                    '<div class="cc-big" style="padding:22px 0">'
                    "Ready for investigation</div>"
                    '<div class="cc-muted">No claim runs are stored yet.</div>',
                    unsafe_allow_html=True,
                )
                st.info(
                    "Open Claim Workspace to submit a shipment claim. "
                    "The case view will appear here after the run."
                )
    with right:
        with st.container(border=True, key="command-inspector-card"):
            st.markdown(
                '<div class="cc-label">Decision inspector</div>',
                unsafe_allow_html=True,
            )
            if selected_run:
                st.markdown(
                    f'<div class="cc-muted">SHIPMENT</div><b>{selected_run["shipment_id"]}</b>'
                    f'<div class="cc-muted" style="margin-top:9px">WORKFLOW STATUS</div>'
                    f'<b>{selected_run["status"].replace("_", " ").title()}</b>'
                    f'<div class="cc-muted" style="margin-top:9px">PREPARED ACTION</div>'
                    f'<b>{(selected_run.get("action_type") or "Not prepared").replace("_", " ").title()}</b>'
                    f'<div class="cc-muted" style="margin-top:9px">AUDIT EVENTS</div>'
                    f'<b>{len(selected_run.get("audit", []))}</b>',
                    unsafe_allow_html=True,
                )
                if selected_run.get("status") == "awaiting_approval":
                    st.warning("Human approval required")
            else:
                st.markdown(
                    "<div class='cc-muted'>Claim details and evidence will appear here "
                    "after the first investigation.</div>",
                    unsafe_allow_html=True,
                )
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    lower_left, lower_mid, lower_right = st.columns(
        [1, 1.15, 1], gap="small"
    )
    with lower_left:
        with st.container(border=True, key="command-queue-card"):
            st.markdown(
                '<div class="cc-label">Mission queue / recent claims</div>',
                unsafe_allow_html=True,
            )
            if all_runs:
                for item in all_runs[:5]:
                    st.markdown(
                        f'<div class="cc-agent"><span>{item["shipment_id"]}<br>'
                        f'<small>{item.get("created_at", "")[:16].replace("T", " ")}</small></span>'
                        f'<span>{item.get("status", "").replace("_", " ").upper()}</span></div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("No claims processed yet.")
    with lower_mid:
        with st.container(border=True, key="command-risk-card"):
            st.markdown(
                '<div class="cc-label">Decision support / risk dimensions</div>',
                unsafe_allow_html=True,
            )
            if selected_run:
                components = (
                    selected_run.get("state", {})
                    .get("uncertainty", {})
                    .get("components", {})
                )
                if components:
                    st.bar_chart({"Support dimension": components}, height=170)
                else:
                    st.caption(
                        "Support dimensions appear after uncertainty assessment."
                    )
            else:
                st.caption(
                    "Risk visualization populates from the selected claim assessment."
                )
    with lower_right:
        with st.container(border=True, key="command-governance-card"):
            st.markdown(
                '<div class="cc-label">Workflow signals / governance</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="cc-agent"><span>Completed reviews</span><b>{completed}</b></div>'
                f'<div class="cc-agent"><span>Awaiting approval</span><b>{awaiting}</b></div>'
                f'<div class="cc-agent"><span>Failed workflows</span><b>{failed}</b></div>'
                '<div class="cc-agent"><span>Safety mode</span>'
                '<b style="color:#227c67">Human gated</b></div>',
                unsafe_allow_html=True,
            )
    st.markdown("<div style='height:7px'></div>",unsafe_allow_html=True)
    if all_runs:
        labels=[f'{x["shipment_id"]} · {x["status"].replace("_"," ")}' for x in all_runs]
        chosen=st.selectbox("Inspect a different claim",options=[x["run_id"] for x in all_runs],index=next((i for i,x in enumerate(all_runs) if x["run_id"]==selected_run_id),0),format_func=lambda rid: next((f'{x["shipment_id"]} · {x["status"].replace("_"," ")}' for x in all_runs if x["run_id"]==rid),rid),key="cc_run_selector")
        if chosen != st.session_state.get("current_run_id"):
            st.session_state["current_run_id"]=chosen
            st.rerun()
    def _open_claim_workspace():
        # Streamlit executes callbacks before rerunning the script, so it is
        # safe to update the radio widget's session-state key here.
        st.session_state["orbit_page"] = "Claim Workspace"

    st.button("＋ Open claim workspace", type="primary", on_click=_open_claim_workspace)
    st.caption(
        "Counts and case details come from SQLite "
        + ("for all users." if is_admin else "for your account only.")
        + " Agent topology describes the configured local workflow, not a live carrier network."
    )
    st.stop()

if selected_page == "AI Assistant":
    try:
        _render_local_assistant()
    except (LocalModelError, OSError, sqlite3.Error) as error:
        st.error(f"Could not prepare the local AI assistant: {error}")
    st.stop()

st.markdown(
    """
    <div class="orbit-topbar"><span><b>ORBIT / MISSION CONTROL</b> &nbsp; LOCAL CLAIM REVIEW</span><span>LOCAL ENVIRONMENT &nbsp; · &nbsp; <b>● SYSTEM READY</b></span></div>
    <section class="orbit-hero">
      <div class="orbit-kicker">Evidence-first shipment claim review</div>
      <h1>What would you like to investigate?</h1>
      <p>Coordinate evidence research, independent analysis, agent challenges and human governance in one shipment-claim command center.</p>
      <br><span class="orbit-pill">SIMULATION MODE · NO LIVE CARRIER CONNECTION</span>
    </section>
    """,
    unsafe_allow_html=True,
)

# Compact mission telemetry strip based on persisted claim runs.
mission_runs = list_runs(
    limit=500, owner_email=user_email, is_admin=is_admin
)
mission_total = len(mission_runs)
mission_escalated = sum(1 for item in mission_runs if item.get("status") == "awaiting_approval")
mission_done = sum(1 for item in mission_runs if item.get("status") == "completed")
mission_cols = st.columns(4)
mission_cols[0].metric("CLAIMS IN SYSTEM" if is_admin else "MY CLAIMS", mission_total)
mission_cols[1].metric("COMPLETED REVIEWS", mission_done)
mission_cols[2].metric("AWAITING HUMAN REVIEW", mission_escalated)
mission_cols[3].metric("ACTIVE USER", user_email.split("@")[0])

with st.expander("Evaluation dashboard", expanded=False):
    _render_evaluation()

st.markdown("### Mission console")
network_left, network_center, network_right = st.columns([1, 1.25, 1])
with network_left:
    st.markdown('<div class="orbit-panel"><div class="orbit-panel-title">Agent network</div><h3 class="orbit-glow">Orchestrator</h3><p>Research → Analysis → Validation</p><small class="cc-muted">Investigation and debate activate when evidence is incomplete or conflicting.</small></div>', unsafe_allow_html=True)
with network_center:
    st.markdown('<div class="orbit-panel" style="text-align:center"><div class="orbit-panel-title">Central command</div><h2>Investigate a claim</h2><p>Select a shipment, add the complaint, and launch the workflow.</p><span class="orbit-pill">EVIDENCE-FIRST DECISIONS</span></div>', unsafe_allow_html=True)
with network_right:
    st.markdown('<div class="orbit-panel"><div class="orbit-panel-title">Governance inspector</div><h3 class="orbit-glow">Human oversight</h3><p>Approval gates · audit trail · uncertainty routing</p><small class="cc-muted">No simulated action executes without a recorded reviewer decision.</small></div>', unsafe_allow_html=True)

st.subheader("Start a claim review")
st.caption(
    "Shipment and policy evidence comes from local sample records in SQLite. "
    "Your complaint and workflow results are stored locally under your account."
)
shipment_cases = list_shipments()
case_ids = [case["shipment_id"] for case in shipment_cases]
st.session_state["shipment_cases"] = shipment_cases
if "selected_case_id" not in st.session_state or st.session_state["selected_case_id"] not in case_ids:
    st.session_state["selected_case_id"] = case_ids[0]
if "shipment_id_input" not in st.session_state:
    st.session_state["shipment_id_input"] = st.session_state["selected_case_id"]
if "complaint_input" not in st.session_state:
    st.session_state["complaint_input"] = next(
        case["complaint"] for case in shipment_cases
        if case["shipment_id"] == st.session_state["selected_case_id"]
    )

selected_case = next(
    case for case in shipment_cases
    if case["shipment_id"] == st.session_state["selected_case_id"]
)
st.selectbox(
    "Load a sample case",
    options=case_ids,
    format_func=lambda case_id: _case_label(next(case for case in shipment_cases if case["shipment_id"] == case_id)),
    key="selected_case_id",
    on_change=_load_selected_case,
)
selected_case = next(
    case for case in shipment_cases
    if case["shipment_id"] == st.session_state["selected_case_id"]
)

left, right = st.columns([1.2, 1])
with left:
    with st.form("claim_review_form"):
        st.text_input("Shipment / AWB ID", key="shipment_id_input", max_chars=16)
        st.text_area(
            "Customer complaint",
            key="complaint_input",
            height=115,
            max_chars=1000,
            help="10–1,000 characters. Use a sample shipment ID to load its local record.",
        )
        submitted = st.form_submit_button("Review claim", type="primary", width="stretch")
with right:
    st.markdown("**Selected simulated shipment**")
    st.markdown(f"**{selected_case['shipment_id']}** · {selected_case['claim_type'].replace('_', ' ').title()}")
    st.write(f"{selected_case['origin']} → {selected_case['destination']}")
    st.caption(f"Current record status: {selected_case['status']}")
    st.caption(
        "Available evidence in local record: "
        + ", ".join(
            document.replace("_", " ")
            for document, present in selected_case["documents"].items()
            if present
        )
    )

if submitted:
    try:
        run = start_claim_workflow(
            st.session_state["shipment_id_input"],
            st.session_state["complaint_input"],
            owner_email=user_email,
        )
        st.session_state["current_run_id"] = run["run_id"]
    except WorkflowError as error:
        st.session_state["current_run_id"] = error.run_id
        st.error(f"{error}. The failed stage and prior results were saved; retry is available below.")
    except ValueError as error:
        st.error(str(error))
    except (OSError, sqlite3.Error) as error:
        st.error(f"ORBIT could not persist this review: {error}")

runs = list_runs(limit=50, owner_email=user_email, is_admin=is_admin)
run_ids = [item["run_id"] for item in runs]
current_run_id = st.session_state.get("current_run_id")
if run_ids:
    if current_run_id in run_ids:
        st.session_state["history_selection"] = current_run_id
    selected_history_id = current_run_id if current_run_id in run_ids else run_ids[0]
    st.selectbox(
        "Review history",
        options=run_ids,
        index=run_ids.index(selected_history_id),
        format_func=lambda run_id: next(
            (
                f"{item['shipment_id']} · {item['decision'] or item['status'].replace('_', ' ')} · "
                f"{item['created_at'][:16].replace('T', ' ')}"
                + (
                    f" · {item['owner_email'] or 'legacy run'}"
                    if is_admin else ""
                )
                for item in runs if item["run_id"] == run_id
            ),
            run_id,
        ),
        key="history_selection",
        on_change=_on_history_change,
    )
    if "current_run_id" not in st.session_state:
        st.session_state["current_run_id"] = st.session_state["history_selection"]

current_run_id = st.session_state.get("current_run_id")
run = (
    get_run_details(
        current_run_id, owner_email=user_email, is_admin=is_admin
    )
    if current_run_id else None
)
if run:
    st.divider()
    st.subheader(f"Claim review · {run['shipment_id']}")
    status_columns = st.columns(4)
    status_columns[0].metric("Workflow status", run["status"].replace("_", " ").title())
    status_columns[1].metric(
        "Eligibility decision",
        (run["decision"] or "Pending").replace("_", " ").title(),
    )
    status_columns[2].metric(
        "Prepared action",
        (run["action_type"] or "Not prepared").replace("_", " ").title(),
    )
    status_columns[3].metric("Agent processing", f"{run['processing_ms']} ms")

    if run["status"] == "failed":
        st.error(f"Workflow error: {run['error']}")
        if st.button("Retry / resume saved workflow", type="primary"):
            try:
                resumed = resume_claim_workflow(
                    run["run_id"], owner_email=user_email, is_admin=is_admin
                )
                st.session_state["current_run_id"] = resumed["run_id"]
                st.rerun()
            except WorkflowError as error:
                st.error(f"{error}. The failure is saved in the audit history.")
            except (OSError, sqlite3.Error, ValueError) as error:
                st.error(f"Could not resume this workflow: {error}")

    if run["recommendation"]:
        st.info(run["recommendation"])
    if run["status"] == "awaiting_approval":
        st.warning(
            "Human approval required. No action has executed. Approving records a simulated action only; "
            "it does not change a shipment, issue a real refund, or create a support ticket."
        )

    tabs = st.tabs(["Overview", "Evidence & policy", "Agent activity", "Approvals & actions", "Audit history"])
    with tabs[0]:
        st.markdown("**Customer complaint**")
        st.write(run["complaint"])
        if is_admin:
            st.caption(
                f"Submitted by: {run['owner_email'] or 'Legacy record (no owner recorded)'}"
            )
        st.markdown("**Shipment record**")
        shipment = next(
            (case for case in shipment_cases if case["shipment_id"] == run["shipment_id"]),
            None,
        )
        if shipment:
            details = st.columns(4)
            details[0].write(f"**Status**  \n{shipment['status']}")
            details[1].write(f"**Route**  \n{shipment['origin']} → {shipment['destination']}")
            details[2].write(f"**Claim type**  \n{shipment['claim_type'].replace('_', ' ').title()}")
            details[3].write(f"**Delivered**  \n{'Yes' if shipment['delivered'] else 'No'}")
            st.markdown("**Recommendation**")
            st.write(run["recommendation"] or "The workflow has not produced a recommendation yet.")
            if run["state"].get("execution_notice"):
                st.caption(run["state"]["execution_notice"])
    with tabs[1]:
        research = run["state"].get("research", {})
        missing = research.get("missing_documents", [])
        if missing:
            st.warning("Missing documents: " + ", ".join(item.replace("_", " ") for item in missing))
        elif research:
            st.success("All policy-required documents are present in the simulated record.")
        if research.get("evidence"):
            st.markdown("**Retrieved evidence**")
            for item in research["evidence"]:
                with st.container(border=True):
                    st.markdown(f"**{item['label']}**")
                    st.caption(item["detail"])
        checks = run["state"].get("analysis", {}).get("policy_checks", [])
        if checks:
            st.markdown("**Policy checks**")
            st.dataframe(
                [
                    {
                        "Check": check["rule"],
                        "Result": check["result"].title(),
                        "Details": check["detail"],
                    }
                    for check in checks
                ],
                hide_index=True,
                width="stretch",
            )
        validation = run["state"].get("validation", {})
        if validation:
            st.markdown("**Validation agent**")
            st.write(validation["message"])
            st.dataframe(
                [
                    {"Validation": check["rule"], "Result": "Passed" if check["passed"] else "Blocked"}
                    for check in validation["checks"]
                ],
                hide_index=True,
                width="stretch",
            )
    with tabs[2]:
        if not run["events"]:
            st.caption("No agent events have been recorded yet.")
        for event in run["events"]:
            icon = {"completed": "✅", "running": "⏳", "failed": "❌"}.get(event["status"], "•")
            with st.expander(f"{icon} {event['agent']} · {event['status'].title()}"):
                st.write(event["message"])
                if event["status"] == "failed":
                    st.error(event["details"].get("error", "Agent failed."))
                elif event["details"]:
                    st.json(event["details"])
                st.caption(event["created_at"])
    with tabs[3]:
        approval = run["approval"]
        action = run["action"]
        if action:
            st.markdown(f"**Action:** `{action['action_type']}`")
            st.write(action["result"])
            st.caption(
                f"Execution mode: {'SIMULATED' if action['simulation'] else 'EXTERNAL'} · "
                f"Status: {action['status'].replace('_', ' ').title()}"
            )
        if approval and approval["status"] == "pending":
            st.markdown("**Approval request · pending**")
            if is_admin:
                st.caption(f"Administrator decision will be recorded as {user_email}.")
                with st.form(f"approval_form_{run['run_id']}"):
                    note = st.text_area("Decision note (optional)", max_chars=500)
                    choice = st.radio("Decision", ["approved", "rejected"], horizontal=True)
                    approval_submitted = st.form_submit_button("Record decision", type="primary")
                if approval_submitted:
                    try:
                        decided = decide_approval(
                            run["run_id"], choice, user_email, note,
                        )
                        st.session_state["current_run_id"] = decided["run_id"]
                        st.rerun()
                    except (ValueError, PermissionError) as error:
                        st.error(str(error))
                    except (OSError, sqlite3.Error) as error:
                        st.error(f"Could not record the approval: {error}")
            else:
                st.info(
                    "This request is awaiting an administrator. Your account can submit "
                    "and track claims, but cannot approve sensitive actions."
                )
        elif approval and approval["status"] in {"approved", "rejected"}:
            st.write(
                f"**{approval['status'].title()}** by {approval['reviewer']} "
                f"at {approval['decided_at']}"
            )
            if approval["note"]:
                st.caption(approval["note"])
        elif approval:
            st.caption("Human approval is not required for this prepared, non-executed action.")
    with tabs[4]:
        if run["audit"]:
            st.dataframe(
                [
                    {
                        "Time (UTC)": entry["created_at"],
                        "Event": entry["event_type"].replace("_", " ").title(),
                        "Details": entry["message"],
                    }
                    for entry in run["audit"]
                ],
                hide_index=True,
                width="stretch",
            )
        else:
            st.caption("No audit events recorded.")

st.divider()
st.caption(
    "ORBIT demo uses local simulated Delhivery records and policy examples. "
    "It has no live carrier, payment, or support-system integration."
)


# ORBIT intelligence workbench — all panels read persisted workflow state.
st.divider()
st.header("ORBIT · Decision Intelligence Workbench")
st.caption("Adaptive orchestration · bounded agent debate · explainable support scoring · human governance")

workbench = st.tabs(["Command Center", "Debate Arena", "Decision Graph", "Memory & Feedback", "Adversarial Lab"])
with workbench[0]:
    if run:
        state = run["state"]
        plan = state.get("adaptive_plan", {})
        uncertainty = state.get("uncertainty", {})
        metrics = st.columns(4)
        metrics[0].metric("Case complexity", plan.get("complexity", "—").title())
        metrics[1].metric("Decision support", f"{uncertainty.get('decision_support_score', '—')} / 100")
        metrics[2].metric("Evidence complete", f"{uncertainty.get('evidence_completeness', '—')}%")
        metrics[3].metric("Routing", uncertainty.get("route", "Pending"))
        st.subheader("Adaptive investigation plan")
        for item in plan.get("selected", []):
            st.markdown(f"**{item['agent']}** · `{item['status']}`  \n{item['reason']}")
        if plan.get("skipped"):
            with st.expander("Agents intentionally skipped"):
                for item in plan["skipped"]:
                    st.write(f"**{item['agent']}** — {item['reason']}")
        st.subheader("Uncertainty breakdown")
        components = uncertainty.get("components", {})
        if components:
            st.bar_chart({"Support component": components})
        for reason in uncertainty.get("reasons", []):
            st.write("• " + reason)
        st.caption("Support score is a transparent heuristic, not a calibrated probability or an LLM confidence score.")
        st.subheader("Agent execution events")
        for event in run.get("events", []):
            st.write(f"{event['created_at']} · **{event['agent']}** · {event['status']} — {event['message']}")
    else:
        st.info("Run a claim investigation to populate the command center with real execution state.")

with workbench[1]:
    if run and run["state"].get("debate"):
        debate = run["state"]["debate"]
        st.metric("Debate status", debate["status"].replace("_", " ").title())
        st.caption(f"{debate['rounds_used']} of {debate['max_rounds']} maximum rounds · {debate['termination_reason']}")
        for argument in debate["arguments"]:
            with st.container(border=True):
                st.markdown(f"**Round {argument['round']} · {argument['agent']}**")
                st.write(f"Position: `{argument['position']}`")
                st.write(argument.get("counterargument") or argument.get("revision_reason"))
                st.caption("Evidence: " + (", ".join(argument.get("supporting_evidence_ids", [])) or "None cited"))
                st.caption("Policy: " + ", ".join(argument.get("policy_references", [])))
        if debate["unresolved_questions"]:
            st.warning("Unresolved questions")
            for question in debate["unresolved_questions"]:
                st.write("• " + question)
    else:
        st.info("Debate trace appears here after a claim run. It is derived from agent outputs and has a bounded round limit.")

with workbench[2]:
    if run and run["state"].get("decision_graph"):
        graph = run["state"]["decision_graph"]
        st.subheader("Decision trace")
        for node in graph["nodes"]:
            icon = "🟢" if node["available"] else "⚪"
            st.markdown(f"{icon} **{node['label']}**")
            if node["available"]:
                with st.expander(f"Inspect {node['label']}"):
                    st.json(node["details"])
        st.caption("Directed relationships: " + " → ".join(edge["from"] for edge in graph["edges"]) + " → recommendation")
    else:
        st.info("Decision graph is generated for each completed investigation.")

with workbench[3]:
    feedback_rows = list_feedback(owner_email=user_email, is_admin=is_admin)
    st.columns(3)[0].metric("Historical feedback", len(feedback_rows))
    st.columns(3)[1].metric("Human corrections", sum(1 for item in feedback_rows if item["human_decision"] != "approved"))
    st.columns(3)[2].metric("Versioned entries", sum(item["version"] for item in feedback_rows))
    if run:
        st.subheader("Record reviewer feedback")
        st.caption(f"Feedback will be attributed to your signed-in account: {user_email}.")
        with st.form(f"orbit_feedback_{run['run_id']}"):
            human_decision = st.selectbox("Human outcome", ["approved", "rejected", "investigate"])
            correction_reason = st.text_area("Correction / rationale", max_chars=1000)
            feedback_submit = st.form_submit_button("Save feedback")
        if feedback_submit:
            try:
                save_feedback(
                    run,
                    human_decision,
                    user_email,
                    correction_reason,
                    owner_email=user_email,
                    is_admin=is_admin,
                )
                st.success("Feedback saved as a versioned historical observation.")
                st.rerun()
            except (ValueError, PermissionError) as error:
                st.error(str(error))
        matches = similar_feedback(
            run["shipment_id"], owner_email=user_email, is_admin=is_admin
        )
        st.subheader("Similar historical examples")
        if matches:
            for item in matches:
                st.write(f"{item['created_at']} · {item['human_decision']} · {item['correction_reason'] or 'No correction note'}")
        else:
            st.caption("No prior feedback for this shipment ID.")
    if feedback_rows:
        st.subheader("Feedback history")
        st.dataframe(feedback_rows, hide_index=True, width="stretch")
        delete_id = st.selectbox("Select feedback entry to delete", [x["feedback_id"] for x in feedback_rows])
        if st.button("Delete selected feedback"):
            try:
                delete_feedback(
                    int(delete_id), owner_email=user_email, is_admin=is_admin
                )
                st.success("Selected feedback entry deleted.")
                st.rerun()
            except PermissionError as error:
                st.error(str(error))
    st.caption("Feedback is stored separately from official policy. It is not used to silently modify policy rules; performance improvement must be demonstrated by evaluation.")

with workbench[4]:
    st.info("SIMULATED SCENARIOS ONLY · These are test prompts, not carrier records.")
    scenarios = simulated_scenarios()
    difficulty = st.selectbox("Difficulty", ["all", "easy", "moderate", "hard"])
    filtered = [item for item in scenarios if difficulty == "all" or item["difficulty"] == difficulty]
    st.dataframe(filtered, hide_index=True, width="stretch")
    st.caption("Scenario catalog is a test design inventory. Automated pass/fail execution against all adversarial fixtures is not yet implemented.")
