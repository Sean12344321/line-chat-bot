import requests
import time
import logging

logging.basicConfig(level=logging.INFO)

def scrape_pchome(keyword, max_items=100):
    items = []
    base_url = "https://ecshweb.pchome.com.tw/search/v3.3/all/results"
    
    # Fetch the first page to get total pages
    params = {
        "q": keyword,
        "page": 1,
        "sort": "sale/dc"
    }
    
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status() # Raise an error for bad responses
        data = response.json()
        
        total_pages = data.get('totalPage', 1) 
        logging.info(f"Total pages found: {total_pages}")
        
        for page in range(1, total_pages + 1):
            logging.info(f"Scraping page {page}...")
            params['page'] = page
            try:
                response = requests.get(base_url, params=params)
                response.raise_for_status()
                data = response.json()
                
                if 'prods' not in data or not data['prods']:
                    logging.warning(f"No products found on page {page}")
                    break
                
                for prod in data['prods']:
                    name = prod['name']
                    price = prod['price']
                    href = f"https://24h.pchome.com.tw/prod/{prod['Id']}"
                    image_url = f"https://cs-a.ecimg.tw/{prod['picB']}" if 'picB' in prod else None
                    items.append({"E-Commerce site": "pchome", "name": name, "price_twd": price, "href": href, "image_url": image_url, "keyword": keyword})
                    logging.info(f"product: {name}, price_twd: {price}, url: {href}, image_url: {image_url}, keyword: {keyword}")

                    if len(items) >= max_items:
                        logging.info(f"Reached {max_items} items, stopping")
                        return items
                
            
            except Exception as e:
                logging.error(f"Error on page {page}: {e}")
                break
                
    except Exception as e:
        logging.error(f"Error fetching initial page: {e}")
    
    return items

if __name__ == "__main__":
    data = scrape_pchome("laptop", max_items=100)
    for item in data:
        print(item)