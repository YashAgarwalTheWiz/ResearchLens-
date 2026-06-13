from graph.state import ResearchState
from langchain_groq import ChatGroq
from config import GROQ_API_KEY
llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=GROQ_API_KEY)

def grader(state:ResearchState)->dict:
    docs=state['retrieved_docs']
    filtered_list=[]
    web_search_triggered=False
    for doc in docs:
        prompt=f'''You are a document relevance grader.
        Given a user query and a document chunk, decide if the chunk contains information useful for answering the query.
        Query: {state['query']}
        Document chunk: {doc['chunk_text']}
        Respond with ONLY 'yes' or 'no'. No explanation.'''
        response=llm.invoke(prompt)
        if 'yes' in response.content:
            filtered_list.append(doc)
    if not filtered_list:
        web_search_triggered=True
    return {'retrieved_docs':filtered_list,'web_search_triggered':web_search_triggered}