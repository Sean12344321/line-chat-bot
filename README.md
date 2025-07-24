# line-shopping-gpt

> LINE ID: [@006whxns](https://line.me/R/ti/p/@006whxns)

## System Architecture

[System Architecture](data/line-chat-bot-system-architecture.png)

## Explanation

This project is a LINE-based chatbot that semantically searches product information across PChome, eBay, and Momo.
In the **building phase**, an AWS EC2 instance crawls product data, generates vector embeddings using GPT, and stores them in OpenSearch.
During the **user interaction phase**, users send queries via LINE. The EC2 server (behind Nginx on port 443) receives the request, uses AWS Translate to produce both Chinese and English versions, and applies GPT Nano to extract user intent and filters (such as product type, platform, or price range). It then queries OpenSearch—using Chinese for PChome and Momo, and English for eBay—and returns the most relevant results to the user.