from services.qdrant_service import get_all_chunks
import json

session_id = 'd317f640-c444-4d16-8b15-5ddca48ecf44'
chunks = get_all_chunks(session_id)

with open('eval/test_chunks.json', 'w') as f:
    json.dump(chunks, f, indent=2)

print(f"Total chunks: {len(chunks)}")
for c in chunks:
    print(f"[{c['chunk_index']}] (page {c['page_number']}): {c['chunk_text'][:80]}...")