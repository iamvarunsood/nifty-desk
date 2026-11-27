#!/usr/bin/env python3
"""Build index.html from template.html + data.json, and append this snapshot to history.json.
Usage: python3 build.py            (reads data.json written by the latest fetch)
History resets automatically when the NSE trade date changes."""
import json, pathlib, re
root = pathlib.Path(__file__).parent
data = json.loads((root.parent/'data'/'data.json').read_text())
hist_p = root/'history.json'
hist = json.loads(hist_p.read_text()) if hist_p.exists() else {'date': None, 'points': []}

c0 = data['chains'][0]
ts = c0['ts']                       # e.g. "30-Oct-2026 15:40:00"
day, t = ts.split(' ')[0], ts.split(' ')[1][:5]
if hist.get('date') != day:
    hist = {'date': day, 'points': [], 'bank': []}
hist.setdefault('bank', [])
def pt(c, vix): return {'t': t, 'spot': c['spot'], 'pcr': c['pcr'], 'vix': vix, 'maxPain': c['maxPain']}
if not hist['points'] or hist['points'][-1]['t'] != t:
    hist['points'].append(pt(c0, data['vix']['last']))
if data.get('bank') and (not hist['bank'] or hist['bank'][-1]['t'] != t):
    hist['bank'].append(pt(data['bank']['chains'][0], data['vix']['last']))
hist_p.write_text(json.dumps(hist))

# Daily open/high/low/close log (feeds the trend check in desk_brief.py); today's row is updated on every run
daily_p = root/'daily.json'
daily = json.loads(daily_p.read_text()) if daily_p.exists() else []
q = lambda n: {k: (n or {}).get(k) for k in ('open', 'high', 'low', 'last')}
row = {'date': day, 'nifty': q(data['nifty']), 'bank': q((data.get('bank') or {}).get('nifty'))}
daily = [d for d in daily if d['date'] != day] + [row]
daily_p.write_text(json.dumps(daily[-30:], indent=0))
history_obj = {'nifty': hist['points'], 'bank': hist['bank']}

desk_p = root/'desk.json'
desk = json.loads(desk_p.read_text()) if desk_p.exists() else {'current': None, 'calls': []}

tpl = (root/'template.html').read_text()
out = (tpl.replace('__DATA__', json.dumps(data, separators=(',',':')))
          .replace('__HISTORY__', json.dumps(history_obj))
          .replace('__DESK__', json.dumps(desk, separators=(',',':'), ensure_ascii=False)))
(root/'index.html').write_text(out)
# Standalone copy for GitHub Pages (the artifact host adds this skeleton itself; Pages does not)
head = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
        '<meta name="color-scheme" content="light dark"><meta name="robots" content="noindex">'
        '<style>html{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}'
        'body{margin:0;font:14px system-ui}img{max-width:100%}[hidden]{display:none!important}</style>')
(root/'index-pages.html').write_text(head + out + '</body></html>')
(root.parent/'index.html').write_text(head + out + '</body></html>')
print(f"built index.html — {day} {t}, spot {c0['spot']}, PCR {c0['pcr']}, bias {data['bias']}, history points {len(hist['points'])}")
