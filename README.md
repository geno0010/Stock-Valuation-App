# Stock Valuation Ratios App (10 Quarters)

A simple Streamlit web app that pulls **Price-to-Sales (P/S)**, **Price-to-Earnings (P/E)**, and **Price-to-Cash-Flow** (P/OCF or P/FCF) for any stock ticker.

## Features
- **Current** ratios (from Yahoo Finance)
- **Last 10 quarters** of TTM ratios at each quarter-end
- **10-quarter averages** for P/S, P/E, and P/CF
- **% Undervalued / Overvalued** vs the stock’s own 10-quarter average
  - Positive % → currently richer (overvalued) relative to recent history
  - Negative % → currently cheaper (undervalued) relative to recent history
- Toggle between Operating Cash Flow and Free Cash Flow
- Option to show/hide negative P/E values
- Trend chart + simple interpretation signals

## How to run

```bash
# 1. Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch the app
streamlit run stock_valuation_app.py
```

Then open the URL shown in the terminal (usually http://localhost:8501).

## Notes & Limitations
- Data comes from Yahoo Finance via the `yfinance` library. It can be rate-limited if you query many tickers quickly.
- Historical share counts are approximated with the latest shares outstanding (so older P/S, P/E, P/CF are approximate).
- P/E is shown as “N/A (loss)” when trailing earnings are negative (unless you enable negative values).
- % Undervalued/Overvalued is **relative to the stock’s own 10-quarter average**, not an absolute fair-value estimate.
- Some tickers have incomplete quarterly cash-flow history → P/CF may be missing for earlier quarters.
- Always cross-check important numbers with official SEC filings or a professional data provider.

## Example
Default ticker is **NTRA**. Change it in the sidebar to any valid Yahoo Finance symbol (AAPL, MSFT, TSLA, etc.).
