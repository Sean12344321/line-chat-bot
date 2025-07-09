from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
import time, random, logging

logging.basicConfig(level=logging.INFO)

def scrape_ebay(keyword, max_items=100):
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

    search_url = f"https://www.ebay.com/sch/i.html?_nkw={keyword.replace(' ', '+')}"
    items = []

    try:
        logging.info(f"Navigating to: {search_url}")
        driver.get(search_url)

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CLASS_NAME, 'pagination__item'))
            )
        except TimeoutException:
            logging.warning("Pagination elements not found, possibly single page")
            total_pages = 1
        else:
            pages = driver.find_elements(By.CLASS_NAME, 'pagination__item')
            total_pages = len(pages)
            logging.info(f"Found {total_pages} pages")

        current_page = 1
        while current_page <= total_pages:  
            logging.info(f"Scraping page {current_page}: {driver.current_url}")

            WebDriverWait(driver, 15).until(
                EC.presence_of_all_elements_located((By.CLASS_NAME, 's-item__wrapper'))
            )
            products = driver.find_elements(By.CLASS_NAME, 's-item__wrapper')
            if len(products) == 2:
                logging.error("Only 2 products found, it's ebay problem that only show 2 invalid products")
                return items
            for p in products:
                try:
                    name = p.find_element(By.CLASS_NAME, 's-item__title').text
                    price_element = p.find_element(By.CLASS_NAME, 's-item__price')
                    price_text = price_element.text.replace('NT', '').replace('$', '').replace(',', '').strip()
                    try:
                        price = int(float(price_text.split(' to ')[0])) 
                    except ValueError:
                        logging.warning(f"Invalid price format: {price_text}")
                        continue

                    href = p.find_element(By.CLASS_NAME, 's-item__link').get_attribute('href')
                    image_wrapper = p.find_element(By.CSS_SELECTOR, '.s-item__image-wrapper.image-treatment')
                    img_tag = image_wrapper.find_element(By.TAG_NAME, 'img')
                    image_url = img_tag.get_attribute('src')
                    items.append({"e_commercesite": "ebay", "name": name, "price_twd": price, "href": href, "image_url": image_url, "keyword": keyword})
                    logging.info(f"name: {name}, price_twd: {price}, href: {href}, image_url: {image_url}, keyword: {keyword}")
                    if len(items) >= max_items:
                        logging.info(f"Reached {max_items} items, stopping")
                        return items

                except StaleElementReferenceException:
                    logging.warning("Stale element encountered, skipping product")
                    continue
                except Exception as e:
                    logging.warning(f"Error parsing product: {e}")
                    continue

            if current_page < total_pages:
                max_attempts = 3
                for attempt in range(max_attempts):
                    try:
                        next_button = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.CLASS_NAME, 'pagination__next'))
                        )
                        if 'disabled' in next_button.get_attribute('class'):
                            logging.info("Reached last page")
                            return items

                        next_button.click()
                        time.sleep(random.uniform(2, 4))  # Random delay to avoid detection
                        current_page += 1
                        break

                    except StaleElementReferenceException:
                        logging.warning(f"Stale next button on attempt {attempt + 1}")
                        if attempt == max_attempts - 1:
                            logging.error("Max attempts reached for next button")
                            return items
                        continue
                    except Exception as e:
                        logging.error(f"Failed to go to next page: {e}")
                        return items

    except Exception as e:
        logging.error(f"Error during scraping: {e}")
    finally:
        driver.quit()
        logging.info("Browser closed")

    return items

if __name__ == "__main__":
    data = []
    max_attempts = 10
    attempts = 0
    while not data and attempts < max_attempts:
        data = scrape_ebay("t-shirt", max_items=100)
        attempts += 1
    for item in data:
        print(item)