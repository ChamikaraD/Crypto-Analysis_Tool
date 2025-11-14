import os
import json
from typing import List

from dotenv import load_dotenv
from fastapi import FastAPI
import requests

from model import CryptoAnalysisRequests

load_dotenv()

OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")
OPENROUTER_URL = os.getenv("OPENROUTER_URL")
COINGECKO_URL = os.getenv("COINGECKO_URL")

app = FastAPI(title="Crypto Analysis AI Tool")



def get_crypto_insights(coin_list:List[str]):
    params ={
        "ids" : ",".join(coin_list),   #model eken coin list ek awam,..koma walin seperate krnw
        "vs_currency" : "usd"
    }
    resp = requests.get(COINGECKO_URL,params=params)

    return resp.json()


SYSTEM_PROMPT = """
You are a "CryptoAnalyst AI" - a professional crypto market analyst.

You will be given recent market for data for several crypto currencies (price, market cap, volume, 24h change)

Your job is to producer a structured analysis with the following a Valid JSON Schema

Rules:
-Return one analysis per coin
-Follow the exact JSON schema:
{
"analysis" : [
    {
        "coin" : "<coin name>",
        "summary" : "<2-3 line summary>",
        "sentiment" : "bullish" | "neutral" | "bearish",
        "key_factors" : [
        { "factor" : "<factor name>" , "impact" : "confidence" : <0 -100>}
        ]
    }]
}
- Provide 3 key_factors and 3 insights per coin
- Base your reasoning on given metrics (e.g, price change %,market cap trends)
- Always output only JSON - no Markdown, no explains
"""

def call_openrouter_api(market_data):
    header = {
        "Authorization" : f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json"
    }

    body = {
        "model" : "meta-llama/llama-3.3-70b-instruct:free",
        "messages" : [
            {"role" : "system", "content" : SYSTEM_PROMPT},
            {"role": "user", "content": f"Here is the market data:\n{json.dumps(market_data, indent=2)}"}

        ]
    }

    llm_respond = requests.post(OPENROUTER_URL, json=body, headers=header)
    llm_resp_json = llm_respond.json()
    print(llm_resp_json)
    return llm_resp_json["choices"][0]["message"]["content"]


@app.post("/crypto/analysis")
def crypto_analysis(request :CryptoAnalysisRequests):

    crypto_data = get_crypto_insights(request.coins)
    market_data = [ {
        "name" : data["name"],
        "symbol" : data["symbol"],
        "current_price" : data["current_price"],
        "market_cap" : data["market_cap"],
        "total_volume" : data["total_volume"],
        "price_change_percentage_24h" : data["price_change_percentage_24h"]
    } for data  in crypto_data] #name,symbol , current_price , market_cap, total_volume , price_change_percentage-24h

    print(crypto_data[0]["id"])

    return call_openrouter_api(market_data)





