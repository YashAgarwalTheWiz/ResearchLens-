"""Chunk storage + vector search in the local SQLite file (replaces Qdrant).

One paper is only ~50-300 chunks, so we load that session's vectors and compute
cosine similarity with numpy. That's milliseconds, and needs no extra service.
Each embedding is stored as raw float32 bytes (a BLOB): compact and fast to load.
"""
from typing import List

import numpy as np

from graph.state import CitationObject
from services.db import get_connection


def upsert_chunks(chunks: List[CitationObject], embeddings: List[List[float]], session_id: str, paper_id: str):
    conn = get_connection()
    conn.execute("DELETE FROM rpa_chunks WHERE session_id = ?", (session_id,))   # re-runs don't duplicate
    rows = [
        (session_id, paper_id, c["chunk_index"], c["page_number"], c.get("section", "unknown"),
         c["chunk_text"], np.asarray(emb, dtype=np.float32).tobytes())
        for c, emb in zip(chunks, embeddings)
    ]
    conn.executemany(
        """INSERT INTO rpa_chunks
           (session_id, paper_id, chunk_index, page_number, section, chunk_text, embedding)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    conn.close()


def search(query_vector, session_id, top_k=5, section=None):
    sql = "SELECT chunk_text, page_number, chunk_index, section, embedding FROM rpa_chunks WHERE session_id = ?"
    params = [session_id]
    if section:
        sql += " AND section = ?"
        params.append(section)
    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    if not rows:
        return []

    # cosine similarity between the query and every chunk of this paper
    matrix = np.stack([np.frombuffer(r[4], dtype=np.float32) for r in rows])
    q = np.asarray(query_vector, dtype=np.float32)
    scores = matrix @ q / (np.linalg.norm(matrix, axis=1) * np.linalg.norm(q) + 1e-9)
    best = np.argsort(-scores)[:top_k]

    return [{
        "chunk_text": rows[i][0],
        "page_number": rows[i][1],
        "chunk_index": rows[i][2],
        "section": rows[i][3] or "unknown",
        "relevance_score": float(scores[i]),
    } for i in best]


def get_all_chunks(session_id: str) -> List[CitationObject]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT chunk_text, page_number, chunk_index, section FROM rpa_chunks
           WHERE session_id = ? ORDER BY chunk_index""",
        (session_id,),
    ).fetchall()
    conn.close()
    return [{"chunk_text": r[0], "page_number": r[1], "chunk_index": r[2], "section": r[3] or "unknown"}
            for r in rows]