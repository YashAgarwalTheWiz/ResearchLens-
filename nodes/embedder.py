from graph.state import ResearchState
from services.embedding_service import get_embeddings
from services.vector_store import upsert_chunks

def embedder(state:ResearchState)->dict:
    chunks=state['chunks']
    texts=[chunk['chunk_text'] for chunk in chunks]
    embeddings=get_embeddings(texts)
    upsert_chunks(chunks, embeddings, state['session_id'], state.get('paper_id', state['session_id']))
    return {}