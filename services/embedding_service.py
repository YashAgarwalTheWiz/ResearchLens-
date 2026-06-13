import cohere
from config import COHERE_API_KEY
from typing import List

client=cohere.ClientV2(api_key=COHERE_API_KEY)

def get_embeddings(texts: List[str]) -> List[List[float]]:
    response=client.embed(
        model='embed-english-light-v3.0',
        input_type='search_document',
        texts=texts
    )
    
    return response.embeddings.float_
