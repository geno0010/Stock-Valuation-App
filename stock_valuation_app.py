#!/usr/bin/env python3
"""
Stock Valuation Ratios App
Uses Finnhub free API (supports all tickers).
Includes historical ratios from the metric series, averages, and current vs history.
"""

import warnings
warnings.filterwarnings("ignore")

import streamlit as st
import pandas as pd
import numpy as np
import re
import requests

st.set_page_config(page_title="Stock Valuation Ratios", page_icon="📊", layout="wide")

st.title("📊 Stock Valuation Ratios")
st.caption("P/S · P/E · P/OCF · Powered by Finnhub · All tickers · History · Averages · Charts")

with st.sidebar:
    st.header("Settings")
    api_key = st.secrets.get("FINNHUB_API_KEY", "")
    if not api_key:
        api_key = st.text_input(
            "Finnhub API Key",
            type="password",
            help="Get a free key at finnhub.io. For shared use, add it as a Streamlit secret named FINNHUB_API_KEY."
        )
    else:
        st.success("Using embedded Finnhub key")

    ticker_input = st.text_input(
        "Ticker(s)",
        value="AAPL",
        help="One or more tickers (comma or space separated). Press Enter to run."
    )
    show_negative_pe = st.checkbox("Show negative P/E values", value=True)
    st.markdown("---")
    st.markdown("[Get free Finnhub key](https://finnhub.io/register)")
    st.caption("Free tier supports all US tickers.")


def parse_tickers(raw: str) -> list[str]:
    if not raw:
        return []
    parts = re.split(r"[,\s\n]+", raw.strip().upper())
    return [p for p in parts if p and re.match(r"^[A-Z0-9.\-^]+$", p)]


def finnhub_get(endpoint: str, params: dict, api_key: str):
    params = params.copy()
    params["token"] = api_key
    try:
        r = requests.get(f"https://finnhub.io/api/v1/{endpoint}", params=params, timeout=15)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}: {r.text[:200]}"
        data = r.json()
        if isinstance(data, dict) and data.get("error"):
            return None, data["error"]
        return data, None
    except Exception as e:
        return None, str(e)


@st.cache_data(ttl=3600, show_spinner=False)
def load_ticker(ticker: str, api_key: str):
    profile, err_p = finnhub_get("stock/profile2", {"symbol": ticker}, api_key)
    quote, err_q = finnhub_get("quote", {"symbol": ticker}, api_key)
    metrics, err_m = finnhub_get("stock/metric", {"symbol": ticker, "metric": "all"}, api_key)

    if err_p or not profile:
        return None, err_p or "No profile data"

    return {
        "profile": profile or {},
        "quote": quote or {},
        "metrics": metrics.get("metric", {}) if isinstance(metrics, dict) else {},
        "series": metrics.get("series", {}) if isinstance(metrics, dict) else {},
        "ticker": ticker,
        "errors": [e for e in [err_q, err_m] if e],
    }, None


def series_to_df(series_dict, freq="annual"):
    if not series_dict or freq not in series_dict:
        return pd.DataFrame()
    data = series_dict[freq]
    if not data:
        return pd.DataFrame()

    rows = []
    dates = set()
    for key in ["pe", "ps", "pfcf", "pb"]:
        if key in data and isinstance(data[key], list):
            for item in data[key]:
                if isinstance(item, dict) and "period" in item:
                    dates.add(item["period"])

    for date in sorted(dates, reverse=True):
        # Compact date label
        try:
            dt = pd.to_datetime(date)
            if freq == "quarterly":
                q = (dt.month - 1) // 3 + 1
                label_date = f"{dt.year} Q{q}"
            else:
                label_date = str(dt.year)
        except Exception:
            label_date = str(date)[:10]

        row = {"Period": label_date}
        for key, label in [("pe", "P/E"), ("ps", "P/S"), ("pfcf", "P/CF"), ("pb", "P/B")]:
            if key in data:
                for item in data[key]:
                    if isinstance(item, dict) and item.get("period") == date:
                        val = item.get("v")
                        row[label] = round(val, 2) if isinstance(val, (int, float)) else val
                        break
        rows.append(row)

    df = pd.DataFrame(rows)
    # Drop columns that are entirely empty
    if not df.empty:
        df = df.dropna(axis=1, how="all")
    return df


# -------------------- Main --------------------
if not api_key:
    st.info("Enter your free Finnhub API key in the sidebar to begin.")
    st.stop()

tickers = parse_tickers(ticker_input)
if not tickers:
    st.warning("Enter at least one valid ticker.")
    st.stop()

st.write(f"**Analyzing:** {', '.join(tickers)}")

results = []
errors = []

progress = st.progress(0)
for i, ticker in enumerate(tickers):
    data, err = load_ticker(ticker, api_key)
    if err or data is None:
        errors.append(f"{ticker}: {err or 'No data'}")
    else:
        profile = data["profile"]
        quote = data["quote"]
        metrics = data["metrics"]
        series = data["series"]

        annual_df = series_to_df(series, "annual")
        quarterly_df = series_to_df(series, "quarterly")

        # Build TTM row from current metrics
        def clean(v):
            if v is None or v == 0:
                return None
            return round(float(v), 2)

        ttm_row = pd.DataFrame([{
            "Period": "TTM",
            "P/S": clean(metrics.get("psTTM") or metrics.get("psAnnual")),
            "P/E": clean(metrics.get("peBasicExclExtraTTM") or metrics.get("peTTM") or metrics.get("peAnnual")),
            "P/CF": clean(metrics.get("pcfShareTTM") or metrics.get("priceToOperatingCashFlowTTM")),
            "P/B": clean(metrics.get("pbQuarterly") or metrics.get("pbAnnual")),
        }])

        # Prepend TTM to both tables
        if not quarterly_df.empty:
            quarterly_df = pd.concat([ttm_row, quarterly_df], ignore_index=True)
        if not annual_df.empty:
            annual_df = pd.concat([ttm_row, annual_df], ignore_index=True)

        current = {
            "Ticker": ticker,
            "Name": profile.get("name") or ticker,
            "Price": quote.get("c"),
            "P/S": metrics.get("psTTM") or metrics.get("psAnnual"),
            "P/E": metrics.get("peBasicExclExtraTTM") or metrics.get("peTTM") or metrics.get("peAnnual"),
            "P/OCF": metrics.get("pcfShareTTM") or metrics.get("priceToOperatingCashFlowTTM"),
            "Market Cap": profile.get("marketCapitalization"),
            "annual_df": annual_df,
            "quarterly_df": quarterly_df,
            "metrics": metrics,
        }
        results.append(current)
        if data.get("errors"):
            errors.extend([f"{ticker}: {e}" for e in data["errors"]])
    progress.progress((i + 1) / len(tickers))

progress.empty()

if errors:
    with st.expander("⚠️ Data issues"):
        for e in errors:
            st.write(e)

if not results:
    st.error("No data could be loaded. Check the error details above.")
    st.stop()

for res in results:
    st.markdown("---")
    st.subheader(f"{res['Name']} ({res['Ticker']})")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Price", f"${res['Price']:,.2f}" if res.get("Price") else "—")
    c2.metric("P/S", f"{res['P/S']:.2f}" if res.get("P/S") else "—")
    pe = res.get("P/E")
    c3.metric("P/E", f"{pe:.2f}" if pe and (pe > 0 or show_negative_pe) else ("N/A (loss)" if pe is not None else "—"))
    c4.metric("P/OCF", f"{res['P/OCF']:.2f}" if res.get("P/OCF") else "—")
    c5.metric("Market Cap", f"${res['Market Cap']/1e3:.1f}B" if res.get("Market Cap") else "—")

    # Growth section
    m = res.get("metrics", {})
    eps_growth = m.get("epsGrowthTTMYoy") or m.get("epsGrowth5Y") or m.get("epsGrowth3Y")
    rev_growth = m.get("revenueGrowthTTMYoy") or m.get("revenueGrowth5Y") or m.get("revenueGrowth3Y")

    st.markdown("**Growth**")
    g1, g2, g3 = st.columns(3)
    with g1:
        if eps_growth is not None:
            st.metric("EPS Growth (approx)", f"{eps_growth:.1f}%")
        else:
            st.metric("EPS Growth", "N/A (free tier)")
    with g2:
        if rev_growth is not None:
            st.metric("Revenue Growth (approx)", f"{rev_growth:.1f}%")
        else:
            st.metric("Revenue Growth", "N/A (free tier)")
    with g3:
        # Simple quality check
        note = "Limited growth data"
        if eps_growth is not None and rev_growth is not None:
            if eps_growth > 5 and rev_growth > 5:
                note = "Growth supports valuation"
            elif eps_growth < 0 or rev_growth < 0:
                note = "Possible value trap — check growth"
            else:
                note = "Mixed growth — review further"
        st.metric("Quality check", note)

    tab1, tab2 = st.tabs(["Quarterly", "Annual"])

    with tab1:
        if res["quarterly_df"].empty:
            st.info("Limited or no quarterly history.")
        else:
            st.write(f"**{len(res['quarterly_df'])} quarterly periods**")
            st.dataframe(
                res["quarterly_df"],
                width="stretch",
                hide_index=True,
                column_config={
                    "Period": st.column_config.TextColumn(width="small"),
                    "P/S": st.column_config.NumberColumn(format="%.2f", width="small"),
                    "P/E": st.column_config.NumberColumn(format="%.2f", width="small"),
                    "P/CF": st.column_config.NumberColumn(format="%.2f", width="small"),
                    "P/B": st.column_config.NumberColumn(format="%.2f", width="small"),
                }
            )

    with tab2:
        if res["annual_df"].empty:
            st.info("Limited or no annual history.")
        else:
            st.write(f"**{len(res['annual_df'])} annual periods**")
            st.dataframe(
                res["annual_df"],
                width="stretch",
                hide_index=True,
                column_config={
                    "Period": st.column_config.TextColumn(width="small"),
                    "P/S": st.column_config.NumberColumn(format="%.2f", width="small"),
                    "P/E": st.column_config.NumberColumn(format="%.2f", width="small"),
                    "P/CF": st.column_config.NumberColumn(format="%.2f", width="small"),
                    "P/B": st.column_config.NumberColumn(format="%.2f", width="small"),
                }
            )

    # Averages and current vs history (prefer annual if available)
    use_df = res["annual_df"] if len(res["annual_df"]) >= 3 else res["quarterly_df"]
    n = len(use_df)
    label = "Annual" if (use_df is res["annual_df"] and not res["annual_df"].empty) else "Quarterly"

    if n > 0:
        ps_avg = use_df["P/S"].mean(skipna=True) if "P/S" in use_df.columns else np.nan
        pe_num = pd.to_numeric(use_df["P/E"], errors="coerce") if "P/E" in use_df.columns else pd.Series(dtype=float)
        pe_avg = pe_num[pe_num > 0].mean() if not show_negative_pe else pe_num.mean(skipna=True)
        pcf_avg = use_df["P/CF"].mean(skipna=True) if "P/CF" in use_df.columns else np.nan

        st.markdown(f"**Average ({label} – {n} periods)**")
        a1, a2, a3 = st.columns(3)
        a1.metric("Avg P/S", f"{ps_avg:.2f}" if not pd.isna(ps_avg) else "—")
        a2.metric("Avg P/E", f"{pe_avg:.2f}" if not pd.isna(pe_avg) else "N/A")
        a3.metric("Avg P/CF", f"{pcf_avg:.2f}" if not pd.isna(pcf_avg) else "—")

        def pct(curr, avg):
            if curr is None or pd.isna(curr) or avg is None or pd.isna(avg) or avg == 0:
                return None
            return (curr - avg) / abs(avg) * 100

        ps_pct = pct(res.get("P/S"), ps_avg)
        pe_pct = pct(res.get("P/E") if res.get("P/E") and (res.get("P/E") > 0 or show_negative_pe) else None, pe_avg)
        pcf_pct = pct(res.get("P/OCF"), pcf_avg)

        st.markdown("**Current vs History**")
        v1, v2, v3 = st.columns(3)
        with v1:
            if ps_pct is not None:
                st.metric("P/S vs avg", f"{res.get('P/S'):.2f}", delta=f"{ps_pct:+.1f}%",
                          delta_color="inverse" if ps_pct > 0 else "normal")
            else:
                st.write("P/S: —")
        with v2:
            if pe_pct is not None:
                st.metric("P/E vs avg", f"{res.get('P/E'):.2f}", delta=f"{pe_pct:+.1f}%",
                          delta_color="inverse" if pe_pct > 0 else "normal")
            else:
                st.write("P/E: N/A")
        with v3:
            if pcf_pct is not None:
                st.metric("P/CF vs avg", f"{res.get('P/OCF'):.2f}", delta=f"{pcf_pct:+.1f}%",
                          delta_color="inverse" if pcf_pct > 0 else "normal")
            else:
                st.write("P/CF: —")

        # Simple charts
        st.markdown("---")
        st.markdown(f"**{label} Ratio Trends**")
        chart_cols = [c for c in ["P/S", "P/E", "P/CF"] if c in use_df.columns]
        if chart_cols and not use_df.empty:
            chart_df = use_df.set_index("Period")[chart_cols].dropna(how="all")
            if not chart_df.empty:
                col1, col2, col3 = st.columns(3)
                if "P/S" in chart_df.columns:
                    with col1:
                        st.caption("P/S")
                        st.line_chart(chart_df[["P/S"]], height=250)
                if "P/E" in chart_df.columns:
                    with col2:
                        st.caption("P/E")
                        st.line_chart(chart_df[["P/E"]], height=250)
                if "P/CF" in chart_df.columns:
                    with col3:
                        st.caption("P/CF")
                        st.line_chart(chart_df[["P/CF"]], height=250)

st.markdown("---")
st.caption("Data from Finnhub · Free tier · Approximate · Educational use only · Not financial advice.")
