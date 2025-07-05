import os, sys, logging, time
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
from src.scrapers.momo import scrape_momo
from src.scrapers.ebay import scrape_ebay
from src.scrapers.pchome import scrape_pchome
from opensearch.function import (
    create_index_for_opensearch,
    store_and_replace_items_from_opensearch,
    delete_outdated_items_from_opensearch,
    delete_all_items_from_opensearch,
    get_document_count_from_opensearch,
    search_top_k_similar_items_from_opensearch,
)


load_dotenv()
logging.basicConfig(level=logging.INFO)

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# def translate_text(text, source_lang='zh', target_lang='en'):
#     """Translate text using AWS Translate."""
#     try:
#         translate = boto3.client('translate')
#         response = translate.translate_text(
#             Text=text,
#             SourceLanguageCode=source_lang,
#             TargetLanguageCode=target_lang
#         )
#         translated_text = response['TranslatedText']
#         logging.info(f"Translated '{text}' to '{translated_text}'")
#         return translated_text
#     except Exception as e:
#         logging.error(f"Translation failed for '{text}': {e}")
#         return text

# def translate_productNames_to_english(items, source_lang='zh', target_lang='en'):
#     """Normalize product names by translating to target language."""
#     normalized_items = []
#     for item in items:
#         if item["E-Commerce site"] == "ebay":
#             normalized_items.append(item)
#             continue
#         item_copy = item.copy()
#         item_copy['name'] = translate_text(item['name'], source_lang, target_lang)
#         normalized_items.append(item_copy)
#     return normalized_items

def run_crawler():
    """Run scraping, translation, and storage for all e-commerce sites."""
    keyword = "laptop"
    retry_limit = 3
    for attempt in range(retry_limit):
        try:
            create_index_for_opensearch()
            all_items = scrape_ebay(keyword) + scrape_momo(keyword) + scrape_pchome(keyword)
            current_time = datetime.now().isoformat()
            for item in all_items:
                item["timestamp"] = current_time
            logging.info(f"Collected {len(all_items)} items from all e-commerce sites")

            # all_items = translate_productNames_to_english(all_items, source_lang='zh', target_lang='en')
            # logging.info("All items translated to English")

            for item in all_items:
                embedding = openai_client.embeddings.create(input=item["name"], model=os.getenv("OPENAI_MODEL")).data[0].embedding
                item["embedding"] = embedding
                logging.info(f"Created embedding for item: {item['name']}")
            logging.info("All items embeddings have been created")

            store_and_replace_items_from_opensearch(all_items)
            logging.info("All items stored to OpenSearch")
            delete_outdated_items_from_opensearch(days=14)
            logging.info("Outdated items deleted from OpenSearch")
            logging.info("Crawler run completed successfully")
            return
        
        except Exception as e:
            logging.warning(f"Attempt {attempt} failed: {e}")
            if attempt == retry_limit:
                logging.error("Failed to run crawler after multiple attempts, exiting.")
                return
            time.sleep(3) 

if __name__ == "__main__":
    run_crawler()