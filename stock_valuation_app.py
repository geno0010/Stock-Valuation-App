#!/usr/bin/env python3
"""
Stock Valuation Ratios App
Robust version using yfinance with better error handling for 401/crumb issues.
"""

import warnings
warnings.filterwarnings("ignore")

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time
import re

st.set_page_config(page_title="Stock Valuation Ratios", page_icon="📊", layout="wide")

st.title("📊 Stock Valuation Ratios")
st.caption("P/S · P/E · P/OCF · Multiple tickers · History · Averages · % vs History")

with st.sidebar:
    st.header("Settings")
    ticker_input = st.text_area(
        "Ticker(s)",
        value="AAPL",
        height=80,
        help="One or more tickers (comma, space, or newline). Example: AAPL, MSFT, NTRA"
    )
    use_fcf = st.checkbox("Prefer Free Cash Flow (P/FCF)", value=False)
    show_negative_pe = st.checkbox("Show negative P/E values", value=True)
    st.markdown("---")
    st.markdown("""
**If you see 401 / Invalid Crumb errors:**
1. Wait 1–2 minutes
2. Refresh the page
3. Or reboot the app from the Streamlit Cloud dashboard
""")


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


def get_price_near(hist, date):
    if hist is None or hist.empty:
        return np.nan
    try:
        h = hist.copy()
        if h.index.tz is not None:
            h.index = h.index.tz_localize(None)
        date = pd.Timestamp(date).tz_localize(None) if getattr(date, "tzinfo", None) else pd.Timestamp(date)
        available = h[h.index <= date]
        if available.empty:
            return np.nan
        return float(available["Close"].iloc[-1])
    except Exception:
        return np.nan


def find_col(df, candidates):
    if df is None or df.empty:
        return None
    for c in candidates:
        if c in df.columns:
            return c
    return None


def load_ticker(ticker: str):
    try:
        t = yf.Ticker(ticker)
        time.sleep(0.5)
        info = t.info or {}
        if not info:
            return None, "Empty response from Yahoo"
        q_inc = t.quarterly_income_stmt
        a_inc = t.income_stmt
        q_cf = t.quarterly_cashflow
        a_cf = t.cashflow
        hist = t.history(period="5y", auto_adjust=True)
        return {
            "info": info,
            "q_inc": q_inc,
            "a_inc": a_inc,
            "q_cf": q_cf,
            "a_cf": a_cf,
            "hist": hist
        }, None
    except Exception as e:
        return None, str(e)


def compute_ratios(income, cashflow, hist, shares, is_quarterly=True, use_fcf=False, show_neg_pe=True):
    if income is None or income.empty:
        return pd.DataFrame()

    try:
        income = income.T.sort_index()
    except Exception:
        return pd.DataFrame()

    cf = pd.DataFrame()
    if cashflow is not None and not cashflow.empty:
        try:
            cf = cashflow.T.sort_index()
        except Exception:
            cf = pd.DataFrame()

    rev_col = find_col(income, ["Total Revenue", "Operating Revenue", "Revenue"])
    ni_col = find_col(income, ["Net Income", "Net Income Common Stockholders",
                               "Net Income From Continuing Operation Net Minority Interest"])
    if rev_col is None:
        return pd.DataFrame()

    ocf_col = find_col(cf, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities",
                            "Total Cash From Operating Activities"])
    fcf_col = find_col(cf, ["Free Cash Flow"])
    if fcf_col is None and ocf_col and "Capital Expenditure" in cf.columns:
        try:
            cf = cf.copy()
            cf["Free Cash Flow"] = cf[ocf_col] + cf["Capital Expenditure"]
            fcf_col = "Free Cash Flow"
        except Exception:
            pass

    rows = []
    dates = list(income.index)

    for i, q_date in enumerate(dates):
        try:
            if is_quarterly:
                if i < 3:
                    continue
                ttm_rev = income[rev_col].iloc[i-3:i+1].sum()
                ttm_ni = income[ni_col].iloc[i-3:i+1].sum() if ni_col else np.nan
                ttm_cf = np.nan
                if use_fcf and fcf_col and fcf_col in cf.columns:
                    ttm_cf = cf[fcf_col].reindex(income.index).iloc[i-3:i+1].sum()
                elif ocf_col and ocf_col in cf.columns:
                    ttm_cf = cf[ocf_col].reindex(income.index).iloc[i-3:i+1].sum()
            else:
                ttm_rev = income[rev_col].iloc[i]
                ttm_ni = income[ni_col].iloc[i] if ni_col else np.nan
                ttm_cf = np.nan
                if use_fcf and fcf_col and fcf_col in cf.columns:
                    ttm_cf = cf[fcf_col].reindex(income.index).iloc[i]
                elif ocf_col and ocf_col in cf.columns:
                    ttm_cf = cf[ocf_col].reindex(income.index).iloc[i]

            price = get_price_near(hist, q_date)
            if pd.isna(price) or price <= 0 or shares is None or shares <= 0:
                continue

            mkt_cap = price * shares
            ps = safe_div(mkt_cap, ttm_rev)
            pe = safe_div(price, ttm_ni / shares) if ttm_ni is not None and not pd.isna(ttm_ni) else np.nan
            pcf = safe_div(mkt_cap, ttm_cf) if not pd.isna(ttm_cf) else np.nan

            pe_disp = pe
            if not pd.isna(pe) and pe <= 0 and not show_neg_pe:
                pe_disp = np.nan

            rows.append({
                "Period End": q_date.strftime("%Y-%m-%d") if hasattr(q_date, "strftime") else str(q_date)[:10],
                "Price": round(price, 2),
                "Revenue ($M)": round(ttm_rev / 1e6, 1) if not pd.isna(ttm_rev) else np.nan,
                "P/S": round(ps, 2) if not pd.isna(ps) else np.nan,
                "Net Income ($M)": round(ttm_ni / 1e6, 1) if not pd.isna(ttm_ni) else np.nan,
                "P/E": round(pe_disp, 2) if not pd.isna(pe_disp) else np.nan,
                "CF ($M)": round(ttm_cf / 1e6, 1) if not pd.isna(ttm_cf) else np.nan,
                "P/CF": round(pcf, 2) if not pd.isna(pcf) else np.nan,
            })
        except Exception:
            continue

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.iloc[::-1].reset_index(drop=True)
    return df


# -------------------- Main --------------------
tickers = parse_tickers(ticker_input)
if not tickers:
    st.warning("Enter at least one valid ticker.")
    st.stop()

st.write(f"**Analyzing:** {', '.join(tickers)}")

results = []
errors = []

progress = st.progress(0)
for i, ticker in enumerate(tickers):
    data, err = load_ticker(ticker)
    if err or data is None:
        errors.append(f"{ticker}: {err or 'No data'}")
    else:
        info = data["info"]
        shares = info.get("sharesOutstanding")
        q_df = compute_ratios(data["q_inc"], data["q_cf"], data["hist"], shares,
                              is_quarterly=True, use_fcf=use_fcf, show_neg_pe=show_negative_pe)
        a_df = compute_ratios(data["a_inc"], data["a_cf"], data["hist"], shares,
                              is_quarterly=False, use_fcf=use_fcf, show_neg_pe=show_negative_pe)

        current = {
            "Ticker": ticker,
            "Name": info.get("longName") or info.get("shortName") or ticker,
            "Price": info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose"),
            "P/S": info.get("priceToSalesTrailing12Months"),
            "P/E": info.get("trailingPE"),
            "P/OCF": info.get("priceToOperatingCashflow") or info.get("priceToCashflow"),
            "Market Cap": info.get("marketCap"),
            "q_df": q_df,
            "a_df": a_df,
        }
        results.append(current)
    progress.progress((i + 1) / len(tickers))
    time.sleep(0.6)

progress.empty()

if errors:
    with st.expander("⚠️ Data issues (Yahoo 401 / crumb / rate limit)"):
        for e in errors:
            st.write(e)
        st.caption("These are usually temporary. Wait a minute and refresh the page, or reboot the app from Streamlit Cloud.")

if not results:
    st.error("No data could be loaded. Yahoo Finance is currently blocking requests. Wait 1–2 minutes and refresh, or reboot the app.")
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
            st.dataframe(res["q_df"], use_container_width=True, hide_index=True)

    with tab2:
        if res["a_df"].empty:
            st.info("No annual data.")
        else:
            st.write(f"**{len(res['a_df'])} annual periods**")
            st.dataframe(res["a_df"], use_container_width=True, hide_index=True)

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
st.caption("Data from Yahoo Finance · Approximate · Educational use only · Not financial advice.")
