"""
Build a self-contained static dashboard (dashboard.html) from the scraped
Credit Derivatives Determinations Committees dataset.

The output is a single HTML file with the data embedded and Plotly.js loaded
from a CDN — no server required. Drop it straight onto gcburton.org.

Usage:
    python build_dashboard.py                       # reads data/determinations.csv
    python build_dashboard.py --input data/foo.csv --output public/index.html
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd

DEFAULT_INPUT = Path("data/determinations.csv")
DEFAULT_OUTPUT = Path("dashboard.html")


def _source_label(df: pd.DataFrame) -> tuple[str, str]:
    """Return (banner_text, css_class) describing the dataset provenance."""
    sources = set(df.get("source", pd.Series(dtype=str)).dropna().unique())
    if sources == {"synthetic-demo"}:
        return ("DEMO DATA — synthetic, illustrative only. "
                "Run cds_dc_scraper.py with network access to refresh live data.",
                "warn")
    if sources <= {"reference"}:
        return ("SEED DATA — a small set of verified reference determinations only. "
                "A full live refresh was not run in this environment.",
                "warn")
    if "synthetic-demo" in sources:
        return ("MIXED DATA — includes synthetic demo rows alongside scraped/seed rows.",
                "warn")
    return (f"Live scrape of cdsdeterminationscommittees.org "
            f"({len(df):,} determinations).", "ok")


def build(input_path: Path, output_path: Path) -> Path:
    if not input_path.exists():
        raise SystemExit(
            f"{input_path} not found. Run `python cds_dc_scraper.py` (or --demo) first."
        )
    df = pd.read_csv(input_path)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date")

    banner_text, banner_class = _source_label(df)

    # ── aggregates ─────────────────────────────────────────────────────────────
    by_year = df.groupby(df["date"].dt.year).size()
    by_region = df["committee"].fillna("Unknown").value_counts()
    by_event = df["credit_event_type"].fillna("Not specified").value_counts()

    n_total = len(df)
    n_entities = df["reference_entity"].dropna().nunique()
    n_events = int(df["credit_event_type"].notna().sum())
    date_min = df["date"].min().date().isoformat()
    date_max = df["date"].max().date().isoformat()

    recent = (
        df.sort_values("date", ascending=False)
        .head(25)[["date", "committee", "reference_entity", "credit_event_type",
                   "decision", "url"]]
        .copy()
    )
    recent["date"] = recent["date"].dt.date.astype(str)
    recent = recent.fillna("—")

    payload = {
        "kpis": {
            "total": n_total,
            "entities": n_entities,
            "credit_events": n_events,
            "date_min": date_min,
            "date_max": date_max,
        },
        "by_year": {"x": [int(y) for y in by_year.index], "y": [int(v) for v in by_year.values]},
        "by_region": {"labels": list(by_region.index), "values": [int(v) for v in by_region.values]},
        "by_event": {"x": list(by_event.index), "y": [int(v) for v in by_event.values]},
        "recent": recent.to_dict(orient="records"),
        "banner": {"text": banner_text, "cls": banner_class},
        "generated": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    }

    html = _TEMPLATE.replace("/*__DATA__*/", json.dumps(payload))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"Wrote {output_path} ({output_path.stat().st_size // 1024} KB, {n_total} determinations)")
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
         font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
  header { padding:28px 32px 8px; }
  h1 { margin:0; font-size:24px; letter-spacing:.2px; }
  .sub { color:var(--muted); font-size:13px; margin-top:4px; }
  .wrap { padding:16px 32px 48px; max-width:1200px; margin:0 auto; }
  .banner { padding:10px 14px; border-radius:8px; font-size:13px; margin:12px 0 20px; }
  .banner.warn { background:#3a2e12; color:#ffd58a; border:1px solid #6b531f; }
  .banner.ok { background:#143524; color:#8af0b8; border:1px solid #1f6b46; }
  .kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:14px; margin-bottom:22px; }
  .kpi { background:var(--card); border-radius:12px; padding:16px 18px; }
  .kpi .v { font-size:26px; font-weight:650; }
  .kpi .l { color:var(--muted); font-size:12px; margin-top:4px; text-transform:uppercase; letter-spacing:.5px; }
  .grid { display:grid; grid-template-columns:1fr 1fr; gap:18px; }
  .card { background:var(--card); border-radius:12px; padding:14px 16px 6px; }
  .card h3 { margin:4px 6px 0; font-size:14px; font-weight:600; color:#cdd8e4; }
  .full { grid-column:1 / -1; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th,td { text-align:left; padding:8px 10px; border-bottom:1px solid #243245; }
  th { color:var(--muted); font-weight:600; position:sticky; top:0; background:var(--card); }
  td a { color:var(--accent); text-decoration:none; }
  .tablewrap { max-height:420px; overflow:auto; }
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
  <div class="grid">
    <div class="card"><h3>Determinations per year</h3><div id="byYear" style="height:320px"></div></div>
    <div class="card"><h3>By committee region</h3><div id="byRegion" style="height:320px"></div></div>
    <div class="card full"><h3>By credit-event type</h3><div id="byEvent" style="height:320px"></div></div>
    <div class="card full">
      <h3>Most recent determinations</h3>
      <div class="tablewrap"><table id="recent"><thead><tr>
        <th>Date</th><th>Committee</th><th>Reference entity</th>
        <th>Credit event</th><th>Decision</th><th>Doc</th>
      </tr></thead><tbody></tbody></table></div>
    </div>
  </div>
</div>
<footer>Generated <span id="gen"></span> · Static dashboard, no server required.</footer>

<script>
const DATA = /*__DATA__*/;
const layout = { paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
  font:{color:'#cdd8e4'}, margin:{t:10,r:14,b:40,l:48}, showlegend:false };
const conf = { displayModeBar:false, responsive:true };

// banner
const b = document.getElementById('banner');
b.textContent = DATA.banner.text; b.classList.add(DATA.banner.cls);
document.getElementById('gen').textContent = DATA.generated;

// KPIs
const k = DATA.kpis;
const kpis = [
  ['Determinations', k.total.toLocaleString()],
  ['Reference entities', k.entities.toLocaleString()],
  ['Credit events tagged', k.credit_events.toLocaleString()],
  ['Earliest', k.date_min],
  ['Latest', k.date_max],
];
document.getElementById('kpis').innerHTML = kpis.map(
  ([l,v]) => `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`
).join('');

Plotly.newPlot('byYear', [{
  type:'bar', x:DATA.by_year.x, y:DATA.by_year.y, marker:{color:'#3aa0ff'}
}], layout, conf);

Plotly.newPlot('byRegion', [{
  type:'pie', labels:DATA.by_region.labels, values:DATA.by_region.values, hole:.55,
  textinfo:'label+percent', marker:{colors:['#3aa0ff','#37c98b','#f5a623','#c86bff','#ff6b6b','#888']}
}], {...layout, margin:{t:10,r:10,b:10,l:10}}, conf);

Plotly.newPlot('byEvent', [{
  type:'bar', x:DATA.by_event.x, y:DATA.by_event.y, marker:{color:'#37c98b'}
}], layout, conf);

// recent table
const tb = document.querySelector('#recent tbody');
tb.innerHTML = DATA.recent.map(r => `<tr>
  <td>${r.date}</td><td>${r.committee}</td><td>${r.reference_entity}</td>
  <td>${r.credit_event_type}</td><td>${r.decision}</td>
  <td><a href="${r.url}" target="_blank" rel="noopener">PDF ↗</a></td></tr>`).join('');
</script>
</body>
</html>
"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build static DC dashboard")
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = ap.parse_args()
    build(args.input, args.output)
