from langchain_groq import ChatGroq
from config import GROQ_API_KEY
from graph.state import ResearchState
llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=GROQ_API_KEY)

def query_router(state:ResearchState)-> dict:
    prompt = f"""Given this query, classify it as one of: summary, gap, qa.
    - summary: user wants a summary of the paper
    - gap: user wants research gaps
    - qa: user wants a specific question answered

    Query: {state['query']}
    Respond with one word only."""
    response=llm.invoke(prompt)
    query_type=response.content.strip().lower()
    return {'query_type':query_type}