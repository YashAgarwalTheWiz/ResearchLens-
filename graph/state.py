from typing import TypedDict, List


class CitationObject(TypedDict):
    chunk_text: str
    page_number: int
    chunk_index: int
    section: str


class RetrievedDoc(TypedDict):
    chunk_text: str
    page_number: int
    chunk_index: int
    relevance_score: float
    section: str


class ResearchState(TypedDict, total=False):
    # --- ingestion (upload a paper) ---
    session_id: str
    paper_id: str
    pdf_path: str
    chunks: List[CitationObject]
    tables: list
    extracted: dict
    error: str

    # --- question answering (Ask tab) ---
    query: str
    chat_history: List
    retrieved_docs: List[RetrievedDoc]
    answer: str
    citations: List[dict]