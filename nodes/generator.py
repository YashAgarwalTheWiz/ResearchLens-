from langchain_groq import ChatGroq
from config import GROQ_API_KEY
from graph.state import ResearchState

llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=GROQ_API_KEY)

def generator(state:ResearchState)->dict:
    context = "\n\n".join([doc['chunk_text'] for doc in state['retrieved_docs']])
    chat_history_str = ""
    for message in state['chat_history']:
        chat_history_str += f"{message['role'].capitalize()}: {message['content']}\n"
    prompt=f"""
        You are a research paper assistant. Answer the user's question using only the provided context from the paper.

        Context:
        {context}

        Previous conversation:
        {chat_history_str}

        Current question:
        {state['query']}

        Rules:
        - Answer strictly from the context. Do not make up information.
        - If the context does not contain enough information to answer, say so explicitly.
        - Be concise and precise.
        - Do not repeat the question back.
    """
    response=llm.invoke(prompt)
    return {'answer':response.content}