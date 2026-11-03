import uuid
import os
import json
import hashlib
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from pydantic import BaseModel

from graph.builder import build_ingestion_graph, build_query_graph, build_positioning_graph
from schemas.paper import NOT_STATED
from services.db import get_connection, init_db, loads
from services.auth_service import validate_token
from services.llm_service import text_call, RateLimited
from api.auth_router import router as auth_router

app = FastAPI()
app.include_router(auth_router)

ingestion_graph = build_ingestion_graph()
query_graph = build_query_graph()
positioning_graph = build_positioning_graph()

UPLOAD_DIR = "uploaded_pdfs"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def require_user(token: str) -> str:
    user_id = validate_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_id


def fact(f):
    """One extracted fact -> plain text ('' if the paper doesn't state it)."""
    return "" if not f or f["value"] == NOT_STATED else f["value"]


def facts(fs):
    return "; ".join(f["value"] for f in fs or [])


@app.on_event("startup")
def startup():
    init_db()   # creates the local SQLite file and all tables if they don't exist yet


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/upload")
def upload(file: UploadFile = File(...), token: str = Form(...)):
    user_id = require_user(token)

    file_bytes = file.file.read()
    pdf_hash = hashlib.sha256(file_bytes).hexdigest()

    conn = get_connection()
    existing = conn.execute(
        "SELECT session_id FROM rpa_sessions WHERE pdf_hash = ? AND user_id = ?",
        (pdf_hash, user_id)
    ).fetchone()
    conn.close()
    if existing:
        return {"session_id": existing[0], "message": "PDF already processed. Reusing existing session."}

    session_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{session_id}.pdf")
    with open(file_path, "wb") as f:
        f.write(file_bytes)

    result = ingestion_graph.invoke({
        'session_id': session_id,
        'paper_id': session_id,
        'pdf_path': file_path,
        'chunks': [],
        'tables': [],
        'extracted': {},
    })
    if result.get('error'):
        raise HTTPException(status_code=500, detail=result['error'])

    conn = get_connection()
    conn.execute(
        """INSERT INTO rpa_sessions (session_id, user_id, pdf_name, pdf_hash, chat_history, extracted)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (session_id, user_id, file.filename, pdf_hash, json.dumps([]), json.dumps(result.get('extracted', {})))
    )
    conn.commit()
    conn.close()

    return {"session_id": session_id, "message": "PDF processed successfully"}


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

    conn = get_connection()
    conn.execute(
        "UPDATE rpa_sessions SET chat_history = ? WHERE session_id = ?",
        (json.dumps(chat_history), req.session_id)
    )
    conn.commit()
    conn.close()

    return {'answer': answer, 'citations': citations}


class TokenRequest(BaseModel):
    token: str


@app.post("/my-sessions")
def my_sessions(req: TokenRequest):
    user_id = require_user(req.token)

    conn = get_connection()
    rows = conn.execute(
        "SELECT session_id, pdf_name, created_at FROM rpa_sessions WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,)
    ).fetchall()
    conn.close()

    return {"sessions": [{"session_id": r[0], "pdf_name": r[1], "created_at": str(r[2])} for r in rows]}


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


class SessionDataRequest(BaseModel):
    session_id: str
    token: str


@app.post("/session-data")
def session_data(req: SessionDataRequest):
    user_id = require_user(req.token)

    conn = get_connection()
    row = conn.execute(
        "SELECT pdf_name, extracted, chat_history FROM rpa_sessions WHERE session_id = ? AND user_id = ?",
        (req.session_id, user_id)
    ).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "pdf_name": row[0],
        "extracted": loads(row[1], None),
        "chat_history": loads(row[2], []),
    }


class PositioningRequest(BaseModel):
    session_id: str
    token: str
    refresh: bool = False


@app.post("/positioning")
def positioning(req: PositioningRequest):
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
        raise HTTPException(status_code=400, detail="This paper has no extracted facts. Re-upload it first.")

    result = positioning_graph.invoke({"mode": "paper", "extracted": extracted})
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])

    conn = get_connection()
    conn.execute(
        "UPDATE rpa_sessions SET positioning = ? WHERE session_id = ?",
        (json.dumps(result["positioning"]), req.session_id)
    )
    conn.commit()
    conn.close()
    return result["positioning"]