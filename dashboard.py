"""
Live markets dashboard built on TradingView's free embeddable widgets.

Prices stream live inside TradingView's own widgets, so there is no auto-refresh.
Use the Edit button on the Watchlist tab to remove or add coins and stocks. Your
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
from html import escape as html_escape

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


st.markdown(
    """<style>
    [class*="st-key-rm_"] button{border-radius:50%;width:28px;height:28px;min-height:0;
      padding:0;background:#dc2626;color:#fff;border:none;font-weight:700;}
    [class*="st-key-rm_"] button:hover{background:#b91c1c;color:#fff;}
    </style>""",
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


# ---------- edit mode ----------
ALL_NAMES = {**CRYPTO_CATALOG, **STOCK_CATALOG}


def remove_symbol(sym: str) -> None:
    if sym in st.session_state.crypto:
        st.session_state.crypto.remove(sym)
    if sym in st.session_state.stocks:
        st.session_state.stocks.remove(sym)
    save_lists()


def add_symbol(sym: str, kind: str) -> None:
    target = st.session_state.crypto if kind == "Crypto" else st.session_state.stocks
    if sym not in target:
        target.append(sym)
    save_lists()


def on_pick(kind: str) -> None:
    key = f"pick_{kind}"
    sym = st.session_state.get(key)
    if sym:
        add_symbol(sym, kind)
    st.session_state[key] = None


def on_custom_add(kind: str) -> None:
    key = f"custom_{kind}"
    for sym in parse_symbols(st.session_state.get(key, ""), kind == "Crypto"):
        add_symbol(sym, kind)
    st.session_state[key] = ""


def move_symbol(kind: str, i: int, delta: int) -> None:
    lst = st.session_state.crypto if kind == "Crypto" else st.session_state.stocks
    j = i + delta
    if 0 <= j < len(lst):
        lst[i], lst[j] = lst[j], lst[i]
        save_lists()


def reset_lists() -> None:
    st.session_state.crypto = list(DEFAULT_CRYPTO)
    st.session_state.stocks = list(DEFAULT_STOCKS)
    save_lists()


BADGE_COLORS = ["#f7931a", "#627eea", "#26a17b", "#3b82f6", "#8b5cf6",
                "#ef4444", "#14b8a6", "#eab308", "#ec4899", "#22c55e"]


def badge(sym: str, is_crypto: bool) -> str:
    """Small colored circle with the ticker's first letters (edit mode only)."""
    base = sym.split(":")[-1]
    if is_crypto:
        for suffix in ("USDT", "USDC", "USD"):
            if base.endswith(suffix) and len(base) > len(suffix):
                base = base[: -len(suffix)]
                break
    color = BADGE_COLORS[sum(ord(ch) for ch in base) % len(BADGE_COLORS)]
    return (
        f'<div style="width:30px;height:30px;border-radius:50%;background:{color};'
        "color:#fff;display:flex;align-items:center;justify-content:center;"
        f'font-weight:700;font-size:10px">{html_escape(base[:3])}</div>'
    )


def edit_group(kind: str) -> None:
    items = st.session_state.crypto if kind == "Crypto" else st.session_state.stocks
    catalog = CRYPTO_CATALOG if kind == "Crypto" else STOCK_CATALOG
    noun = "crypto" if kind == "Crypto" else "stock"
    st.markdown(f"**{kind.upper()}**")
    for i, sym in enumerate(list(items)):
        c_rm, c_logo, c_name, c_up, c_dn = st.columns(
            [1, 1, 8, 1, 1], vertical_alignment="center"
        )
        c_rm.button("−", key=f"rm_{sym}", on_click=remove_symbol, args=(sym,), help="Remove")
        c_logo.markdown(badge(sym, kind == "Crypto"), unsafe_allow_html=True)
        c_name.markdown(label(sym, ALL_NAMES))
        c_up.button("▲", key=f"up_{sym}", on_click=move_symbol,
                    args=(kind, i, -1), disabled=i == 0, help="Move up")
        c_dn.button("▼", key=f"dn_{sym}", on_click=move_symbol,
                    args=(kind, i, 1), disabled=i == len(items) - 1, help="Move down")
    with st.expander(f"＋ Add {noun}"):
        options = [s for s in catalog if s not in items]
        st.selectbox(
            "Browse the list or type to search",
            options,
            index=None,
            key=f"pick_{kind}",
            placeholder="Click to browse, or start typing a name...",
            format_func=lambda s: label(s, ALL_NAMES),
            on_change=on_pick,
            args=(kind,),
        )
        st.text_input(
            "Not in the list? Type any symbol",
            key=f"custom_{kind}",
            placeholder="KRAKEN:FLRUSD" if kind == "Crypto" else "NYSE:JPM",
        )
        st.button("Add symbol", key=f"addbtn_{kind}", on_click=on_custom_add, args=(kind,))


def edit_view() -> None:
    st.caption("Tap − to remove, ▲ ▼ to reorder, and use the Add row under each group to add more.")
    edit_group("Crypto")
    edit_group("Stocks")
    st.button("Reset to defaults", on_click=reset_lists)


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
    editing = st.session_state.get("editing", False)
    if st.button("Done" if editing else "✎ Edit", type="primary" if editing else "secondary"):
        st.session_state.editing = not editing
        st.rerun()

    if editing:
        edit_view()
    else:
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
            st.info("Your watchlist is empty. Click Edit to add some.")

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
