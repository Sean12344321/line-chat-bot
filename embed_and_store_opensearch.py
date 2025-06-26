import time, random, boto3, requests, logging, os
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth
from openai import OpenAI
from flask import Flask, request, jsonify
from scrapers.ebay import scrape_ebay
from scrapers.momo import scrape_momo
from scrapers.pchome import scrape_pchome  
from typing import List, Dict
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
load_dotenv()
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
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

def translate_text(text, source_lang='zh', target_lang='en'):
    try:
        translate = boto3.client('translate')
        
        response = translate.translate_text(
            Text=text,
            SourceLanguageCode=source_lang,
            TargetLanguageCode=target_lang
        )
        
        translated_text = response['TranslatedText']
        logging.info(f"Translated '{text}' to '{translated_text}'")
        return translated_text
    
    except Exception as e:
        logging.error(f"Translation failed for '{text}': {e}")
        return text

def translate_productNames_to_english(items, source_lang='zh', target_lang='en'):
    """
    Normalize product names in a list of scraped items by translating to target language.
    
    Args:
        items (list): List of dicts with 'name' field (e.g., from eBay, Momo, PChome).
        source_lang (str): Source language code.
        target_lang (str): Target language code.
    
    Returns:
        list: Items with translated 'name' fields.
    """
    normalized_items = []
    for item in items:
        if item["E-Commerce site"] == "ebay":
            continue  # Skip eBay items for translation, as they are already in English
        item_copy = item.copy()
        item_copy['name'] = translate_text(item['name'], source_lang, target_lang)
        normalized_items.append(item_copy)
    return normalized_items

def create_opensearch_index(index_name: str = "products"):
    if not opensearch_client.indices.exists(index=index_name):
        index_body = {
            "settings": {"index": {"knn": True}},
            "mappings": {
                "properties": {
                    "EC": {"type": "keyword"}, "name": {"type": "text"},
                    "price_usd": {"type": "float"}, "price_twd": {"type": "float"},
                    "href": {"type": "keyword"},
                    "embedding": {"type": "knn_vector", "dimension": 1536, "method": {"name": "hnsw", "space_type": "cosinesimil", "engine": "nmslib"}}
                }
            }
        }
        opensearch_client.indices.create(index=index_name, body=index_body)
        logging.info(f"Index created: {index_name}")

def store_items_to_opensearch(items: List[Dict], index_name: str = "products"):
    """ Store items in OpenSearch with embeddings."""
    for item in items:
        try:
            doc = {"E-Commerce site": item["E-Commerce site"], "name": item["name"],  "price_twd": item["price_twd"], "href": item["href"], "embedding": item["embedding"]}
            opensearch_client.index(index=index_name, id=item["href"], body=doc) #if href repeated, it will overwrite the existing document 
            logging.info(f"Item stored: {item['name']}") 
        except Exception as e:
            logging.error(f"Failed to store item: {item['name']} - {str(e)}")

def run_crawler():
    keyword = "laptop"
    create_opensearch_index()
    all_items = scrape_ebay(keyword) + scrape_momo(keyword) + scrape_pchome(keyword)
    logging.info(f"Collect {len(all_items)} items from all electronic commerce sites")

    all_items = translate_productNames_to_english(all_items, source_lang='zh', target_lang='en')
    logging.info("All items translated to English")
    
    for item in all_items:
        embedding = openai_client.embeddings.create(input=item["name"], model=os.getenv("OPENAI_MODEL")).data[0].embedding
        item["embedding"] = embedding
    logging.info("All items normalized and embeddings created")

    store_items_to_opensearch(all_items)
    logging.info("All items stored to OpenSearch")

def search_similar(name: str, index_name: str = "products", top_k: int = 5) -> List[Dict]:
    try:
        embedding = openai_client.embeddings.create(input=name, model=os.getenv("OPENAI_MODEL")).data[0].embedding
        query = {"query": {"knn": {"embedding": {"vector": embedding, "k": top_k}}}, "_source": ["EC", "name", "price_usd", "price_twd", "href"]}
        response = opensearch_client.search(index=index_name, body=query)
        return [hit["_source"] for hit in response["hits"]["hits"]]
    except Exception as e:
        logging.error(f"Search failed: {e}")
        return []

@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('query')
    if not query:
        return jsonify({"error": "Missing query parameter"}), 400
    results = search_similar(query)
    return jsonify({"results": results})

if __name__ == "__main__":
    # app.run(host="0.0.0.0", port=8080) 
    run_crawler()  
    # items = [{"EC": "ebay", "name": "Laptop A", "price_twd": 30000, "href": "http://example.com/laptop-a"},
    #           {"EC": "momo", "name": "Laptop B", "price_twd": 25000, "href": "http://example.com/laptop-b"},
    #           {"EC": "pchome", "name": "Laptop C", "price_twd": 28000, "href": "http://example.com/laptop-c"}]
    # items = translate_productNames_to_english(items, source_lang='zh', target_lang='en')
    # store_items_to_opensearch(items)
    # print(items)