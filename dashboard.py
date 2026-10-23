"""
Live markets dashboard built on TradingView's free embeddable widgets.

Prices stream live inside TradingView's own widgets, so there is no auto-refresh.
Edit your watchlist in the sidebar; it is saved in the page URL, so bookmark
the page after you customize it.

Run locally:
    pip install -r requirements.txt
    streamlit run dashboard.py

Analysis only. No broker connection, no orders. Data is TradingView's; some
exchanges are delayed on the free widgets, so confirm prices in your broker.
"""

import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import streamlit as st
import streamlit.components.v1 as components

THEME = "dark"  # "dark" or "light"

DEFAULT_STOCKS = (
    "AMEX:SPY, NASDAQ:QQQ, NASDAQ:AAPL, NASDAQ:NVDA, NASDAQ:TSLA, "
    "NASDAQ:MSFT, NASDAQ:AMZN, NASDAQ:META, NASDAQ:AMD, NASDAQ:GOOGL"
)
DEFAULT_CRYPTO = "BTC, ETH, XRP, XLM, SOL, DOGE, ADA, LINK"
DEFAULT_TERMS = "XRP, Bitcoin, Federal Reserve"

st.set_page_config(page_title="Live Markets", layout="wide")
st.markdown(
    "<style>.block-container{padding-top:4.5rem;}</style>", unsafe_allow_html=True
)


# ---------- helpers ----------
def parse_list(raw: str) -> list[str]:
    out = []
    for tok in raw.replace("\n", ",").replace(" ", ",").split(","):
        tok = tok.strip().upper()
        if tok and tok not in out:
            out.append(tok)
    return out


def stock_symbol(t: str) -> str:
    # EXCHANGE:SYMBOL is safest (e.g. NASDAQ:AAPL). A bare symbol is passed through
    # and TradingView tries to resolve it.
    return t


def crypto_symbol(t: str) -> str:
    # Bare coins default to Coinbase USD pairs. Use EXCHANGE:PAIR for anything else.
    return t if ":" in t else f"COINBASE:{t}USD"


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


@st.cache_data(ttl=300, show_spinner=False)
def fetch_news(term: str, limit: int = 8) -> list[dict]:
    """Recent headlines for a search term from Google News' public RSS feed."""
    url = (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(f"{term} when:2d")
        + "&hl=en-US&gl=US&ceid=US:en"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        root = ET.fromstring(resp.read())
    items = []
    for it in root.iter("item"):
        items.append(
            {
                "title": it.findtext("title", ""),
                "link": it.findtext("link", ""),
                "source": it.findtext("source", ""),
                "date": it.findtext("pubDate", ""),
            }
        )
        if len(items) >= limit:
            break
    return items


def age(pub: str) -> str:
    try:
        dt = parsedate_to_datetime(pub)
        mins = int((datetime.now(timezone.utc) - dt).total_seconds() // 60)
    except Exception:
        return ""
    if mins < 60:
        return f"{max(mins, 1)}m ago"
    if mins < 60 * 24:
        return f"{mins // 60}h ago"
    return f"{mins // (60 * 24)}d ago"


def md_escape(s: str) -> str:
    return s.replace("[", "(").replace("]", ")")


# ---------- sidebar: customize watchlist (saved in the URL) ----------
qp = st.query_params
with st.sidebar:
    st.header("My watchlist")
    stocks_raw = st.text_area(
        "Stocks",
        qp.get("stocks", DEFAULT_STOCKS),
        help="Use EXCHANGE:SYMBOL, like NASDAQ:AAPL or NYSE:JPM. Find exact symbols by "
        "searching in the Chart tab.",
    )
    crypto_raw = st.text_area(
        "Crypto",
        qp.get("crypto", DEFAULT_CRYPTO),
        help="Plain coins like XRP or SOL use Coinbase USD pairs. For other exchanges "
        "use EXCHANGE:PAIR, like KRAKEN:FLRUSD.",
    )
    if st.button("Reset to defaults"):
        st.query_params.clear()
        st.rerun()
    st.caption(
        "Your lists are saved in this page's web address. Bookmark the page after "
        "editing to keep them. If a row shows an error, the symbol needs its exchange "
        "prefix; check the exact name in the Chart tab's search."
    )

stocks = [stock_symbol(t) for t in parse_list(stocks_raw)]
crypto = [crypto_symbol(t) for t in parse_list(crypto_raw)]

if qp.get("stocks") != ", ".join(parse_list(stocks_raw)):
    st.query_params["stocks"] = ", ".join(parse_list(stocks_raw))
if qp.get("crypto") != ", ".join(parse_list(crypto_raw)):
    st.query_params["crypto"] = ", ".join(parse_list(crypto_raw))

# ---------- live ticker tape ----------
tape = (crypto[:3] + stocks[:5]) or ["COINBASE:BTCUSD"]
tv(
    "embed-widget-ticker-tape.js",
    {
        "symbols": [{"proName": s, "title": s.split(":")[-1]} for s in tape],
        "showSymbolLogo": True,
        "colorTheme": THEME,
        "isTransparent": True,
        "displayMode": "adaptive",
        "locale": "en",
    },
    height=100,
)

tab_watch, tab_chart, tab_heat, tab_news = st.tabs(
    ["Watchlist", "Chart", "Heatmaps", "News"]
)

# ---------- watchlist with logos + names, tabs for crypto/stocks ----------
with tab_watch:
    groups = []
    if crypto:
        groups.append(
            {
                "name": "Crypto",
                "originalName": "Crypto",
                "symbols": [{"name": s} for s in crypto],
            }
        )
    if stocks:
        groups.append(
            {
                "name": "Stocks",
                "originalName": "Stocks",
                "symbols": [{"name": s} for s in stocks],
            }
        )
    if groups:
        tv(
            "embed-widget-market-quotes.js",
            {
                "width": "100%",
                "height": 700,
                "symbolsGroups": groups,
                "showSymbolLogo": True,
                "colorTheme": THEME,
                "isTransparent": True,
                "locale": "en",
            },
            height=720,
        )
        st.caption(
            "Live prices stream in on their own. Click a row to open that symbol on "
            "TradingView. Edit your lists in the sidebar (arrow at the top-left)."
        )
    else:
        st.info("Add some stocks or crypto in the sidebar.")

# ---------- full chart with built-in search for ANY stock or coin ----------
with tab_chart:
    tv(
        "embed-widget-advanced-chart.js",
        {
            "autosize": True,
            "symbol": crypto[0] if crypto else "COINBASE:BTCUSD",
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

# ---------- news: your own search terms ----------
with tab_news:
    terms_raw = st.text_input(
        "Search terms (separate with commas)",
        qp.get("terms", DEFAULT_TERMS),
        help="Examples: XRP, SEC lawsuit, NVDA earnings, Fed rate cut",
    )
    terms = [t.strip() for t in terms_raw.split(",") if t.strip()]
    if qp.get("terms") != ", ".join(terms):
        st.query_params["terms"] = ", ".join(terms)

    if not terms:
        st.info("Type a few search terms above to see headlines for them.")
    for term in terms:
        st.subheader(term)
        try:
            items = fetch_news(term)
        except Exception:
            items = None
        if items is None:
            st.warning("Couldn't load headlines right now. Try again in a minute.")
        elif not items:
            st.caption("No news from the last 2 days for this term.")
        else:
            for it in items:
                meta = " · ".join(x for x in [it["source"], age(it["date"])] if x)
                st.markdown(f"- [{md_escape(it['title'])}]({it['link']})  \n  {meta}")
        st.link_button(
            f'Search "{term}" live on X',
            "https://x.com/search?q=" + urllib.parse.quote(term) + "&f=live",
        )
    st.caption(
        "Headlines come from Google News (last 2 days) and refresh every 5 minutes. "
        "X posts can't be shown inside the app without X's paid API, so the button "
        "opens a live X search for that term in a new tab."
    )

st.caption("Data and charts by TradingView. Analysis only, not financial advice.")
