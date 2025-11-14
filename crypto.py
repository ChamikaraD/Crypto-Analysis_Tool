import os
import json
import re
from json import JSONDecodeError
from typing import List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
import requests
from pydantic import ValidationError

from model import CryptoAnalysisRequests, CryptoAnalysisResponse

load_dotenv()

OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")
OPENROUTER_URL = os.getenv("OPENROUTER_URL")
COINGECKO_URL = os.getenv("COINGECKO_URL")

app = FastAPI(title="Crypto Analysis AI Tool")


def get_crypto_insights(coin_list: List[str]):
    params = {
        "ids": ",".join(coin_list),
        "vs_currency": "usd"
    }
    resp = requests.get(COINGECKO_URL, params=params)
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Failed to fetch crypto data from Coingecko")
    return resp.json()


SYSTEM_PROMPT = """
You are a "CryptoAnalyst AI" - a professional crypto market analyst.

You will be given recent market data for several crypto currencies (price, market cap, volume, 24h change).

CRITICAL INSTRUCTIONS:
- Output ONLY valid JSON.
- Do not include markdown, explanations, greetings, or any text before or after JSON.
- JSON must begin with { and end with }.
- Do not insert line breaks inside string values.

Rules:
- Return one analysis per coin
- Follow this JSON schema:
{
"analysis" : [
    {
        "coin" : "<coin name>",
        "summary" : "<2-3 line summary>",
        "sentiment" : "bullish" | "neutral" | "bearish",
        "key_factors" : [
            { "factor" : "<factor name>", "impact": "<low|medium|high>", "confidence": <0-100> }
        ]
    }
]
}
- Provide 3 key_factors per coin
- Base reasoning on given metrics (price change %, market cap trends)
"""


def call_openrouter_api(market_data):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json"
    }

    body = {
        "model": "meta-llama/llama-3.3-70b-instruct:free",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Here is the market data:\n{json.dumps(market_data)}"}
        ]
    }

    response = requests.post(OPENROUTER_URL, json=body, headers=headers)
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Failed to get response from LLM")

    llm_resp_json = response.json()
    try:
        json_str = llm_resp_json["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise HTTPException(status_code=502, detail="LLM response missing expected content")

    print("LLM output:", json_str)

    # Step 1: Remove raw newlines inside strings
    json_str_clean = re.sub(r'(?<!\\)\n', ' ', json_str)

    # Step 2: Extract JSON from any extra text
    match = re.search(r"\{.*\}", json_str_clean, re.DOTALL)
    if not match:
        raise HTTPException(status_code=502, detail="LLM did not return valid JSON structure")

    try:
        payload = json.loads(match.group(0))
    except JSONDecodeError:
        raise HTTPException(status_code=502, detail="LLM did not return valid JSON")

    # Step 3: Validate with Pydantic
    try:
        return CryptoAnalysisResponse.model_validate(payload)
    except ValidationError as e:
        raise HTTPException(status_code=502, detail=f"LLM JSON validation failed: {str(e)}")


@app.post("/crypto/analysis")
def crypto_analysis(request: CryptoAnalysisRequests):
    crypto_data = get_crypto_insights(request.coins)

    market_data = [{
        "name": data["name"],
        "symbol": data["symbol"],
        "current_price": data["current_price"],
        "market_cap": data["market_cap"],
        "total_volume": data["total_volume"],
        "price_change_percentage_24h": data["price_change_percentage_24h"]
    } for data in crypto_data]

    return call_openrouter_api(market_data)
