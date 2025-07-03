from typing import List, Dict
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth
from dotenv import load_dotenv
import os, logging, boto3

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
    timeout=10,
)

def create_opensearch_index(index_name: str = "products"):
    """Create an OpenSearch index with k-NN settings if it doesn't exist."""
    if not opensearch_client.indices.exists(index=index_name):
        index_body = {
            "settings": {
                "index": {"knn": True}
            },
            "mappings": {
                "properties": {
                    "E-Commerce site": {"type": "keyword"},
                    "name": {"type": "text"},
                    "price_twd": {"type": "float"},
                    "href": {"type": "keyword"},
                    "image_url": {"type": "keyword"},
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

def store_items_to_opensearch(items: List[Dict], index_name: str = "products"):
    """Store items in OpenSearch with embeddings."""
    for item in items:
        try:
            doc = {
                "E-Commerce site": item["E-Commerce site"],
                "name": item["name"],
                "price_twd": item["price_twd"],
                "href": item["href"],
                "image_url": item["image_url"],
                "embedding": item["embedding"]
            }
            opensearch_client.index(index=index_name, id=item["href"], body=doc)
            logging.info(f"Item stored: {item['name']}")
        except Exception as e:
            logging.error(f"Failed to store item: {item['name']} - {str(e)}")

def delete_all_items_from_opensearch(index_name: str = "products"):
    """Delete all documents from the specified OpenSearch index."""
    try:
        query = {"query": {"match_all": {}}}
        response = opensearch_client.delete_by_query(index=index_name, body=query)
        logging.info(f"Deleted {response['deleted']} documents from index '{index_name}'")
    except Exception as e:
        logging.error(f"Failed to delete documents from index '{index_name}': {str(e)}")

def search_similar(user_input: str, index_name: str = "products", top_k: int = 5) -> List[Dict]:
    """Search for similar products using k-NN based on user input."""
    try:
        from openai import OpenAI
        openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        embedding = openai_client.embeddings.create(input=user_input, model=os.getenv("OPENAI_MODEL")).data[0].embedding
        query = {
            "size": top_k,
            "query": {
                "knn": {
                    "embedding": {
                        "vector": embedding,
                        "k": top_k,
                    }
                }
            },
            "_source": ["E-Commerce site", "name", "price_twd", "href", "image_url"]
        }
        response = opensearch_client.search(index=index_name, body=query)
        return [hit["_source"] for hit in response["hits"]["hits"]]
    except Exception as e:
        logging.error(f"Search failed: {e}")
        return []