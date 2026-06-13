from services.qdrant_service import init_collection
from graph.builder import build_graph

# 1. Init Qdrant collection
init_collection()

# 2. Build the graph
graph = build_graph()

# 3. Define initial state
state = {
    'pdf_path': 'test2.pdf',
    'query': 'What is the current state-of-the-art top-1 accuracy on ImageNet using Vision Transformers?',
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

# 4. Run it
result = graph.invoke(state)

# 5. Print output
print(result['web_search_triggered']) 
print('_*20')
print(result['retrieved_docs']) 
print('_*20')
