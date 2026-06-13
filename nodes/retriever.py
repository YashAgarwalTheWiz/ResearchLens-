from services.embedding_service import get_embeddings
from services.qdrant_service import search
from graph.state import ResearchState

def retriever(state:ResearchState):
    query=state['query']
    embeddings=get_embeddings([query])
    res=search(embeddings[0],session_id=state['session_id'])
    return {'retrieved_docs':res}