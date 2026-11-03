#!/usr/bin/env python3
"""
Stock Valuation Ratios App
Uses Finnhub free API (supports all tickers, 60 calls/min).
"""

import warnings
warnings.filterwarnings("ignore")

import streamlit as st
import pandas as pd
import numpy as np
import time
import re
import requests

st.set_page_config(page_title="Stock Valuation Ratios", page_icon="📊", layout="wide")

st.title("📊 Stock Valuation Ratios")
st.caption("P/S · P/E · P/OCF · Powered by Finnhub · All tickers · Current · History")

with st.sidebar:
    st.header("Settings")
    api_key = st.secrets.get("FINNHUB_API_KEY", "")
    if not api_key:
        api_key = st.text_input(
            "Finnhub API Key",
            type="password",
            help="Get a free key at finnhub.io (60 calls/min). For shared use, add it as a Streamlit secret named FINNHUB_API_KEY."
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
        "ticker": ticker,
        "errors": [e for e in [err_q, err_m] if e],
    }, None


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

        current = {
            "Ticker": ticker,
            "Name": profile.get("name") or ticker,
            "Price": quote.get("c"),
            "P/S": metrics.get("psTTM") or metrics.get("psAnnual"),
            "P/E": metrics.get("peBasicExclExtraTTM") or metrics.get("peTTM") or metrics.get("peAnnual"),
            "P/OCF": metrics.get("pcfShareTTM") or metrics.get("priceToOperatingCashFlowTTM"),
            "Market Cap": profile.get("marketCapitalization"),
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

    # Show a selection of useful metrics from Finnhub
    st.markdown("**Key Metrics**")
    m = res["metrics"]
    metrics_to_show = {
        "P/E (TTM)": m.get("peBasicExclExtraTTM"),
        "P/S (TTM)": m.get("psTTM"),
        "P/B": m.get("pbQuarterly") or m.get("pbAnnual"),
        "ROE (TTM)": m.get("roeTTM"),
        "ROA (TTM)": m.get("roaTTM"),
        "Debt/Equity": m.get("totalDebt/totalEquityQuarterly"),
        "Current Ratio": m.get("currentRatioQuarterly"),
        "Gross Margin (TTM)": m.get("grossMarginTTM"),
        "Operating Margin (TTM)": m.get("operatingMarginTTM"),
        "52W High": m.get("52WeekHigh"),
        "52W Low": m.get("52WeekLow"),
    }

    cols = st.columns(4)
    for i, (label, value) in enumerate(metrics_to_show.items()):
        with cols[i % 4]:
            if value is not None:
                if isinstance(value, float):
                    st.metric(label, f"{value:.2f}")
                else:
                    st.metric(label, str(value))
            else:
                st.metric(label, "—")

st.markdown("---")
st.caption("Data from Finnhub · Free tier · Approximate · Educational use only · Not financial advice.")
