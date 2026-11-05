"""Feasibility probe: can a GitHub Actions runner fetch the NSE option chain? Appends one line per run to probe/log.txt."""
import json, time, datetime, sys, requests

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9", "Referer": "https://www.nseindia.com/option-chain"}
s = requests.Session(); s.headers.update(UA)
now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).strftime("%d-%b %H:%M")
result = []
for attempt in range(3):
    try:
        r0 = s.get("https://www.nseindia.com/option-chain", timeout=20)
        r1 = s.get("https://www.nseindia.com/api/option-chain-contract-info?symbol=NIFTY", timeout=20)
        exp = r1.json()["expiryDates"][0]
        r2 = s.get(f"https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol=NIFTY&expiry={exp}", timeout=20)
        d = r2.json()["records"]
        result = [f"OK attempt={attempt+1} home={r0.status_code} spot={d['underlyingValue']} ts={d['timestamp']} rows={len(d['data'])}"]
        break
    except Exception as e:
        result.append(f"FAIL attempt={attempt+1} {type(e).__name__}: {str(e)[:80]} status={getattr(locals().get('r1',None),'status_code',None)}/{getattr(locals().get('r2',None),'status_code',None)}")
        time.sleep(5)
line = f"{now} | " + " ; ".join(result)
print(line)
with open("probe/log.txt", "a") as f: f.write(line + "\n")
