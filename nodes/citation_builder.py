from graph.state import ResearchState

def citation_builder(state:ResearchState)->dict:
    citations_list=[]
    for chunk in (state['retrieved_docs']):
        citations_list.append({
            'chunk_text':chunk['chunk_text'],
            'page_number':chunk['page_number'],
            'chunk_index':chunk['chunk_index']
        })
    return {'citations':citations_list}