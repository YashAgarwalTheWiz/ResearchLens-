import uuid
import shutil
import os
import json
import hashlib
import psycopg2
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from pydantic import BaseModel

from graph.builder import build_ingestion_graph, build_query_graph
from services.qdrant_service import init_collection
from services.auth_service import validate_token
from api.auth_router import router as auth_router
from config import DATABASE_URL
from langchain_groq import ChatGroq
from config import GROQ_API_KEY

compare_llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=GROQ_API_KEY)

app = FastAPI()
app.include_router(auth_router)

ingestion_graph = build_ingestion_graph()
query_graph = build_query_graph()

UPLOAD_DIR = "uploaded_pdfs"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def get_connection():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rpa_sessions (
            session_id UUID PRIMARY KEY,
            chat_history JSONB DEFAULT '[]'::jsonb,
            created_at TIMESTAMP DEFAULT NOW(),
            user_id UUID,
            pdf_name TEXT
        )
    """)
    
    cur.execute("ALTER TABLE rpa_sessions ADD COLUMN IF NOT EXISTS pdf_hash TEXT")
    cur.execute("ALTER TABLE rpa_sessions ADD COLUMN IF NOT EXISTS summary TEXT")
    cur.execute("ALTER TABLE rpa_sessions ADD COLUMN IF NOT EXISTS research_gaps JSONB DEFAULT '[]'::jsonb")
    cur.execute("ALTER TABLE rpa_sessions ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb")
    conn.commit()
    cur.close()
    conn.close()


def classify_query(query: str) -> str:
    q = query.lower()
    if any(w in q for w in ['summary', 'summarize', 'summarise', 'overview']):
        return 'summary'
    if any(w in q for w in ['gap', 'gaps', 'limitation', 'limitations', 'future work']):
        return 'gap'
    return 'qa'


@app.on_event("startup")
def startup():
    init_collection()
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/upload")
def upload(file: UploadFile = File(...), token: str = Form(...)):
    user_id = validate_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    file_bytes = file.file.read()
    pdf_hash = hashlib.sha256(file_bytes).hexdigest()

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT session_id FROM rpa_sessions WHERE pdf_hash = %s AND user_id = %s",
        (pdf_hash, user_id)
    )
    existing = cur.fetchone()
    if existing:
        cur.close()
        conn.close()
        return {
            "session_id": str(existing[0]),
            "message": "PDF already processed. Reusing existing session."
        }

    session_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{session_id}.pdf")

    with open(file_path, "wb") as f:
        f.write(file_bytes)

    state = {
        'session_id': session_id,
        'pdf_path': file_path,
        'query': '',
        'query_type': '',
        'chunks': [],
        'retrieved_docs': [],
        'web_search_triggered': False,
        'summary': '',
        'research_gaps': [],
        'answer': '',
        'citations': [],
        'chat_history': [],
        'metadata': {}       
    }

    result = ingestion_graph.invoke(state)

    cur.execute(
        """INSERT INTO rpa_sessions
           (session_id, chat_history, user_id, pdf_name, pdf_hash, summary, research_gaps, metadata)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            session_id,
            json.dumps([]),
            user_id,
            file.filename,
            pdf_hash,
            result.get('summary', ''),
            json.dumps(result.get('research_gaps', [])),
            json.dumps(result.get('metadata', {}))
        )
    )
    conn.commit()
    cur.close()
    conn.close()

    return {"session_id": session_id, "message": "PDF processed successfully"}


class QueryRequest(BaseModel):
    session_id: str
    query: str
    token: str


@app.post("/query")
def query(req: QueryRequest):
    user_id = validate_token(req.token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT chat_history, summary, research_gaps FROM rpa_sessions WHERE session_id = %s AND user_id = %s",
        (req.session_id, user_id)
    )
    row = cur.fetchone()

    if row is None:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found")

    chat_history = row[0]
    cached_summary = row[1]
    cached_gaps = row[2]

    query_type = classify_query(req.query)

    if query_type == 'summary':
        response_text = cached_summary
        response_payload = {
            'query_type': 'summary',
            'summary': cached_summary,
            'research_gaps': None,
            'answer': None,
            'citations': None
        }
    elif query_type == 'gap':
        response_text = str(cached_gaps)
        response_payload = {
            'query_type': 'gap',
            'summary': None,
            'research_gaps': cached_gaps,
            'answer': None,
            'citations': None
        }
    else:
        state = {
            'session_id': req.session_id,
            'pdf_path': '',
            'query': req.query,
            'query_type': 'qa',
            'chunks': [],
            'retrieved_docs': [],
            'web_search_triggered': False,
            'summary': '',
            'research_gaps': [],
            'answer': '',
            'citations': [],
            'chat_history': chat_history,
            'metadata': {}
        }
        result = query_graph.invoke(state)
        response_text = result['answer']
        response_payload = {
            'query_type': 'qa',
            'summary': None,
            'research_gaps': None,
            'answer': result.get('answer'),
            'citations': result.get('citations')
        }

    chat_history.append({'role': 'user', 'content': req.query})
    chat_history.append({'role': 'assistant', 'content': str(response_text)})

    cur.execute(
        "UPDATE rpa_sessions SET chat_history = %s WHERE session_id = %s",
        (json.dumps(chat_history), req.session_id)
    )
    conn.commit()
    cur.close()
    conn.close()

    return response_payload


class TokenRequest(BaseModel):
    token: str


@app.post("/my-sessions")
def my_sessions(req: TokenRequest):
    user_id = validate_token(req.token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT session_id, pdf_name, created_at FROM rpa_sessions WHERE user_id = %s ORDER BY created_at DESC",
        (user_id,)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return {
        "sessions": [
            {"session_id": str(r[0]), "pdf_name": r[1], "created_at": str(r[2])}
            for r in rows
        ]
    }


class CompareRequest(BaseModel):
    session_ids: list[str]
    token: str

@app.post("/compare")
def compare(req: CompareRequest):
    user_id = validate_token(req.token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if len(req.session_ids) < 2:
        raise HTTPException(status_code=400, detail="Select at least 2 papers to compare")

    conn = get_connection()
    cur = conn.cursor()

    papers = []
    for sid in req.session_ids:
        cur.execute(
            "SELECT pdf_name, summary, metadata FROM rpa_sessions WHERE session_id = %s AND user_id = %s",
            (sid, user_id)
        )
        row = cur.fetchone()
        if row is None:
            cur.close()
            conn.close()
            raise HTTPException(status_code=404, detail=f"Session {sid} not found")
        papers.append({"pdf_name": row[0], "summary": row[1], "metadata": row[2]})

    cur.close()
    conn.close()

    paper_block = "\n\n".join([
        f"Paper {i+1}: {p['pdf_name']}\nSummary: {p['summary']}\nKey Metadata: {json.dumps(p['metadata'])}"
        for i, p in enumerate(papers)
    ])

    prompt = f"""You are a research analyst comparing multiple research papers.

{paper_block}

Provide a structured comparison covering:
1. Core problem each paper addresses
2. Methodological differences
3. Key findings and how they relate or conflict
4. Complementary contributions — what each adds that the others don't
5. Which paper's approach is strongest and why

Be specific. Reference paper names, not Paper 1/Paper 2."""

    response = compare_llm.invoke(prompt)

    return {
        "comparison": response.content,
        "papers": [{"session_id": sid, "pdf_name": p["pdf_name"]} for sid, p in zip(req.session_ids, papers)]
    }

class SessionDataRequest(BaseModel):
    session_id: str
    token: str

@app.post("/session-data")
def session_data(req: SessionDataRequest):
    user_id = validate_token(req.token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT summary, research_gaps, metadata, pdf_name FROM rpa_sessions WHERE session_id = %s AND user_id = %s",
        (req.session_id, user_id)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "summary": row[0],
        "research_gaps": row[1],
        "metadata": row[2],
        "pdf_name": row[3]
    }