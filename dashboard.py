"""
Interactive Streamlit dashboard for Credit Derivatives Determinations
Committees (DC) data.

This is the *local/interactive* companion to the static `build_dashboard.py`
output. Run with:

    streamlit run dashboard.py

For a deployable, server-free dashboard (e.g. for gcburton.org) use:

    python build_dashboard.py      # -> dashboard.html
"""

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

import cds_dc_scraper as scraper

DATA_CSV = Path("data/determinations.csv")

st.set_page_config(page_title="CDS Determinations Committees", page_icon="⚖️", layout="wide")


@st.cache_data(show_spinner="Loading determinations…")
def load_data(mode: str) -> pd.DataFrame:
    if mode == "Demo (synthetic)":
        scraper.run(mode="demo")
    elif mode == "Live refresh":
        scraper.run(mode="live")
    elif not DATA_CSV.exists():
        scraper.run(mode="seed-only")
    df = pd.read_csv(DATA_CSV)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.dropna(subset=["date"]).sort_values("date")


# ── sidebar ─────────────────────────────────────────────────────────────────
st.sidebar.title("⚙️ Data")
mode = st.sidebar.radio(
    "Source",
    ["Use existing file", "Live refresh", "Demo (synthetic)"],
    help="‘Live refresh’ scrapes cdsdeterminationscommittees.org — only works "
    "from a network that can reach the site.",
)
df = load_data(mode)

# provenance banner
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
if len(years):
    lo, hi = int(years.min()), int(years.max())
    if lo < hi:
        yr_lo, yr_hi = st.sidebar.slider("Year range", lo, hi, (lo, hi))
        df = df[(years >= yr_lo) & (years <= yr_hi)]

# ── header + KPIs ───────────────────────────────────────────────────────────
st.title("⚖️ Credit Derivatives Determinations Committees")
st.caption("Determinations / decisions published at cdsdeterminationscommittees.org")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Determinations", f"{len(df):,}")
c2.metric("Reference entities", f"{df['reference_entity'].dropna().nunique():,}")
c3.metric("Credit events tagged", f"{int(df['credit_event_type'].notna().sum()):,}")
if len(df):
    c4.metric("Date range", f"{df['date'].min().date()} → {df['date'].max().date()}")

st.divider()

# ── charts ──────────────────────────────────────────────────────────────────
left, right = st.columns(2)
with left:
    st.subheader("Determinations per year")
    per_year = df.groupby(df["date"].dt.year).size().reset_index(name="count")
    per_year.columns = ["year", "count"]
    st.plotly_chart(
        px.bar(per_year, x="year", y="count", color_discrete_sequence=["#3aa0ff"]),
        width="stretch",
    )
with right:
    st.subheader("By committee region")
    reg = df["committee"].fillna("Unknown").value_counts().reset_index()
    reg.columns = ["region", "count"]
    st.plotly_chart(
        px.pie(reg, names="region", values="count", hole=0.55),
        width="stretch",
    )

st.subheader("By credit-event type")
ev = df["credit_event_type"].fillna("Not specified").value_counts().reset_index()
ev.columns = ["event", "count"]
st.plotly_chart(
    px.bar(ev, x="event", y="count", color_discrete_sequence=["#37c98b"]),
    width="stretch",
)

st.subheader("Determinations")
show = df.sort_values("date", ascending=False)[
    ["date", "committee", "reference_entity", "credit_event_type", "decision", "url"]
]
st.dataframe(show, width="stretch", height=380, column_config={
    "url": st.column_config.LinkColumn("document")
})
st.download_button(
    "Download CSV", df.to_csv(index=False).encode(), "determinations.csv", "text/csv"
)
