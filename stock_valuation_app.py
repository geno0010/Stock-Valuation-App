import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import time
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

st.set_page_config(page_title="Stock Valuation Ratios", layout="wide")

st.markdown("""
<style>
    .stMetric { font-size: 1.15rem; }
    .stMetric label { font-size: 0.95rem !important; }
    .stMetric [data-testid="stMetricValue"] { font-size: 1.8rem !important; }
    .stDataFrame { font-size: 1.05rem !important; }
    .stCaption { font-size: 0.95rem !important; }
</style>
""", unsafe_allow_html=True)

st.title("📊 Stock Valuation Ratios")
st.caption("P/S · P/E · P/OCF · Current · History · Averages · % Undervalued/Overvalued")

with st.sidebar:
    ticker = st.text_input("Ticker Symbol", value="AAPL").upper().strip()
    prefer_fcf = st.checkbox("Prefer Free Cash Flow (P/FCF) when available", value=True)
    show_negative_pe = st.checkbox("Show negative P/E values", value=False)
    st.markdown("---")
    st.caption("Data from Yahoo Finance · Approximate · Educational use only · Not financial advice")

def safe_call(func, *args, retries=3, **kwargs):
    for attempt in range(retries):
        try:
            result = func(*args, **kwargs)
            if result is not None:
                return result
        except Exception:
            if attempt == retries - 1:
                return None
            time.sleep(1.5)
    return None

@st.cache_data(ttl=1800, show_spinner=False)
def get_data(symbol):
    stock = yf.Ticker(symbol)
    hist = safe_call(stock.history, period="10y")
    info = safe_call(lambda: stock.info) or {}
    quarterly_fin = safe_call(lambda: stock.quarterly_financials)
    annual_fin = safe_call(lambda: stock.financials)
    quarterly_cf = safe_call(lambda: stock.quarterly_cashflow)
    annual_cf = safe_call(lambda: stock.cashflow)
    return hist, info, quarterly_fin, annual_fin, quarterly_cf, annual_cf

def latest_value(df, names):
    if df is None or df.empty:
        return None
    for name in names:
        if name in df.index:
            s = df.loc[name].dropna()
            if not s.empty:
                return float(s.iloc[0])
    return None

def build_history(fin_df, cf_df, hist, market_cap, shares, prefer_fcf):
    if fin_df is None or fin_df.empty or hist is None or hist.empty:
        return pd.DataFrame()
    
    hist_naive = hist.copy()
    if hist_naive.index.tz is not None:
        hist_naive.index = hist_naive.index.tz_localize(None)
    
    rows = []
    for col in fin_df.columns:
        date = col if isinstance(col, datetime) else pd.to_datetime(col)
        if hasattr(date, "tz") and date.tz is not None:
            date = date.tz_localize(None)
        
        price_on_date = hist_naive["Close"].asof(date)
        if pd.isna(price_on_date):
            continue
        
        rev = latest_value(fin_df[[col]], ["Total Revenue", "TotalRevenue"])
        ni = latest_value(fin_df[[col]], ["Net Income", "NetIncome"])
        ocf = latest_value(cf_df[[col]] if cf_df is not None else None, ["Operating Cash Flow", "OperatingCashFlow"])
        fcf = latest_value(cf_df[[col]] if cf_df is not None else None, ["Free Cash Flow", "FreeCashFlow"])
        
        ps = (market_cap / rev) if (market_cap and rev and rev > 0) else None
        pe = (price_on_date / (ni / shares)) if (ni and shares and ni > 0) else None
        pocf = (market_cap / ocf) if (market_cap and ocf and ocf > 0) else None
        pfcf = (market_cap / fcf) if (market_cap and fcf and fcf > 0) else None
        
        rows.append({
            "Date": date.strftime("%Y-%m-%d"),
            "Price": round(price_on_date, 2),
            "Revenue ($M)": round(rev / 1e6, 1) if rev else None,
            "P/S": round(ps, 2) if ps else None,
            "Net Income ($M)": round(ni / 1e6, 1) if ni else None,
            "P/E": round(pe, 2) if pe else None,
            "CF ($M)": round((fcf or ocf) / 1e6, 1) if (fcf or ocf) else None,
            "P/CF": round(pfcf or pocf, 2) if (pfcf or pocf) else None,
        })
    return pd.DataFrame(rows).sort_values("Date", ascending=False)

if ticker:
    with st.spinner(f"Loading {ticker}…"):
        hist, info, q_fin, a_fin, q_cf, a_cf = get_data(ticker)

    if hist is None or hist.empty:
        st.error(f"No price data for {ticker}. Yahoo Finance may be rate-limiting. Try again in a minute.")
    else:
        price = float(hist["Close"].iloc[-1])
        market_cap = info.get("marketCap") or info.get("enterpriseValue")
        shares = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding") or info.get("floatShares")

        rev = latest_value(a_fin, ["Total Revenue", "TotalRevenue"])
        ni = latest_value(a_fin, ["Net Income", "NetIncome"])
        ocf = latest_value(a_cf, ["Operating Cash Flow", "OperatingCashFlow"])
        fcf = latest_value(a_cf, ["Free Cash Flow", "FreeCashFlow"])

        ps = info.get("priceToSalesTrailing12Months") or ((market_cap / rev) if (market_cap and rev and rev > 0) else None)
        pe = info.get("trailingPE") or ((price / (ni / shares)) if (ni and shares and ni > 0) else None)
        pocf = (market_cap / ocf) if (market_cap and ocf and ocf > 0) else None
        pfcf = info.get("priceToFreeCashflow") or ((market_cap / fcf) if (market_cap and fcf and fcf > 0) else None)

        cols = st.columns(5)
        cols[0].metric("Price", f"${price:.2f}")
        cols[1].metric("P/S", f"{ps:.2f}" if ps else "—")
        pe_d = pe if (pe and (show_negative_pe or pe > 0)) else None
        cols[2].metric("P/E", f"{pe_d:.2f}" if pe_d else "—")
        cols[3].metric("P/FCF" if prefer_fcf else "P/OCF", f"{pfcf:.2f}" if prefer_fcf and pfcf else (f"{pocf:.2f}" if pocf else "—"))
        cols[4].metric("Market Cap", f"${market_cap/1e9:.1f}B" if market_cap else "—")

        st.success(f"Data loaded for {ticker}")

        q_hist = build_history(q_fin, q_cf, hist, market_cap, shares, prefer_fcf)
        a_hist = build_history(a_fin, a_cf, hist, market_cap, shares, prefer_fcf)

        tab1, tab2 = st.tabs(["Quarterly (recent)", "Annual (longer history)"])

        def show_history(df, label, current_ps, current_pe, current_pcf):
            if df.empty:
                st.info(f"No {label.lower()} history available.")
                return
            
            st.caption(f"{len(df)} {label.lower()} periods")
            st.dataframe(df, width="stretch", hide_index=True)

            st.subheader(f"Average ({label} – {len(df)} periods)")
            avg_cols = st.columns(3)
            ps_avg = df["P/S"].mean() if not df["P/S"].dropna().empty else None
            pe_avg = df["P/E"].mean() if not df["P/E"].dropna().empty else None
            pcf_avg = df["P/CF"].mean() if not df["P/CF"].dropna().empty else None

            avg_cols[0].metric("Avg P/S", f"{ps_avg:.2f}" if ps_avg else "—")
            avg_cols[1].metric("Avg P/E", f"{pe_avg:.2f}" if pe_avg else "—")
            avg_cols[2].metric("Avg P/FCF", f"{pcf_avg:.2f}" if pcf_avg else "—")

            st.subheader("Current vs History — % Undervalued / Overvalued")
            vs_cols = st.columns(3)

            def vs_metric(col, curr, avg, name):
                if curr is None or avg is None or avg == 0:
                    col.metric(name, "—")
                    return
                pct = (curr - avg) / abs(avg) * 100
                delta = f"{pct:+.1f}%"
                col.metric(name, f"{curr:.2f}", delta=delta, delta_color="inverse")

            vs_metric(vs_cols[0], current_ps, ps_avg, "P/S")
            vs_metric(vs_cols[1], current_pe, pe_avg, "P/E")
            vs_metric(vs_cols[2], current_pcf, pcf_avg, "P/FCF")

        with tab1:
            show_history(q_hist, "Quarterly", ps, pe, pfcf or pocf)

        with tab2:
            show_history(a_hist, "Annual", ps, pe, pfcf or pocf)
else:
    st.info("Enter a ticker in the sidebar.")
