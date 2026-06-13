import uuid
import shutil
import os
import json
import psycopg2
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from pydantic import BaseModel

from graph.builder import build_ingestion_graph, build_query_graph
from services.qdrant_service import init_collection
from services.auth_service import validate_token
from api.auth_router import router as auth_router
from config import DATABASE_URL

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
    conn.commit()
    cur.close()
    conn.close()


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

    session_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{session_id}.pdf")

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

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
        'chat_history': []
    }

    ingestion_graph.invoke(state)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO rpa_sessions (session_id, chat_history, user_id, pdf_name) VALUES (%s, %s, %s, %s)",
        (session_id, json.dumps([]), user_id, file.filename)
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
        "SELECT chat_history FROM rpa_sessions WHERE session_id = %s AND user_id = %s",
        (req.session_id, user_id)
    )
    row = cur.fetchone()

    if row is None:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found")

    chat_history = row[0]

    state = {
        'session_id': req.session_id,
        'pdf_path': '',
        'query': req.query,
        'query_type': '',
        'chunks': [],
        'retrieved_docs': [],
        'web_search_triggered': False,
        'summary': '',
        'research_gaps': [],
        'answer': '',
        'citations': [],
        'chat_history': chat_history
    }

    result = query_graph.invoke(state)

    if result['query_type'] == 'summary':
        response_text = result['summary']
    elif result['query_type'] == 'gap':
        response_text = result['research_gaps']
    else:
        response_text = result['answer']

    chat_history.append({'role': 'user', 'content': req.query})
    chat_history.append({'role': 'assistant', 'content': str(response_text)})

    cur.execute(
        "UPDATE rpa_sessions SET chat_history = %s WHERE session_id = %s",
        (json.dumps(chat_history), req.session_id)
    )
    conn.commit()
    cur.close()
    conn.close()

    return {
        "query_type": result['query_type'],
        "summary": result.get('summary'),
        "research_gaps": result.get('research_gaps'),
        "answer": result.get('answer'),
        "citations": result.get('citations')
    }


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

    sessions = [
        {"session_id": str(row[0]), "pdf_name": row[1], "created_at": str(row[2])}
        for row in rows
    ]
    return {"sessions": sessions}