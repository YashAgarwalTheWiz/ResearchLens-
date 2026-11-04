import uuid
import os
import json
import hashlib
from fastapi import FastAPI, UploadFile, File, HTTPException, Form, BackgroundTasks
from pydantic import BaseModel

from graph.builder import build_ingestion_graph, build_query_graph, build_positioning_graph
from schemas.paper import NOT_STATED
from services.db import get_connection, init_db, loads
from services.auth_service import validate_token
from services.llm_service import text_call, RateLimited
from services.openalex_service import OpenAlexError
from services.reference_checker import check_references
from api.auth_router import router as auth_router

app = FastAPI()
app.include_router(auth_router)

ingestion_graph = build_ingestion_graph()
query_graph = build_query_graph()
positioning_graph = build_positioning_graph()

UPLOAD_DIR = "uploaded_pdfs"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# what the user sees while each ingestion node runs (in order)
UPLOAD_STEPS = {
    "pdf_parser": "Reading the PDF",
    "embedder": "Indexing the text",
    "table_extractor": "Finding tables",
    "extractor": "Extracting facts with sources",
}
STEP_ORDER = list(UPLOAD_STEPS)
STEP_LABELS = list(UPLOAD_STEPS.values())


def require_user(token: str) -> str:
    user_id = validate_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_id


def pdf_path(session_id: str) -> str:
    return os.path.join(UPLOAD_DIR, f"{session_id}.pdf")


def fact(f):
    """One extracted fact -> plain text ('' if the paper doesn't state it)."""
    return "" if not f or f["value"] == NOT_STATED else f["value"]


def facts(fs):
    return "; ".join(f["value"] for f in fs or [])


def update_session(session_id, **fields):
    conn = get_connection()
    sets = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE rpa_sessions SET {sets} WHERE session_id = ?", (*fields.values(), session_id))
    conn.commit()
    conn.close()


def delete_session_data(session_id):
    conn = get_connection()
    conn.execute("DELETE FROM rpa_chunks WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM rpa_sessions WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()
    if os.path.exists(pdf_path(session_id)):
        os.remove(pdf_path(session_id))


@app.on_event("startup")
def startup():
    init_db()   # creates the local SQLite file and all tables if they don't exist yet
    # a server restart kills background uploads; don't leave them stuck on "processing" forever
    conn = get_connection()
    conn.execute("UPDATE rpa_sessions SET status = 'failed', error = 'Server restarted during processing. "
                 "Delete and upload again.' WHERE status = 'processing'")
    conn.commit()
    conn.close()


@app.get("/health")
def health():
    return {"status": "ok"}


# ── Upload: returns immediately, processing continues in the background ───────
def run_ingestion(session_id: str):
    """Runs after /upload has already answered. Saves progress after every node so the UI can show it."""
    state = {'session_id': session_id, 'paper_id': session_id, 'pdf_path': pdf_path(session_id),
             'chunks': [], 'tables': [], 'extracted': {}}
    try:
        update_session(session_id, progress=STEP_LABELS[0])
        for update in ingestion_graph.stream(state, stream_mode="updates"):
            for node, output in update.items():
                state.update(output or {})
                nxt = STEP_ORDER.index(node) + 1
                if nxt < len(STEP_ORDER):
                    update_session(session_id, progress=UPLOAD_STEPS[STEP_ORDER[nxt]])
        if state.get('error'):
            update_session(session_id, status='failed', error=state['error'])
        else:
            update_session(session_id, status='ready', progress='Done',
                           extracted=json.dumps(state.get('extracted', {})))
    except Exception as e:
        update_session(session_id, status='failed', error=f"Processing failed: {e}")


@app.post("/upload")
def upload(background_tasks: BackgroundTasks, file: UploadFile = File(...), token: str = Form(...)):
    user_id = require_user(token)

    file_bytes = file.file.read()
    pdf_hash = hashlib.sha256(file_bytes).hexdigest()

    conn = get_connection()
    existing = conn.execute(
        "SELECT session_id, status FROM rpa_sessions WHERE pdf_hash = ? AND user_id = ?",
        (pdf_hash, user_id)
    ).fetchone()
    conn.close()
    if existing and existing[1] != 'failed':
        return {"session_id": existing[0], "status": existing[1],
                "message": "PDF already uploaded. Reusing it."}
    if existing:                          # a failed earlier attempt: clear it and try again
        delete_session_data(existing[0])

    session_id = str(uuid.uuid4())
    with open(pdf_path(session_id), "wb") as f:
        f.write(file_bytes)

    conn = get_connection()
    conn.execute(
        """INSERT INTO rpa_sessions (session_id, user_id, pdf_name, pdf_hash, chat_history, status, progress)
           VALUES (?, ?, ?, ?, ?, 'processing', 'Queued')""",
        (session_id, user_id, file.filename, pdf_hash, json.dumps([]))
    )
    conn.commit()
    conn.close()

    background_tasks.add_task(run_ingestion, session_id)
    return {"session_id": session_id, "status": "processing", "message": "Processing started"}


class SessionRequest(BaseModel):
    session_id: str
    token: str


@app.post("/status")
def status(req: SessionRequest):
    user_id = require_user(req.token)
    conn = get_connection()
    row = conn.execute(
        "SELECT status, progress, error FROM rpa_sessions WHERE session_id = ? AND user_id = ?",
        (req.session_id, user_id)
    ).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")
    step = STEP_LABELS.index(row[1]) + 1 if row[1] in STEP_LABELS else (len(STEP_LABELS) if row[0] == 'ready' else 0)
    return {"status": row[0], "progress": row[1], "error": row[2], "step": step, "total_steps": len(STEP_LABELS)}


@app.post("/delete-session")
def delete_session(req: SessionRequest):
    user_id = require_user(req.token)
    conn = get_connection()
    row = conn.execute("SELECT status FROM rpa_sessions WHERE session_id = ? AND user_id = ?",
                       (req.session_id, user_id)).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if row[0] == 'processing':
        raise HTTPException(status_code=409, detail="This paper is still processing. Try again when it's done.")
    delete_session_data(req.session_id)
    return {"message": "Deleted"}


# ── Ask ────────────────────────────────────────────────────────────────────────
class QueryRequest(BaseModel):
    session_id: str
    query: str
    token: str


@app.post("/query")
def query(req: QueryRequest):
    user_id = require_user(req.token)

    conn = get_connection()
    row = conn.execute(
        "SELECT chat_history FROM rpa_sessions WHERE session_id = ? AND user_id = ?",
        (req.session_id, user_id)
    ).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    chat_history = loads(row[0], [])

    result = query_graph.invoke({
        'session_id': req.session_id,
        'query': req.query,
        'chat_history': chat_history,
        'retrieved_docs': [],
    })
    answer, citations = result.get('answer', ''), result.get('citations', [])

    # citations are saved too, so reopening a paper shows the full chat with its sources
    chat_history.append({'role': 'user', 'content': req.query})
    chat_history.append({'role': 'assistant', 'content': answer, 'citations': citations})
    update_session(req.session_id, chat_history=json.dumps(chat_history))

    return {'answer': answer, 'citations': citations}


class TokenRequest(BaseModel):
    token: str


@app.post("/my-sessions")
def my_sessions(req: TokenRequest):
    user_id = require_user(req.token)

    conn = get_connection()
    rows = conn.execute(
        "SELECT session_id, pdf_name, created_at, status, progress, error FROM rpa_sessions "
        "WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,)
    ).fetchall()
    conn.close()

    return {"sessions": [{"session_id": r[0], "pdf_name": r[1], "created_at": str(r[2]),
                          "status": r[3] or "ready", "progress": r[4], "error": r[5]} for r in rows]}


# ── Compare your own papers ───────────────────────────────────────────────────
class CompareRequest(BaseModel):
    session_ids: list[str]
    token: str


@app.post("/compare")
def compare(req: CompareRequest):
    """Compare the user's own papers: a facts table built in code + a short LLM write-up of the differences."""
    user_id = require_user(req.token)
    if len(req.session_ids) < 2:
        raise HTTPException(status_code=400, detail="Select at least 2 papers to compare")

    conn = get_connection()
    papers = []
    for sid in req.session_ids:
        row = conn.execute(
            "SELECT pdf_name, extracted FROM rpa_sessions WHERE session_id = ? AND user_id = ?",
            (sid, user_id)
        ).fetchone()
        if row is None:
            conn.close()
            raise HTTPException(status_code=404, detail=f"Session {sid} not found")
        papers.append({"session_id": sid, "pdf_name": row[0], "ex": loads(row[1], {}) or {}})
    conn.close()

    # 1. the table: straight from the grounded facts, no LLM involved
    table = [{
        "Paper": p["ex"].get("title") or p["pdf_name"],
        "Year": p["ex"].get("year", ""),
        "Problem": fact(p["ex"].get("problem")),
        "Method": fact(p["ex"].get("method")),
        "Datasets": facts(p["ex"].get("datasets")),
        "Metrics": facts(p["ex"].get("metrics")),
        "Key results": facts(p["ex"].get("results")),
        "Limitations": facts(p["ex"].get("limitations")),
    } for p in papers]

    # 2. the write-up: the LLM only sees those same facts
    block = "\n\n".join(
        "\n".join(f"{k}: {v or 'not stated'}" for k, v in row.items()) for row in table
    )
    prompt = f"""Compare these research papers using ONLY the facts below.

{block}

Write a short comparison in markdown with these sections:
1. **Same problem?** - how their problems relate
2. **Key differences in method**
3. **Results** - compare only where they use the same dataset and metric; otherwise say they can't be compared directly
4. **Which to use when**

Refer to papers by title. If a fact is 'not stated', don't guess it."""

    try:
        comparison = text_call(prompt)
    except RateLimited as e:
        raise HTTPException(status_code=429, detail=str(e))

    return {
        "comparison": comparison,
        "table": table,
        "papers": [{"session_id": p["session_id"], "pdf_name": p["pdf_name"]} for p in papers],
    }


@app.post("/session-data")
def session_data(req: SessionRequest):
    user_id = require_user(req.token)

    conn = get_connection()
    row = conn.execute(
        "SELECT pdf_name, extracted, chat_history, status FROM rpa_sessions WHERE session_id = ? AND user_id = ?",
        (req.session_id, user_id)
    ).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "pdf_name": row[0],
        "extracted": loads(row[1], None),
        "chat_history": loads(row[2], []),
        "status": row[3] or "ready",
    }


# ── Where It Stands (uploaded paper) ──────────────────────────────────────────
class RefreshableRequest(BaseModel):
    session_id: str
    token: str
    refresh: bool = False


@app.post("/positioning")
def positioning(req: RefreshableRequest):
    user_id = require_user(req.token)

    conn = get_connection()
    row = conn.execute(
        "SELECT extracted, positioning FROM rpa_sessions WHERE session_id = ? AND user_id = ?",
        (req.session_id, user_id)
    ).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    extracted, cached = loads(row[0], None), loads(row[1], None)
    if cached and not req.refresh:          # already analysed -> no API calls at all
        return cached
    if not extracted:
        raise HTTPException(status_code=400, detail="This paper has no extracted facts yet.")

    result = positioning_graph.invoke({"mode": "paper", "extracted": extracted})
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])

    update_session(req.session_id, positioning=json.dumps(result["positioning"]))
    return result["positioning"]


# ── Idea Check: same pipeline, but for an idea typed in plain text ────────────
class IdeaRequest(BaseModel):
    idea: str
    token: str
    refresh: bool = False


@app.post("/idea-check")
def idea_check(req: IdeaRequest):
    user_id = require_user(req.token)
    idea = " ".join(req.idea.split())
    if len(idea) < 40:
        raise HTTPException(status_code=400, detail="Describe your idea in at least a couple of sentences.")

    idea_hash = hashlib.sha256(idea.lower().encode()).hexdigest()
    conn = get_connection()
    row = conn.execute("SELECT positioning FROM rpa_ideas WHERE idea_hash = ? AND user_id = ?",
                       (idea_hash, user_id)).fetchone()
    conn.close()
    if row and not req.refresh:            # same idea checked before -> no API calls
        return loads(row[0], {})

    result = positioning_graph.invoke({"mode": "idea", "idea_text": idea})
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])

    conn = get_connection()
    conn.execute(
        """INSERT INTO rpa_ideas (idea_hash, user_id, idea_text, positioning) VALUES (?, ?, ?, ?)
           ON CONFLICT (idea_hash, user_id) DO UPDATE SET positioning = excluded.positioning,
           created_at = CURRENT_TIMESTAMP""",
        (idea_hash, user_id, idea, json.dumps(result["positioning"]))
    )
    conn.commit()
    conn.close()
    return result["positioning"]


@app.post("/my-ideas")
def my_ideas(req: TokenRequest):
    user_id = require_user(req.token)
    conn = get_connection()
    rows = conn.execute("SELECT idea_text, created_at FROM rpa_ideas WHERE user_id = ? "
                        "ORDER BY created_at DESC LIMIT 5", (user_id,)).fetchall()
    conn.close()
    return {"ideas": [{"idea": r[0], "created_at": str(r[1])} for r in rows]}


# ── Reference check ───────────────────────────────────────────────────────────
@app.post("/references")
def references(req: RefreshableRequest):
    user_id = require_user(req.token)

    conn = get_connection()
    row = conn.execute("SELECT ref_check, status FROM rpa_sessions WHERE session_id = ? AND user_id = ?",
                       (req.session_id, user_id)).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    cached = loads(row[0], None)
    if cached and not req.refresh:
        return cached
    if row[1] != 'ready':
        raise HTTPException(status_code=400, detail="This paper is still processing.")
    if not os.path.exists(pdf_path(req.session_id)):
        raise HTTPException(status_code=404, detail="The original PDF is missing. Delete the paper and upload it again.")

    try:
        result = check_references(pdf_path(req.session_id))
    except RateLimited as e:
        raise HTTPException(status_code=429, detail=str(e))
    except OpenAlexError as e:
        raise HTTPException(status_code=503, detail=str(e))
    if result.get("error"):
        raise HTTPException(status_code=422, detail=result["error"])

    update_session(req.session_id, ref_check=json.dumps(result))
    return result