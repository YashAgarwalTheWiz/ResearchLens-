import streamlit as st
import requests

API_URL = "http://127.0.0.1:8000"
NOT_STATED = "not stated in paper"

st.set_page_config(page_title="ResearchLens", layout="wide", page_icon="📚")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    .main-header {
        font-size: 2.4rem;
        font-weight: 700;
        background: linear-gradient(90deg, #7C5CFC, #B794F6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }

    .sub-header { color: #9CA3AF; font-size: 0.95rem; margin-bottom: 1.5rem; }

    div[data-testid="stExpander"] {
        border: 1px solid #2D2D3A;
        border-radius: 10px;
        background-color: #1A1D29;
    }

    div[data-testid="stExpander"] summary {
        font-size: 0.85rem;
        color: #B794F6;
        font-weight: 600;
    }

    .stButton button { border-radius: 8px; font-weight: 600; border: none; }

    div[data-testid="stChatInput"] { border-radius: 12px; }

    .session-card {
        background-color: #1A1D29;
        border: 1px solid #2D2D3A;
        border-radius: 10px;
        padding: 14px 18px;
        margin-bottom: 8px;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">📚 ResearchLens</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">See what a paper really says, where it stands against related work, '
            'and ask questions — every claim linked to its source.</div>', unsafe_allow_html=True)

# ── Session state init ─────────────────────────────────────────────────────────
DEFAULTS = {
    "token": None,
    "session_id": None,
    "pdf_name": None,
    "extracted": {},
    "chat_history": [],
    "comparison": None,
    "positioning": {},
}
for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ── HELPERS ────────────────────────────────────────────────────────────────────
def error_text(res):
    try:
        return res.json().get("detail", res.text)
    except Exception:
        return f"Server error ({res.status_code}): {res.text[:300]}"


def open_paper(session_id: str):
    """Load a paper's facts + saved chat and switch to the paper view."""
    res = requests.post(f"{API_URL}/session-data",
                        json={"session_id": session_id, "token": st.session_state.token})
    if res.status_code != 200:
        st.error(f"Failed to load paper: {error_text(res)}")
        return
    data = res.json()
    st.session_state.session_id = session_id
    st.session_state.pdf_name = data["pdf_name"]
    st.session_state.extracted = data.get("extracted") or {}
    st.session_state.chat_history = data.get("chat_history") or []
    st.session_state.comparison = None
    st.rerun()


def close_paper():
    st.session_state.session_id = None
    st.session_state.pdf_name = None
    st.session_state.extracted = {}
    st.session_state.chat_history = []


def where(ev):
    return "table" if ev["chunk_index"] == -1 else ev["section"]


def show_fact(fact, bullet=True):
    """A fact with its proof: the value, then the page. Hover the page to see the exact quote."""
    st.markdown(f"- {fact['value']}" if bullet else fact["value"])
    for ev in fact["evidence"]:
        st.caption(f"📍 p.{ev['page_number']} · {where(ev)}", help=f"“{ev['quote']}”")


def show_fact_list(facts, empty="Not stated in the paper."):
    if not facts:
        st.caption(empty)
    for f in facts:
        show_fact(f)


def render_paper(ex):
    st.markdown(f"### {ex['title']}")
    st.caption(f"{', '.join(ex['authors'])} · {ex['year']}")

    # --- at a glance ---
    with st.container(border=True):
        for label, key in [("🎯 Problem", "problem"), ("💡 Core idea", "core_idea"), ("⚙️ Method", "method")]:
            st.markdown(f"**{label}**")
            if ex[key]["value"] == NOT_STATED:
                st.caption("Not stated in the paper.")
            else:
                show_fact(ex[key], bullet=False)

    # --- the numbers ---
    st.subheader("📊 Results")
    scores = ex.get("scores") or []
    if scores:
        st.dataframe(
            [{
                "Metric": sc["metric"],
                "Dataset": sc["dataset"] or "—",
                "This paper": sc["value"],
                "Best compared method": sc["baseline"] or "—",
                "Its score": sc["baseline_value"] or "—",
                "Page": sc["evidence"][0]["page_number"],
            } for sc in scores],
            hide_index=True, width="stretch",
        )
        with st.popover("🔎 Where do these numbers come from?"):
            for sc in scores:
                ev = sc["evidence"][0]
                st.markdown(f"**{sc['metric']} = {sc['value']}** · p.{ev['page_number']} ({where(ev)})")
                st.caption(f"“{ev['quote']}”")
    else:
        st.caption("No numbers table for this paper yet. Delete it and upload it again to get one.")

    st.markdown("**Key findings**")
    show_fact_list(ex["results"])

    # --- what was used ---
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("🗂️ Datasets")
        show_fact_list(ex["datasets"])
    with col_b:
        st.subheader("📏 Metrics")
        show_fact_list(ex["metrics"])

    # --- the authors' own view ---
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("⚠️ Limitations")
        st.caption("As stated by the authors")
        show_fact_list(ex["limitations"])
    with col_b:
        st.subheader("🔭 Future work")
        st.caption("As suggested by the authors")
        show_fact_list(ex["future_work"])


OVERLAP = {
    "low": ("Mostly new", "green"),
    "partial": ("Partly done before", "orange"),
    "high": ("Largely done before", "red"),
}
RELATION = {"earlier": "published earlier", "later": "published later",
            "same year": "same year", "unknown": "year unknown"}


def paper_links(sources):
    return " · ".join(f"[{s['title'][:70]} ({s['year'] or 'n.d.'})]({s['url']})" for s in sources)


def render_positioning(pos):
    related, contributions, gaps = pos["related"], pos["contributions"], pos["gaps"]
    new_count = sum(c["overlap"] == "low" for c in contributions)

    # --- the verdict, at a glance ---
    m1, m2, m3 = st.columns(3)
    m1.metric("Contributions that look new", f"{new_count} of {len(contributions)}")
    m2.metric("Gaps vs. the field", len(gaps))
    m3.metric("Related papers compared", len(related))

    with st.container(border=True):
        st.markdown("**In short**")
        st.markdown(pos["summary"])
        st.caption("P1, P2, … are the related papers listed in the 📚 Related papers tab.")

    new_tab, missing_tab, papers_tab = st.tabs(["✨ What's new", "🕳️ What's missing", "📚 Related papers"])

    # --- what's new: each contribution checked against the closest earlier work ---
    with new_tab:
        st.caption("Each contribution of this paper, checked against the most similar published work.")
        if not contributions:
            st.info("No contributions could be checked against the related papers.")
        for c in contributions:
            label, color = OVERLAP.get(c["overlap"], (c["overlap"], "gray"))
            with st.container(border=True):
                st.badge(label, color=color)
                st.markdown(f"**{c['claim']}**")
                st.markdown(f"How it differs: {c['how_it_differs']}")
                st.caption("Closest work: " + paper_links(c["sources"]))

    # --- what's missing: gaps + what the field commonly uses ---
    with missing_tab:
        st.caption("What related papers do that this paper doesn't, or questions none of them answer.")
        if not gaps:
            st.info("No gaps found compared with the related papers.")
        for g in gaps:
            with st.container(border=True):
                st.markdown(f"**{g['gap']}**")
                st.caption("Based on: " + paper_links(g["sources"]))

        if pos["coverage"]:
            st.markdown("**What the related papers commonly use**")
            st.dataframe(
                [{
                    "Type": item["kind"].capitalize(),
                    "Name": item["name"],
                    "Used by related papers": len(item["refs"]),
                    "In this paper": "—" if item["we_use"] is None else ("✅ Yes" if item["we_use"] else "❌ No"),
                } for item in pos["coverage"]],
                column_config={"Used by related papers": st.column_config.ProgressColumn(
                    "Used by related papers", min_value=0, max_value=max(len(related), 1), format="%d papers")},
                hide_index=True, width="stretch",
            )

    # --- the related papers themselves ---
    with papers_tab:
        st.caption("The most similar published papers, most similar first. Facts come from each paper's abstract.")
        for p in related:
            f = p.get("facts") or {}
            with st.expander(f"**{p['ref']}** · {p['title']} ({p['year'] or 'n.d.'})"):
                st.caption(f"{RELATION.get(p['relation'], p['relation'])} · found via {', '.join(p['found_via'])}"
                           + (f" · {p['venue']}" if p.get("venue") else ""))
                if f:
                    st.markdown(f"**Method:** {f['method']}")
                    st.markdown(f"**Datasets:** {', '.join(f['datasets']) or 'not stated'}")
                    st.markdown(f"**Key result:** {f['key_result']}")
                st.link_button("Open paper ↗", p["url"])

    if pos["dropped_claims"]:
        st.caption(f"🛡️ {len(pos['dropped_claims'])} claim(s) were removed because they didn't cite a real paper.")


def show_citations(citations):
    for c in citations or []:
        with st.expander(f"📄 {c.get('ref', 'Source')} — page {c['page_number']}"):
            st.write(c["chunk_text"])


# ── AUTH PAGE ──────────────────────────────────────────────────────────────────
if st.session_state.token is None:

    login_tab, register_tab = st.tabs(["Login", "Register"])

    with login_tab:
        st.subheader("Login")
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")

        if st.button("Login", type="primary"):
            if email and password:
                res = requests.post(f"{API_URL}/login", json={"email": email, "password": password})
                if res.status_code == 200:
                    st.session_state.token = res.json()["token"]
                    st.rerun()
                else:
                    st.error(error_text(res))
            else:
                st.warning("Please fill in both fields")

    with register_tab:
        st.subheader("Create Account")
        reg_email = st.text_input("Email", key="reg_email")
        reg_password = st.text_input("Password", type="password", key="reg_password")

        if st.button("Register", type="primary"):
            if reg_email and reg_password:
                res = requests.post(f"{API_URL}/register", json={"email": reg_email, "password": reg_password})
                if res.status_code == 200:
                    st.success("Account created! Please switch to the Login tab.")
                else:
                    st.error(error_text(res))
            else:
                st.warning("Please fill in both fields")


# ── DASHBOARD (logged in, no paper open) ───────────────────────────────────────
elif st.session_state.session_id is None:

    col1, col2 = st.columns([8, 1])
    with col2:
        if st.button("Logout"):
            st.session_state.token = None
            st.rerun()

    st.subheader("Your Papers")

    sessions = []
    res = requests.post(f"{API_URL}/my-sessions", json={"token": st.session_state.token})
    if res.status_code == 200:
        sessions = res.json()["sessions"]
        if not sessions:
            st.info("No papers yet. Upload one below to get started.")
        for s in sessions:
            col_a, col_b = st.columns([6, 1])
            with col_a:
                st.markdown(
                    f'<div class="session-card">📄 <b>{s["pdf_name"]}</b>'
                    f'<br><small style="color:#9CA3AF">{s["created_at"][:19]}</small></div>',
                    unsafe_allow_html=True
                )
            with col_b:
                st.write("")  # vertical alignment nudge
                if st.button("Open", key=s["session_id"]):
                    open_paper(s["session_id"])
    else:
        st.error(f"Could not load your papers: {error_text(res)}")

    # ── Compare your own papers ────────────────────────────────────────────────
    if len(sessions) >= 2:
        st.divider()
        st.subheader("🔬 Compare Your Papers")

        # "pdf_name (date)" -> session_id, so duplicate filenames still work
        label_to_id = {f"{s['pdf_name']} ({s['created_at'][:10]})": s["session_id"] for s in sessions}
        selected = st.multiselect("Select 2 or more papers", options=list(label_to_id), placeholder="Choose papers...")

        if len(selected) >= 2 and st.button("Compare", type="primary"):
            with st.spinner("Comparing..."):
                res = requests.post(f"{API_URL}/compare", json={
                    "session_ids": [label_to_id[label] for label in selected],
                    "token": st.session_state.token,
                }, timeout=180)
            if res.status_code == 200:
                st.session_state.comparison = res.json()
            else:
                st.error(f"Comparison failed: {error_text(res)}")

        if st.session_state.comparison:
            st.dataframe(st.session_state.comparison["table"], hide_index=True, width="stretch")
            st.markdown(st.session_state.comparison["comparison"])
            if st.button("Clear comparison"):
                st.session_state.comparison = None
                st.rerun()

    # ── Upload ─────────────────────────────────────────────────────────────────
    st.divider()
    st.subheader("Upload a New Paper")
    st.caption("Works best with papers of 20 pages or fewer (free API limits).")
    uploaded_file = st.file_uploader("Choose a PDF", type="pdf")

    if uploaded_file is not None and st.button("Process PDF", type="primary"):
        with st.spinner("Reading the paper and extracting facts... this can take a minute"):
            res = requests.post(
                f"{API_URL}/upload",
                files={"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")},
                data={"token": st.session_state.token},
                timeout=600,
            )
        if res.status_code == 200:
            open_paper(res.json()["session_id"])
        else:
            st.error(f"Upload failed: {error_text(res)}")


# ── PAPER VIEW (logged in + paper open) ────────────────────────────────────────
else:

    col1, col2, col3 = st.columns([6, 1, 1])
    with col2:
        if st.button("← Back"):
            close_paper()
            st.rerun()
    with col3:
        if st.button("Logout"):
            close_paper()
            st.session_state.token = None
            st.rerun()

    ex = st.session_state.extracted
    st.caption(f"📄 **{st.session_state.pdf_name}**")

    paper_tab, stands_tab, ask_tab = st.tabs(["📄 Paper", "🧭 Where It Stands", "💬 Ask"])

    # --- Paper tab: what the paper says, every line with page + quote ---
    with paper_tab:
        if not ex:
            st.info("No extracted facts for this paper. Delete it and upload it again.")
        else:
            render_paper(ex)

    # --- Where It Stands tab: compared against the 10 closest published papers ---
    with stands_tab:
        sid = st.session_state.session_id

        def run_positioning(refresh):
            with st.spinner("Finding related papers and comparing (takes ~30-60s)..."):
                res = requests.post(f"{API_URL}/positioning", json={
                    "session_id": sid, "token": st.session_state.token, "refresh": refresh
                }, timeout=300)
            if res.status_code == 200:
                st.session_state.positioning[sid] = res.json()
                return True
            st.error(f"Failed: {error_text(res)}")
            return False

        pos = st.session_state.positioning.get(sid)
        if pos is None:
            with st.container(border=True):
                st.markdown("**How original is this paper?**")
                st.write("We'll find the 10 most similar published papers, compare them with this one, "
                         "and show what's new, what was done before, and what's missing. Every claim links to a real paper.")
                if st.button("Analyze related work", type="primary") and run_positioning(refresh=False):
                    st.rerun()
        else:
            render_positioning(pos)
            if st.button("↻ Re-run analysis") and run_positioning(refresh=True):
                st.rerun()

    # --- Ask tab: questions about this paper, answers cite the exact excerpts ---
    with ask_tab:
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])
                if msg["role"] == "assistant":
                    show_citations(msg.get("citations"))

        user_query = st.chat_input("Ask a question about the paper")
        if user_query:
            st.session_state.chat_history.append({"role": "user", "content": user_query})
            with st.spinner("Thinking..."):
                res = requests.post(f"{API_URL}/query", json={
                    "session_id": st.session_state.session_id,
                    "query": user_query,
                    "token": st.session_state.token,
                }, timeout=180)
            if res.status_code == 200:
                data = res.json()
                st.session_state.chat_history.append(
                    {"role": "assistant", "content": data["answer"], "citations": data.get("citations", [])}
                )
            else:
                st.session_state.chat_history.append(
                    {"role": "assistant", "content": f"Error: {error_text(res)}", "citations": []}
                )
            st.rerun()