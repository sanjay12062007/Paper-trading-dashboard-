import streamlit as st
import pandas as pd
import yfinance as yf

st.set_page_config(page_title="AI Paper Trading Dashboard", page_icon="📈", layout="wide")
st.title("📈 Indian Stocks — Paper Trading Dashboard")
st.caption("Simulation only. This dashboard does not place real orders or provide investment advice.")

with st.sidebar:
    st.header("Settings")
    ticker = st.text_input("Yahoo Finance ticker", value="ITC.NS").strip().upper()
    starting_cash = st.number_input("Starting virtual cash (₹)", min_value=100.0, max_value=1000000.0, value=500.0, step=100.0)
    period = st.selectbox("Historical period", ["3mo", "6mo", "1y", "2y", "5y"], index=2)
    fast_days = st.number_input("Fast moving average (days)", min_value=2, max_value=30, value=5, step=1)
    slow_days = st.number_input("Slow moving average (days)", min_value=fast_days + 1, max_value=100, value=20, step=1)
    fee_pct = st.number_input("Estimated fee per side (%)", min_value=0.0, max_value=2.0, value=0.10, step=0.05)
    slippage_pct = st.number_input("Estimated slippage per side (%)", min_value=0.0, max_value=2.0, value=0.05, step=0.05)
    max_position = st.number_input("Max position value (₹)", min_value=100.0, max_value=1000000.0, value=500.0, step=100.0)

if not ticker:
    st.warning("Enter a ticker such as ITC.NS or RELIANCE.NS.")
    st.stop()

@st.cache_data(ttl=300)
def get_prices(symbol, history_period):
    data = yf.download(symbol, period=history_period, interval="1d", auto_adjust=True, progress=False)
    if data.empty:
        return pd.DataFrame()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    needed = [col for col in ["Open", "Close"] if col in data.columns]
    return data[needed].dropna().copy()

try:
    prices = get_prices(ticker, period)
except Exception as exc:
    st.error(f"Could not download market data: {exc}")
    st.stop()

if prices.empty or not {"Open", "Close"}.issubset(prices.columns):
    st.error("No usable prices were returned. Check the ticker and internet connection, then try again.")
    st.info("Examples: ITC.NS, SBIN.NS, TCS.NS, RELIANCE.NS. These are data symbols, not stock recommendations.")
    st.stop()

prices["fast_ma"] = prices["Close"].rolling(int(fast_days)).mean()
prices["slow_ma"] = prices["Close"].rolling(int(slow_days)).mean()
prices["signal"] = (prices["fast_ma"] > prices["slow_ma"]).astype(int)
# Avoid look-ahead: today's open uses the signal known after the previous day's close.
prices["target"] = prices["signal"].shift(1).fillna(0).astype(int)

fee_rate = fee_pct / 100
slippage_rate = slippage_pct / 100
cash = float(starting_cash)
shares = 0
position = None
orders = []
closed_trades = []
equity_rows = []

for date, row in prices.iterrows():
    open_price = float(row["Open"])
    target = int(row["target"])

    if shares > 0 and target == 0:
        sell_price = open_price * (1 - slippage_rate)
        gross_proceeds = shares * sell_price
        sell_fee = gross_proceeds * fee_rate
        cash += gross_proceeds - sell_fee
        net_pnl = shares * (sell_price - position["buy_price"]) - position["buy_fee"] - sell_fee
        orders.append({
            "Date": date, "Action": "SELL", "Shares": shares,
            "Price (₹)": sell_price, "Order value (₹)": gross_proceeds,
            "Estimated fee (₹)": sell_fee
        })
        closed_trades.append({
            "Buy date": position["buy_date"], "Sell date": date,
            "Shares": shares, "Buy price (₹)": position["buy_price"],
            "Sell price (₹)": sell_price,
            "Buy value (₹)": position["buy_value"],
            "Sell value (₹)": gross_proceeds,
            "Buy fee (₹)": position["buy_fee"], "Sell fee (₹)": sell_fee,
            "Net P/L (₹)": net_pnl,
            "Result": "Profit" if net_pnl > 0 else ("Loss" if net_pnl < 0 else "Break-even")
        })
        shares = 0
        position = None

    if shares == 0 and target == 1:
        buy_price = open_price * (1 + slippage_rate)
        max_value = min(float(max_position), cash / (1 + fee_rate))
        qty = int(max_value / (buy_price * (1 + fee_rate)))
        if qty > 0:
            buy_value = qty * buy_price
            buy_fee = buy_value * fee_rate
            cash -= buy_value + buy_fee
            shares = qty
            position = {
                "buy_date": date, "buy_price": buy_price,
                "buy_value": buy_value, "buy_fee": buy_fee
            }
            orders.append({
                "Date": date, "Action": "BUY", "Shares": qty,
                "Price (₹)": buy_price, "Order value (₹)": buy_value,
                "Estimated fee (₹)": buy_fee
            })

    close_price = float(row["Close"])
    market_value = shares * close_price
    unrealized_pnl = 0.0
    if shares > 0 and position:
        unrealized_pnl = shares * (close_price - position["buy_price"]) - position["buy_fee"]
    equity_rows.append({
        "Date": date, "Cash (₹)": cash, "Shares": shares,
        "Close (₹)": close_price, "Market value (₹)": market_value,
        "Unrealized P/L (₹)": unrealized_pnl,
        "Portfolio value (₹)": cash + market_value
    })

equity = pd.DataFrame(equity_rows).set_index("Date")
orders_df = pd.DataFrame(orders)
trades_df = pd.DataFrame(closed_trades)
final_equity = float(equity["Portfolio value (₹)"].iloc[-1])
total_pnl = final_equity - float(starting_cash)
return_pct = total_pnl / float(starting_cash) * 100
peak = equity["Portfolio value (₹)"].cummax()
max_drawdown_pct = ((equity["Portfolio value (₹)"] / peak) - 1).min() * 100
current_shares = int(equity["Shares"].iloc[-1])
current_cash = float(equity["Cash (₹)"].iloc[-1])
latest_close = float(equity["Close (₹)"].iloc[-1])
current_market_value = float(equity["Market value (₹)"].iloc[-1])
current_unrealized = float(equity["Unrealized P/L (₹)"].iloc[-1])
realized_pnl = float(trades_df["Net P/L (₹)"].sum()) if not trades_df.empty else 0.0

m1, m2, m3, m4 = st.columns(4)
m1.metric("Portfolio value", f"₹{final_equity:,.2f}", f"{total_pnl:+,.2f} ({return_pct:+.2f}%)")
m2.metric("Available cash", f"₹{current_cash:,.2f}")
m3.metric("Realized P/L", f"₹{realized_pnl:+,.2f}")
m4.metric("Open-position P/L", f"₹{current_unrealized:+,.2f}" if current_shares else "₹0.00")

st.subheader(f"{ticker} — price and moving averages")
chart_data = prices[["Close", "fast_ma", "slow_ma"]].rename(columns={
    "Close": "Close price", "fast_ma": f"{int(fast_days)}-day average",
    "slow_ma": f"{int(slow_days)}-day average"
})
st.line_chart(chart_data)

st.subheader("Current position")
if current_shares:
    st.write(f"**Holding:** {current_shares} share(s) · **Latest close:** ₹{latest_close:,.2f} · **Market value:** ₹{current_market_value:,.2f}")
    st.write(f"Unrealized P/L is estimated from the simulated buy price and includes the entry fee, but not a hypothetical exit fee.")
else:
    st.write("No open position right now.")

st.subheader("Completed trades — buy vs sell")
if trades_df.empty:
    st.info("No completed buy/sell pairs in this period. Try a longer period or another ticker. A current open position, if any, is shown above.")
else:
    display_trades = trades_df.copy()
    money_cols = ["Buy price (₹)", "Sell price (₹)", "Buy value (₹)", "Sell value (₹)", "Buy fee (₹)", "Sell fee (₹)", "Net P/L (₹)"]
    display_trades[money_cols] = display_trades[money_cols].round(2)
    st.dataframe(display_trades, use_container_width=True, hide_index=True)
    wins = int((trades_df["Net P/L (₹)"] > 0).sum())
    st.caption(f"Closed trades: {len(trades_df)} · Profitable trades: {wins} · Losing/breakeven trades: {len(trades_df) - wins}")

st.subheader("Order history")
if orders_df.empty:
    st.info("No simulated orders were generated in this period.")
else:
    order_display = orders_df.copy()
    for col in ["Price (₹)", "Order value (₹)", "Estimated fee (₹)"]:
        order_display[col] = order_display[col].round(2)
    st.dataframe(order_display.sort_values("Date", ascending=False), use_container_width=True, hide_index=True)

st.subheader("Portfolio value over time")
st.line_chart(equity[["Portfolio value (₹)"]])
st.caption(f"Maximum historical drawdown in this simulation: {max_drawdown_pct:.2f}%. Fee and slippage inputs are estimates, not actual broker charges.")

st.download_button("Download completed trades CSV", data=trades_df.to_csv(index=False).encode("utf-8"), file_name="paper_completed_trades.csv", mime="text/csv")
st.download_button("Download order history CSV", data=orders_df.to_csv(index=False).encode("utf-8"), file_name="paper_order_history.csv", mime="text/csv")

with st.expander("Important notes"):
    st.markdown("""
    - This is a historical paper-trading demo. It does not place real orders.
    - Yahoo Finance data may be delayed, incomplete, adjusted, or unavailable; it is not an exchange-grade live feed.
    - The strategy uses a moving-average crossover for learning, not as a recommendation or a proven profitable strategy.
    - Costs are user-configurable estimates. Actual Indian brokerage, taxes, exchange charges, and slippage vary.
    - Backtest results can be misleading and do not predict future returns. Keep real-money trading disabled while testing.
    """)
