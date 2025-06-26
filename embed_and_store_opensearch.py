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
    connection_class=RequestsHttpConnection
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

def create_index(index_name: str = "products"):
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
        print(f"已創建索引: {index_name}")

def store_items(items: List[Dict], index_name: str = "products"):
    for item in items:
        try:
            embedding = openai_client.embeddings.create(input=item["name"], model="text-embedding-ada-002").data[0].embedding
            doc = {"EC": item["EC"], "name": item["name"],  "price_twd": item["price_twd"], "href": item["href"], "embedding": embedding}
            opensearch_client.index(index=index_name, id=item["href"], body=doc)
            print(f"已儲存: {item['name']}")
        except Exception as e:
            print(f"儲存失敗: {item['name']} - {e}")
        time.sleep(random.uniform(0.5, 1.5))

def run_crawler():
    keyword = "laptop"
    create_index()
    all_items = scrape_ebay(keyword) + scrape_momo(keyword) + scrape_pchome(keyword)
    print(f"收集 {len(all_items)} 筆數據")
    store_items(all_items)

def search_similar(name: str, index_name: str = "products", top_k: int = 5) -> List[Dict]:
    try:
        embedding = openai_client.embeddings.create(input=name, model="text-embedding-ada-002").data[0].embedding
        query = {"query": {"knn": {"embedding": {"vector": embedding, "k": top_k}}}, "_source": ["EC", "name", "price_usd", "price_twd", "href"]}
        response = opensearch_client.search(index=index_name, body=query)
        return [hit["_source"] for hit in response["hits"]["hits"]]
    except Exception as e:
        print(f"搜尋失敗: {e}")
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
    run_crawler()  # 啟動爬蟲