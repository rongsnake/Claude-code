"""
Build a self-contained static dashboard (dashboard.html) from the scraped
Credit Derivatives Determinations Committees dataset.

The output is a single HTML file with the data embedded and Plotly.js from a
CDN — no server required. Drop it straight onto gcburton.org. It includes:
  * KPI cards + charts (per year / region / credit-event type)
  * an "Ask the data" panel: headline answers + an interactive group-by pivot
  * download buttons (raw CSV, tidy CSV, analytics JSON) for downstream graphing

Usage:
    python build_dashboard.py
    python build_dashboard.py --input data/determinations.csv --output public/index.html
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import analytics

DEFAULT_OUTPUT = Path("dashboard.html")

ROW_COLS = [
    "date", "year", "committee", "reference_entity", "credit_event_type",
    "decision", "days_to_auction", "auction_held", "is_restructuring",
    "credit_event_occurred", "final_price", "auction_date", "ticker",
    "currency", "net_open_interest_amount", "match_status", "url",
]


def _source_label(df: pd.DataFrame) -> tuple[str, str]:
    sources = set(df.get("source", pd.Series(dtype=str)).dropna().unique())
    if sources == {"synthetic-demo"}:
        return ("DEMO DATA — synthetic, illustrative only. "
                "Run cds_dc_scraper.py with network access to refresh live data.", "warn")
    if sources <= {"reference"}:
        return ("SEED DATA — a small set of verified reference determinations only. "
                "A full live refresh was not run in this environment.", "warn")
    if "synthetic-demo" in sources:
        return ("MIXED DATA — synthetic demo rows alongside scraped/seed rows.", "warn")
    return (f"Live scrape of cdsdeterminationscommittees.org ({len(df):,} determinations).", "ok")


def _clean_rows(df: pd.DataFrame) -> list[dict]:
    """JSON-safe records (NaN/NaT -> None) for client-side aggregation."""
    d = analytics.enrich(df)
    for col in ("date", "auction_date"):
        if col in d:
            d[col] = d[col].dt.strftime("%Y-%m-%d")
    keep = [c for c in ROW_COLS if c in d.columns]
    d = d[keep].astype(object).where(pd.notna(d[keep]), None)
    records = d.to_dict(orient="records")
    # final guard against stray float NaNs
    for r in records:
        for k, v in r.items():
            if isinstance(v, float) and math.isnan(v):
                r[k] = None
    return records


def build(input_path: Path, output_path: Path) -> Path:
    if not input_path.exists():
        raise SystemExit(
            f"{input_path} not found. Run `python cds_dc_scraper.py` (or --demo) first."
        )
    df = pd.read_csv(input_path)
    metrics = analytics.compute(df)
    answers = analytics.headline_answers(metrics)
    banner_text, banner_class = _source_label(df)

    d = analytics.enrich(df).dropna(subset=["date"]).sort_values("date")
    by_year = d.groupby(d["date"].dt.year).size()
    by_region = d["committee"].fillna("Unknown").value_counts()
    by_event = d["credit_event_type"].fillna("Not specified").value_counts()

    recent_cols = ["date", "committee", "reference_entity", "credit_event_type",
                   "final_price", "auction_date", "decision", "url"]
    recent = (
        d.sort_values("date", ascending=False)
        .head(25)[[c for c in recent_cols if c in d.columns]]
        .copy()
    )
    recent["date"] = recent["date"].dt.date.astype(str)
    if "auction_date" in recent:
        recent["auction_date"] = pd.to_datetime(recent["auction_date"], errors="coerce").dt.date.astype(str)
    recent = recent.astype(object).where(pd.notna(recent), "—")

    payload = {
        "kpis": {
            "total": metrics["total_determinations"],
            "entities": metrics["distinct_reference_entities"],
            "credit_events": metrics["credit_events_tagged"],
            "date_min": metrics["date_min"],
            "date_max": metrics["date_max"],
        },
        "answers": [{"label": l, "value": v} for l, v in answers],
        "by_year": {"x": [int(y) for y in by_year.index], "y": [int(v) for v in by_year.values]},
        "by_region": {"labels": list(by_region.index), "values": [int(v) for v in by_region.values]},
        "by_event": {"x": list(by_event.index), "y": [int(v) for v in by_event.values]},
        "by_recovery": {
            "x": list(metrics.get("avg_final_price_by_event", {}).keys()),
            "y": [round(v, 2) for v in metrics.get("avg_final_price_by_event", {}).values()],
        },
        "recent": recent.to_dict(orient="records"),
        "rows": _clean_rows(df),
        "analytics": metrics,
        "banner": {"text": banner_text, "cls": banner_class},
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }

    html = _TEMPLATE.replace("/*__DATA__*/", json.dumps(payload))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"Wrote {output_path} ({output_path.stat().st_size // 1024} KB, "
          f"{metrics['total_determinations']} determinations)")
    return output_path


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>CDS Determinations Committees — Dashboard</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
<style>
  :root { --bg:#0f1620; --card:#172230; --ink:#e8eef5; --muted:#8aa0b6; --accent:#3aa0ff; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
  header { padding:28px 32px 8px; }
  h1 { margin:0; font-size:24px; }
  .sub { color:var(--muted); font-size:13px; margin-top:4px; }
  .wrap { padding:16px 32px 48px; max-width:1200px; margin:0 auto; }
  .banner { padding:10px 14px; border-radius:8px; font-size:13px; margin:12px 0 20px; }
  .banner.warn { background:#3a2e12; color:#ffd58a; border:1px solid #6b531f; }
  .banner.ok { background:#143524; color:#8af0b8; border:1px solid #1f6b46; }
  .kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; margin-bottom:18px; }
  .kpi { background:var(--card); border-radius:12px; padding:16px 18px; }
  .kpi .v { font-size:24px; font-weight:650; }
  .kpi .l { color:var(--muted); font-size:11px; margin-top:4px; text-transform:uppercase; letter-spacing:.5px; }
  .grid { display:grid; grid-template-columns:1fr 1fr; gap:18px; }
  .card { background:var(--card); border-radius:12px; padding:14px 16px 8px; margin-bottom:18px; }
  .card h3 { margin:4px 6px 10px; font-size:14px; font-weight:600; color:#cdd8e4; }
  .full { grid-column:1 / -1; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th,td { text-align:left; padding:8px 10px; border-bottom:1px solid #243245; }
  th { color:var(--muted); font-weight:600; position:sticky; top:0; background:var(--card); }
  td a { color:var(--accent); text-decoration:none; }
  .tablewrap { max-height:420px; overflow:auto; }
  select,button { background:#0f1620; color:var(--ink); border:1px solid #2c3c50;
                  border-radius:8px; padding:8px 10px; font-size:13px; }
  button { cursor:pointer; }
  button:hover { border-color:var(--accent); }
  .controls { display:flex; gap:10px; flex-wrap:wrap; align-items:center; margin:0 6px 12px; }
  .answers { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; margin:0 6px 6px; }
  .ans { background:#0f1a26; border:1px solid #243245; border-radius:10px; padding:12px 14px; }
  .ans .q { color:var(--muted); font-size:12px; } .ans .a { font-size:18px; font-weight:600; margin-top:4px; }
  footer { color:var(--muted); font-size:12px; padding:0 32px 32px; max-width:1200px; margin:0 auto; }
  @media (max-width:760px){ .grid{grid-template-columns:1fr;} }
</style>
</head>
<body>
<header>
  <h1>Credit Derivatives Determinations Committees</h1>
  <div class="sub">Determinations dashboard · source: cdsdeterminationscommittees.org</div>
</header>
<div class="wrap">
  <div id="banner" class="banner"></div>
  <div class="kpis" id="kpis"></div>

  <div class="card full">
    <h3>Ask the data</h3>
    <div class="answers" id="answers"></div>
    <div class="controls">
      <span style="color:#8aa0b6;font-size:13px">Group by</span>
      <select id="dim">
        <option value="committee">Committee region</option>
        <option value="credit_event_type">Credit-event type</option>
        <option value="year">Year</option>
        <option value="decision">Decision</option>
      </select>
      <span style="color:#8aa0b6;font-size:13px">Measure</span>
      <select id="measure">
        <option value="count">Count of determinations</option>
        <option value="pct">% of total</option>
        <option value="avg_days_to_auction">Avg days to auction</option>
        <option value="avg_final_price">Avg final price (recovery)</option>
        <option value="credit_event_rate">Credit-event rate (%)</option>
      </select>
      <button id="dlCsv">⬇ Raw CSV</button>
      <button id="dlTidy">⬇ Tidy CSV</button>
      <button id="dlJson">⬇ Analytics JSON</button>
    </div>
    <div id="pivot" style="height:340px"></div>
  </div>

  <div class="grid">
    <div class="card"><h3>Determinations per year</h3><div id="byYear" style="height:320px"></div></div>
    <div class="card"><h3>By committee region</h3><div id="byRegion" style="height:320px"></div></div>
  </div>
  <div class="card full"><h3>By credit-event type</h3><div id="byEvent" style="height:320px"></div></div>
  <div class="card full"><h3>Avg auction final price / recovery (Creditex) by credit-event type</h3><div id="byRecovery" style="height:320px"></div></div>

  <div class="card full">
    <h3>Most recent determinations (reconciled with Creditex auctions)</h3>
    <div class="tablewrap"><table id="recent"><thead><tr>
      <th>Date</th><th>Committee</th><th>Reference entity</th>
      <th>Credit event</th><th>Final price</th><th>Auction date</th><th>Decision</th><th>Doc</th>
    </tr></thead><tbody></tbody></table></div>
  </div>
</div>
<footer>Generated <span id="gen"></span> · Static dashboard, no server required.</footer>

<script>
const DATA = /*__DATA__*/;
const layout = { paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
  font:{color:'#cdd8e4'}, margin:{t:10,r:14,b:60,l:48}, showlegend:false };
const conf = { displayModeBar:false, responsive:true };

const b = document.getElementById('banner');
b.textContent = DATA.banner.text; b.classList.add(DATA.banner.cls);
document.getElementById('gen').textContent = DATA.generated;

const k = DATA.kpis;
document.getElementById('kpis').innerHTML = [
  ['Determinations', (k.total||0).toLocaleString()],
  ['Reference entities', (k.entities||0).toLocaleString()],
  ['Credit events tagged', (k.credit_events||0).toLocaleString()],
  ['Earliest', k.date_min||'—'],
  ['Latest', k.date_max||'—'],
].map(([l,v]) => `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join('');

document.getElementById('answers').innerHTML = DATA.answers.map(
  a => `<div class="ans"><div class="q">${a.label}</div><div class="a">${a.value}</div></div>`
).join('');

Plotly.newPlot('byYear', [{type:'bar', x:DATA.by_year.x, y:DATA.by_year.y, marker:{color:'#3aa0ff'}}], layout, conf);
Plotly.newPlot('byRegion', [{type:'pie', labels:DATA.by_region.labels, values:DATA.by_region.values, hole:.55,
  textinfo:'label+percent', marker:{colors:['#3aa0ff','#37c98b','#f5a623','#c86bff','#ff6b6b','#888']}}],
  {...layout, margin:{t:10,r:10,b:10,l:10}}, conf);
Plotly.newPlot('byEvent', [{type:'bar', x:DATA.by_event.x, y:DATA.by_event.y, marker:{color:'#37c98b'}}], layout, conf);
if (DATA.by_recovery.x.length)
  Plotly.newPlot('byRecovery', [{type:'bar', x:DATA.by_recovery.x, y:DATA.by_recovery.y, marker:{color:'#c86bff'},
    text:DATA.by_recovery.y.map(v=>v.toFixed(2)), textposition:'auto'}], {...layout, yaxis:{range:[0,100], title:'final price'}}, conf);
else document.getElementById('byRecovery').innerHTML =
  '<div style="color:#8aa0b6;padding:24px">No auction final-price data yet — run a live Creditex refresh.</div>';

// ── interactive pivot ────────────────────────────────────────────────────────
function aggregate(dim, measure) {
  const groups = {};
  for (const r of DATA.rows) {
    const key = (r[dim] === null || r[dim] === undefined || r[dim] === '') ? 'Unknown' : r[dim];
    (groups[key] = groups[key] || []).push(r);
  }
  const keys = Object.keys(groups).sort();
  const vals = keys.map(key => {
    const rows = groups[key];
    if (measure === 'count') return rows.length;
    if (measure === 'pct') return +(rows.length / DATA.rows.length * 100).toFixed(1);
    if (measure === 'avg_days_to_auction') {
      const d = rows.map(r => r.days_to_auction).filter(v => v !== null && v !== undefined);
      return d.length ? +(d.reduce((a,b)=>a+b,0)/d.length).toFixed(1) : 0;
    }
    if (measure === 'avg_final_price') {
      const d = rows.map(r => r.final_price).filter(v => v !== null && v !== undefined && v !== '');
      return d.length ? +(d.reduce((a,b)=>a+Number(b),0)/d.length).toFixed(2) : 0;
    }
    if (measure === 'credit_event_rate') {
      const ce = rows.filter(r => r.credit_event_occurred).length;
      return +(ce / rows.length * 100).toFixed(1);
    }
    return rows.length;
  });
  return {keys, vals};
}
function drawPivot() {
  const dim = document.getElementById('dim').value;
  const measure = document.getElementById('measure').value;
  const {keys, vals} = aggregate(dim, measure);
  Plotly.react('pivot', [{type:'bar', x:keys, y:vals, marker:{color:'#f5a623'},
    text:vals.map(String), textposition:'auto'}], layout, conf);
}
document.getElementById('dim').onchange = drawPivot;
document.getElementById('measure').onchange = drawPivot;
drawPivot();

// ── downloads ─────────────────────────────────────────────────────────────────
function download(name, text, type) {
  const blob = new Blob([text], {type}); const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = name; a.click();
  URL.revokeObjectURL(url);
}
function toCsv(rows) {
  if (!rows.length) return '';
  const cols = Object.keys(rows[0]);
  const esc = v => (v===null||v===undefined) ? '' :
    /[",\n]/.test(String(v)) ? '"'+String(v).replace(/"/g,'""')+'"' : String(v);
  return [cols.join(','), ...rows.map(r => cols.map(c => esc(r[c])).join(','))].join('\n');
}
document.getElementById('dlCsv').onclick  = () => download('determinations.csv', toCsv(DATA.recent.length?DATA.rows:[]), 'text/csv');
document.getElementById('dlTidy').onclick = () => download('determinations_tidy.csv', toCsv(DATA.rows), 'text/csv');
document.getElementById('dlJson').onclick = () => download('determinations_analytics.json', JSON.stringify(DATA.analytics, null, 2), 'application/json');

// ── recent table ──────────────────────────────────────────────────────────────
document.querySelector('#recent tbody').innerHTML = DATA.recent.map(r => `<tr>
  <td>${r.date}</td><td>${r.committee}</td><td>${r.reference_entity}</td>
  <td>${r.credit_event_type}</td><td>${r.final_price ?? '—'}</td><td>${r.auction_date ?? '—'}</td><td>${r.decision}</td>
  <td><a href="${r.url}" target="_blank" rel="noopener">PDF ↗</a></td></tr>`).join('');
</script>
</body>
</html>
"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build static DC dashboard")
    ap.add_argument("--input", type=Path, default=None)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = ap.parse_args()
    build(args.input or analytics.default_input(), args.output)
