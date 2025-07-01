import os, logging, boto3
from dotenv import load_dotenv
from flask import Flask, request, abort
from typing import List, Dict
from openai import OpenAI
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth
from linebot.v3 import WebhookHandler
from linebot.v3.webhooks import MessageEvent, TextMessageContent, FollowEvent
from linebot.v3.messaging import FlexMessage, ReplyMessageRequest, Configuration, ApiClient, MessagingApi, FlexContainer
from linebot.v3.exceptions import InvalidSignatureError
from scrapers.ebay import scrape_ebay
from scrapers.momo import scrape_momo
from scrapers.pchome import scrape_pchome
import json

load_dotenv()

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
configuration = Configuration(access_token=os.getenv('LINE_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_SECRET'))
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
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

def delete_all_items_from_opensearch(index_name: str = "products"):
    """Delete all documents from the specified OpenSearch index."""
    try:
        query = {
            "query": {
                "match_all": {}
            }
        }
        response = opensearch_client.delete_by_query(index=index_name, body=query)
        logging.info(f"Deleted {response['deleted']} documents from index '{index_name}'")
    except Exception as e:
        logging.error(f"Failed to delete documents from index '{index_name}': {str(e)}")


def run_crawler():
    keyword = "laptop"
    create_opensearch_index()
    all_items = scrape_ebay(keyword) + scrape_momo(keyword) + scrape_pchome(keyword)
    logging.info(f"Collect {len(all_items)} items from all electronic commerce sites")

    # all_items = translate_productNames_to_english(all_items, source_lang='zh', target_lang='en')
    # logging.info("All items translated to English")
    
    for item in all_items:
        embedding = openai_client.embeddings.create(input=item["name"], model=os.getenv("OPENAI_MODEL")).data[0].embedding
        item["embedding"] = embedding
    logging.info("All items normalized and embeddings created")

    store_items_to_opensearch(all_items)
    logging.info("All items stored to OpenSearch")

def search_similar(user_input: str, index_name: str = "products", top_k: int = 5) -> List[Dict]:
    try:
        embedding = openai_client.embeddings.create(input=user_input, model=os.getenv("OPENAI_MODEL")).data[0].embedding
        query = {
            "size": top_k, 
            "query": {
                "knn": {
                    "embedding": {
                        "vector": embedding,
                        "k": top_k
                    }
                }
            },
            "_source": ["E-Commerce site", "name", "price_twd", "href"]
        }
        response = opensearch_client.search(index=index_name, body=query)
        return [hit["_source"] for hit in response["hits"]["hits"]]
    except Exception as e:
        logging.error(f"Search failed: {e}")
        return []

with open("flex_message.json", encoding='utf-8') as f:
    flex_msg = json.load(f)

@app.route("/", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.info("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)

    return 'OK'

@handler.add(FollowEvent)
def handle_follow(event):
    welcome_msg = flex_msg["welcome"]
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        bubble_string = json.dumps(welcome_msg, ensure_ascii=False)
        message = FlexMessage(alt_text="Welcome!", contents=FlexContainer.from_json(bubble_string))
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[message]
            )
        )
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    bubble_template = flex_msg["product_template"]
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        user_input = event.message.text
        products = search_similar(user_input)
        items = []
        for p in products:
            try:
                bubble_str = json.dumps(bubble_template, ensure_ascii=False)
                bubble_str = bubble_str.replace("{name}", p["name"])
                bubble_str = bubble_str.replace("{price}", str(p["price_twd"]))
                bubble_str = bubble_str.replace("{uri}", p["href"])
                bubble = json.loads(bubble_str)
                items.append(bubble)
            except KeyError as e:  
                logging.error(f"Missing key in product data: {e}")
                continue
        print(f"Found {len(items)} products for user input: {user_input}")
        bubble_msg = {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": items
            }
        }
        print(bubble_msg)
        bubble_string = json.dumps(bubble_msg, ensure_ascii=False)
        message = FlexMessage(alt_text="Search Results", contents=FlexContainer.from_json(bubble_string))
        try:
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[message]
                )
            )
        except Exception as e:
            logging.error(f"Failed to reply message: {e}")

if __name__ == "__main__":
    # app.run(host="0.0.0.0", port=5000, debug=True)

    # run_crawler()
    # store_items_to_opensearch(items)
    # print(items)