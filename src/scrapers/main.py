import os, sys, logging, time
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime
from pathlib import Path
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
    refresh_aws_auth
)

env_path = Path(__file__).resolve().parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path, override=True)
logging.basicConfig(level=logging.INFO) 

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def run_crawler():
    """Run scraping, translation, and storage for all e-commerce sites."""
    with open("./data/search_keywords.txt", "r", encoding="utf-8") as file:
        lines = file.readlines()
    retry_limit = 3
    all_items = []
    for attempt in range(retry_limit):
        try:
            create_index_for_opensearch()
            keywords = {
                "Fitness": {"zh": [], "en": []},
                "Technology": {"zh": [], "en": []},
            }
            current_category = None
            for line in lines:
                line = line.strip()
                if line.startswith("#"):
                    current_category = line[1:].strip().split('-')
                elif line and current_category:
                    keywords[current_category[0]][current_category[1]].append(line)
            for category in keywords:
                for zh_keyword, en_keyword in zip(keywords[category]["zh"], keywords[category]["en"]):
                    try:
                        all_items.extend(scrape_ebay(en_keyword))
                        all_items.extend(scrape_momo(en_keyword, zh_keyword))
                        all_items.extend(scrape_pchome(en_keyword, zh_keyword))
                    except Exception as e:
                        logging.error(f"failed for {zh_keyword}/{en_keyword}: {str(e)}")
            current_time = datetime.now().isoformat()
            for item in all_items:
                item["timestamp"] = current_time
            logging.info(f"Collected {len(all_items)} items from all e-commerce sites")
            for item in all_items:
                embedding = openai_client.embeddings.create(input=item["name"], model=os.getenv("OPENAI_EMBEDDING_MODEL")).data[0].embedding
                item["embedding"] = embedding 
                logging.info(f"Created embedding for item: {item['name']}")
            logging.info("All items embeddings have been created")

            store_and_replace_items_from_opensearch(all_items)
            logging.info("All items stored to OpenSearch")
            delete_outdated_items_from_opensearch(days=3)
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
    refresh_aws_auth()
    get_document_count_from_opensearch(e_commercesite="ebay", keyword="treadmill")
    get_document_count_from_opensearch(e_commercesite="ebay", keyword="dumbbell")
    get_document_count_from_opensearch(e_commercesite="ebay", keyword="yoga mat")
    get_document_count_from_opensearch(e_commercesite="ebay", keyword="resistance band")
    get_document_count_from_opensearch(e_commercesite="ebay", keyword="hand grip strengthener")
    get_document_count_from_opensearch(e_commercesite="ebay", keyword="exercise ball")
    get_document_count_from_opensearch(e_commercesite="ebay", keyword="jump rope")
    get_document_count_from_opensearch(e_commercesite="ebay", keyword="tablet")
    get_document_count_from_opensearch(e_commercesite="ebay", keyword="bluetooth earphone")
    get_document_count_from_opensearch(e_commercesite="ebay", keyword="smartphone")
    get_document_count_from_opensearch(e_commercesite="ebay", keyword="mouse")
    get_document_count_from_opensearch(e_commercesite="ebay", keyword="laptop")
    get_document_count_from_opensearch(e_commercesite="ebay", keyword="charging cable")
    get_document_count_from_opensearch(e_commercesite="ebay", keyword="power bank")
    # search_top_k_similar_items_from_opensearch("laptop", "筆電")