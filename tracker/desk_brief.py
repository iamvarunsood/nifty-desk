"""Print a compact view for the analyst: current views, open calls, last resolved, record,
plus the trend check and the standing lessons/review. The trend block is a rule, not a suggestion."""
import json, pathlib, math
root = pathlib.Path(__file__).parent
d = json.loads((root / "desk.json").read_text())
brief = json.loads((root.parent / "data" / "brief.json").read_text())
daily = json.loads((root / "daily.json").read_text()) if (root / "daily.json").exists() else []
review = json.loads((root / "review.json").read_text()) if (root / "review.json").exists() else {"lessons": [], "days": []}

def trend(key, b):
    if not b: return None
    q, vix = b["index"], (b.get("vix") or {}).get("last") or 15
    today = b["chains"][0]["ts"].split(" ")[0]
    prior = [x[key] for x in daily if x["date"] != today and x.get(key, {}).get("last")][-5:]
    last, op, pc = q["last"], q["open"], q["prevClose"]
    if not prior: return {"note": "no daily history yet; no lean allowed"}
    avg = sum(p["last"] for p in prior) / len(prior)
    multi = "up" if last > avg * 1.003 else "down" if last < avg * 0.997 else "flat"
    tday = "up" if last > op and last > pc else "down" if last < op and last < pc else "mixed"
    lean = "up" if multi == "up" and tday != "down" else "down" if multi == "down" and tday != "up" else "none"
    move = last * vix / 100 / math.sqrt(252)
    p3 = prior[-3:]
    return {"last": last, "avg_close_5d": round(avg), "multi_day": multi, "today": tday, "lean_allowed": lean,
            "high_3d": max(p["high"] for p in p3), "low_3d": min(p["low"] for p in p3),
            "today_high": q["high"], "today_low": q["low"], "prev_close": pc,
            "dayMove": round(move), "min_stop": round(move * 0.5), "min_half_range": round(move * 0.75),
            "closes": [round(p["last"]) for p in prior]}

def slim(block, key, b):
    calls = block.get("calls", [])
    today = (b["chains"][0]["ts"].split(" ")[0][:6]) if b else ""
    return {"trend": trend(key, b),
            "current": block.get("current"), "simple": {k: v for k, v in (block.get("simple") or {}).items() if k != "glossary"},
            "open_calls": [c for c in calls if c.get("status") == "open"],
            "calls_opened_today": sum(1 for c in calls if c.get("opened", "").startswith(today)) if today else 0,
            "last_resolved": [c for c in calls if c.get("status") in ("right", "wrong")][-3:],
            "record": {"right": sum(c.get("status") == "right" for c in calls), "wrong": sum(c.get("status") == "wrong" for c in calls), "next_id": max([c["id"] for c in calls] + [0]) + 1}}
print(json.dumps({"lessons": review.get("lessons", []), "recent_reviews": review.get("days", [])[-3:],
                  "nifty": slim(d, "nifty", brief.get("nifty")), "bank": slim(d.get("bank", {}), "bank", brief.get("bank"))}, ensure_ascii=False, indent=1))
