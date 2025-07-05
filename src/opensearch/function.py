from typing import List, Dict
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth
from dotenv import load_dotenv
import os, logging, boto3
from datetime import datetime, timedelta
import numpy as np
load_dotenv()
logging.basicConfig(level=logging.INFO)

# Initialize OpenSearch client
credentials = boto3.Session().get_credentials()
aws_auth = AWS4Auth(credentials.access_key, credentials.secret_key, 'ap-northeast-1', 'es', session_token=credentials.token)
opensearch_client = OpenSearch(
    hosts=[{'host': os.getenv("OpenSearch_Domain"), 'port': 443}],
    http_auth=aws_auth,
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection,
    timeout=30,
)

def create_index_for_opensearch(index_name: str = "products"):
    """Create an OpenSearch index with k-NN settings if it doesn't exist."""
    if not opensearch_client.indices.exists(index=index_name):
        index_body = {
            "settings": {
                "index": {"knn": True}
            },
            "mappings": {
                "properties": {
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": 1536,
                        "method": {
                            "name": "hnsw",
                            "space_type": "cosinesimil",
                            "engine": "lucene",
                        }
                    }
                }
            }
        }
        opensearch_client.indices.create(index=index_name, body=index_body)
        logging.info(f"Index created: {index_name}")
    else:
        logging.info(f"Index already exists: {index_name}")

import logging
from opensearchpy import OpenSearch

def get_document_count_from_opensearch(index_name: str = "products", ec_commercesite: str = "\0") -> int:
    """Return the total number of documents in the specified OpenSearch index and optionally filter by ec_commercesite."""
    try:
        if ec_commercesite == "\0":
            response = opensearch_client.count(index=index_name)
            logging.info(f"Total documents in index '{index_name}': {response['count']}")
        else:
            query = {
                "query": {
                    "match": {
                        "E-Commerce site": ec_commercesite
                    }
                }
            }
            response = opensearch_client.count(index=index_name, body=query)
            logging.info(f"Total documents in index '{index_name}' for ec_commercesite '{ec_commercesite}': {response['count']}")
        return response['count']
    except Exception as e:
        log_message = (f"Failed to get document count from index '{index_name}' "
                       f"for ec_commercesite '{ec_commercesite}': {str(e)}" if ec_commercesite != "\0"
                       else f"Failed to get document count from index '{index_name}': {str(e)}")
        logging.error(log_message)
        return -1

def store_and_replace_items_from_opensearch(items: List[Dict], index_name: str = "products"):
    """Store items in OpenSearch with embeddings, replacing highly similar items."""
    for item in items:
        try:
            doc = {
                "E-Commerce site": item["E-Commerce site"],
                "name": item["name"],
                "price_twd": item["price_twd"],
                "href": item["href"],
                "image_url": item["image_url"],
                "embedding": item["embedding"],
                "keyword": item["keyword"],
                "timestamp": item["timestamp"]
            }

            most_similar_item_query = {
                "size": 1,
                "query": {
                    "knn": {
                        "embedding": {
                            "vector": item["embedding"],
                            "k": 1,
                        }
                    }
                },
                "_source": ["name", "embedding"],
            }

            def cosine_similarity(vec1, vec2):
                vec1 = np.array(vec1)
                vec2 = np.array(vec2)
                return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
            
            response = opensearch_client.search(index=index_name, body=most_similar_item_query)
            hits = response["hits"]["hits"]

            if hits:
                similar_item_id = hits[0]["_id"]
                logging.info(f"Most similar item found: {hits[0]['_source']['name']} (ID: {similar_item_id})")
                most_similar_embedding = hits[0]["_source"]["embedding"]
                if cosine_similarity(item["embedding"], most_similar_embedding) > 0.95:
                    # If the most similar item is highly similar, replace it
                    opensearch_client.index(index=index_name, id=similar_item_id, body=doc)
                    logging.info(f"Item replaced: {item['name']} (similar to {hits[0]['_source']['name']})")
                else: 
                    opensearch_client.index(index=index_name, id=item["href"], body=doc)
                    logging.info(f"Item stored: {item['name']}")
            else:
                opensearch_client.index(index=index_name, id=item["href"], body=doc)
                logging.info(f"Item stored: {item['name']}")

        except Exception as e:
            logging.error(f"Failed to store item: {item['name']} - {str(e)}")

def delete_outdated_items_from_opensearch(index_name: str = "products", days: int = 14):
    """Delete items from OpenSearch with timestamps older than the specified number of days."""
    try:
        cutoff_time = (datetime.now() - timedelta(days=days)).isoformat()
        query = {"query": {"range": {"timestamp": {"lte": cutoff_time}}}}
        response = opensearch_client.delete_by_query(index=index_name, body=query)
        deleted = response["deleted"]
        logging.info(f"Deleted {deleted} outdated items")
    except Exception as e:
        logging.error(f"Error deleting outdated items: {str(e)}")


def delete_all_items_from_opensearch(index_name: str = "products"):
    """Delete all documents from the specified OpenSearch index."""
    try:
        query = {"query": {"match_all": {}}}
        response = opensearch_client.delete_by_query(index=index_name, body=query)
        logging.info(f"Deleted {response['deleted']} documents from index '{index_name}'")
        # opensearch_client.indices.delete(index=index_name)
        # logging.info(f"Deleted index '{index_name}'")
    except Exception as e:
        logging.error(f"Failed to delete documents from index '{index_name}': {str(e)}")

def search_top_k_similar_items_from_opensearch(user_input: str, index_name: str = "products", top_k: int = 5) -> List[Dict]:
    """Search for similar products using k-NN based on user input."""
    try:
        from openai import OpenAI
        openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        embedding = openai_client.embeddings.create(input=user_input, model=os.getenv("OPENAI_MODEL")).data[0].embedding
        find_k_similar_items_query = {
            "size": top_k,
            "query": {
                "bool": {
                    "filter": [
                        {
                            "term": {
                                "E-Commerce site": "pchome"
                            }
                        }
                    ],
                    "must": [
                        {
                            "knn": {
                                "embedding": {
                                    "vector": embedding,
                                    "k": top_k
                                }
                            }
                        }
                    ]
                }
            },
            "_source": ["E-Commerce site", "name", "price_twd", "href", "image_url", "keyword"]
        }
        response = opensearch_client.search(index=index_name, body=find_k_similar_items_query)
        return [hit["_source"] for hit in response["hits"]["hits"]]
    except Exception as e:
        logging.error(f"Search failed: {e}")
        return []
    

from opensearchpy.exceptions import NotFoundError

def safe_index_exists(index):
    try:
        opensearch_client.indices.get(index=index)
        return True
    except NotFoundError:
        return False
safe_index_exists("products")