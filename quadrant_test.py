from qdrant_client import QdrantClient
from config import QDRANT_API_KEY,QDRANT_URL

client=QdrantClient(url=QDRANT_URL,api_key=QDRANT_API_KEY)

print(client.get_collections())