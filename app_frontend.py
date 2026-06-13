import streamlit as st
import requests

API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="Research Paper Assistant", layout="wide", page_icon="📚")

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

    .gap-card {
        background-color: #1A1D29;
        border-left: 3px solid #7C5CFC;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 10px;
        font-size: 0.95rem;
    }

    .session-card {
        background-color: #1A1D29;
        border: 1px solid #2D2D3A;
        border-radius: 10px;
        padding: 14px 18px;
        margin-bottom: 8px;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">📚 Research Paper Assistant</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Upload a paper, get a summary, find research gaps, and chat with citations.</div>', unsafe_allow_html=True)

# ── Session state init ─────────────────────────────────────────────────────────
if "token" not in st.session_state:
    st.session_state.token = None
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "summary" not in st.session_state:
    st.session_state.summary = None
if "research_gaps" not in st.session_state:
    st.session_state.research_gaps = None


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
                    st.success("Logged in!")
                    st.rerun()
                else:
                    try:
                        detail = res.json().get("detail", "Registration failed")
                    except Exception:
                        detail = f"Server error ({res.status_code}): {res.text[:300]}"
                    st.error(detail)
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
                    try:
                        detail = res.json().get("detail", "Registration failed")
                    except Exception:
                        detail = f"Server error ({res.status_code}): {res.text[:300]}"
                    st.error(detail)
            else:
                st.warning("Please fill in both fields")


# ── DASHBOARD (logged in, no paper selected) ───────────────────────────────────
elif st.session_state.session_id is None:

    col1, col2 = st.columns([8, 1])
    with col2:
        if st.button("Logout"):
            st.session_state.token = None
            st.rerun()

    st.subheader("Your Past Sessions")

    res = requests.post(f"{API_URL}/my-sessions", json={"token": st.session_state.token})
    if res.status_code == 200:
        sessions = res.json()["sessions"]
        if sessions:
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
                    if st.button("Load", key=s["session_id"]):
                        st.session_state.session_id = s["session_id"]
                        st.session_state.chat_history = []
                        st.session_state.summary = None
                        st.session_state.research_gaps = None
                        st.rerun()
        else:
            st.info("No past sessions yet. Upload a paper below to get started.")
    else:
        st.error("Could not load sessions.")

    st.divider()
    st.caption("⚠️ Please limit uploads to 20 pages or fewer. Larger PDFs may exceed the daily AI usage quota and fail to process.")
    st.subheader("Upload a New Paper")
    uploaded_file = st.file_uploader("Choose a PDF", type="pdf")

    if uploaded_file is not None:
        if st.button("Process PDF", type="primary"):
            with st.spinner("Parsing and embedding your paper... this may take a minute"):
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
                data = {"token": st.session_state.token}
                response = requests.post(f"{API_URL}/upload", files=files, data=data)

            if response.status_code == 200:
                st.session_state.session_id = response.json()["session_id"]
                st.session_state.chat_history = []
                st.session_state.summary = None
                st.session_state.research_gaps = None
                st.success("PDF processed successfully!")
                st.rerun()
            else:
                st.error(f"Upload failed: {response.text}")


# ── MAIN APP (logged in + paper selected) ──────────────────────────────────────
else:

    col1, col2, col3 = st.columns([6, 1, 1])
    with col2:
        if st.button("← Back"):
            st.session_state.session_id = None
            st.session_state.chat_history = []
            st.session_state.summary = None
            st.session_state.research_gaps = None
            st.rerun()
    with col3:
        if st.button("Logout"):
            st.session_state.token = None
            st.session_state.session_id = None
            st.rerun()

    st.caption(f"Session: `{st.session_state.session_id}`")

    tab1, tab2, tab3 = st.tabs(["💬 Chat", "📝 Summary", "🔍 Research Gaps"])

    # --- Chat tab ---
    with tab1:
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])
                if msg["role"] == "assistant" and msg.get("citations"):
                    for citation in msg["citations"]:
                        with st.expander(f"📄 Source — Page {citation['page_number']}"):
                            st.write(citation["chunk_text"])

        user_query = st.chat_input("Ask a question about the paper")

        if user_query:
            st.session_state.chat_history.append({"role": "user", "content": user_query})

            with st.spinner("Thinking..."):
                response = requests.post(f"{API_URL}/query", json={
                    "session_id": st.session_state.session_id,
                    "query": user_query,
                    "token": st.session_state.token
                })

            if response.status_code == 200:
                data = response.json()
                answer = data.get("answer") or str(data.get("summary")) or str(data.get("research_gaps"))
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": answer,
                    "citations": data.get("citations", [])
                })
            else:
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": f"Error: {response.text}"
                })
            st.rerun()

    # --- Summary tab ---
    with tab2:
        if st.session_state.summary is None:
            if st.button("Generate Summary", type="primary"):
                with st.spinner("Generating summary..."):
                    response = requests.post(f"{API_URL}/query", json={
                        "session_id": st.session_state.session_id,
                        "query": "summarize this paper",
                        "token": st.session_state.token
                    })
                if response.status_code == 200:
                    st.session_state.summary = response.json()["summary"]
                    st.rerun()
                else:
                    st.error(f"Failed: {response.text}")
        else:
            st.markdown(st.session_state.summary)

    # --- Research Gaps tab ---
    with tab3:
        if st.session_state.research_gaps is None:
            if st.button("Find Research Gaps", type="primary"):
                with st.spinner("Analyzing gaps..."):
                    response = requests.post(f"{API_URL}/query", json={
                        "session_id": st.session_state.session_id,
                        "query": "what are the research gaps",
                        "token": st.session_state.token
                    })
                if response.status_code == 200:
                    st.session_state.research_gaps = response.json()["research_gaps"]
                    st.rerun()
                else:
                    st.error(f"Failed: {response.text}")
        else:
            for gap in st.session_state.research_gaps:
                st.markdown(f'<div class="gap-card">{gap}</div>', unsafe_allow_html=True)