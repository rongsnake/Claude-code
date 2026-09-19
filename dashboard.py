"""
Interactive Streamlit dashboard for Credit Derivatives Determinations
Committees (DC) data, with an "ask the data" SQL box.

    streamlit run dashboard.py

For a deployable, server-free dashboard (e.g. for gcburton.org) use:

    python build_dashboard.py      # -> dashboard.html
"""

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

import cds_dc_scraper as scraper
import creditex_scraper
import reconcile
import analytics

st.set_page_config(page_title="CDS Determinations Committees", page_icon="⚖️", layout="wide")


def _pipeline(mode: str) -> None:
    """Scrape determinations + Creditex auctions, then reconcile."""
    scraper.run(mode=mode)
    creditex_scraper.run(mode=mode)
    reconcile.run()


@st.cache_data(show_spinner="Loading determinations + auctions…")
def load_data(mode: str) -> pd.DataFrame:
    if mode == "Demo (synthetic)":
        _pipeline("demo")
    elif mode == "Live refresh":
        _pipeline("live")
    elif not analytics.default_input().exists():
        _pipeline("seed-only")
    df = pd.read_csv(analytics.default_input())
    return analytics.enrich(df).sort_values("date", na_position="last")


# ── sidebar ─────────────────────────────────────────────────────────────────
st.sidebar.title("⚙️ Data")
mode = st.sidebar.radio(
    "Source",
    ["Use existing file", "Live refresh", "Demo (synthetic)"],
    help="‘Live refresh’ scrapes cdsdeterminationscommittees.org — only works "
    "from a network that can reach the site.",
)
df = load_data(mode)

sources = set(df["source"].dropna().unique()) if "source" in df else set()
if sources == {"synthetic-demo"}:
    st.warning("**Demo data** — synthetic and illustrative only. Use *Live refresh* "
               "from a permitted network to pull real determinations.")
elif sources <= {"reference"}:
    st.warning("**Seed data** — a handful of verified reference determinations only. "
               "A full live refresh has not been run here.")
elif "synthetic-demo" in sources:
    st.info("**Mixed data** — scraped/seed rows plus synthetic demo rows.")
else:
    st.success(f"Live scrape — {len(df):,} determinations from cdsdeterminationscommittees.org")

# filters
regions = sorted(df["committee"].dropna().unique())
picked = st.sidebar.multiselect("Committee region", regions, default=regions)
if picked:
    df = df[df["committee"].isin(picked)]
years = df["date"].dt.year
if len(years) and int(years.min()) < int(years.max()):
    yr_lo, yr_hi = st.sidebar.slider("Year range", int(years.min()), int(years.max()),
                                     (int(years.min()), int(years.max())))
    df = df[(years >= yr_lo) & (years <= yr_hi)]

metrics = analytics.compute(df)

# ── header + KPIs ───────────────────────────────────────────────────────────
st.title("⚖️ Credit Derivatives Determinations Committees")
st.caption("Determinations / decisions published at cdsdeterminationscommittees.org")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Determinations", f"{len(df):,}")
c2.metric("Reference entities", f"{df['reference_entity'].dropna().nunique():,}")
c3.metric("Credit events tagged", f"{int(df['credit_event_type'].notna().sum()):,}")
if len(df):
    c4.metric("Date range", f"{df['date'].min().date()} → {df['date'].max().date()}")

# ── ask-the-data: headline answers ──────────────────────────────────────────
st.subheader("💬 Ask the data")
dta = metrics["days_to_auction"]
fp = metrics.get("auction_final_price")
a1, a2, a3, a4 = st.columns(4)
a1.metric("% of credit events that are Restructuring",
          "n/a" if metrics["pct_restructuring_of_events"] is None
          else f"{metrics['pct_restructuring_of_events']}%")
a2.metric("Avg days to auction",
          "n/a" if dta["mean"] is None else f"{dta['mean']:.1f} days",
          help=None if dta["mean"] is None else f"median {dta['median']:.0f}, n={dta['count']}")
a3.metric("Avg final price (recovery)",
          "n/a" if not fp else f"{fp['mean']:.2f}",
          help=None if not fp else f"median {fp['median']:.2f}, n={fp['count']} (Creditex)")
a4.metric("Determinations reconciled to an auction",
          "n/a" if metrics.get("reconciliation_rate_pct") is None
          else f"{metrics['reconciliation_rate_pct']}%")

with st.expander("Ask your own question — SQL over the `determinations` table"):
    st.caption("Columns include: date, year, committee, reference_entity, "
               "credit_event_type, decision, days_to_auction, final_price, "
               "auction_date, ticker, currency, net_open_interest_amount, "
               "match_status, is_restructuring, credit_event_occurred.")
    default_sql = (
        "SELECT credit_event_type,\n"
        "       count(*) AS n,\n"
        "       round(avg(final_price), 2) AS avg_recovery,\n"
        "       round(avg(days_to_auction), 1) AS avg_days_to_auction\n"
        "FROM determinations\n"
        "WHERE credit_event_type IS NOT NULL\n"
        "GROUP BY credit_event_type\n"
        "ORDER BY n DESC"
    )
    sql = st.text_area("Query", default_sql, height=160)
    if st.button("Run query"):
        try:
            import duckdb
            con = duckdb.connect()
            con.register("determinations", df)
            res = con.execute(sql).df()
            st.dataframe(res, width="stretch")
            num = res.select_dtypes("number").columns
            if len(res.columns) >= 2 and len(num):
                st.bar_chart(res.set_index(res.columns[0])[num[0]])
        except ModuleNotFoundError:
            st.error("duckdb not installed — run `pip install duckdb`.")
        except Exception as exc:  # surface SQL errors to the user
            st.error(f"Query error: {exc}")

st.divider()

# ── charts ──────────────────────────────────────────────────────────────────
left, right = st.columns(2)
with left:
    st.subheader("Determinations per year")
    per_year = df.groupby(df["date"].dt.year).size().reset_index(name="count")
    per_year.columns = ["year", "count"]
    st.plotly_chart(px.bar(per_year, x="year", y="count",
                           color_discrete_sequence=["#3aa0ff"]), width="stretch")
with right:
    st.subheader("By committee region")
    reg = df["committee"].fillna("Unknown").value_counts().reset_index()
    reg.columns = ["region", "count"]
    st.plotly_chart(px.pie(reg, names="region", values="count", hole=0.55), width="stretch")

st.subheader("By credit-event type")
ev = df["credit_event_type"].fillna("Not specified").value_counts().reset_index()
ev.columns = ["event", "count"]
st.plotly_chart(px.bar(ev, x="event", y="count",
                       color_discrete_sequence=["#37c98b"]), width="stretch")

# ── table + downloads ────────────────────────────────────────────────────────
st.subheader("Determinations × Creditex auctions (reconciled)")
cols = ["date", "committee", "reference_entity", "credit_event_type",
        "final_price", "auction_date", "days_to_auction", "match_status", "url"]
show = df.sort_values("date", ascending=False)[[c for c in cols if c in df.columns]]
st.dataframe(show, width="stretch", height=380,
             column_config={"url": st.column_config.LinkColumn("document"),
                            "final_price": st.column_config.NumberColumn("final price", format="%.3f")})

d1, d2, d3 = st.columns(3)
d1.download_button("⬇ Raw CSV", df.to_csv(index=False).encode(),
                   "determinations.csv", "text/csv")
d2.download_button("⬇ Tidy CSV (derived cols)",
                   analytics.enrich(df).to_csv(index=False).encode(),
                   "determinations_tidy.csv", "text/csv")
d3.download_button("⬇ Analytics JSON",
                   pd.Series(metrics).to_json(indent=2).encode(),
                   "determinations_analytics.json", "application/json")
