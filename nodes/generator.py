from config import QA_HISTORY_MESSAGES
from graph.state import ResearchState
from services.llm_service import text_call, RateLimited

NOT_FOUND = "I couldn't find this in the paper."


def generator(state: ResearchState) -> dict:
    docs = state.get('retrieved_docs', [])
    if not docs:
        return {'answer': NOT_FOUND}

    # label each excerpt [S1], [S2], ... so the answer can point at its sources
    context = "\n\n".join(
        f"[S{i}] (page {d['page_number']}, {d['section']})\n{d['chunk_text']}"
        for i, d in enumerate(docs, start=1)
    )
    history = state.get('chat_history', [])[-QA_HISTORY_MESSAGES:]
    history_text = "\n".join(f"{m['role'].capitalize()}: {m['content'][:500]}" for m in history) or "(none)"

    prompt = f"""You are a research paper assistant. Answer the question using ONLY the excerpts from the paper below.

Excerpts:
{context}

Previous conversation (for context only):
{history_text}

Question: {state['query']}

Rules:
- After each sentence, cite the excerpt(s) it comes from, like [S1] or [S2][S4].
- If the excerpts don't contain the answer, reply exactly: "{NOT_FOUND}"
- Do not use outside knowledge. Be concise. Don't repeat the question."""

    try:
        return {'answer': text_call(prompt)}
    except RateLimited as e:
        return {'answer': str(e)}
    except Exception as e:
        return {'answer': f"Answer generation failed: {e}"}