from config import QA_TOP_K
from graph.state import ResearchState
from services.embedding_service import get_embeddings
from services.vector_store import search


def retriever(state: ResearchState) -> dict:
    query_vector = get_embeddings([state['query']], input_type='search_query')[0]
    docs = search(query_vector, session_id=state['session_id'], top_k=QA_TOP_K)
    return {'retrieved_docs': docs}