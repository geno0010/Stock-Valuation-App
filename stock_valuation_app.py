#!/usr/bin/env python3
"""
Stock Valuation Ratios App
Current + historical P/S, P/E, P/OCF (and P/FCF when available)
Uses Yahoo Finance (quarterly + annual)

pip install streamlit yfinance pandas numpy
python -m streamlit run stock_valuation_app.py
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time

st.set_page_config(page_title="Stock Valuation Ratios", page_icon="📊", layout="wide")

st.title("📊 Stock Valuation Ratios")
st.caption("P/S · P/E · P/OCF (Price to Operating Cash Flow) · Current · History · Averages · % Undervalued/Overvalued")

with st.sidebar:
    st.header("Settings")
    ticker_input = st.text_input("Ticker Symbol", value="NTRA", max_chars=10).strip().upper()
    use_fcf = st.checkbox("Prefer Free Cash Flow (P/FCF) when available", value=False)
    show_negative_pe = st.checkbox("Show negative P/E values", value=True)
    st.markdown("---")
    st.markdown("""
**Notes**
- Data from Yahoo Finance (free)
- Quarterly data often limited to last 4–6 periods
- Annual data usually goes back further
- P/OCF = Price / Operating Cash Flow
- P/FCF = Price / Free Cash Flow (when available)
- % vs history = (Current − Average) / |Average|
""")


@st.cache_data(ttl=1800, show_spinner=False)
def load_data(ticker: str):
    t = yf.Ticker(ticker)
    time.sleep(0.6)
    info = t.info or {}
    time.sleep(0.4)
    q_inc = t.quarterly_income_stmt
    time.sleep(0.3)
    a_inc = t.income_stmt
    time.sleep(0.3)
    q_cf = t.quarterly_cashflow
    time.sleep(0.3)
    a_cf = t.cashflow
    time.sleep(0.3)
    hist = t.history(period="5y", auto_adjust=True)
    return info, q_inc, a_inc, q_cf, a_cf, hist


def safe_div(a, b):
    if b is None or b == 0 or (isinstance(b, float) and np.isnan(b)):
        return np.nan
    return a / b


def get_price_near(hist, date):
    if hist is None or hist.empty:
        return np.nan
    if hist.index.tz is not None:
        hist = hist.copy()
        hist.index = hist.index.tz_localize(None)
    date = pd.Timestamp(date).tz_localize(None) if getattr(date, "tzinfo", None) else pd.Timestamp(date)
    available = hist[hist.index <= date]
    if available.empty:
        return np.nan
    return float(available["Close"].iloc[-1])


def find_col(df, candidates):
    if df is None or df.empty:
        return None
    for c in candidates:
        if c in df.columns:
            return c
    return None


def compute_ratios(income, cashflow, hist, shares, is_quarterly=True, use_fcf=False, show_neg_pe=True):
    if income is None or income.empty:
        return pd.DataFrame()

    income = income.T.sort_index()
    cf = cashflow.T.sort_index() if cashflow is not None and not cashflow.empty else pd.DataFrame()

    rev_col = find_col(income, ["Total Revenue", "Operating Revenue", "Revenue"])
    ni_col = find_col(income, ["Net Income", "Net Income Common Stockholders",
                               "Net Income From Continuing Operation Net Minority Interest"])
    if rev_col is None:
        return pd.DataFrame()

    ocf_col = find_col(cf, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities",
                            "Total Cash From Operating Activities"])
    fcf_col = find_col(cf, ["Free Cash Flow"])
    if fcf_col is None and ocf_col and "Capital Expenditure" in cf.columns:
        cf["Free Cash Flow"] = cf[ocf_col] + cf["Capital Expenditure"]  # Capex usually negative
        fcf_col = "Free Cash Flow"

    rows = []
    dates = list(income.index)

    for i, q_date in enumerate(dates):
        if is_quarterly:
            if i < 3:
                continue
            ttm_rev = income[rev_col].iloc[i-3:i+1].sum()
            ttm_ni = income[ni_col].iloc[i-3:i+1].sum() if ni_col else np.nan
            ttm_cf = np.nan
            if use_fcf and fcf_col and fcf_col in cf.columns:
                try:
                    ttm_cf = cf[fcf_col].reindex(income.index).iloc[i-3:i+1].sum()
                except Exception:
                    ttm_cf = np.nan
            elif ocf_col and ocf_col in cf.columns:
                try:
                    ttm_cf = cf[ocf_col].reindex(income.index).iloc[i-3:i+1].sum()
                except Exception:
                    ttm_cf = np.nan
        else:
            ttm_rev = income[rev_col].iloc[i]
            ttm_ni = income[ni_col].iloc[i] if ni_col else np.nan
            ttm_cf = np.nan
            if use_fcf and fcf_col and fcf_col in cf.columns:
                try:
                    ttm_cf = cf[fcf_col].reindex(income.index).iloc[i]
                except Exception:
                    ttm_cf = np.nan
            elif ocf_col and ocf_col in cf.columns:
                try:
                    ttm_cf = cf[ocf_col].reindex(income.index).iloc[i]
                except Exception:
                    ttm_cf = np.nan

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

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.iloc[::-1].reset_index(drop=True)
    return df


# -------------------- Main --------------------
if not ticker_input:
    st.warning("Enter a ticker.")
    st.stop()

with st.spinner(f"Fetching {ticker_input}…"):
    try:
        info, q_inc, a_inc, q_cf, a_cf, hist = load_data(ticker_input)
    except Exception as e:
        st.error(f"Could not fetch data: {e}")
        st.info("Yahoo sometimes rate-limits. Wait 1–2 minutes and try again.")
        st.stop()

current = {
    "Price": info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose"),
    "P/S": info.get("priceToSalesTrailing12Months"),
    "P/E": info.get("trailingPE"),
    "P/OCF": info.get("priceToOperatingCashflow") or info.get("priceToCashflow"),
    "Market Cap": info.get("marketCap"),
    "Name": info.get("longName") or info.get("shortName") or ticker_input,
    "Shares": info.get("sharesOutstanding"),
}

st.subheader(f"{current['Name']} ({ticker_input})")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Price", f"${current['Price']:,.2f}" if current.get("Price") else "—")
c2.metric("P/S", f"{current['P/S']:.2f}" if current.get("P/S") else "—")
pe = current.get("P/E")
c3.metric("P/E", f"{pe:.2f}" if pe and (pe > 0 or show_negative_pe) else ("N/A (loss)" if pe is not None else "—"))
c4.metric("P/OCF", f"{current['P/OCF']:.2f}" if current.get("P/OCF") else "—")
c5.metric("Market Cap", f"${current['Market Cap']/1e9:.1f}B" if current.get("Market Cap") else "—")

st.markdown("---")

q_df = compute_ratios(q_inc, q_cf, hist, current.get("Shares"),
                      is_quarterly=True, use_fcf=use_fcf, show_neg_pe=show_negative_pe)
a_df = compute_ratios(a_inc, a_cf, hist, current.get("Shares"),
                      is_quarterly=False, use_fcf=use_fcf, show_neg_pe=show_negative_pe)

cf_label = "P/FCF" if use_fcf else "P/OCF"

tab1, tab2 = st.tabs(["Quarterly (recent)", "Annual (longer history)"])

with tab1:
    if q_df.empty:
        st.info("Limited quarterly data from Yahoo (common). Check the Annual tab.")
    else:
        st.write(f"**{len(q_df)} complete TTM quarterly periods**")
        st.dataframe(q_df, use_container_width=True, hide_index=True)

with tab2:
    if a_df.empty:
        st.info("No annual data available.")
    else:
        st.write(f"**{len(a_df)} annual periods**")
        st.dataframe(a_df, use_container_width=True, hide_index=True)

# Choose best series for averages
use_df = a_df if len(a_df) >= 3 else q_df
n = len(use_df)
label = "Annual" if (use_df is a_df and not a_df.empty) else "Quarterly"

if n > 0:
    ps_avg = use_df["P/S"].mean(skipna=True)
    pe_num = pd.to_numeric(use_df["P/E"], errors="coerce")
    pe_avg = pe_num[pe_num > 0].mean() if not show_negative_pe else pe_num.mean(skipna=True)
    pcf_avg = use_df["P/CF"].mean(skipna=True)

    st.subheader(f"Average ({label} – {n} periods)")
    a1, a2, a3 = st.columns(3)
    a1.metric("Avg P/S", f"{ps_avg:.2f}" if not pd.isna(ps_avg) else "—")
    a2.metric("Avg P/E", f"{pe_avg:.2f}" if not pd.isna(pe_avg) else "N/A")
    a3.metric(f"Avg {cf_label}", f"{pcf_avg:.2f}" if not pd.isna(pcf_avg) else "—")

    st.subheader("Current vs History — % Undervalued / Overvalued")

    def pct(curr, avg):
        if curr is None or pd.isna(curr) or avg is None or pd.isna(avg) or avg == 0:
            return None
        return (curr - avg) / abs(avg) * 100

    ps_pct = pct(current.get("P/S"), ps_avg)
    pe_pct = pct(current.get("P/E") if current.get("P/E") and (current.get("P/E") > 0 or show_negative_pe) else None, pe_avg)
    # For P/CF use current P/OCF from info, or most recent computed
    curr_pcf = current.get("P/OCF")
    if (curr_pcf is None or pd.isna(curr_pcf)) and "P/CF" in use_df.columns and not use_df["P/CF"].isna().all():
        curr_pcf = use_df["P/CF"].dropna().iloc[0]
    pcf_pct = pct(curr_pcf, pcf_avg)

    v1, v2, v3 = st.columns(3)
    with v1:
        st.markdown("**P/S**")
        if ps_pct is not None:
            st.metric("vs history", f"{current.get('P/S'):.2f}", delta=f"{ps_pct:+.1f}%",
                      delta_color="inverse" if ps_pct > 0 else "normal")
            st.caption(f"{'Overvalued' if ps_pct > 5 else 'Undervalued' if ps_pct < -5 else 'In-line'} vs {label.lower()} avg")
        else:
            st.write("—")
    with v2:
        st.markdown("**P/E**")
        if pe_pct is not None:
            st.metric("vs history", f"{current.get('P/E'):.2f}", delta=f"{pe_pct:+.1f}%",
                      delta_color="inverse" if pe_pct > 0 else "normal")
            st.caption(f"{'Overvalued' if pe_pct > 5 else 'Undervalued' if pe_pct < -5 else 'In-line'} vs {label.lower()} avg")
        else:
            st.write("N/A (loss-making)")
    with v3:
        st.markdown(f"**{cf_label}**")
        if pcf_pct is not None:
            st.metric("vs history", f"{curr_pcf:.2f}", delta=f"{pcf_pct:+.1f}%",
                      delta_color="inverse" if pcf_pct > 0 else "normal")
            st.caption(f"{'Overvalued' if pcf_pct > 5 else 'Undervalued' if pcf_pct < -5 else 'In-line'} vs {label.lower()} avg")
        else:
            st.write(f"{curr_pcf:.2f}" if curr_pcf else "—")
            st.caption("Limited history for cash-flow ratio")

    # Charts
    col_a, col_b = st.columns(2)
    with col_a:
        chart_ps = use_df.set_index("Period End")[["P/S"]].dropna()
        if not chart_ps.empty:
            st.subheader(f"P/S Trend ({label})")
            st.line_chart(chart_ps)
    with col_b:
        chart_pcf = use_df.set_index("Period End")[["P/CF"]].dropna()
        if not chart_pcf.empty:
            st.subheader(f"{cf_label} Trend ({label})")
            st.line_chart(chart_pcf)

st.markdown("---")
st.caption("Data from Yahoo Finance · Approximate · Educational use only · Not financial advice")
