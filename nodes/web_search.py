from tavily import TavilyClient
from config import TAVILY_API_KEY
from graph.state import ResearchState

client = TavilyClient(TAVILY_API_KEY)

def web_search(state:ResearchState)->dict:
    responses = client.search(
        query=state['query'],
        search_depth="advanced"
    )
    results_list=[]
    for i,response in enumerate(responses['results']):
        results_list.append({
        'chunk_text':response['content'],
        'page_number':0,
        'chunk_index':i,
        'relevance_score':1.0
        })
    return {'retrieved_docs':results_list}