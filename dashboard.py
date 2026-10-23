"""
Live markets dashboard built on TradingView's free embeddable widgets.

Everything here streams live inside TradingView's own widgets, so there is no
auto-refresh and no ticker typing: click a row, or use the search box inside
the chart to open any stock or crypto.

Run locally:
    pip install -r requirements.txt
    streamlit run dashboard.py

Analysis only. No broker connection, no orders. Data is TradingView's; some
exchanges are delayed on the free widgets, so confirm prices in your broker.
"""

import json

import streamlit as st
import streamlit.components.v1 as components

THEME = "dark"  # "dark" or "light"

# Edit these lists any time. Format is EXCHANGE:SYMBOL (find them by searching
# inside the Chart tab). The second value is the display name.
STOCKS = [
    ("AMEX:SPY", "S&P 500 ETF"),
    ("NASDAQ:QQQ", "Nasdaq 100 ETF"),
    ("NASDAQ:AAPL", "Apple"),
    ("NASDAQ:NVDA", "NVIDIA"),
    ("NASDAQ:TSLA", "Tesla"),
    ("NASDAQ:MSFT", "Microsoft"),
    ("NASDAQ:AMZN", "Amazon"),
    ("NASDAQ:META", "Meta"),
    ("NASDAQ:AMD", "AMD"),
    ("NASDAQ:GOOGL", "Alphabet"),
]
CRYPTO = [
    ("COINBASE:BTCUSD", "Bitcoin"),
    ("COINBASE:ETHUSD", "Ethereum"),
    ("COINBASE:XRPUSD", "XRP"),
    ("COINBASE:XLMUSD", "Stellar"),
    ("COINBASE:SOLUSD", "Solana"),
    ("COINBASE:DOGEUSD", "Dogecoin"),
    ("COINBASE:ADAUSD", "Cardano"),
    ("COINBASE:LINKUSD", "Chainlink"),
]

st.set_page_config(page_title="Live Markets", layout="wide")
st.markdown(
    "<style>.block-container{padding-top:4.5rem;}</style>", unsafe_allow_html=True
)


def tv(script: str, config: dict, height: int) -> None:
    """Embed one TradingView widget. `script` is the widget's file name."""
    html = f"""
    <style>html,body{{margin:0;height:100%;background:transparent}}</style>
    <div class="tradingview-widget-container" style="height:100%;width:100%">
      <div class="tradingview-widget-container__widget" style="height:100%;width:100%"></div>
      <script type="text/javascript"
        src="https://s3.tradingview.com/external-embedding/{script}" async>
      {json.dumps(config)}
      </script>
    </div>
    """
    components.html(html, height=height)


# ---------- live ticker tape ----------
tv(
    "embed-widget-ticker-tape.js",
    {
        "symbols": [{"proName": s, "title": n} for s, n in CRYPTO[:3] + STOCKS[:5]],
        "showSymbolLogo": True,
        "colorTheme": THEME,
        "isTransparent": True,
        "displayMode": "adaptive",
        "locale": "en",
    },
    height=100,
)

tab_watch, tab_chart, tab_heat = st.tabs(["Watchlist", "Chart", "Heatmaps"])

# ---------- watchlist with logos + names, tabs for stocks/crypto ----------
with tab_watch:
    tv(
        "embed-widget-market-quotes.js",
        {
            "width": "100%",
            "height": 700,
            "symbolsGroups": [
                {
                    "name": "Crypto",
                    "originalName": "Crypto",
                    "symbols": [{"name": s, "displayName": n} for s, n in CRYPTO],
                },
                {
                    "name": "Stocks",
                    "originalName": "Stocks",
                    "symbols": [{"name": s, "displayName": n} for s, n in STOCKS],
                },
            ],
            "showSymbolLogo": True,
            "colorTheme": THEME,
            "isTransparent": True,
            "locale": "en",
        },
        height=720,
    )
    st.caption(
        "Live prices stream in on their own. Click a row to open that symbol on "
        "TradingView. To add or remove items, edit the STOCKS and CRYPTO lists at "
        "the top of dashboard.py."
    )

# ---------- full chart with built-in search for ANY stock or coin ----------
with tab_chart:
    tv(
        "embed-widget-advanced-chart.js",
        {
            "autosize": True,
            "symbol": "COINBASE:BTCUSD",
            "interval": "5",
            "timezone": "America/New_York",
            "theme": THEME,
            "style": "1",
            "locale": "en",
            "allow_symbol_change": True,
            "hide_side_toolbar": False,
            "details": True,
            "withdateranges": True,
            "calendar": False,
            "support_host": "https://www.tradingview.com",
        },
        height=780,
    )
    st.caption(
        "Click the symbol name at the top-left of the chart to search any stock or "
        "crypto. Use the toolbar to add indicators like VWAP, EMA and RSI."
    )

# ---------- heatmaps: the whole market at a glance ----------
with tab_heat:
    st.subheader("Crypto")
    tv(
        "embed-widget-crypto-coins-heatmap.js",
        {
            "dataSource": "Crypto",
            "blockSize": "market_cap_calc",
            "blockColor": "change",
            "locale": "en",
            "colorTheme": THEME,
            "hasTopBar": False,
            "isDataSetEnabled": False,
            "isZoomEnabled": True,
            "hasSymbolTooltip": True,
            "isMonoSize": False,
            "width": "100%",
            "height": 520,
        },
        height=540,
    )
    st.subheader("US stocks (S&P 500)")
    tv(
        "embed-widget-stock-heatmap.js",
        {
            "exchanges": [],
            "dataSource": "SPX500",
            "grouping": "sector",
            "blockSize": "market_cap_basic",
            "blockColor": "change",
            "locale": "en",
            "colorTheme": THEME,
            "hasTopBar": False,
            "isDataSetEnabled": False,
            "isZoomEnabled": True,
            "hasSymbolTooltip": True,
            "isMonoSize": False,
            "width": "100%",
            "height": 520,
        },
        height=540,
    )

st.caption("Data and charts by TradingView. Analysis only, not financial advice.")
