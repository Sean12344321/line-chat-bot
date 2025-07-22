import os, logging, json, copy, sys, boto3, atexit
from datetime import datetime
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from apscheduler.schedulers.background import BackgroundScheduler
from typing import Dict
from pathlib import Path
from flask import Flask, request, abort
from dotenv import load_dotenv
from linebot.v3 import WebhookHandler 
from linebot.v3.webhooks import MessageEvent, TextMessageContent, FollowEvent
from linebot.v3.messaging import FlexMessage, ReplyMessageRequest, Configuration, ApiClient, MessagingApi, FlexContainer, TextMessage
from opensearchpy.exceptions import TransportError
from linebot.v3.exceptions import InvalidSignatureError
from opensearch.function import refresh_aws_auth, search_top_k_similar_items_from_opensearch
from apscheduler.schedulers.background import BackgroundScheduler
from scrapers.main import run_crawler
env_path = Path(__file__).resolve().parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path, override=True)
logging.basicConfig(level=logging.INFO)
logging.getLogger('apscheduler').setLevel(logging.DEBUG)
app = Flask(__name__)

def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_crawler, 'cron', hour=4, minute=30, day='*/2')
    scheduler.add_job(refresh_aws_auth, 'interval', hours=5)
    # Run immediately on startup as well
    scheduler.add_job(run_crawler, 'date', run_date=datetime.now())
    scheduler.add_job(refresh_aws_auth, 'date', run_date=datetime.now())
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())

configuration = Configuration(access_token=os.getenv('LINE_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_SECRET'))

def translate_text(text, source_lang='zh', target_lang='en'):
    """Translate text using AWS Translate."""
    try:
        translate = boto3.client('translate', region_name='ap-northeast-1')
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

def build_bubble(product: Dict, template: Dict) -> Dict:
    """Build a Flex Message bubble for a product."""
    try:
        bubble = copy.deepcopy(template)
        bubble["hero"]["url"] = product.get("image_url", "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQsI1LNctDqWA1iEu24tUcfbiWZKqabrF7moQ&s")
        bubble["body"]["contents"][0]["text"] = product["name"]
        bubble["body"]["contents"][0]["action"]["uri"] = product["href"]
        bubble["body"]["contents"][1]["contents"][0]["text"] = f"NT$ {product['price_twd']}"
        bubble["body"]["contents"][1]["contents"][1]["text"] = product["e_commercesite"].upper()
        return bubble
    except KeyError as e:
        logging.error(f"Missing key in product data: {e}")
        raise

def build_flex_message(user_input: str, template: Dict) -> FlexMessage:
    """Build a Flex Message carousel from search results."""
    try:
        translated_input = translate_text(user_input, source_lang='zh', target_lang='en')
        products = search_top_k_similar_items_from_opensearch(en_userprompt=translated_input, zh_userprompt=user_input)
        bubbles = [bubble for product in products if (bubble := build_bubble(product, template))]
        if not bubbles:
            logging.info(f"No products found for user input: {user_input}")
            return TextMessage(text="搜尋不到符合要求的商品")
        logging.info(f"Found {len(bubbles)} products for user input: {user_input}")
        bubble_msg = {"type": "carousel", "contents": bubbles}
        return FlexMessage(
            alt_text="Search Results",
            contents=FlexContainer.from_json(json.dumps(bubble_msg, ensure_ascii=False))
        )
    except TransportError as e:
        if e.status_code == 504 or e.status_code == 503 or e.status_code == 502:
            logging.error(f"504 Gateway Timeout from OpenSearch: {str(e)}")
            return TextMessage(text="aws資料庫暫時崩潰，請稍後再試")
        else:
            logging.error(f"OpenSearch TransportError: {str(e)}")
            return TextMessage(text="搜尋商品時發生資料庫錯誤，請稍後再試")

    except Exception as e:
        logging.error(f"Failed to build Flex Message for input '{user_input}': {str(e)}")
        return TextMessage(text="搜尋商品時發生資料庫錯誤，請稍後再試")

@app.route("/", methods=['POST'])
def callback():
    """Handle LINE webhook callbacks.""" 
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.info("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)
    return 'OK'

with open("./data/flex_message.json", encoding='utf-8') as f:
    flex_msg = json.load(f)

@handler.add(FollowEvent)
def handle_follow(event):
    """Handle LINE follow events."""
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
    """Handle LINE text messages."""
    with ApiClient(configuration) as api_client:
        try:
            line_bot_api = MessagingApi(api_client)
            user_input = event.message.text
            
            message = build_flex_message(user_input, flex_msg["product_template"])
            if isinstance(message, FlexMessage) and not message.contents.to_dict().get("contents"):
                raise ValueError("FlexMessage contents is empty")
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[message]
                )
            )
        except Exception as e:
            logging.error(f"Failed to reply message: {str(e)}")
            line_bot_api = MessagingApi(api_client)
            message = TextMessage(text="搜尋失敗，請稍後再試")
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[message] 
                )
            )


# if __name__ == "__main__":
    # start_scheduler()
    # app.run(host="0.0.0.0", port=5000, debug=False)  # Use port 5000 for Flask app
start_scheduler()