from services.qdrant_service import get_all_chunks
import json

session_id = '10d0d11d-1af2-4e26-94cf-0315b2b8a098'
chunks = get_all_chunks(session_id)

with open('eval/test2_chunks.json', 'w') as f:
    json.dump(chunks, f, indent=2)

print(f"Total chunks: {len(chunks)}")
for c in chunks:
    print(f"[{c['chunk_index']}] (page {c['page_number']}): {c['chunk_text'][:80]}...")