"""Print a compact view of desk.json for the analyst: current views + open calls + last 3 resolved per index."""
import json, pathlib
d = json.loads((pathlib.Path(__file__).parent / "desk.json").read_text())
def slim(block):
    calls = block.get("calls", [])
    return {"current": block.get("current"), "simple": {k: v for k, v in (block.get("simple") or {}).items() if k != "glossary"},
            "open_calls": [c for c in calls if c.get("status") == "open"],
            "last_resolved": [c for c in calls if c.get("status") in ("right", "wrong")][-3:],
            "record": {"right": sum(c.get("status") == "right" for c in calls), "wrong": sum(c.get("status") == "wrong" for c in calls), "next_id": max([c["id"] for c in calls] + [0]) + 1}}
print(json.dumps({"nifty": slim(d), "bank": slim(d.get("bank", {}))}, ensure_ascii=False, indent=1))
