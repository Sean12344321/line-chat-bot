# ShoppingBot - LINE Bot for E-Commerce Search

## Overview
ShoppingBot is a LINE Bot that helps users search for products across multiple e-commerce platforms (PChome, eBay, Momo) using natural language queries. It leverages AWS OpenSearch for product indexing and similarity search, and Python for web scraping and LINE integration. Users can input sentences like "I want to find treadmills priced under 10000 TWD" to get relevant products displayed in a LINE response.

## Features
- **Multi-Platform Search**: Searches PChome, eBay, and Momo for products matching user queries.
- **Natural Language Processing**: Parses user inputs (e.g., "Please find a yoga mat") to extract keywords and filters (e.g., price ceilings).
- **Embedding-Based Search**: Uses k-NN search in AWS OpenSearch to find similar products based on embeddings.
- **Deduplication**: Ensures unique products by deleting items with >0.95 cosine similarity.
- **LINE Integration**: Delivers results via a responsive Flex Message carousel or text replies.

## Prerequisites
- **AWS Account**: Access to AWS OpenSearch and EC2.
- **LINE Developer Account**: Channel access token and secret for LINE Messaging API.
- **Python**: Version 3.8+.
- **Dependencies**: Install via `pip install -r requirements.txt`.

## File description
### src/scrapers/main.py: 
Scrapes products from eBay, Momo, PChome using keywords in data/search_keywords.txt.
### src/opensearch/function.py: 
Functions that related to opensearch.
### src/line/app.py: 
Starts the webhook server to handle LINE messages and run scrapers in background per two days.

## execute
`cd line-chat-bot`
`gunicorn -w 4 -b 0.0.0.0:5000 src.line.app:app`

## License
### MIT License
