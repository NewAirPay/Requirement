"""
Live markets dashboard built on TradingView's free embeddable widgets.

Prices stream live inside TradingView's own widgets, so there is no auto-refresh.
Use the "Add / edit" button on the Watchlist tab to pick coins and stocks. Your
choices are saved in the page URL, so bookmark the page after you customize it.

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


# ---------- catalogs shown in the Add picker ----------
def _coins(pairs: str) -> dict[str, str]:
    out = {}
    for item in pairs.split(";"):
        sym, name = [x.strip() for x in item.split("=")]
        out[f"COINBASE:{sym}USD"] = name
    return out


CRYPTO_CATALOG = _coins(
    "BTC=Bitcoin; ETH=Ethereum; XRP=XRP; SOL=Solana; ADA=Cardano; DOGE=Dogecoin; "
    "AVAX=Avalanche; LINK=Chainlink; DOT=Polkadot; LTC=Litecoin; BCH=Bitcoin Cash; "
    "XLM=Stellar; ATOM=Cosmos; UNI=Uniswap; SHIB=Shiba Inu; HBAR=Hedera; "
    "ALGO=Algorand; NEAR=NEAR Protocol; APT=Aptos; ARB=Arbitrum; OP=Optimism; "
    "AAVE=Aave; FIL=Filecoin; ICP=Internet Computer; ETC=Ethereum Classic; SUI=Sui; "
    "INJ=Injective; PEPE=Pepe; RENDER=Render; BONK=Bonk; FET=Fetch.ai; GRT=The Graph; "
    "MKR=Maker; CRV=Curve; SAND=The Sandbox; MANA=Decentraland; AXS=Axie Infinity; "
    "QNT=Quant; XTZ=Tezos; EOS=EOS; SEI=Sei; TIA=Celestia; IMX=Immutable; LDO=Lido DAO"
)

STOCK_CATALOG = {
    # Index / popular ETFs
    "AMEX:SPY": "S&P 500 ETF", "NASDAQ:QQQ": "Nasdaq 100 ETF",
    "AMEX:IWM": "Russell 2000 ETF", "AMEX:DIA": "Dow Jones ETF",
    "AMEX:ARKK": "ARK Innovation ETF", "AMEX:GLD": "Gold ETF",
    "NASDAQ:TQQQ": "3x Nasdaq ETF", "NASDAQ:SQQQ": "3x Short Nasdaq ETF",
    "AMEX:SOXL": "3x Semiconductor ETF",
    # Big tech / growth
    "NASDAQ:AAPL": "Apple", "NASDAQ:MSFT": "Microsoft", "NASDAQ:NVDA": "NVIDIA",
    "NASDAQ:AMZN": "Amazon", "NASDAQ:GOOGL": "Alphabet", "NASDAQ:META": "Meta",
    "NASDAQ:TSLA": "Tesla", "NASDAQ:AVGO": "Broadcom", "NASDAQ:NFLX": "Netflix",
    "NASDAQ:AMD": "AMD", "NASDAQ:ADBE": "Adobe", "NASDAQ:INTC": "Intel",
    "NASDAQ:QCOM": "Qualcomm", "NASDAQ:MU": "Micron", "NASDAQ:AMAT": "Applied Materials",
    "NASDAQ:SMCI": "Super Micro", "NASDAQ:ARM": "Arm Holdings", "NASDAQ:PLTR": "Palantir",
    "NASDAQ:COIN": "Coinbase", "NASDAQ:HOOD": "Robinhood", "NASDAQ:MSTR": "Strategy (MicroStrategy)",
    "NASDAQ:SOFI": "SoFi", "NASDAQ:RIVN": "Rivian", "NASDAQ:LCID": "Lucid",
    "NASDAQ:PYPL": "PayPal", "NASDAQ:SBUX": "Starbucks", "NASDAQ:COST": "Costco",
    "NASDAQ:PEP": "PepsiCo", "NASDAQ:CSCO": "Cisco", "NASDAQ:ABNB": "Airbnb",
    "NYSE:ORCL": "Oracle", "NYSE:CRM": "Salesforce", "NYSE:SNOW": "Snowflake",
    "NYSE:UBER": "Uber", "NYSE:SHOP": "Shopify",
    # Finance
    "NYSE:JPM": "JPMorgan", "NYSE:BAC": "Bank of America", "NYSE:WFC": "Wells Fargo",
    "NYSE:GS": "Goldman Sachs", "NYSE:V": "Visa", "NYSE:MA": "Mastercard",
    # Consumer / industrial / energy / health
    "NYSE:WMT": "Walmart", "NYSE:DIS": "Disney", "NYSE:KO": "Coca-Cola",
    "NYSE:NKE": "Nike", "NYSE:BA": "Boeing", "NYSE:XOM": "Exxon Mobil",
    "NYSE:CVX": "Chevron", "NYSE:PFE": "Pfizer", "NYSE:JNJ": "Johnson & Johnson",
    "NYSE:UNH": "UnitedHealth", "NYSE:HD": "Home Depot", "NYSE:F": "Ford",
    "NYSE:GM": "General Motors", "NYSE:T": "AT&T", "NYSE:NIO": "NIO",
    # Meme / high-volume
    "NYSE:GME": "GameStop", "NYSE:AMC": "AMC Entertainment",
}

DEFAULT_STOCKS = [
    "AMEX:SPY", "NASDAQ:QQQ", "NASDAQ:AAPL", "NASDAQ:NVDA", "NASDAQ:TSLA",
    "NASDAQ:MSFT", "NASDAQ:AMZN", "NASDAQ:META", "NASDAQ:AMD", "NASDAQ:GOOGL",
]
DEFAULT_CRYPTO = [f"COINBASE:{s}USD" for s in ("BTC", "ETH", "XRP", "XLM", "SOL", "DOGE", "ADA", "LINK")]
DEFAULT_TERMS = "XRP, Bitcoin, Federal Reserve"

st.set_page_config(page_title="Live Markets", layout="wide", initial_sidebar_state="collapsed")
st.markdown(
    "<style>.block-container{padding-top:4.5rem;} [data-testid='stSidebar']{display:none;}"
    " [data-testid='stSidebarCollapsedControl']{display:none;}</style>",
    unsafe_allow_html=True,
)


# ---------- helpers ----------
def parse_symbols(raw: str, crypto: bool) -> list[str]:
    out = []
    for tok in raw.replace("\n", ",").replace(" ", ",").split(","):
        tok = tok.strip().upper()
        if not tok:
            continue
        if crypto and ":" not in tok:
            tok = f"COINBASE:{tok}USD"
        if tok not in out:
            out.append(tok)
    return out


def label(sym: str, names: dict[str, str]) -> str:
    short = sym.split(":")[-1]
    return f"{names[sym]}  ({short})" if sym in names else short


def save_lists() -> None:
    st.query_params["stocks"] = ",".join(st.session_state.stocks)
    st.query_params["crypto"] = ",".join(st.session_state.crypto)


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


# ---------- saved watchlist (kept in the page URL) ----------
qp = st.query_params
if "stocks" not in st.session_state:
    st.session_state.stocks = parse_symbols(qp["stocks"], False) if qp.get("stocks") else list(DEFAULT_STOCKS)
if "crypto" not in st.session_state:
    st.session_state.crypto = parse_symbols(qp["crypto"], True) if qp.get("crypto") else list(DEFAULT_CRYPTO)

stocks = st.session_state.stocks
crypto = st.session_state.crypto


# ---------- the Add / edit picker ----------
@st.dialog("Add to your watchlist", width="large")
def add_dialog() -> None:
    st.caption(
        "Click a box to browse the list, or start typing to search. Remove anything "
        "by clicking the x on it. Press Save when you're done."
    )
    tab_c, tab_s, tab_x = st.tabs(["Crypto", "Stocks", "Other symbol"])

    crypto_opts = list(dict.fromkeys(list(CRYPTO_CATALOG) + crypto))
    stock_opts = list(dict.fromkeys(list(STOCK_CATALOG) + stocks))
    names = {**CRYPTO_CATALOG, **STOCK_CATALOG}

    with tab_c:
        c_sel = st.multiselect(
            "Coins", crypto_opts, default=crypto,
            format_func=lambda s: label(s, names),
        )
    with tab_s:
        s_sel = st.multiselect(
            "Stocks and ETFs", stock_opts, default=stocks,
            format_func=lambda s: label(s, names),
        )
    with tab_x:
        st.caption(
            "Not in the lists? Type it with its exchange, like KRAKEN:FLRUSD or "
            "NYSE:JPM. The Chart tab's search shows exact names."
        )
        custom = st.text_input("Symbol(s), separated by commas")
        custom_kind = st.radio("Add to", ["Crypto", "Stocks"], horizontal=True)

    left, right = st.columns([3, 1])
    if left.button("Save", type="primary", use_container_width=True):
        new_c, new_s = list(c_sel), list(s_sel)
        for sym in parse_symbols(custom, custom_kind == "Crypto"):
            target = new_c if custom_kind == "Crypto" else new_s
            if sym not in target:
                target.append(sym)
        st.session_state.crypto, st.session_state.stocks = new_c, new_s
        save_lists()
        st.rerun()
    if right.button("Reset", use_container_width=True):
        st.session_state.crypto = list(DEFAULT_CRYPTO)
        st.session_state.stocks = list(DEFAULT_STOCKS)
        save_lists()
        st.rerun()


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
    if st.button("＋ Add / edit watchlist", type="primary"):
        add_dialog()

    groups = []
    if crypto:
        groups.append({"name": "Crypto", "originalName": "Crypto",
                       "symbols": [{"name": s} for s in crypto]})
    if stocks:
        groups.append({"name": "Stocks", "originalName": "Stocks",
                       "symbols": [{"name": s} for s in stocks]})
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
            "TradingView. Bookmark this page after you edit to keep your list."
        )
    else:
        st.info("Your watchlist is empty. Click Add / edit watchlist to pick some.")

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
