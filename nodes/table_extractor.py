from graph.state import ResearchState
from services.table_service import extract_tables


def table_extractor(state: ResearchState) -> dict:
    pages = {c['page_number'] for c in state['chunks']
             if c['section'] in ('experiments', 'results')}
    return {'tables': extract_tables(state['pdf_path'], pages)}