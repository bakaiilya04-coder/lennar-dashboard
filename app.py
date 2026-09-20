import os
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import yfinance as yf

st.set_page_config(
    page_title="US Housing & Lennar Dashboard",
    page_icon="🏗️",
    layout="wide",
)

# ============================================================
# Configuration / authentication
# ============================================================

SECRET_TOKEN = st.secrets.get("SECRET_TOKEN", os.getenv("SECRET_TOKEN", ""))

if not SECRET_TOKEN:
    st.error("SECRET_TOKEN не настроен.")
    st.info("Создайте .streamlit/secrets.toml и добавьте SECRET_TOKEN = \"ваш_секрет\"")
    st.stop()

user_token = st.query_params.get("token")

if user_token != SECRET_TOKEN:
    st.error("⛔ Доступ запрещён.")
    st.info("Откройте панель по ссылке с параметром ?token=...")
    st.stop()


# ============================================================
# Data loading
# ============================================================

@st.cache_data(ttl=3600, show_spinner=False)
def load_market_data(symbol: str = "LEN", period: str = "2y"):
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period=period, auto_adjust=False)

    if hist.empty:
        raise ValueError(f"Не удалось получить котировки для {symbol}.")

    close = hist["Close"]
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    hist["RSI"] = 100 - (100 / (1 + rs))

    # Дополнительные технические метрики
    hist["MA50"] = close.rolling(50).mean()
    hist["MA200"] = close.rolling(200).mean()

    return hist, ticker


@st.cache_data(ttl=3600, show_spinner=False)
def load_fred_series(series_id: str, start_date: str):
    """
    Получает публичные FRED CSV endpoints без API key.
    """
    url = (
        "https://fred.stlouisfed.org/graph/fredgraph.csv"
        f"?id={series_id}&cosd={start_date}"
    )
    df = pd.read_csv(url)
    df["observation_date"] = pd.to_datetime(df["observation_date"])
    df = df.rename(columns={"observation_date": "Date", series_id: series_id})
    df[series_id] = pd.to_numeric(df[series_id], errors="coerce")
    return df.dropna(subset=[series_id])


def latest_value(df: pd.DataFrame, column: str):
    if df.empty:
        return None
    return float(df[column].dropna().iloc[-1])


# ============================================================
# Helpers
# ============================================================

def fmt_number(value, decimals=2):
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value:,.{decimals}f}"


def fmt_pct(value, decimals=2):
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value * 100:.{decimals}f}%"


def signal_rsi(rsi):
    if rsi is None or pd.isna(rsi):
        return "⚪ Нет данных"
    if rsi >= 70:
        return "🔴 Перекупленность"
    if rsi <= 30:
        return "🔵 Перепроданность"
    return "🟢 Нейтральная зона"


def signal_yoy(current, previous):
    if current is None or previous is None or previous == 0:
        return "⚪ Нет данных"
    change = (current / previous) - 1
    if change <= -0.10:
        return "🔴 Сильное снижение"
    if change < 0:
        return "🟡 Снижение"
    if change >= 0.10:
        return "🟢 Рост"
    return "🟢 Стабильно"


# ============================================================
# Load data
# ============================================================

try:
    market_df, lennar = load_market_data("LEN", "2y")
    info = lennar.info
except Exception as exc:
    st.error(f"Ошибка загрузки данных Lennar: {exc}")
    st.stop()

start = (datetime.utcnow() - timedelta(days=365 * 5)).strftime("%Y-%m-%d")

try:
    fed_df = load_fred_series("FEDFUNDS", start)
except Exception:
    fed_df = pd.DataFrame(columns=["Date", "FEDFUNDS"])

try:
    permits_df = load_fred_series("PERMIT", start)
except Exception:
    permits_df = pd.DataFrame(columns=["Date", "PERMIT"])

try:
    starts_df = load_fred_series("HOUST", start)
except Exception:
    starts_df = pd.DataFrame(columns=["Date", "HOUST"])

try:
    us10y_df = load_fred_series("DGS10", start)
except Exception:
    us10y_df = pd.DataFrame(columns=["Date", "DGS10"])


# ============================================================
# Header
# ============================================================

st.title("🏗️ US Housing & Lennar Monitoring Dashboard")
st.caption(
    "Мониторинг Lennar (LEN), ставок, доходности US 10Y и макроиндикаторов "
    "рынка жилья. Данные обновляются примерно раз в час."
)

st.sidebar.header("⚙️ Настройки")

period = st.sidebar.selectbox(
    "Период графика LEN",
    ["6mo", "1y", "2y"],
    index=1,
)

if st.sidebar.button("🔄 Обновить данные"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.caption(
    "Источники: Yahoo Finance и FRED. "
    "Публичные данные могут иметь задержку."
)

# Reload selected period
try:
    market_df, lennar = load_market_data("LEN", period)
    info = lennar.info
except Exception as exc:
    st.error(f"Не удалось загрузить выбранный период: {exc}")
    st.stop()


# ============================================================
# Lennar metrics
# ============================================================

current_price = float(market_df["Close"].iloc[-1])
previous_price = float(market_df["Close"].iloc[-2]) if len(market_df) > 1 else current_price
day_change = current_price / previous_price - 1

current_rsi = float(market_df["RSI"].dropna().iloc[-1]) if market_df["RSI"].notna().any() else None

pe_ratio = info.get("trailingPE")
pb_ratio = info.get("priceToBook")
debt_to_equity = info.get("debtToEquity")
gross_margin = info.get("grossMargins")
revenue_growth = info.get("revenueGrowth")
profit_margin = info.get("profitMargins")

st.header("1. Lennar — рыночные и финансовые показатели")

c1, c2, c3, c4, c5 = st.columns(5)

c1.metric(
    "LEN",
    f"${current_price:.2f}",
    f"{day_change * 100:+.2f}% за день",
)

c2.metric(
    "RSI (14D)",
    fmt_number(current_rsi, 1),
    signal_rsi(current_rsi),
)

c3.metric(
    "P/E",
    fmt_number(pe_ratio),
)

c4.metric(
    "P/B",
    fmt_number(pb_ratio),
)

c5.metric(
    "Debt / Equity",
    f"{fmt_number(debt_to_equity)}%" if debt_to_equity is not None else "N/A",
)

c6, c7, c8 = st.columns(3)

c6.metric("Gross Margin", fmt_pct(gross_margin))
c7.metric("Profit Margin", fmt_pct(profit_margin))
c8.metric("Revenue Growth", fmt_pct(revenue_growth))


# ============================================================
# Price + RSI chart
# ============================================================

st.subheader("📈 Цена LEN и технические индикаторы")

fig = make_subplots(
    rows=2,
    cols=1,
    shared_xaxes=True,
    vertical_spacing=0.06,
    row_heights=[0.68, 0.32],
)

fig.add_trace(
    go.Scatter(
        x=market_df.index,
        y=market_df["Close"],
        name="LEN",
        line=dict(width=2),
    ),
    row=1,
    col=1,
)

fig.add_trace(
    go.Scatter(
        x=market_df.index,
        y=market_df["MA50"],
        name="MA 50",
        line=dict(width=1),
    ),
    row=1,
    col=1,
)

fig.add_trace(
    go.Scatter(
        x=market_df.index,
        y=market_df["MA200"],
        name="MA 200",
        line=dict(width=1),
    ),
    row=1,
    col=1,
)

fig.add_trace(
    go.Scatter(
        x=market_df.index,
        y=market_df["RSI"],
        name="RSI 14",
        line=dict(width=2),
    ),
    row=2,
    col=1,
)

fig.add_hline(y=70, line_dash="dash", row=2, col=1)
fig.add_hline(y=30, line_dash="dash", row=2, col=1)

fig.update_yaxes(title_text="Цена ($)", row=1, col=1)
fig.update_yaxes(title_text="RSI", range=[0, 100], row=2, col=1)

fig.update_layout(
    height=650,
    margin=dict(l=20, r=20, t=20, b=20),
    hovermode="x unified",
    template="plotly_white",
)

st.plotly_chart(fig, use_container_width=True)

st.info(
    f"Текущий RSI: {fmt_number(current_rsi, 1)} — {signal_rsi(current_rsi)}. "
    "RSI является техническим индикатором и сам по себе не определяет направление будущей цены."
)


# ============================================================
# Macro section
# ============================================================

st.divider()
st.header("2. Макроэкономика США")

fed_value = latest_value(fed_df, "FEDFUNDS")
permits_value = latest_value(permits_df, "PERMIT")
starts_value = latest_value(starts_df, "HOUST")
us10y_value = latest_value(us10y_df, "DGS10")

m1, m2, m3, m4 = st.columns(4)

m1.metric(
    "ФРС / Effective Federal Funds",
    f"{fmt_number(fed_value, 2)}%",
)

m2.metric(
    "US 10Y Treasury",
    f"{fmt_number(us10y_value, 2)}%",
)

m3.metric(
    "Building Permits",
    fmt_number(permits_value, 0),
)

m4.metric(
    "Housing Starts",
    fmt_number(starts_value, 0),
)


# ============================================================
# Fed chart
# ============================================================

if not fed_df.empty or not us10y_df.empty:
    st.subheader("🏛️ Ставки и доходность Treasuries")

    macro_fig = go.Figure()

    if not fed_df.empty:
        macro_fig.add_trace(
            go.Scatter(
                x=fed_df["Date"],
                y=fed_df["FEDFUNDS"],
                name="Federal Funds Rate",
                mode="lines",
            )
        )

    if not us10y_df.empty:
        macro_fig.add_trace(
            go.Scatter(
                x=us10y_df["Date"],
                y=us10y_df["DGS10"],
                name="US 10Y",
                mode="lines",
            )
        )

    macro_fig.update_layout(
        height=420,
        template="plotly_white",
        hovermode="x unified",
        yaxis_title="Процентные пункты",
        margin=dict(l=20, r=20, t=20, b=20),
    )

    st.plotly_chart(macro_fig, use_container_width=True)


# ============================================================
# Housing chart
# ============================================================

if not permits_df.empty or not starts_df.empty:
    st.subheader("🏠 Building Permits и Housing Starts")

    housing_fig = go.Figure()

    if not permits_df.empty:
        housing_fig.add_trace(
            go.Scatter(
                x=permits_df["Date"],
                y=permits_df["PERMIT"],
                name="Building Permits",
                mode="lines",
            )
        )

    if not starts_df.empty:
        housing_fig.add_trace(
            go.Scatter(
                x=starts_df["Date"],
                y=starts_df["HOUST"],
                name="Housing Starts",
                mode="lines",
            )
        )

    housing_fig.update_layout(
        height=420,
        template="plotly_white",
        hovermode="x unified",
        yaxis_title="Тысяч единиц",
        margin=dict(l=20, r=20, t=20, b=20),
    )

    st.plotly_chart(housing_fig, use_container_width=True)


# ============================================================
# Signal table
# ============================================================

st.divider()
st.header("3. Мониторинг сигналов")

# Year-over-year calculation for monthly FRED series
def yoy_signal(df, column):
    if df.empty:
        return None, None

    series = df.set_index("Date")[column].dropna().sort_index()
    if len(series) < 13:
        return None, None

    current = float(series.iloc[-1])
    target_date = series.index[-1] - pd.DateOffset(years=1)
    previous_candidates = series.loc[:target_date]

    if previous_candidates.empty:
        return None, None

    previous = float(previous_candidates.iloc[-1])
    change = current / previous - 1
    return change, current


permits_yoy, _ = yoy_signal(permits_df, "PERMIT")
starts_yoy, _ = yoy_signal(starts_df, "HOUST")

signal_rows = [
    {
        "Индикатор": "LEN RSI (14D)",
        "Текущее значение": fmt_number(current_rsi, 1),
        "Изменение / статус": signal_rsi(current_rsi),
        "Интерпретация": "Технический индикатор импульса; зоны 30/70 требуют контекста.",
    },
    {
        "Индикатор": "Building Permits YoY",
        "Текущее значение": (
            f"{permits_yoy * 100:+.1f}%" if permits_yoy is not None else "N/A"
        ),
        "Изменение / статус": signal_yoy(
            1 + permits_yoy if permits_yoy is not None else None, 1
        ) if permits_yoy is not None else "⚪ Нет данных",
        "Интерпретация": "Динамика разрешений на строительство.",
    },
    {
        "Индикатор": "Housing Starts YoY",
        "Текущее значение": (
            f"{starts_yoy * 100:+.1f}%" if starts_yoy is not None else "N/A"
        ),
        "Изменение / статус": signal_yoy(
            1 + starts_yoy if starts_yoy is not None else None, 1
        ) if starts_yoy is not None else "⚪ Нет данных",
        "Интерпретация": "Динамика начала строительства жилья.",
    },
    {
        "Индикатор": "Gross Margin Lennar",
        "Текущее значение": fmt_pct(gross_margin),
        "Изменение / статус": "ℹ️ Отслеживать квартальную динамику",
        "Интерпретация": "Снижение маржи может отражать изменение цен, затрат или структуры продаж.",
    },
    {
        "Индикатор": "US 10Y",
        "Текущее значение": f"{fmt_number(us10y_value, 2)}%",
        "Изменение / статус": "ℹ️ Мониторинг стоимости финансирования",
        "Интерпретация": "Доходность 10-летних Treasuries является одним из ориентиров стоимости долгосрочного финансирования.",
    },
]

st.dataframe(
    pd.DataFrame(signal_rows),
    use_container_width=True,
    hide_index=True,
)


# ============================================================
# Financial data details
# ============================================================

with st.expander("📋 Дополнительные данные Lennar"):
    fields = {
        "Название": info.get("longName"),
        "Сектор": info.get("sector"),
        "Индустрия": info.get("industry"),
        "Market Cap": info.get("marketCap"),
        "Trailing EPS": info.get("trailingEps"),
        "Forward P/E": info.get("forwardPE"),
        "Enterprise Value": info.get("enterpriseValue"),
        "Revenue": info.get("totalRevenue"),
        "Free Cash Flow": info.get("freeCashflow"),
        "52W High": info.get("fiftyTwoWeekHigh"),
        "52W Low": info.get("fiftyTwoWeekLow"),
    }

    details = pd.DataFrame(
        [{"Показатель": k, "Значение": v} for k, v in fields.items()]
    )

    st.dataframe(details, use_container_width=True, hide_index=True)


# ============================================================
# Footer
# ============================================================

st.divider()
st.caption(
    f"Последняя загрузка данных: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}. "
    "Информация предназначена для мониторинга и анализа, а не является инвестиционной рекомендацией."
)
