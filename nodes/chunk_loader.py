from graph.state import ResearchState
from services.qdrant_service import get_all_chunks

def chunk_loader(state:ResearchState):
    chunks = get_all_chunks(state['session_id'])
    return {'chunks': chunks}