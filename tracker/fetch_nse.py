"""Nifty Options Desk — data fetcher for GitHub Actions.
Python port of fetch.js: pulls NIFTY and BANKNIFTY option chains from NSE, computes the same
summary metrics, and writes data/data.json in exactly the shape the page template expects."""
import json, time, datetime, sys, re, pathlib
import requests

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9", "Referer": "https://www.nseindia.com/option-chain"}
BASE = "https://www.nseindia.com"
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "data.json"

s = requests.Session(); s.headers.update(UA)

def g(path, tries=3):
    last = None
    for i in range(tries):
        try:
            r = s.get(BASE + path, timeout=25)
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code}"
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:80]}"
        time.sleep(4)
    raise RuntimeError(f"{path} failed: {last}")

def rnd(x, d=2): return round(x, d)

def analyse(oc, expiry):
    rec = oc["records"]; spot = rec["underlyingValue"]
    rows_all = [r for r in rec["data"] if r.get("CE") and r.get("PE")]
    S = lambda r: r["strikePrice"]
    NEAR, ROWS = spot * 0.035, spot * 0.017
    near = [r for r in rows_all if abs(S(r) - spot) <= NEAR]
    atm = min(rows_all, key=lambda r: abs(S(r) - spot))
    # max pain over the whole chain
    best = None
    for c in rows_all:
        K = S(c); pain = 0
        for r in rows_all:
            pain += r["CE"]["openInterest"] * max(0, K - S(r)) + r["PE"]["openInterest"] * max(0, S(r) - K)
        if best is None or pain < best[1]: best = (K, pain)
    def top(side, filt, key, n=3, desc=True):
        xs = sorted([r for r in rows_all if filt(r)], key=lambda r: r[side][key], reverse=desc)[:n]
        return [{"k": S(r), "oi": r[side]["openInterest"], "chg": r[side]["changeinOpenInterest"], "ltp": r[side]["lastPrice"]} for r in xs]
    totCE, totPE = oc["filtered"]["CE"]["totOI"], oc["filtered"]["PE"]["totOI"]
    nearCE = sum(r["CE"]["openInterest"] for r in near); nearPE = sum(r["PE"]["openInterest"] for r in near)
    addCE = sum(r["CE"]["changeinOpenInterest"] for r in near); addPE = sum(r["PE"]["changeinOpenInterest"] for r in near)
    def buildup(x):
        p, o = x["change"], x["changeinOpenInterest"]
        if not o and not p: return "—"
        if p > 0 and o > 0: return "Buying"
        if p < 0 and o > 0: return "Writing"
        if p > 0 and o < 0: return "Short covering"
        if p < 0 and o < 0: return "Long unwinding"
        return "—"
    leg = lambda x: {"oi": x["openInterest"], "chg": x["changeinOpenInterest"], "iv": x["impliedVolatility"], "ltp": x["lastPrice"], "b": buildup(x)}
    rows = [{"k": S(r), "ce": leg(r["CE"]), "pe": leg(r["PE"])} for r in near if abs(S(r) - spot) <= ROWS]
    straddle = atm["CE"]["lastPrice"] + atm["PE"]["lastPrice"]
    return {
        "expiry": expiry, "ts": rec["timestamp"], "spot": spot, "atm": S(atm),
        "pcr": rnd(totPE / totCE) if totCE else 0, "pcrNear": rnd(nearPE / nearCE) if nearCE else 0,
        "totCE": totCE, "totPE": totPE, "addCE": addCE, "addPE": addPE, "maxPain": best[0],
        "resistance": top("CE", lambda r: S(r) >= spot, "openInterest"),
        "support": top("PE", lambda r: S(r) <= spot, "openInterest"),
        "ceAdds": top("CE", lambda r: abs(S(r) - spot) <= NEAR, "changeinOpenInterest"),
        "peAdds": top("PE", lambda r: abs(S(r) - spot) <= NEAR, "changeinOpenInterest"),
        "atmIV": {"ce": atm["CE"]["impliedVolatility"], "pe": atm["PE"]["impliedVolatility"]},
        "straddle": rnd(straddle), "expMove": rnd(straddle * 0.85), "rows": rows,
    }

def pull(sym, idx, cm, fut):
    info = g(f"/api/option-chain-contract-info?symbol={sym}")
    exps = info["expiryDates"][:2]
    pick = lambda n: next((x for x in idx["data"] if x["index"] == n), {})
    n50 = pick("NIFTY 50" if sym == "NIFTY" else "NIFTY BANK"); vix = pick("INDIA VIX")
    chains = [analyse(g(f"/api/option-chain-v3?type=Indices&symbol={sym}&expiry={e}"), e) for e in exps]
    d, t = chains[0]["ts"].split(" ")[0], (chains[0]["ts"].split(" ") + [""])[1]
    c = next((x for x in chains if not (x["expiry"] == d and t >= "15:30")), chains[0])
    notes, score = [], 0
    if c["pcr"] >= 1.2: score += 1; notes.append(f"PCR {c['pcr']} — put writers dominant, dips are being sold into")
    elif c["pcr"] <= 0.7: score -= 1; notes.append(f"PCR {c['pcr']} — call writers dominant, rallies are being sold into")
    else: notes.append(f"PCR {c['pcr']} — balanced positioning")
    if c["addPE"] > c["addCE"] * 1.3: score += 1; notes.append(f"Fresh put writing ({c['addPE']/1e5:.1f}L) outpaces call writing ({c['addCE']/1e5:.1f}L) near spot")
    elif c["addCE"] > c["addPE"] * 1.3: score -= 1; notes.append(f"Fresh call writing ({c['addCE']/1e5:.1f}L) outpaces put writing ({c['addPE']/1e5:.1f}L) near spot")
    MP = c["spot"] * 0.004
    if c["spot"] > c["maxPain"] + MP: notes.append(f"Spot is {round(c['spot']-c['maxPain'])} pts above max pain {c['maxPain']} — gravity toward expiry is downward")
    elif c["spot"] < c["maxPain"] - MP: notes.append(f"Spot is {round(c['maxPain']-c['spot'])} pts below max pain {c['maxPain']} — gravity toward expiry is upward")
    else: notes.append(f"Spot sits close to max pain {c['maxPain']}")
    if c["resistance"] and c["support"]:
        notes.append(f"Option writers' range: {c['support'][0]['k']} (put wall) to {c['resistance'][0]['k']} (call wall); straddle implies ±{round(c['expMove'])} pts by {c['expiry']}")
    if vix.get("last", 0) >= 18: notes.append(f"VIX {vix['last']} is elevated — premiums rich, moves can be sharp")
    elif vix.get("last", 99) <= 12: notes.append(f"VIX {vix['last']} is low — premiums cheap, range-bound bias")
    bias = "Bullish" if score >= 2 else "Mildly bullish" if score == 1 else "Neutral" if score == 0 else "Mildly bearish" if score == -1 else "Bearish"
    return {
        "nifty": {"last": n50.get("last"), "chg": n50.get("percentChange"), "open": n50.get("open"), "high": n50.get("high"), "low": n50.get("low"), "prevClose": n50.get("previousClose")},
        "vix": {"last": vix.get("last"), "chg": vix.get("percentChange")},
        "fut": fut if sym == "NIFTY" else None,
        "market": {"status": cm.get("marketStatus"), "msg": cm.get("marketStatusMessage"), "tradeDate": cm.get("tradeDate")},
        "bias": bias, "notes": notes, "chains": chains,
    }

def futures_from_page():
    """Nearest Nifty futures quote from the option-chain page header (not in the JSON APIs)."""
    try:
        html = s.get(BASE + "/option-chain", timeout=25).text
        text = re.sub(r"<[^>]+>", "\n", html)
        m = re.search(r"Futures (\d{2}-\w{3}-\d{4})\s*\n\s*([\d,]+\.\d+)\s+(-?[\d.]+)\s+\((-?[\d.]+)%\)", text)
        return {"expiry": m.group(1), "last": float(m.group(2).replace(",", "")), "chg": float(m.group(4))} if m else None
    except Exception:
        return None

def main():
    s.get(BASE + "/option-chain", timeout=25)          # cookies
    idx = g("/api/allIndices")
    ms = g("/api/marketStatus")
    cm = next((x for x in ms.get("marketState", []) if x.get("market") == "Capital Market"), {})
    fut = futures_from_page()
    N = pull("NIFTY", idx, cm, fut)
    try: B = pull("BANKNIFTY", idx, cm, None)
    except Exception as e: print("bank failed:", e); B = None
    out = {"fetchedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"), **N, "bank": B}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    print(f"ok {N['chains'][0]['ts']} spot {N['chains'][0]['spot']} bank {'ok' if B else 'none'} fut {fut}")

if __name__ == "__main__":
    main()
