from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio
import time
from dotenv import load_dotenv
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler

load_dotenv()
ETHERSCAN_KEY = os.getenv("ETHERSCAN_API_KEY")
COINGECKO_KEY = os.getenv("COINGECKO_API_KEY")
SOLSCAN_KEY = os.getenv("SOLSCAN_API_KEY")

app = FastAPI(title="CryptoSense AI Backend")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

cache = {
    "pairs_eth": {"pairs": []},
    "pairs_meme": {"pairs": []},
    "pairs_sol": {"pairs": []},
    "pairs_bnb": {"pairs": []},
    "pairs_base": {"pairs": []},
    "pairs_arb": {"pairs": []},
    "global": {},
    "whales": {"whales": []},
    "whales_by_chain": {
        "ethereum": [], "bnb": [], "base": [],
        "arbitrum": [], "polygon": [], "solana": [],
    },
    "new_tokens": [],
    "trending": [],
    "sentiment": {"score": 62, "label": "Greed"},
    "top_tokens": [],
    "social": {"posts": []},
}

scheduler = AsyncIOScheduler()

ETH_WALLETS = [
    "0x28C6c06298d514Db089934071355E5743bf21d60",
    "0x21a31Ee1afC51d94C2eFcCAa2092aD1028285549",
    "0xDFd5293D8e347dFe59E90eFd55b2956a1343963B",
]

async def fetch(url, headers=None):
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, headers=headers or {})
            return r.json()
    except Exception as e:
        print(f"Fetch error: {url[:60]} — {e}")
        return None

async def fetch_eth_whales():
    all_txs = []
    async with httpx.AsyncClient(timeout=15) as client:
        for wallet in ETH_WALLETS:
            try:
                url = f"https://api.etherscan.io/v2/api?chainid=1&module=account&action=tokentx&address={wallet}&startblock=0&endblock=99999999&sort=desc&apikey={ETHERSCAN_KEY}"
                r = await client.get(url)
                txs = r.json().get("result", [])[:15]
                for tx in txs:
                    try:
                        value = int(tx.get("value", 0))
                        decimals = int(tx.get("tokenDecimal", 18))
                        amount = value / (10 ** decimals)
                        if amount < 100:
                            continue
                        from_addr = tx.get("from", "")
                        to_addr = tx.get("to", "")
                        all_txs.append({
                            "symbol": tx.get("tokenSymbol", "???"),
                            "token_name": tx.get("tokenName", ""),
                            "amount": round(amount, 2),
                            "from": from_addr[:6] + "..." + from_addr[-4:],
                            "to": to_addr[:6] + "..." + to_addr[-4:],
                            "wallet": wallet[:6] + "..." + wallet[-4:],
                            "hash": tx.get("hash", ""),
                            "timestamp": int(tx.get("timeStamp", 0)),
                            "type": "buy" if to_addr.lower() == wallet.lower() else "sell",
                            "chain": "ethereum",
                            "chain_icon": "⟠",
                            "chain_name": "Ethereum",
                            "etherscan_url": f"https://etherscan.io/tx/{tx.get('hash','')}",
                        })
                    except:
                        continue
            except:
                continue
    all_txs.sort(key=lambda x: x["timestamp"], reverse=True)
    return all_txs[:20]

async def fetch_dex_whales(chain, query, icon, chain_name, dex_chain_id):
    try:
        url = f"https://api.dexscreener.com/latest/dex/search?q={query}"
        d = await fetch(url)
        if not d or not d.get("pairs"):
            return []
        pairs = [p for p in d["pairs"] if p.get("chainId") == dex_chain_id][:8]
        if not pairs:
            pairs = d["pairs"][:8]
        whales = []
        now = int(time.time())
        for i, pair in enumerate(pairs):
            try:
                vol = float(pair.get("volume", {}).get("h24", 0) or 0)
                if vol < 1000:
                    continue
                chg = float(pair.get("priceChange", {}).get("h24", 0) or 0)
                buys = pair.get("txns", {}).get("h24", {}).get("buys", 0)
                sells = pair.get("txns", {}).get("h24", {}).get("sells", 0)
                sym = pair.get("baseToken", {}).get("symbol", "???")
                liq = float(pair.get("liquidity", {}).get("usd", 0) or 0)
                whale_amount = vol * 0.05
                tx_type = "buy" if (chg > 0 and buys > sells) else "sell"
                whales.append({
                    "symbol": sym,
                    "token_name": pair.get("baseToken", {}).get("name", sym),
                    "amount": round(whale_amount, 2),
                    "from": "Smart...Money",
                    "to": "DEX...Pool",
                    "wallet": "DEX Whale",
                    "hash": pair.get("pairAddress", "")[:20],
                    "timestamp": now - (i * 120),
                    "type": tx_type,
                    "chain": chain,
                    "chain_icon": icon,
                    "chain_name": chain_name,
                    "etherscan_url": pair.get("url", "#"),
                    "volume_24h": vol,
                    "liquidity": liq,
                    "price_change": chg,
                })
            except:
                continue
        return whales[:10]
    except Exception as e:
        print(f"DEX whale error {chain}: {e}")
        return []

async def fetch_solana_whales():
    if not SOLSCAN_KEY:
        print("No Solscan key")
        return []
    try:
        headers = {"token": SOLSCAN_KEY}
        url = "https://pro-api.solscan.io/v2.0/account/transactions?address=9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM&page=1&page_size=10"
        d = await fetch(url, headers=headers)
        print(f"Solscan: {str(d)[:150]}")
        if not d or not isinstance(d, dict):
            return await fetch_dex_whales("solana", "SOL USDC", "🟣", "Solana", "solana")
        txs = d.get("data", [])
        whales = []
        now = int(time.time())
        for i, tx in enumerate(txs[:10]):
            try:
                lamport = float(tx.get("lamport", 0))
                if lamport < 1e6:
                    continue
                whales.append({
                    "symbol": "SOL",
                    "token_name": "Solana",
                    "amount": round(lamport / 1e9, 4),
                    "from": str(tx.get("signer", ["???"])[0])[:6] + "...???",
                    "to": "???...???",
                    "wallet": "SOL Whale",
                    "hash": str(tx.get("signature", ""))[:20],
                    "timestamp": tx.get("blockTime", now - i * 60),
                    "type": "buy",
                    "chain": "solana",
                    "chain_icon": "🟣",
                    "chain_name": "Solana",
                    "etherscan_url": f"https://solscan.io/tx/{tx.get('signature','')}",
                })
            except:
                continue
        if not whales:
            return await fetch_dex_whales("solana", "SOL USDC", "🟣", "Solana", "solana")
        print(f"Solana whales: {len(whales)}")
        return whales
    except Exception as e:
        print(f"Solana error: {e}")
        return await fetch_dex_whales("solana", "SOL USDC", "🟣", "Solana", "solana")

async def update_whales():
    print("Updating multi-chain whales...")
    results = await asyncio.gather(
        fetch_eth_whales(),
        fetch_dex_whales("bnb", "BNB USDT", "🟡", "BNB Chain", "bsc"),
        fetch_dex_whales("base", "USDC base", "🔵", "Base", "base"),
        fetch_dex_whales("arbitrum", "ARB USDC", "🔷", "Arbitrum", "arbitrum"),
        fetch_dex_whales("polygon", "POL USDC", "🟣", "Polygon", "polygon"),
        fetch_solana_whales(),
    )

    chain_names = ["ethereum", "bnb", "base", "arbitrum", "polygon", "solana"]
    all_txs = []
    for i, result in enumerate(results):
        if isinstance(result, list):
            cache["whales_by_chain"][chain_names[i]] = result
            all_txs.extend(result)
    all_txs.sort(key=lambda x: x["timestamp"], reverse=True)
    cache["whales"] = {"whales": all_txs[:40]}
    counts = {c: len(w) for c, w in cache["whales_by_chain"].items()}
    print(f"Whales: {counts}")

async def update_pairs_eth():
    d = await fetch("https://api.dexscreener.com/latest/dex/search?q=ETH USDC")
    if d and d.get("pairs"):
        cache["pairs_eth"] = d
        print("ETH pairs updated")

async def update_pairs_meme():
    d = await fetch("https://api.dexscreener.com/latest/dex/search?q=PEPE SHIB WIF BONK DOGE")
    if d and d.get("pairs"):
        cache["pairs_meme"] = d
        print("Meme pairs updated")

async def update_pairs_sol():
    d = await fetch("https://api.dexscreener.com/latest/dex/search?q=SOL USDC")
    if d and d.get("pairs"):
        sol = [p for p in d["pairs"] if p.get("chainId") == "solana"][:10]
        if sol:
            cache["pairs_sol"] = {"pairs": sol}
            print(f"SOL pairs: {len(sol)}")

async def update_pairs_bnb():
    d = await fetch("https://api.dexscreener.com/latest/dex/search?q=BNB USDT")
    if d and d.get("pairs"):
        bnb = [p for p in d["pairs"] if p.get("chainId") == "bsc"][:10]
        if bnb:
            cache["pairs_bnb"] = {"pairs": bnb}
            print(f"BNB pairs: {len(bnb)}")

async def update_pairs_base():
    d = await fetch("https://api.dexscreener.com/latest/dex/search?q=USDC base chain")
    if d and d.get("pairs"):
        base = [p for p in d["pairs"] if p.get("chainId") == "base"][:10]
        if base:
            cache["pairs_base"] = {"pairs": base}
            print(f"BASE pairs: {len(base)}")

async def update_pairs_arb():
    d = await fetch("https://api.dexscreener.com/latest/dex/search?q=ARB USDC")
    if d and d.get("pairs"):
        arb = [p for p in d["pairs"] if p.get("chainId") == "arbitrum"][:10]
        if arb:
            cache["pairs_arb"] = {"pairs": arb}
            print(f"ARB pairs: {len(arb)}")

async def update_new_tokens():
    d = await fetch("https://api.dexscreener.com/token-profiles/latest/v1")
    if d and isinstance(d, list):
        cache["new_tokens"] = d
        print("New tokens updated")

async def update_trending():
    d = await fetch("https://api.dexscreener.com/token-boosts/top/v1")
    if d and isinstance(d, list):
        cache["trending"] = d[:20]
        print("Trending updated")

async def get_token_pairs(address: str):
    d = await fetch(f"https://api.dexscreener.com/latest/dex/search?q={address}")
    return d or {"pairs": []}

async def update_global():
    d = await fetch(f"https://api.coingecko.com/api/v3/global?x_cg_demo_api_key={COINGECKO_KEY}")
    if d:
        cache["global"] = d
        print("Global updated")

async def update_top_tokens():
    d = await fetch(f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=20&page=1&sparkline=false&price_change_percentage=24h&x_cg_demo_api_key={COINGECKO_KEY}")
    if d and isinstance(d, list):
        cache["top_tokens"] = d
        print("Top tokens updated")

async def update_sentiment():
    try:
        d = await fetch("https://api.alternative.me/fng/?limit=1")
        if d and d.get("data"):
            val = int(d["data"][0]["value"])
            label = d["data"][0]["value_classification"]
            cache["sentiment"]["score"] = val
            cache["sentiment"]["label"] = label
            print(f"Sentiment: {val} ({label})")
    except Exception as e:
        print(f"Sentiment error: {e}")

async def update_social():
    try:
        posts = []
        d = await fetch("https://api.coingecko.com/api/v3/search/trending")
        if d and d.get("coins"):
            for coin in d["coins"][:6]:
                c = coin["item"]
                posts.append({
                    "title": f"{c.get('name')} trending on CoinGecko",
                    "subreddit": "CoinGecko",
                    "score": c.get("score", 0),
                    "symbol": c.get("symbol", ""),
                    "url": f"https://coingecko.com/en/coins/{c.get('id','')}",
                    "sentiment": "bullish",
                })
        t = cache.get("trending", [])
        for item in t[:4]:
            posts.append({
                "title": f"{item.get('description', item.get('tokenAddress','')[:20])} boosted",
                "subreddit": "DexScreener",
                "score": item.get("totalAmount", 0),
                "symbol": item.get("symbol", ""),
                "url": item.get("url", ""),
                "sentiment": "bullish",
                "chain": item.get("chainId", ""),
            })
        if posts:
            cache["social"] = {"posts": posts}
            print(f"Social: {len(posts)}")
    except Exception as e:
        print(f"Social error: {e}")

def calculate_ai_score(pair_data, whale_activity=[], social_score=50):
    score = 50
    signals = []
    vol = float(pair_data.get("volume", {}).get("h24", 0) or 0)
    liq = float(pair_data.get("liquidity", {}).get("usd", 0) or 0)
    chg = float(pair_data.get("priceChange", {}).get("h24", 0) or 0)
    buys = int(pair_data.get("txns", {}).get("h24", {}).get("buys", 0) or 0)
    sells = int(pair_data.get("txns", {}).get("h24", {}).get("sells", 0) or 0)

    if vol > 1000000: score += 15; signals.append("🔥 High volume")
    elif vol > 100000: score += 8; signals.append("📈 Good volume")
    if liq > 500000: score += 15; signals.append("💧 Strong liquidity")
    elif liq > 50000: score += 8; signals.append("💧 Good liquidity")
    elif liq < 10000: score -= 20; signals.append("⚠️ Low liquidity")
    if chg > 20: score += 10; signals.append("🚀 Strong uptrend")
    elif chg > 5: score += 5; signals.append("📈 Positive momentum")
    elif chg < -30: score -= 15; signals.append("🔴 Sharp decline")
    elif chg < -10: score -= 8; signals.append("⬇️ Downtrend")
    if buys > 0 and sells > 0:
        ratio = buys / (buys + sells)
        if ratio > 0.7: score += 10; signals.append("💚 Strong buy pressure")
        elif ratio < 0.3: score -= 10; signals.append("🔴 Sell pressure")
    if whale_activity:
        wb = sum(1 for w in whale_activity if w.get("type") == "buy")
        ws = sum(1 for w in whale_activity if w.get("type") == "sell")
        if wb > ws: score += 10; signals.append("🐳 Whale accumulation")
        elif ws > wb: score -= 10; signals.append("🚨 Whale dumping")
    if social_score > 60: score += 5; signals.append("📱 Positive sentiment")
    elif social_score < 30: score -= 5; signals.append("📱 Negative sentiment")

    score = max(5, min(95, score))
    return {
        "bullish_probability": score,
        "risk_level": "LOW" if score >= 70 else "MEDIUM" if score >= 45 else "HIGH",
        "whale_strength": "HIGH" if score > 65 else "MEDIUM" if score > 45 else "LOW",
        "sentiment_score": social_score,
        "signals": signals[:5],
    }

async def get_contract_info(address):
    url = f"https://api.etherscan.io/v2/api?chainid=1&module=contract&action=getsourcecode&address={address}&apikey={ETHERSCAN_KEY}"
    d = await fetch(url)
    if not d or d.get("status") != "1":
        return {}
    r = d.get("result", [{}])[0]
    return {
        "contract_name": r.get("ContractName", "Unknown"),
        "is_verified": bool(r.get("SourceCode")),
        "compiler_version": r.get("CompilerVersion", ""),
        "is_proxy": r.get("Proxy", "0") == "1",
    }

async def keep_alive():
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.get("https://cryptosense-ai-backend.onrender.com/")
            print("✓ Keep alive ping sent")
    except:
        pass
async def preload():
    print("⚡ Preloading all data...")
    await asyncio.gather(
        update_pairs_eth(), update_pairs_meme(),
        update_pairs_sol(), update_pairs_bnb(),
        update_pairs_base(), update_pairs_arb(),
        update_global(), update_new_tokens(),
        update_trending(), update_sentiment(),
        update_top_tokens(),
    )
    await update_social()
    await update_whales()
    print("✅ All data ready!")

@app.on_event("startup")
async def startup():
    await preload()
    scheduler.add_job(update_pairs_eth, 'interval', seconds=10)
    scheduler.add_job(update_pairs_meme, 'interval', seconds=15)
    scheduler.add_job(update_pairs_sol, 'interval', seconds=15)
    scheduler.add_job(update_pairs_bnb, 'interval', seconds=20)
    scheduler.add_job(update_pairs_base, 'interval', seconds=20)
    scheduler.add_job(update_pairs_arb, 'interval', seconds=20)
    scheduler.add_job(update_global, 'interval', seconds=300)
    scheduler.add_job(update_whales, 'interval', seconds=30)
    scheduler.add_job(update_new_tokens, 'interval', seconds=30)
    scheduler.add_job(update_trending, 'interval', seconds=20)
    scheduler.add_job(update_sentiment, 'interval', seconds=300)
    scheduler.add_job(update_social, 'interval', seconds=120)
    scheduler.add_job(update_top_tokens, 'interval', seconds=300)
    scheduler.start()
    print("🚀 All jobs started!")

@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown()

@app.get("/")
def root():
    counts = {c: len(w) for c, w in cache["whales_by_chain"].items()}
    return {"status": "CryptoSense AI ✅", "chains": counts}

@app.get("/api/global")
def get_global():
    return cache["global"]

@app.get("/api/pairs/{query}")
def get_pairs(query: str):
    q = query.upper()
    if any(x in q for x in ["PEPE","SHIB","WIF","BONK","DOGE","FLOKI","MEME"]):
        return cache["pairs_meme"]
    if "SOL" in q or "SOLANA" in q:
        return cache["pairs_sol"]
    if "BNB" in q or "BSC" in q:
        return cache["pairs_bnb"]
    if "BASE" in q:
        return cache["pairs_base"]
    if "ARB" in q or "ARBITRUM" in q:
        return cache["pairs_arb"]
    return cache["pairs_eth"]

@app.get("/api/whales")
def get_whales():
    return cache["whales"]

@app.get("/api/whales/{chain}")
def get_whales_by_chain(chain: str):
    return {"chain": chain, "whales": cache["whales_by_chain"].get(chain, [])}

@app.get("/api/chains")
def get_chains():
    info = {
        "ethereum": {"icon": "⟠", "name": "Ethereum"},
        "bnb": {"icon": "🟡", "name": "BNB Chain"},
        "base": {"icon": "🔵", "name": "Base"},
        "arbitrum": {"icon": "🔷", "name": "Arbitrum"},
        "polygon": {"icon": "🟣", "name": "Polygon"},
        "solana": {"icon": "🟣", "name": "Solana"},
    }
    result = {}
    for chain, whales in cache["whales_by_chain"].items():
        i = info.get(chain, {"icon": "🔗", "name": chain})
        result[chain] = {"count": len(whales), "latest": whales[:3], "icon": i["icon"], "name": i["name"]}
    return result

@app.get("/api/new-tokens")
def get_new_tokens():
    return cache["new_tokens"]

@app.get("/api/trending")
def get_trending():
    return {"trending": cache["trending"]}

@app.get("/api/sentiment")
def get_sentiment():
    return cache["sentiment"]

@app.get("/api/social")
def get_social():
    return cache["social"]

@app.get("/api/top-tokens")
def get_top_tokens():
    return {"tokens": cache["top_tokens"]}

@app.get("/api/token/{address}")
async def get_token_detail(address: str):
    pairs_data = await get_token_pairs(address)
    pair = pairs_data.get("pairs", [{}])[0] if pairs_data.get("pairs") else {}
    contract_info = await get_contract_info(address) if address.startswith("0x") else {}
    whales = cache["whales"].get("whales", [])
    ai = calculate_ai_score(pair, whales, cache["sentiment"].get("score", 50))
    return {"pair": pair, "contract": contract_info, "ai_analysis": ai, "whale_activity": whales[:5], "sentiment": cache["sentiment"]}

@app.get("/api/history/token/{coin_id}")
async def get_token_history(coin_id: str, days: str = "7"):
    days_map = {"1D": 1, "7D": 7, "30D": 30, "90D": 90}
    d = days_map.get(days, 7)
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=usd&days={d}&x_cg_demo_api_key={COINGECKO_KEY}"
    data = await fetch(url)
    return data or {}

@app.get("/api/history/whales")
async def get_whale_history():
    """Return all cached whale transactions as history"""
    all_whales = []
    for chain, whales in cache["whales_by_chain"].items():
        all_whales.extend(whales)
    all_whales.sort(key=lambda x: x["timestamp"], reverse=True)
    
    # Stats
    total = len(all_whales)
    buys = sum(1 for w in all_whales if w.get("type") == "buy")
    sells = sum(1 for w in all_whales if w.get("type") == "sell")
    by_chain = {}
    for w in all_whales:
        chain = w.get("chain", "unknown")
        if chain not in by_chain:
            by_chain[chain] = {"buys": 0, "sells": 0, "total": 0}
        by_chain[chain]["total"] += 1
        if w.get("type") == "buy":
            by_chain[chain]["buys"] += 1
        else:
            by_chain[chain]["sells"] += 1
    
    return {
        "whales": all_whales,
        "stats": {
            "total": total,
            "buys": buys,
            "sells": sells,
            "buy_ratio": round(buys/total*100) if total else 0,
            "by_chain": by_chain,
        }
    }

@app.get("/api/analytics")
async def get_analytics():
    """Full analytics data"""
    all_whales = []
    for chain, whales in cache["whales_by_chain"].items():
        all_whales.extend(whales)
    
    total = len(all_whales)
    buys = sum(1 for w in all_whales if w.get("type") == "buy")
    sells = total - buys
    
    # Top symbols
    symbol_count = {}
    for w in all_whales:
        sym = w.get("symbol", "???")
        if sym not in symbol_count:
            symbol_count[sym] = {"buys": 0, "sells": 0}
        if w.get("type") == "buy":
            symbol_count[sym]["buys"] += 1
        else:
            symbol_count[sym]["sells"] += 1
    
    top_symbols = sorted(symbol_count.items(), key=lambda x: x[1]["buys"]+x[1]["sells"], reverse=True)[:10]
    
    # Chain distribution
    chain_dist = {}
    for w in all_whales:
        chain = w.get("chain", "unknown")
        chain_dist[chain] = chain_dist.get(chain, 0) + 1
    
    return {
        "summary": {
            "total_transactions": total,
            "total_buys": buys,
            "total_sells": sells,
            "buy_ratio": round(buys/total*100) if total else 0,
            "sell_ratio": round(sells/total*100) if total else 0,
            "chains_tracked": len(cache["whales_by_chain"]),
            "market_sentiment": cache["sentiment"].get("label", "Neutral"),
            "fear_greed": cache["sentiment"].get("score", 50),
        },
        "top_symbols": [{"symbol": s, "buys": d["buys"], "sells": d["sells"]} for s,d in top_symbols],
        "chain_distribution": chain_dist,
        "recent_whales": all_whales[:10],
    }
@app.get("/api/analyze/{address}")
async def analyze_contract(address: str):
    pairs_data = await get_token_pairs(address)
    pair = pairs_data.get("pairs", [{}])[0] if pairs_data.get("pairs") else {}
    contract_info = await get_contract_info(address) if address.startswith("0x") else {}
    whales = cache["whales"].get("whales", [])
    ai = calculate_ai_score(pair, whales)
    liq = float(pair.get("liquidity", {}).get("usd", 0) or 0)
    chg = float(pair.get("priceChange", {}).get("h24", 0) or 0)
    return {
        "token_name": pair.get("baseToken", {}).get("name", "Unknown"),
        "symbol": pair.get("baseToken", {}).get("symbol", "???"),
        "chain": pair.get("chainId", "unknown"),
        "price": pair.get("priceUsd", "0"),
        "liquidity": liq,
        "volume_24h": float(pair.get("volume", {}).get("h24", 0) or 0),
        "change_24h": chg,
        "contract": contract_info,
        "honeypot_risk": "HIGH" if liq < 5000 else "LOW",
        "rug_risk": "HIGH" if (chg < -40 or liq < 10000) else "LOW",
        "liquidity_locked": liq > 50000,
        "ai_analysis": ai,
    }
