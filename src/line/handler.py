import os, logging, json, copy
from typing import Dict
from flask import Flask, request, abort
from dotenv import load_dotenv
from linebot.v3 import WebhookHandler
from linebot.v3.webhooks import MessageEvent, TextMessageContent, FollowEvent
from linebot.v3.messaging import FlexMessage, ReplyMessageRequest, Configuration, ApiClient, MessagingApi, FlexContainer
from linebot.v3.exceptions import InvalidSignatureError
from src.opensearch.embed_and_store import search_similar

load_dotenv()
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
configuration = Configuration(access_token=os.getenv('LINE_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_SECRET'))

def build_bubble(product: Dict, template: Dict) -> Dict:
    """Build a Flex Message bubble for a product."""
    try:
        bubble = copy.deepcopy(template)
        bubble["hero"]["url"] = product.get("image_url", "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQsI1LNctDqWA1iEu24tUcfbiWZKqabrF7moQ&s")
        bubble["body"]["contents"][0]["text"] = product["name"]
        bubble["body"]["contents"][0]["action"]["uri"] = product["href"]
        bubble["body"]["contents"][1]["contents"][0]["text"] = f"NT$ {product['price_twd']}"
        bubble["body"]["contents"][1]["contents"][1]["text"] = product["E-Commerce site"].upper()
        return bubble
    except KeyError as e:
        logging.error(f"Missing key in product data: {e}")
        return None

def build_flex_message(user_input: str, template: Dict) -> FlexMessage:
    """Build a Flex Message carousel from search results."""
    products = search_similar(user_input)
    bubbles = [bubble for product in products if (bubble := build_bubble(product, template))]
    logging.info(f"Found {len(bubbles)} products for user input: {user_input}")
    bubble_msg = {"type": "carousel", "contents": bubbles}
    return FlexMessage(
        alt_text="Search Results",
        contents=FlexContainer.from_json(json.dumps(bubble_msg, ensure_ascii=False))
    )

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

with open("data/flex_message.json", encoding='utf-8') as f:
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
        line_bot_api = MessagingApi(api_client)
        user_input = event.message.text
        try:
            message = build_flex_message(user_input, flex_msg["product_template"])
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[message]
                )
            )
        except Exception as e:
            logging.error(f"Failed to reply message: {e}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)