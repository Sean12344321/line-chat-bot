# line-shopping-bot

> LINE ID: [@006whxns](https://line.me/R/ti/p/@006whxns)

## System Architecture

<img width="756" height="321" alt="line-chat-bot flowchart" src="https://github.com/user-attachments/assets/92a20128-4c1c-4f66-9044-d698a8c2a896" />

## Explanation

This project is a LINE-based chatbot that semantically searches real time products information across PChome, eBay, and Momo.

In the **building phase**, an AWS EC2 instance crawls product data, generates vector embeddings using GPT, and stores them in OpenSearch.

During the **user interaction phase**, users send queries via LINE. The EC2 server (behind Nginx on port 443) receives the request, applies GPT Nano to extract user intent and filters (such as product type, platform, or price range) and uses AWS Translate to produce both Chinese and English versions. It then queries OpenSearch—using Chinese for PChome and Momo, and English for eBay—and returns the most relevant results to the user.

The project ensures real-time product information by re-crawling fresh data daily and deleting products that haven't been updated in two days.
