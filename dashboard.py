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
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from plotly.subplots import make_subplots

STATE_FILE = Path(__file__).with_name("dashboard_state.json")
DEFAULT_WATCHLIST = ["SPY", "QQQ", "AAPL", "NVDA", "TSLA", "AMD"]

st.set_page_config(page_title="Day Trading Dashboard", layout="wide")


# ---------- persistence ----------
def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"watchlist": DEFAULT_WATCHLIST, "alerts": []}


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
        "Last": round(float(last["Close"]), 2),
        "Chg %": round((last["Close"] / prev_close - 1) * 100, 2),
        "vs VWAP %": round((last["Close"] / last["VWAP"] - 1) * 100, 2)
        if pd.notna(last["VWAP"]) else None,
        "RSI": round(float(last["RSI"]), 1) if pd.notna(last["RSI"]) else None,
        "Day High": round(float(today["High"].max()), 2),
        "Day Low": round(float(today["Low"].min()), 2),
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
    watchlist = list(dict.fromkeys(t.strip().upper() for t in raw.replace(",", " ").split() if t.strip()))
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
            "price": st.column_config.NumberColumn("Price", format="%.2f"),
        },
        key="alerts_editor",
        use_container_width=True,
    )

    new_state = {
        "watchlist": watchlist,
        "alerts": alerts_df.dropna().to_dict(orient="records"),
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
        (rows if s else failed).append(s or t)

    if failed:
        st.warning("No data for: " + ", ".join(failed) + " (bad symbol, or market data unavailable).")
    if not rows:
        return

    table = pd.DataFrame(rows)

    # alerts
    prices = dict(zip(table["Ticker"], table["Last"]))
    for a in state.get("alerts", []):
        t = str(a.get("ticker", "")).upper()
        p = a.get("price")
        if t in prices and p:
            if a["direction"] == "above" and prices[t] >= p:
                st.error(f"ALERT: {t} is at {prices[t]:.2f}, at or above {p:.2f}")
            elif a["direction"] == "below" and prices[t] <= p:
                st.error(f"ALERT: {t} is at {prices[t]:.2f}, at or below {p:.2f}")

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
