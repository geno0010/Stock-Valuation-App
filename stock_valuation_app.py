#!/usr/bin/env python3
"""
Stock Valuation Ratios App
Uses Financial Modeling Prep free API.
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
st.caption("P/S · P/E · P/OCF · Powered by Financial Modeling Prep · History · Averages · Charts")

with st.sidebar:
    st.header("Settings")
    api_key = st.secrets.get("FMP_API_KEY", "")
    if not api_key:
        api_key = st.text_input(
            "FMP API Key",
            type="password",
            help="Get a free key at financialmodelingprep.com (250 calls/day). For shared use, add it as a Streamlit secret named FMP_API_KEY."
        )
    else:
        st.success("Using embedded FMP API key")

    ticker_input = st.text_input(
        "Ticker(s)",
        value="AAPL",
        help="One or more tickers (comma or space separated). Press Enter to run."
    )
    use_fcf = st.checkbox("Prefer Free Cash Flow (P/FCF)", value=False)
    show_negative_pe = st.checkbox("Show negative P/E values", value=True)
    st.markdown("---")
    st.markdown("[Get free FMP API key](https://site.financialmodelingprep.com/developer/docs)")


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


def fmp_get(endpoint: str, params: dict, api_key: str):
    params = params.copy()
    params["apikey"] = api_key
    try:
        r = requests.get(f"https://financialmodelingprep.com/stable/{endpoint}", params=params, timeout=15)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}: {r.text[:300]}"
        data = r.json()
        if isinstance(data, dict) and ("Error Message" in data or "error" in data):
            return None, str(data.get("Error Message") or data.get("error") or data)
        return data, None
    except Exception as e:
        return None, str(e)


def load_ticker(ticker: str, api_key: str):
    quote, err = fmp_get("quote", {"symbol": ticker}, api_key)
    if err or not quote or not isinstance(quote, list) or len(quote) == 0:
        return None, err or f"No quote data for {ticker}"

    quote = quote[0]

    income_q, err_q = fmp_get("income-statement", {"symbol": ticker, "period": "quarter", "limit": 5}, api_key)
    income_a, err_a = fmp_get("income-statement", {"symbol": ticker, "period": "annual", "limit": 5}, api_key)
    cash_q, err_cq = fmp_get("cash-flow-statement", {"symbol": ticker, "period": "quarter", "limit": 5}, api_key)
    cash_a, err_ca = fmp_get("cash-flow-statement", {"symbol": ticker, "period": "annual", "limit": 5}, api_key)
    ratios_q, err_rq = fmp_get("ratios", {"symbol": ticker, "period": "quarter", "limit": 5}, api_key)
    ratios_a, err_ra = fmp_get("ratios", {"symbol": ticker, "period": "annual", "limit": 5}, api_key)
    ratios_ttm, _ = fmp_get("ratios-ttm", {"symbol": ticker}, api_key)

    return {
        "quote": quote,
        "income_q": income_q if isinstance(income_q, list) else [],
        "income_a": income_a if isinstance(income_a, list) else [],
        "cash_q": cash_q if isinstance(cash_q, list) else [],
        "cash_a": cash_a if isinstance(cash_a, list) else [],
        "ratios_q": ratios_q if isinstance(ratios_q, list) else [],
        "ratios_a": ratios_a if isinstance(ratios_a, list) else [],
        "ratios_ttm": ratios_ttm[0] if isinstance(ratios_ttm, list) and ratios_ttm else {},
        "ticker": ticker,
        "errors": [e for e in [err_q, err_a, err_cq, err_ca, err_rq, err_ra] if e],
    }, None


def build_table(statements, cashflows, ratios, is_quarterly=False, use_fcf=False, show_neg_pe=True):
    if not ratios:
        return pd.DataFrame()

    ratios = sorted(ratios, key=lambda x: x.get("date", ""))
    stmt_map = {s.get("date"): s for s in (statements or [])}
    cash_map = {c.get("date"): c for c in (cashflows or [])}

    rows = []
    for r in ratios:
        date = r.get("date")
        stmt = stmt_map.get(date, {})
        cf = cash_map.get(date, {})

        revenue = stmt.get("revenue")
        net_income = stmt.get("netIncome")
        cf_val = cf.get("freeCashFlow") if use_fcf else cf.get("operatingCashFlow")

        ps = r.get("priceToSalesRatio")
        pe = r.get("priceToEarningsRatio")
        pcf = r.get("priceToFreeCashFlowRatio") if use_fcf else r.get("priceToOperatingCashFlowRatio")

        if not show_neg_pe and pe is not None and pe <= 0:
            pe = np.nan

        rows.append({
            "Period End": date,
            "Revenue ($M)": round((revenue or 0) / 1e6, 1) if revenue else np.nan,
            "P/S": round(ps, 2) if ps is not None else np.nan,
            "Net Income ($M)": round((net_income or 0) / 1e6, 1) if net_income else np.nan,
            "P/E": round(pe, 2) if pe is not None else np.nan,
            "CF ($M)": round((cf_val or 0) / 1e6, 1) if cf_val else np.nan,
            "P/CF": round(pcf, 2) if pcf is not None else np.nan,
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.iloc[::-1].reset_index(drop=True)
    return df


# -------------------- Main --------------------
if not api_key:
    st.info("Enter your free Financial Modeling Prep API key in the sidebar to begin.")
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
        q_df = build_table(data["income_q"], data["cash_q"], data["ratios_q"], is_quarterly=True, use_fcf=use_fcf, show_neg_pe=show_negative_pe)
        a_df = build_table(data["income_a"], data["cash_a"], data["ratios_a"], is_quarterly=False, use_fcf=use_fcf, show_neg_pe=show_negative_pe)

        quote = data["quote"]
        ratios = data["ratios_ttm"]

        current = {
            "Ticker": ticker,
            "Name": quote.get("name") or ticker,
            "Price": quote.get("price"),
            "P/S": ratios.get("priceToSalesRatioTTM") or quote.get("priceToSales"),
            "P/E": ratios.get("priceToEarningsRatioTTM") or quote.get("pe"),
            "P/OCF": ratios.get("priceToOperatingCashFlowRatioTTM") or ratios.get("priceToFreeCashFlowRatioTTM"),
            "Market Cap": quote.get("marketCap"),
            "q_df": q_df,
            "a_df": a_df,
        }
        results.append(current)
        if data.get("errors"):
            errors.extend([f"{ticker}: {e}" for e in data["errors"]])
    progress.progress((i + 1) / len(tickers))
    time.sleep(0.3)

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
            st.write(f"**{len(res['q_df'])} TTM periods**")
            st.dataframe(res["q_df"], width="stretch", hide_index=True)

    with tab2:
        if res["a_df"].empty:
            st.info("No annual data.")
        else:
            st.write(f"**{len(res['a_df'])} annual periods**")
            st.dataframe(res["a_df"], width="stretch", hide_index=True)

    use_df = res["a_df"] if len(res["a_df"]) >= 3 else res["q_df"]
    n = len(use_df)
    label = "Annual" if (use_df is res["a_df"] and not res["a_df"].empty) else "Quarterly"

    if n > 0:
        ps_avg = use_df["P/S"].mean(skipna=True)
        pe_num = pd.to_numeric(use_df["P/E"], errors="coerce")
        pe_avg = pe_num[pe_num > 0].mean() if not show_negative_pe else pe_num.mean(skipna=True)
        pcf_avg = use_df["P/CF"].mean(skipna=True)

        st.markdown(f"**Average ({label} – {n} periods)**")
        a1, a2, a3 = st.columns(3)
        a1.metric("Avg P/S", f"{ps_avg:.2f}" if not pd.isna(ps_avg) else "—")
        a2.metric("Avg P/E", f"{pe_avg:.2f}" if not pd.isna(pe_avg) else "N/A")
        a3.metric(f"Avg {cf_label}", f"{pcf_avg:.2f}" if not pd.isna(pcf_avg) else "—")

        def pct(curr, avg):
            if curr is None or pd.isna(curr) or avg is None or pd.isna(avg) or avg == 0:
                return None
            return (curr - avg) / abs(avg) * 100

        ps_pct = pct(res.get("P/S"), ps_avg)
        pe_pct = pct(res.get("P/E") if res.get("P/E") and (res.get("P/E") > 0 or show_negative_pe) else None, pe_avg)
        curr_pcf = res.get("P/OCF")
        if (curr_pcf is None or pd.isna(curr_pcf)) and "P/CF" in use_df.columns and not use_df["P/CF"].isna().all():
            curr_pcf = use_df["P/CF"].dropna().iloc[0]
        pcf_pct = pct(curr_pcf, pcf_avg)

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
                st.metric(f"{cf_label} vs avg", f"{curr_pcf:.2f}", delta=f"{pcf_pct:+.1f}%",
                          delta_color="inverse" if pcf_pct > 0 else "normal")
            else:
                st.write(f"{cf_label}: —")

        st.markdown("---")
        st.markdown(f"**{label} Ratio Trends**")

        chart_df = use_df.set_index("Period End")[["P/S", "P/E", "P/CF"]].copy()
        chart_df = chart_df.dropna(how="all")

        if not chart_df.empty:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.caption("P/S")
                st.line_chart(chart_df[["P/S"]], height=250)
            with col2:
                st.caption("P/E")
                st.line_chart(chart_df[["P/E"]], height=250)
            with col3:
                st.caption("P/CF")
                st.line_chart(chart_df[["P/CF"]], height=250)
        else:
            st.info("Not enough data for charts.")

st.markdown("---")
st.caption("Data from Financial Modeling Prep · Approximate · Educational use only · Not financial advice.")
