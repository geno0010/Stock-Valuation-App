#!/usr/bin/env python3
"""
Stock Valuation Ratios App
Uses Alpha Vantage free API (supports all tickers, 25 calls/day).
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
st.caption("P/S · P/E · P/OCF · Powered by Alpha Vantage · All tickers · History · Averages · Charts")

with st.sidebar:
    st.header("Settings")
    api_key = st.secrets.get("ALPHAVANTAGE_API_KEY", "")
    if not api_key:
        api_key = st.text_input(
            "Alpha Vantage API Key",
            type="password",
            help="Get a free key at alphavantage.co (25 calls/day). For shared use, add it as a Streamlit secret named ALPHAVANTAGE_API_KEY."
        )
    else:
        st.success("Using embedded Alpha Vantage key")

    ticker_input = st.text_input(
        "Ticker(s)",
        value="AAPL",
        help="One or more tickers (comma or space separated). Press Enter to run."
    )
    use_fcf = st.checkbox("Prefer Free Cash Flow (P/FCF)", value=False)
    show_negative_pe = st.checkbox("Show negative P/E values", value=True)
    st.markdown("---")
    st.markdown("[Get free Alpha Vantage key](https://www.alphavantage.co/support/#api-key)")
    st.caption("Free tier: 25 requests/day. Each ticker uses 3–4 requests.")


def parse_tickers(raw: str) -> list[str]:
    if not raw:
        return []
    parts = re.split(r"[,\s\n]+", raw.strip().upper())
    return [p for p in parts if p and re.match(r"^[A-Z0-9.\-^]+$", p)]


def safe_div(a, b):
    try:
        if b is None or b == 0 or pd.isna(b):
            return np.nan
        return a / b
    except Exception:
        return np.nan


def av_get(function: str, params: dict, api_key: str):
    params = params.copy()
    params["function"] = function
    params["apikey"] = api_key
    try:
        r = requests.get("https://www.alphavantage.co/query", params=params, timeout=15)
        data = r.json()
        if "Note" in data or "Information" in data:
            return None, data.get("Note") or data.get("Information")
        if "Error Message" in data:
            return None, data["Error Message"]
        return data, None
    except Exception as e:
        return None, str(e)


@st.cache_data(ttl=3600, show_spinner=False)
def load_ticker(ticker: str, api_key: str):
    overview, err_o = av_get("OVERVIEW", {"symbol": ticker}, api_key)
    if err_o:
        return None, err_o

    income, err_i = av_get("INCOME_STATEMENT", {"symbol": ticker}, api_key)
    cashflow, err_c = av_get("CASH_FLOW", {"symbol": ticker}, api_key)
    quote, err_q = av_get("GLOBAL_QUOTE", {"symbol": ticker}, api_key)

    return {
        "overview": overview or {},
        "income": income or {},
        "cashflow": cashflow or {},
        "quote": quote or {},
        "ticker": ticker,
        "errors": [e for e in [err_i, err_c, err_q] if e],
    }, None


def build_table(income_data, cashflow_data, is_quarterly=False, use_fcf=False, show_neg_pe=True):
    key = "quarterlyReports" if is_quarterly else "annualReports"
    statements = income_data.get(key, [])
    cashflows = cashflow_data.get(key, [])

    if not statements:
        return pd.DataFrame()

    cash_map = {c.get("fiscalDateEnding"): c for c in cashflows}

    rows = []
    for stmt in statements[:10]:  # limit display
        date = stmt.get("fiscalDateEnding")
        revenue = float(stmt.get("totalRevenue") or 0)
        net_income = float(stmt.get("netIncome") or 0)

        cf = cash_map.get(date, {})
        if use_fcf:
            cf_val = float(cf.get("operatingCashflow") or 0) - float(cf.get("capitalExpenditures") or 0)
        else:
            cf_val = float(cf.get("operatingCashflow") or 0)

        # Alpha Vantage statements don't include price/ratios directly; we approximate from reported numbers
        # For display we show the statement values; ratios will be calculated if we have shares
        shares = float(stmt.get("weightedAverageShsOut") or 0)

        rows.append({
            "Period End": date,
            "Revenue ($M)": round(revenue / 1e6, 1),
            "Net Income ($M)": round(net_income / 1e6, 1),
            "CF ($M)": round(cf_val / 1e6, 1) if cf_val else np.nan,
            "Shares (M)": round(shares / 1e6, 1) if shares else np.nan,
        })

    df = pd.DataFrame(rows)
    return df


# -------------------- Main --------------------
if not api_key:
    st.info("Enter your free Alpha Vantage API key in the sidebar to begin.")
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
        overview = data["overview"]
        quote_data = data["quote"].get("Global Quote", {})

        q_df = build_table(data["income"], data["cashflow"], is_quarterly=True, use_fcf=use_fcf, show_neg_pe=show_negative_pe)
        a_df = build_table(data["income"], data["cashflow"], is_quarterly=False, use_fcf=use_fcf, show_neg_pe=show_negative_pe)

        current = {
            "Ticker": ticker,
            "Name": overview.get("Name") or ticker,
            "Price": float(quote_data.get("05. price") or overview.get("Price") or 0) or None,
            "P/S": float(overview.get("PriceToSalesRatioTTM") or 0) or None,
            "P/E": float(overview.get("PERatio") or overview.get("TrailingPE") or 0) or None,
            "P/OCF": float(overview.get("PriceToOperatingCashFlowRatioTTM") or 0) or None,
            "Market Cap": float(overview.get("MarketCapitalization") or 0) or None,
            "q_df": q_df,
            "a_df": a_df,
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

cf_label = "P/FCF" if use_fcf else "P/OCF"

for res in results:
    st.markdown("---")
    st.subheader(f"{res['Name']} ({res['Ticker']})")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Price", f"${res['Price']:,.2f}" if res.get("Price") else "—")
    c2.metric("P/S", f"{res['P/S']:.2f}" if res.get("P/S") else "—")
    pe = res.get("P/E")
    c3.metric("P/E", f"{pe:.2f}" if pe and (pe > 0 or show_negative_pe) else ("N/A (loss)" if pe is not None else "—"))
    c4.metric(cf_label, f"{res['P/OCF']:.2f}" if res.get("P/OCF") else "—")
    c5.metric("Market Cap", f"${res['Market Cap']/1e9:.1f}B" if res.get("Market Cap") else "—")

    tab1, tab2 = st.tabs(["Quarterly", "Annual"])

    with tab1:
        if res["q_df"].empty:
            st.info("Limited or no quarterly data.")
        else:
            st.write(f"**{len(res['q_df'])} quarterly periods**")
            st.dataframe(res["q_df"], width="stretch", hide_index=True)

    with tab2:
        if res["a_df"].empty:
            st.info("No annual data.")
        else:
            st.write(f"**{len(res['a_df'])} annual periods**")
            st.dataframe(res["a_df"], width="stretch", hide_index=True)

    # Note: Alpha Vantage free statements don't include pre-calculated historical ratios.
    # Current ratios come from OVERVIEW. Historical tables show the raw financials.
    st.caption("Historical tables show reported financials. Current ratios come from the company overview.")

st.markdown("---")
st.caption("Data from Alpha Vantage · Free tier · Approximate · Educational use only · Not financial advice.")
