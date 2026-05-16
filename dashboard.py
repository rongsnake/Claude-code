"""
CDS Dashboard — visualises ERA5 climate data scraped from the
Copernicus Climate Data Store (or demo data when credentials are absent).

Run with:
    streamlit run dashboard.py
"""

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import scraper

# ── page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CDS Climate Dashboard",
    page_icon="🌍",
    layout="wide",
)

# ── sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.title("⚙️ Controls")

force_demo = st.sidebar.checkbox("Use demo data", value=not scraper._HAS_CREDENTIALS)

if not force_demo and scraper._HAS_CREDENTIALS:
    st.sidebar.markdown("---")
    st.sidebar.subheader("ERA5 Parameters")
    variable = st.sidebar.selectbox(
        "Variable",
        ["2m_temperature", "total_precipitation", "10m_u_component_of_wind"],
        index=0,
    )
    year = st.sidebar.slider("Year", 1979, 2024, 2023)
    month = st.sidebar.slider("Month", 1, 12, 6)
else:
    variable, year, month = "2m_temperature", 2023, 6


# ── load data ─────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner="Fetching climate data…")
def load(demo: bool, var: str, yr: int, mo: int) -> pd.DataFrame:
    if demo:
        datasets = scraper.fetch_era5_demo()
    else:
        datasets = scraper.fetch_era5_api(variable=var, year=yr, month=mo)
    return datasets["era5"]


df = load(force_demo, variable, year, month)
df["date"] = pd.to_datetime(df["date"])

# ── header ────────────────────────────────────────────────────────────────────
st.title("🌍 CDS Climate Data Dashboard")
mode_label = "Demo mode" if force_demo else "Live CDS data"
st.caption(f"Data source: Copernicus Climate Data Store (ERA5) · {mode_label}")

# ── KPI row ───────────────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)

if "t2m_celsius" in df.columns:
    temp_col = "t2m_celsius"
elif "t2m" in df.columns:
    temp_col = "t2m"
else:
    temp_col = None

precip_col = "tp_mm" if "tp_mm" in df.columns else ("tp" if "tp" in df.columns else None)

with col1:
    if temp_col:
        st.metric("Avg Temperature", f"{df[temp_col].mean():.1f} °C")
    else:
        st.metric("Records", f"{len(df):,}")

with col2:
    if temp_col:
        st.metric("Max Temperature", f"{df[temp_col].max():.1f} °C")
    else:
        st.metric("Columns", len(df.columns))

with col3:
    if precip_col:
        st.metric("Total Precipitation", f"{df[precip_col].sum():.0f} mm")
    elif temp_col:
        st.metric("Min Temperature", f"{df[temp_col].min():.1f} °C")

with col4:
    date_range = f"{df['date'].min().date()} → {df['date'].max().date()}"
    st.metric("Date Range", date_range)

st.divider()

# ── temperature time series ───────────────────────────────────────────────────
if temp_col:
    st.subheader("🌡️ Temperature over Time")
    fig_temp = px.line(
        df,
        x="date",
        y=temp_col,
        labels={"date": "Date", temp_col: "Temperature (°C)"},
        color_discrete_sequence=["#e74c3c"],
    )
    fig_temp.update_layout(hovermode="x unified", height=350)

    # 30-day rolling average
    df_sorted = df.sort_values("date")
    df_sorted["rolling_30"] = df_sorted[temp_col].rolling(30, center=True).mean()
    fig_temp.add_scatter(
        x=df_sorted["date"],
        y=df_sorted["rolling_30"],
        mode="lines",
        name="30-day avg",
        line=dict(color="#2c3e50", width=2, dash="dash"),
    )
    st.plotly_chart(fig_temp, width="stretch")

# ── precipitation ─────────────────────────────────────────────────────────────
if precip_col:
    st.subheader("🌧️ Precipitation over Time")
    fig_precip = px.bar(
        df.sort_values("date"),
        x="date",
        y=precip_col,
        labels={"date": "Date", precip_col: "Precipitation (mm)"},
        color_discrete_sequence=["#2980b9"],
    )
    fig_precip.update_layout(height=320)
    st.plotly_chart(fig_precip, width="stretch")

# ── side-by-side: monthly & distribution ─────────────────────────────────────
left, right = st.columns(2)

with left:
    st.subheader("📅 Monthly Summary")
    df_monthly = df.copy()
    df_monthly["month"] = df_monthly["date"].dt.to_period("M").astype(str)
    agg: dict = {}
    if temp_col:
        agg[temp_col] = "mean"
    if precip_col:
        agg[precip_col] = "sum"
    if agg:
        monthly = df_monthly.groupby("month").agg(agg).reset_index()
        primary = temp_col or precip_col
        fig_bar = px.bar(
            monthly,
            x="month",
            y=primary,
            labels={"month": "Month", primary: primary},
            color_discrete_sequence=["#27ae60"],
        )
        fig_bar.update_layout(xaxis_tickangle=-45, height=350)
        st.plotly_chart(fig_bar, width="stretch")

with right:
    st.subheader("📊 Temperature Distribution")
    if temp_col:
        fig_hist = px.histogram(
            df,
            x=temp_col,
            nbins=40,
            labels={temp_col: "Temperature (°C)"},
            color_discrete_sequence=["#8e44ad"],
        )
        fig_hist.update_layout(height=350)
        st.plotly_chart(fig_hist, width="stretch")
    else:
        st.info("Temperature column not available.")

# ── raw data expander ─────────────────────────────────────────────────────────
with st.expander("🗂️ Raw data"):
    st.dataframe(df, width="stretch", height=300)
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("Download CSV", csv, "cds_data.csv", "text/csv")

st.sidebar.markdown("---")
st.sidebar.caption("Built with Streamlit + Plotly · CDS ERA5")
