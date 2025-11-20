import os
import json
import re
from json import JSONDecodeError
from typing import List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
import requests
from pydantic import ValidationError

from model import CryptoAnalysisRequests, CryptoAnalysisResponse, CryptoCompareRequest, CryptoComparisonResponse

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


SYSTEM_PROMPT_COMPARE = """
You are a CryptoAnalyst AI. You will compare multiple cryptocurrencies using their market data.

CRITICAL INSTRUCTIONS:
- Output ONLY valid JSON.
- JSON must start with { and end with }.
- Do NOT include markdown.
- Do NOT add extra text before or after the JSON.

Your JSON output MUST follow this exact schema:

{
  "comparison": [
    {
      "winner": "<coin name with strongest outlook>",
      "summary": "<2-3 line human-style summary>",
      "reasons": [
        "<reason 1>",
        "<reason 2>",
        "<reason 3>"
      ]
    }
  ]
}

Rules:
- Only one winner.
- Reasons must be based on the provided metrics (price change %, market cap, volume).
- Write clean, short, factual analysis.
"""



SYSTEM_PROMPT_ANALYSIS = """
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


def call_openrouter_api(market_data, system_prompt, request_type:str = "analyze"):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json"
    }

    body = {
        "model": "meta-llama/llama-3.3-70b-instruct",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Here is the market data:\n{json.dumps(market_data)}"}
        ]
    }

    response = requests.post(OPENROUTER_URL, json=body, headers=headers)
    if response.status_code != 200:
        try:
            err = response.json()
        except:
            err = response.text

        raise HTTPException(
            status_code=502,
            detail=f"Failed to get response from LLM: {err}"
        )

    llm_resp_json = response.json()
    try:
        json_str = llm_resp_json["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise HTTPException(status_code=502, detail="LLM response missing expected content")


    # print("LLM output:", json_str)

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
    #print("Parsed payload:", payload)
    # Step 3: Validate with Pydantic
    try:
        if request_type == "analyze":
            return CryptoAnalysisResponse.model_validate(payload)
        else:
            return CryptoComparisonResponse.model_validate(payload)
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

    return call_openrouter_api(market_data, system_prompt=SYSTEM_PROMPT_ANALYSIS, request_type= "analyze")

@app.post("/crypto/compare")
def crypto_compare(request:CryptoCompareRequest):
    crypto_data = get_crypto_insights(request.coins)

    market_data = [{
        "name": data["name"],
        "symbol": data["symbol"],
        "current_price": data["current_price"],
        "market_cap": data["market_cap"],
        "total_volume": data["total_volume"],
        "price_change_percentage_24h": data["price_change_percentage_24h"]
    } for data in crypto_data]

    return call_openrouter_api(market_data=market_data, system_prompt=SYSTEM_PROMPT_COMPARE, request_type="compare")