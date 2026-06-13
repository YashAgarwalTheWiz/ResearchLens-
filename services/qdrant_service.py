from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams,Distance
from config import QDRANT_API_KEY,QDRANT_URL,COLLECTION_NAME
from graph.state import CitationObject,RetrievedDoc
from typing import List
from qdrant_client.models import PointStruct,Filter, FieldCondition, MatchValue
import uuid
from qdrant_client.models import PayloadSchemaType

client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=60)

def init_collection():
    if not client.collection_exists(collection_name=COLLECTION_NAME):
        vectors_config = VectorParams(size=384, distance=Distance.COSINE)
        client.create_collection(collection_name=COLLECTION_NAME, vectors_config=vectors_config)

    client.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="session_id",
        field_schema=PayloadSchemaType.KEYWORD
    )


def upsert_chunks(chunks: List[CitationObject], embeddings: List[List[float]],session_id: str):
    points=[]
    for chunk,embed in zip(chunks,embeddings):
        id=str(uuid.uuid4())
        vector=embed
        payload={
            'chunk_text':chunk['chunk_text'],
            'page_number':chunk['page_number'],
            'chunk_index':chunk['chunk_index'],
            'session_id' :session_id
        }
        point=PointStruct(id=id,vector=vector,payload=payload)
        points.append(point)

    client.upsert(collection_name=COLLECTION_NAME,points=points)

def search(query_vector: List[float],session_id:str,top_k:int =5)->List[RetrievedDoc]:
    query_filter=Filter(
        must=[FieldCondition(key='session_id',match=MatchValue(value=session_id))]
    )
    response=client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=top_k,
        query_filter=query_filter
    )
    results = response.points
    res=[]
    for result in results:
        res.append({
            'chunk_text':result.payload['chunk_text'],
            'page_number':result.payload['page_number'],
            'chunk_index':result.payload['chunk_index'],
            'relevance_score':result.score
        })
    return res

def get_all_chunks(session_id: str) -> List[CitationObject]:
    query_filter = Filter(
        must=[FieldCondition(key='session_id', match=MatchValue(value=session_id))]
    )

    all_points = []
    offset = None

    while True:
        points, next_offset = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=query_filter,
            limit=100,
            offset=offset
        )
        all_points.extend(points)
        if next_offset is None:
            break
        offset = next_offset

    chunks = []
    for point in all_points:
        chunks.append({
            'chunk_text': point.payload['chunk_text'],
            'page_number': point.payload['page_number'],
            'chunk_index': point.payload['chunk_index']
        })

    chunks.sort(key=lambda c: c['chunk_index'])
    return chunks