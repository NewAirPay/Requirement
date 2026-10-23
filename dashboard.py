"""
Personal day-trading watchlist & market dashboard.
Analysis only: no broker connection, no order placement.

Run:
    pip install -r requirements.txt
    streamlit run dashboard.py

Data comes from Yahoo Finance via yfinance (free, unofficial, may be delayed
or occasionally wrong). Verify prices in your broker before acting on anything.
"""

import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
from plotly.subplots import make_subplots

STATE_FILE = Path(__file__).with_name("dashboard_state.json")
DEFAULT_WATCHLIST = ["SPY", "QQQ", "AAPL", "NVDA", "TSLA", "AMD"]

# Plain coin symbols get "-USD" added automatically (Yahoo's crypto format).
# Add more coins here any time.
CRYPTO_SYMBOLS = {
    "BTC", "ETH", "XRP", "XLM", "FLR", "XDC", "SOL", "DOGE", "ADA", "LINK",
    "AVAX", "LTC", "DOT", "MATIC", "SHIB", "BCH", "ATOM", "HBAR", "ALGO", "QNT",
    "YELLOW",
}


def normalize_symbol(t: str) -> str:
    t = t.strip().upper()
    return f"{t}-USD" if t in CRYPTO_SYMBOLS else t


def px_round(v: float) -> float:
    """Cheap coins (XRP, XLM, ...) need more decimals than 2."""
    v = float(v)
    return round(v, 2) if abs(v) >= 1 else round(v, 6)


def fmt_px(v: float) -> str:
    return f"{v:,.2f}" if abs(v) >= 1 else f"{v:.6f}"


st.set_page_config(page_title="Day Trading Dashboard", layout="wide")


# ---------- persistence ----------
def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"watchlist": DEFAULT_WATCHLIST, "alerts": [], "follow": []}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ---------- data ----------
@st.cache_data(ttl=30, show_spinner=False)
def get_intraday(ticker: str, period: str, interval: str, prepost: bool) -> pd.DataFrame:
    df = yf.Ticker(ticker).history(period=period, interval=interval, prepost=prepost)
    return df.dropna(subset=["Close"]) if not df.empty else df


@st.cache_data(ttl=300, show_spinner=False)
def get_daily(ticker: str) -> pd.DataFrame:
    df = yf.Ticker(ticker).history(period="1mo", interval="1d")
    return df.dropna(subset=["Close"]) if not df.empty else df


# ---------- indicators ----------
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    day = df.index.date
    pv = (typical * df["Volume"]).groupby(day).cumsum()
    vol = df["Volume"].groupby(day).cumsum()
    df["VWAP"] = pv / vol.replace(0, pd.NA)
    df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA21"] = df["Close"].ewm(span=21, adjust=False).mean()
    delta = df["Close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = gain / loss.replace(0, pd.NA)
    df["RSI"] = 100 - 100 / (1 + rs)
    return df


def summarize(ticker: str, period: str, interval: str, prepost: bool) -> dict | None:
    intra = get_intraday(ticker, period, interval, prepost)
    daily = get_daily(ticker)
    if intra.empty or daily.empty:
        return None
    intra = add_indicators(intra)
    last = intra.iloc[-1]
    last_date = intra.index[-1].date()
    if daily.index[-1].date() == last_date and len(daily) > 1:
        prev_close = daily["Close"].iloc[-2]
    else:
        prev_close = daily["Close"].iloc[-1]
    today = intra[intra.index.date == last_date]
    avg_daily_vol = daily["Volume"].iloc[:-1].mean() if len(daily) > 1 else daily["Volume"].mean()
    rel_vol = today["Volume"].sum() / avg_daily_vol if avg_daily_vol else float("nan")
    return {
        "Ticker": ticker,
        "Last": px_round(last["Close"]),
        "Chg %": round((last["Close"] / prev_close - 1) * 100, 2),
        "vs VWAP %": round((last["Close"] / last["VWAP"] - 1) * 100, 2)
        if pd.notna(last["VWAP"]) else None,
        "RSI": round(float(last["RSI"]), 1) if pd.notna(last["RSI"]) else None,
        "Day High": px_round(today["High"].max()),
        "Day Low": px_round(today["Low"].min()),
        "Rel Vol (so far)": round(float(rel_vol), 2),
        "Bar time": intra.index[-1].strftime("%m-%d %H:%M"),
    }


# ---------- charts ----------
def make_chart(ticker: str, period: str, interval: str, prepost: bool) -> go.Figure | None:
    df = get_intraday(ticker, period, interval, prepost)
    if df.empty:
        return None
    df = add_indicators(df)
    # use string x-axis so overnight/weekend gaps don't stretch the chart
    x = df.index.strftime("%m-%d %H:%M")
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        row_heights=[0.6, 0.2, 0.2], vertical_spacing=0.03,
    )
    fig.add_trace(go.Candlestick(
        x=x, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"], name="Price",
    ), row=1, col=1)
    fig.add_trace(go.Scatter(x=x, y=df["VWAP"], name="VWAP", line=dict(width=1.5, color="orange")), row=1, col=1)
    fig.add_trace(go.Scatter(x=x, y=df["EMA9"], name="EMA 9", line=dict(width=1, color="dodgerblue")), row=1, col=1)
    fig.add_trace(go.Scatter(x=x, y=df["EMA21"], name="EMA 21", line=dict(width=1, color="violet")), row=1, col=1)
    fig.add_trace(go.Bar(x=x, y=df["Volume"], name="Volume", marker_color="gray"), row=2, col=1)
    fig.add_trace(go.Scatter(x=x, y=df["RSI"], name="RSI 14", line=dict(width=1.2)), row=3, col=1)
    fig.add_hline(y=70, line_dash="dot", line_color="red", row=3, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="green", row=3, col=1)
    fig.update_xaxes(type="category", nticks=10, rangeslider_visible=False)
    fig.update_layout(height=680, margin=dict(l=10, r=10, t=30, b=10), legend=dict(orientation="h"))
    return fig


# ---------- sidebar ----------
state = load_state()

with st.sidebar:
    st.header("Settings")
    raw = st.text_area("Watchlist (comma or space separated)", ", ".join(state["watchlist"]))
    watchlist = list(dict.fromkeys(normalize_symbol(t) for t in raw.replace(",", " ").split() if t.strip()))
    st.caption("Stocks and crypto go in the same box. Type coins as XRP XLM FLR XDC (auto-converted to XRP-USD) or any SYMBOL-USD. Coins Yahoo doesn't carry show a 'No data' warning. Pre/post-market applies to stocks only; crypto trades 24/7.")
    follow_raw = st.text_area(
        "X accounts to follow (handles or profile links)",
        ", ".join(state.get("follow", [])),
        help="Example: elonmusk, @SEC_News, https://x.com/coinbase",
    )
    follow = []
    for tok in follow_raw.replace(",", " ").split():
        tok = tok.split("?")[0].rstrip("/").split("/")[-1].lstrip("@")
        if re.fullmatch(r"[A-Za-z0-9_]{1,15}", tok) and tok not in follow:
            follow.append(tok)

    interval = st.selectbox("Candle interval", ["1m", "5m", "15m"], index=1)
    period = st.selectbox("History", ["1d", "5d"], index=1)
    prepost = st.checkbox("Include pre/post-market", value=False)
    refresh = st.select_slider("Auto-refresh (seconds, 0 = off)", [0, 15, 30, 60, 120], value=30)

    st.subheader("Price alerts")
    alerts_df = pd.DataFrame(state.get("alerts", []), columns=["ticker", "direction", "price"])
    alerts_df = st.data_editor(
        alerts_df,
        num_rows="dynamic",
        column_config={
            "ticker": st.column_config.TextColumn("Ticker"),
            "direction": st.column_config.SelectboxColumn("When price is", options=["above", "below"]),
            "price": st.column_config.NumberColumn("Price"),
        },
        key="alerts_editor",
        use_container_width=True,
    )

    new_state = {
        "watchlist": watchlist,
        "alerts": alerts_df.dropna().to_dict(orient="records"),
        "follow": follow,
    }
    if new_state != state:
        save_state(new_state)
        state = new_state

    st.caption("Data: Yahoo Finance via yfinance. Unofficial, can be delayed or wrong. Not financial advice.")


# ---------- main ----------
def render() -> None:
    st.title("Day Trading Dashboard")
    st.caption(f"Last refreshed {datetime.now().strftime('%H:%M:%S')}  |  analysis only, no orders")

    if not watchlist:
        st.info("Add some tickers in the sidebar.")
        return

    rows, failed = [], []
    for t in watchlist:
        try:
            s = summarize(t, period, interval, prepost)
        except Exception:
            s = None
        # Unknown bare symbol? Try it as a coin (e.g. "PEPE" -> "PEPE-USD").
        if s is None and "-" not in t and "." not in t:
            try:
                s = summarize(f"{t}-USD", period, interval, prepost)
            except Exception:
                s = None
        (rows if s else failed).append(s or t)

    if failed:
        st.warning("No data for: " + ", ".join(failed) + " (bad symbol, or market data unavailable).")
    if not rows:
        return

    table = pd.DataFrame(rows)

    # alerts
    prices = dict(zip(table["Ticker"], table["Last"]))
    for a in state.get("alerts", []):
        t = normalize_symbol(str(a.get("ticker", "")))
        if t not in prices and f"{t}-USD" in prices:
            t = f"{t}-USD"
        p = a.get("price")
        if t in prices and p:
            if a["direction"] == "above" and prices[t] >= p:
                st.error(f"ALERT: {t} is at {fmt_px(prices[t])}, at or above {fmt_px(p)}")
            elif a["direction"] == "below" and prices[t] <= p:
                st.error(f"ALERT: {t} is at {fmt_px(prices[t])}, at or below {fmt_px(p)}")

    def color_pct(v):
        if pd.isna(v):
            return ""
        return "color: #16a34a" if v > 0 else "color: #dc2626" if v < 0 else ""

    st.dataframe(
        table.style.map(color_pct, subset=["Chg %", "vs VWAP %"]),
        use_container_width=True, hide_index=True,
    )

    chosen = st.selectbox("Chart", table["Ticker"].tolist())
    fig = make_chart(chosen, period, interval, prepost)
    if fig:
        st.plotly_chart(fig, use_container_width=True)


if refresh:
    st.fragment(run_every=refresh)(render)()
else:
    render()

# ---------- following (X) ----------
st.divider()
st.subheader("Following on X")
if follow:
    cols = st.columns(min(len(follow), 2))
    for i, handle in enumerate(follow):
        with cols[i % len(cols)]:
            components.html(
                f"""
                <a class="twitter-timeline" data-height="420" data-tweet-limit="1"
                   data-chrome="noheader nofooter transparent"
                   href="https://twitter.com/{handle}">Loading latest post from @{handle}...</a>
                <script async src="https://platform.twitter.com/widgets.js" charset="utf-8"></script>
                """,
                height=440,
                scrolling=True,
            )
            st.caption(f"[@{handle} on x.com](https://x.com/{handle})")
    st.caption(
        "Latest post per account via X's free embed. If a box stays blank, X is blocking "
        "the embed for this browser; use the x.com link under it."
    )
else:
    st.caption("Add X handles in the sidebar to show each account's latest post here.")
