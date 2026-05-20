from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio
import json
import time
from cachetools import TTLCache

app = FastAPI(title="CryptoSense AI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cache — 15 second TTL
cache = TTLCache(maxsize=100, ttl=15)

async def fetch_url(url: str):
    cached = cache.get(url)
    if cached:
        return cached
    async with httpx.AsyncClient(timeout=8) as client:
        r = await client.get(url, headers={"Cache-Control": "no-cache"})
        data = r.json()
        cache[url] = data
        return data

@app.get("/")
def root():
    return {"status": "CryptoSense AI Running ✅"}

@app.get("/api/global")
async def get_global():
    return await fetch_url("https://api.coingecko.com/api/v3/global")

@app.get("/api/pairs/{query}")
async def get_pairs(query: str):
    return await fetch_url(f"https://api.dexscreener.com/latest/dex/search?q={query}")

@app.get("/api/new-tokens")
async def get_new_tokens():
    return await fetch_url("https://api.dexscreener.com/token-profiles/latest/v1")

@app.get("/api/trending")
async def get_trending():
    return await fetch_url("https://api.dexscreener.com/token-boosts/top/v1")

@app.on_event("startup")
async def preload_cache():
    """App start হলেই data preload করবে"""
    print("⚡ Preloading cache...")
    urls = [
        "https://api.dexscreener.com/latest/dex/search?q=ETH USDC",
        "https://api.coingecko.com/api/v3/global",
        "https://api.dexscreener.com/token-profiles/latest/v1",
    ]
    async with httpx.AsyncClient(timeout=10) as client:
        for url in urls:
            try:
                r = await client.get(url)
                cache[url] = r.json()
                print(f"✓ Cached: {url[:50]}")
            except Exception as e:
                print(f"✗ Failed: {url[:50]} — {e}")
    print("✅ Cache ready!")
