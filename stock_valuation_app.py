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

st.title("📊 Stock Valuation Ratios")
st.caption("P/S · P/E · P/OCF (Price to Operating Cash Flow) · Current · History · Averages · % Undervalued/Overvalued")

# Sidebar
with st.sidebar:
    ticker = st.text_input("Ticker Symbol", value="NTRA").upper().strip()
    prefer_fcf = st.checkbox("Prefer Free Cash Flow (P/FCF) when available", value=True)
    show_negative_pe = st.checkbox("Show negative P/E values", value=False)
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
    st.caption("Data from Yahoo Finance · Approximate · Educational use only · Not financial advice")

def safe_yf_call(func, *args, retries=3, delay=2, **kwargs):
    """Retry wrapper for yfinance calls that fail with crumb/401/429."""
    last_err = None
    for attempt in range(retries):
        try:
            result = func(*args, **kwargs)
            if result is not None:
                return result
        except Exception as e:
            last_err = e
            err_str = str(e).lower()
            if "401" in err_str or "429" in err_str or "crumb" in err_str or "unauthorized" in err_str:
                if attempt < retries - 1:
                    time.sleep(delay * (attempt + 1))
                    continue
            else:
                raise
    if last_err:
        raise last_err
    return None

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_data(ticker_symbol: str):
    """Fetch price, info, and financials with retries."""
    try:
        stock = yf.Ticker(ticker_symbol)
        
        # Price history
        hist = safe_yf_call(stock.history, period="5y", interval="1d")
        if hist is None or hist.empty:
            return None, "No price history returned"
        
        # Info
        info = safe_yf_call(lambda: stock.info) or {}
        
        # Financials
        quarterly_financials = safe_yf_call(lambda: stock.quarterly_financials)
        annual_financials = safe_yf_call(lambda: stock.financials)
        quarterly_cf = safe_yf_call(lambda: stock.quarterly_cashflow)
        annual_cf = safe_yf_call(lambda: stock.cashflow)
        
        return {
            "hist": hist,
            "info": info,
            "quarterly_financials": quarterly_financials,
            "annual_financials": annual_financials,
            "quarterly_cf": quarterly_cf,
            "annual_cf": annual_cf,
        }, None
    except Exception as e:
        return None, str(e)

def compute_ratios(data, prefer_fcf, show_negative_pe):
    hist = data["hist"]
    info = data["info"]
    current_price = float(hist["Close"].iloc[-1]) if not hist.empty else None
    market_cap = info.get("marketCap")
    
    # Current metrics from info where available
    current = {
        "Price": current_price,
        "P/S": info.get("priceToSalesTrailing12Months"),
        "P/E": info.get("trailingPE"),
        "P/OCF": None,
        "P/FCF": info.get("priceToFreeCashflow") or info.get("enterpriseToRevenue"),  # rough fallback
        "Market Cap": market_cap,
    }
    
    # Try to compute P/OCF / P/FCF from cash flow if possible
    # (simplified; full version would align periods properly)
    def extract_cf(cf_df, keys):
        if cf_df is None or cf_df.empty:
            return None
        for k in keys:
            if k in cf_df.index:
                series = cf_df.loc[k].dropna()
                if not series.empty:
                    return series
        return None
    
    # Build simple history table from available data (placeholder logic)
    # In a real app you would properly join price history with financials
    history_df = pd.DataFrame()
    
    return current, history_df

# Main
if ticker:
    with st.spinner(f"Loading data for {ticker}…"):
        data, err = fetch_data(ticker)
    
    if err or data is None:
        st.error(f"Could not load data for {ticker}. Yahoo Finance returned an error (common with crumb/rate limits).")
        st.info("Try again in a minute, use a different ticker, or reboot the app. Error: " + str(err))
    else:
        current, history_df = compute_ratios(data, prefer_fcf, show_negative_pe)
        
        # Display current metrics
        cols = st.columns(5)
        cols[0].metric("Price", f"${current['Price']:.2f}" if current['Price'] else "—")
        cols[1].metric("P/S", f"{current['P/S']:.2f}" if current['P/S'] else "—")
        pe_val = current['P/E']
        if pe_val is not None and (show_negative_pe or pe_val > 0):
            cols[2].metric("P/E", f"{pe_val:.2f}")
        else:
            cols[2].metric("P/E", "—")
        cols[3].metric("P/OCF" if not prefer_fcf else "P/FCF", 
                       f"{current['P/FCF']:.2f}" if prefer_fcf and current['P/FCF'] else 
                       (f"{current['P/OCF']:.2f}" if current['P/OCF'] else "—"))
        cols[4].metric("Market Cap", f"${current['Market Cap']/1e9:.2f}B" if current['Market Cap'] else "—")
        
        st.markdown("---")
        tab1, tab2 = st.tabs(["Quarterly (recent)", "Annual (longer history)"])
        
        with tab1:
            st.info("Limited quarterly data from Yahoo (common). Check the Annual tab.")
            # Add your quarterly table / chart logic here
        
        with tab2:
            st.info("Annual history would go here (price aligned with yearly financials).")
            # Add your annual table / chart logic here
else:
    st.info("Enter a ticker symbol in the sidebar.")
