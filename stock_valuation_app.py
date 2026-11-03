#!/usr/bin/env python3
"""
Stock Valuation Ratios App
Uses yahooquery + restores historical ratio charts with optional grid overlay.
"""

import warnings
warnings.filterwarnings("ignore")

import streamlit as st
import pandas as pd
import numpy as np
import time
import re
import plotly.graph_objects as go
from plotly.subplots import make_subplots

try:
    from yahooquery import Ticker
    YQ_AVAILABLE = True
except ImportError:
    YQ_AVAILABLE = False
    Ticker = None

st.set_page_config(page_title="Stock Valuation Ratios", page_icon="📊", layout="wide")

st.title("📊 Stock Valuation Ratios")
st.caption("P/S · P/E · P/OCF · History · Averages · Charts · % vs History")

if not YQ_AVAILABLE:
    st.error("""
**yahooquery is not installed.**

Go to your Streamlit Cloud dashboard → your app → **Manage app** → **Reboot**.

If it still fails, make sure your `requirements.txt` contains:
```
yahooquery>=2.3.0
streamlit
pandas
numpy
plotly
```
Then commit and reboot again.
""")
    st.stop()

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
    show_grid = st.checkbox("Show 2D grid overlay on charts", value=True)
    st.markdown("---")
    st.success("Using yahooquery")


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


def load_data(ticker: str):
    try:
        t = Ticker(ticker)
        time.sleep(0.4)

        price = t.price.get(ticker, {}) or {}
        summary = t.summary_detail.get(ticker, {}) or {}
        financial = t.financial_data.get(ticker, {}) or {}
        key_stats = t.key_stats.get(ticker, {}) or {}

        income_a = t.income_statement(frequency="a")
        income_q = t.income_statement(frequency="q")
        cash_a = t.cash_flow(frequency="a")
        cash_q = t.cash_flow(frequency="q")
        hist = t.history(period="5y", interval="1d")

        return {
            "price": price,
            "summary": summary,
            "financial": financial,
            "key_stats": key_stats,
            "income_a": income_a,
            "income_q": income_q,
            "cash_a": cash_a,
            "cash_q": cash_q,
            "hist": hist,
            "ticker": ticker,
        }, None
    except Exception as e:
        return None, str(e)


def build_table(data, is_quarterly=False, use_fcf=False, show_neg_pe=True):
    income = data["income_q"] if is_quarterly else data["income_a"]
    cf = data["cash_q"] if is_quarterly else data["cash_a"]
    hist = data["hist"]
    ticker = data["ticker"]

    if income is None or income.empty:
        return pd.DataFrame()

    try:
        if isinstance(income.index, pd.MultiIndex):
            income = income.reset_index()
        if "asOfDate" in income.columns:
            income = income.set_index("asOfDate")
        income = income.sort_index()

        if cf is not None and not cf.empty:
            if isinstance(cf.index, pd.MultiIndex):
                cf = cf.reset_index()
            if "asOfDate" in cf.columns:
                cf = cf.set_index("asOfDate")
            cf = cf.sort_index()
        else:
            cf = pd.DataFrame()
    except Exception:
        return pd.DataFrame()

    rows = []
    dates = list(income.index)
    shares = data["key_stats"].get("sharesOutstanding") or data["summary"].get("sharesOutstanding")

    for i, date in enumerate(dates):
        try:
            if is_quarterly and i < 3:
                continue

            rev_series = income.get("TotalRevenue")
            if rev_series is None:
                rev_series = income.get("OperatingRevenue")
            if rev_series is None:
                continue
            if is_quarterly:
                rev = rev_series.iloc[i-3:i+1].sum()
            else:
                rev = rev_series.iloc[i]

            ni = np.nan
            for col in ["NetIncome", "NetIncomeCommonStockholders", "NetIncomeContinuousOperations"]:
                if col in income.columns:
                    if is_quarterly:
                        ni = income[col].iloc[i-3:i+1].sum()
                    else:
                        ni = income[col].iloc[i]
                    break

            ttm_cf = np.nan
            ocf_col = next((c for c in ["OperatingCashFlow", "CashFlowFromContinuingOperatingActivities"] if c in cf.columns), None)
            fcf_col = "FreeCashFlow" if "FreeCashFlow" in cf.columns else None
            if use_fcf and fcf_col:
                if is_quarterly:
                    ttm_cf = cf[fcf_col].reindex(income.index).iloc[i-3:i+1].sum()
                else:
                    ttm_cf = cf[fcf_col].reindex(income.index).iloc[i]
            elif ocf_col:
                if is_quarterly:
                    ttm_cf = cf[ocf_col].reindex(income.index).iloc[i-3:i+1].sum()
                else:
                    ttm_cf = cf[ocf_col].reindex(income.index).iloc[i]

            price = np.nan
            if hist is not None and not hist.empty:
                try:
                    h = hist.copy()
                    if isinstance(h.index, pd.MultiIndex):
                        h = h.reset_index()
                        h = h[h["symbol"] == ticker] if "symbol" in h.columns else h
                    if "date" in h.columns:
                        h = h.set_index("date")
                    h.index = pd.to_datetime(h.index).tz_localize(None)
                    avail = h[h.index <= pd.Timestamp(date).tz_localize(None)]
                    if not avail.empty:
                        price = float(avail["close"].iloc[-1])
                except Exception:
                    pass

            if pd.isna(price) or price <= 0 or not shares:
                continue

            mkt_cap = price * shares
            ps = safe_div(mkt_cap, rev)
            pe = safe_div(price, ni / shares) if not pd.isna(ni) else np.nan
            pcf = safe_div(mkt_cap, ttm_cf) if not pd.isna(ttm_cf) else np.nan

            if not show_neg_pe and not pd.isna(pe) and pe <= 0:
                pe = np.nan

            rows.append({
                "Period End": pd.Timestamp(date).strftime("%Y-%m-%d"),
                "Price": round(price, 2),
                "Revenue ($M)": round(rev / 1e6, 1) if not pd.isna(rev) else np.nan,
                "P/S": round(ps, 2) if not pd.isna(ps) else np.nan,
                "Net Income ($M)": round(ni / 1e6, 1) if not pd.isna(ni) else np.nan,
                "P/E": round(pe, 2) if not pd.isna(pe) else np.nan,
                "CF ($M)": round(ttm_cf / 1e6, 1) if not pd.isna(ttm_cf) else np.nan,
                "P/CF": round(pcf, 2) if not pd.isna(pcf) else np.nan,
            })
        except Exception:
            continue

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.iloc[::-1].reset_index(drop=True)
    return df


def plot_ratios(df, title, show_grid=True):
    if df is None or df.empty or "Period End" not in df.columns:
        return None

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                        subplot_titles=("P/S", "P/E", "P/CF"))

    fig.add_trace(go.Scatter(x=df["Period End"], y=df["P/S"], mode="lines+markers", name="P/S",
                             line=dict(color="#1f77b4", width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["Period End"], y=df["P/E"], mode="lines+markers", name="P/E",
                             line=dict(color="#ff7f0e", width=2)), row=2, col=1)
    fig.add_trace(go.Scatter(x=df["Period End"], y=df["P/CF"], mode="lines+markers", name="P/CF",
                             line=dict(color="#2ca02c", width=2)), row=3, col=1)

    fig.update_layout(
        height=600,
        title=title,
        showlegend=False,
        template="plotly_dark" if st.get_option("theme.base") == "dark" else "plotly_white",
        margin=dict(l=40, r=20, t=40, b=40),
    )

    # Grid overlay
    fig.update_xaxes(showgrid=show_grid, gridwidth=1, gridcolor="rgba(128,128,128,0.25)")
    fig.update_yaxes(showgrid=show_grid, gridwidth=1, gridcolor="rgba(128,128,128,0.25)")

    return fig


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
    data, err = load_data(ticker)
    if err or data is None:
        errors.append(f"{ticker}: {err or 'No data'}")
    else:
        q_df = build_table(data, is_quarterly=True, use_fcf=use_fcf, show_neg_pe=show_negative_pe)
        a_df = build_table(data, is_quarterly=False, use_fcf=use_fcf, show_neg_pe=show_negative_pe)

        price = data["price"]
        summary = data["summary"]
        fin = data["financial"]

        current = {
            "Ticker": ticker,
            "Name": price.get("longName") or price.get("shortName") or ticker,
            "Price": price.get("regularMarketPrice") or summary.get("previousClose"),
            "P/S": summary.get("priceToSalesTrailing12Months") or fin.get("priceToSales"),
            "P/E": summary.get("trailingPE") or fin.get("trailingPE"),
            "P/OCF": summary.get("priceToOperatingCashflow") or fin.get("priceToCashflow"),
            "Market Cap": price.get("marketCap") or summary.get("marketCap"),
            "q_df": q_df,
            "a_df": a_df,
        }
        results.append(current)
    progress.progress((i + 1) / len(tickers))
    time.sleep(0.4)

progress.empty()

if errors:
    with st.expander("⚠️ Data issues"):
        for e in errors:
            st.write(e)

if not results:
    st.error("No data could be loaded. Try rebooting the app from Streamlit Cloud, or wait a few minutes and refresh.")
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
            fig = plot_ratios(res["q_df"], f"{res['Ticker']} — Quarterly Ratios", show_grid=show_grid)
            if fig:
                st.plotly_chart(fig, use_container_width=True)

    with tab2:
        if res["a_df"].empty:
            st.info("No annual data.")
        else:
            st.write(f"**{len(res['a_df'])} annual periods**")
            st.dataframe(res["a_df"], use_container_width=True, hide_index=True)
            fig = plot_ratios(res["a_df"], f"{res['Ticker']} — Annual Ratios", show_grid=show_grid)
            if fig:
                st.plotly_chart(fig, use_container_width=True)

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
st.caption("Data via yahooquery · Approximate · Educational use only · Not financial advice.")
