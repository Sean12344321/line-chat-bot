from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import StaleElementReferenceException
import time, logging

logging.basicConfig(level=logging.INFO)

def scrape_momo(keyword, max_items=100):
    # Configure Chrome options for Linux
    options = Options()
    options.add_argument('--headless')  
    options.add_argument('--no-sandbox')  
    options.add_argument('--disable-dev-shm-usage')  
    options.add_argument('--lang=en-US') 
    
    try:
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
    except Exception as e:
        logging.error(f"Failed to initialize ChromeDriver: {e}")
        return []
    
    search_url = f"https://www.momoshop.com.tw/search/searchShop.jsp?keyword={keyword}"
    items = []

    try:
        logging.info(f"Navigating to: {search_url}")
        driver.get(search_url)
        start_page = 0
        while start_page == 0:
            pages = driver.find_elements(By.CLASS_NAME, 'pagination-link')
            start_page = len(pages) // 2 # momo pagination is invalide for first half of the pages, so we start from the second half
            logging.info(f"Find {len(pages)} pages")
        for page in pages[start_page:len(pages)]:
            page.click()
            time.sleep(2) # Wait for page to load, can't use WebDriverWait here due to dynamic content
            print(driver.current_url)
            products = driver.find_elements(By.CLASS_NAME, 'listAreaLi')
            for p in products:
                try:
                    name = p.find_element(By.CLASS_NAME, 'prdNameTitle').text
                    price = p.find_element(By.CLASS_NAME, 'price').text.replace(",", "")
                    href = p.find_element(By.CLASS_NAME, 'goods-img-url').get_attribute('href')
                    image_url = p.find_element(By.CLASS_NAME, 'prdImg').get_attribute('src')
                    items.append({"E-Commerce site": "momo", "name": name, "price_twd": int(price), "href": href, "image_url": image_url, "keyword": keyword})
                    logging.info(f"name: {name}, price_twd: {price}, image_url: {image_url}, keyword: {keyword}")
                    if len(items) >= max_items:
                        logging.info(f"Reached maximum items limit: {max_items}")
                        driver.quit()
                        return items
                except StaleElementReferenceException:
                    logging.warning("Stale element encountered, skipping this product")
                    continue
                except Exception as e:
                    logging.warning(f"Error parsing product: {e}")
                    break
    except Exception as e:
        logging.error(f"Error during scraping: {e}")
    finally:
        driver.quit()
        logging.info("Browser closed")
    return items

if __name__ == "__main__":
    data = scrape_momo("laptop", max_items=200)
    for item in data:
        print(item)