#!/usr/bin/env python3
"""
미국 시장 트랙커 — Daily US Market Dashboard for Korean Investors
Pulls data via yfinance, generates static HTML dashboard.
Designed to run daily at 06:10 KST via GitHub Actions.
"""

import json
import os
import time
import warnings
from datetime import datetime, timezone, timedelta

import yfinance as yf
import pandas as pd

warnings.filterwarnings("ignore")

# ── Paths ──────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
OUTPUT_DIR = SCRIPT_DIR  # HTML goes to repo root for GitHub Pages

KST = timezone(timedelta(hours=9))
NOW_KST = datetime.now(KST)
UPDATE_TIME = NOW_KST.strftime("%Y.%m.%d %H:%M KST")


# ── Helper Functions ───────────────────────────────────────────────────

def load_json(filename):
    with open(os.path.join(DATA_DIR, filename), "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(filename, data):
    with open(os.path.join(DATA_DIR, filename), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fmt_number(n):
    """Format large numbers: 1234567 -> 1.23M"""
    if n is None or pd.isna(n):
        return "N/A"
    if abs(n) >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if abs(n) >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if abs(n) >= 1_000:
        return f"{n / 1_000:.1f}K"
    return f"{n:.0f}"


def fmt_price(p):
    if p is None or pd.isna(p):
        return "N/A"
    return f"${p:,.2f}"


def fmt_pct(p):
    if p is None or pd.isna(p):
        return "N/A"
    return f"{p:+.2f}%"


def safe_download(tickers, period="1d", retries=2):
    """Download with retry logic."""
    for attempt in range(retries):
        try:
            data = yf.download(tickers, period=period, progress=False, threads=True)
            return data
        except Exception as e:
            print(f"  Retry {attempt+1}/{retries}: {e}")
            time.sleep(5)
    return pd.DataFrame()


def batch_download(ticker_list, period="1d", batch_size=100):
    """Download in batches to avoid rate limits."""
    all_data = {}
    for i in range(0, len(ticker_list), batch_size):
        batch = ticker_list[i:i + batch_size]
        print(f"  Downloading batch {i//batch_size + 1} ({len(batch)} tickers)...")
        data = safe_download(batch, period=period)
        if not data.empty:
            if len(batch) == 1:
                # Single ticker returns different structure
                for col in ["Close", "Volume", "High", "Low", "Open"]:
                    if col in data.columns:
                        all_data.setdefault(col, {})[batch[0]] = data[col].iloc[-1] if len(data) > 0 else None
            else:
                for col in ["Close", "Volume", "High", "Low", "Open"]:
                    if col in data.columns:
                        for ticker in batch:
                            try:
                                val = data[col][ticker].iloc[-1] if ticker in data[col].columns else None
                                all_data.setdefault(col, {})[ticker] = val
                            except (KeyError, IndexError):
                                all_data.setdefault(col, {})[ticker] = None
        time.sleep(2)  # Be nice to Yahoo
    return all_data


# ── Data Collection Functions ──────────────────────────────────────────

def get_index_data():
    """Fetch major index prices and KRW exchange rate."""
    print("📊 Fetching index data...")
    indices = {
        "^GSPC": "S&P 500",
        "^IXIC": "나스닥",
        "^DJI": "다우존스",
        "KRW=X": "원/달러",
    }
    result = {}
    for symbol, name in indices.items():
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="5d")
            if len(hist) >= 2:
                current = hist["Close"].iloc[-1]
                prev = hist["Close"].iloc[-2]
                change_pct = ((current - prev) / prev) * 100
                result[name] = {
                    "value": current,
                    "change_pct": change_pct,
                    "formatted_value": f"{current:,.2f}",
                    "formatted_change": fmt_pct(change_pct),
                }
            elif len(hist) == 1:
                current = hist["Close"].iloc[-1]
                result[name] = {
                    "value": current,
                    "change_pct": 0,
                    "formatted_value": f"{current:,.2f}",
                    "formatted_change": "0.00%",
                }
        except Exception as e:
            print(f"  Error fetching {symbol}: {e}")
            result[name] = {"value": 0, "change_pct": 0, "formatted_value": "N/A", "formatted_change": "N/A"}
    return result


def get_stock_data(sp500_tickers, russell_tickers):
    """Fetch stock data for gainers, unusual volume, 52-week high."""
    print("📈 Fetching stock data...")

    all_tickers = list(sp500_tickers.keys()) + list(russell_tickers.keys())
    # Remove duplicates
    all_tickers = list(dict.fromkeys(all_tickers))
    print(f"  Total tickers: {len(all_tickers)}")

    # Get today's data
    today_data = batch_download(all_tickers, period="1d")

    # Get 1-month data for volume average
    print("  Fetching 1-month history for volume average...")
    vol_data = {}
    for i in range(0, len(all_tickers), 100):
        batch = all_tickers[i:i + 100]
        try:
            hist = yf.download(batch, period="1mo", progress=False, threads=True)
            if not hist.empty and "Volume" in hist.columns:
                if len(batch) == 1:
                    vol_data[batch[0]] = hist["Volume"].mean()
                else:
                    for t in batch:
                        try:
                            vol_data[t] = hist["Volume"][t].mean()
                        except (KeyError, TypeError):
                            pass
        except Exception as e:
            print(f"  Error: {e}")
        time.sleep(2)

    # Process results
    stocks = []
    for ticker in all_tickers:
        try:
            close = today_data.get("Close", {}).get(ticker)
            volume = today_data.get("Volume", {}).get(ticker)
            open_price = today_data.get("Open", {}).get(ticker)

            if close is None or pd.isna(close) or close == 0:
                continue

            change_pct = ((close - open_price) / open_price * 100) if open_price and open_price > 0 else 0
            avg_vol = vol_data.get(ticker, 0)
            vol_ratio = (volume / avg_vol) if avg_vol and avg_vol > 0 else 0

            # Get info from our ticker databases
            info = sp500_tickers.get(ticker, russell_tickers.get(ticker, {}))
            name = info.get("name", ticker)
            sector_kr = info.get("sector_kr", "")

            stocks.append({
                "ticker": ticker,
                "name": name,
                "sector_kr": sector_kr,
                "close": close,
                "change_pct": change_pct,
                "volume": volume,
                "avg_volume": avg_vol,
                "vol_ratio": vol_ratio,
            })
        except Exception:
            continue

    # Top 10 Gainers
    gainers = sorted(stocks, key=lambda x: x["change_pct"], reverse=True)[:10]

    # Top 10 Unusual Volume (min 2x average)
    unusual_vol = sorted(
        [s for s in stocks if s["vol_ratio"] >= 1.5],
        key=lambda x: x["vol_ratio"],
        reverse=True
    )[:10]

    # 52-week high tracking
    print("  Checking 52-week highs...")
    high_52w_file = os.path.join(DATA_DIR, "52week_highs.json")
    try:
        with open(high_52w_file, "r") as f:
            stored_highs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        stored_highs = {}

    new_highs = []
    # Check a subset (top performing stocks are most likely to hit new highs)
    candidates = sorted(stocks, key=lambda x: x["change_pct"], reverse=True)[:200]
    check_tickers = [s["ticker"] for s in candidates]

    for i in range(0, len(check_tickers), 50):
        batch = check_tickers[i:i + 50]
        try:
            hist = yf.download(batch, period="1y", progress=False, threads=True)
            if not hist.empty and "High" in hist.columns:
                if len(batch) == 1:
                    yr_high = hist["High"].max()
                    ticker = batch[0]
                    close = today_data.get("Close", {}).get(ticker, 0)
                    if close and not pd.isna(close):
                        prev_high = stored_highs.get(ticker, 0)
                        if close >= yr_high * 0.99:  # Within 1% of 52-week high
                            stock_info = next((s for s in stocks if s["ticker"] == ticker), None)
                            if stock_info:
                                new_highs.append({
                                    **stock_info,
                                    "prev_high": float(yr_high) if not pd.isna(yr_high) else 0,
                                    "beat_pct": ((close - yr_high) / yr_high * 100) if yr_high > 0 else 0
                                })
                        stored_highs[ticker] = max(float(close), prev_high)
                else:
                    for ticker in batch:
                        try:
                            yr_high = hist["High"][ticker].max()
                            close = today_data.get("Close", {}).get(ticker, 0)
                            if close and not pd.isna(close) and not pd.isna(yr_high):
                                prev_high = stored_highs.get(ticker, 0)
                                if close >= yr_high * 0.99:
                                    stock_info = next((s for s in stocks if s["ticker"] == ticker), None)
                                    if stock_info:
                                        new_highs.append({
                                            **stock_info,
                                            "prev_high": float(yr_high),
                                            "beat_pct": ((close - yr_high) / yr_high * 100) if yr_high > 0 else 0
                                        })
                                stored_highs[ticker] = max(float(close), prev_high)
                        except (KeyError, TypeError):
                            pass
        except Exception as e:
            print(f"  52w error: {e}")
        time.sleep(2)

    save_json("52week_highs.json", stored_highs)
    new_highs_top10 = sorted(new_highs, key=lambda x: x.get("beat_pct", 0), reverse=True)[:10]

    return gainers, unusual_vol, new_highs_top10


def get_etf_data(etf_list):
    """Fetch ETF data for gainers, losers, most active."""
    print("📊 Fetching ETF data...")
    tickers = list(etf_list.keys())

    today_data = batch_download(tickers, period="1d")

    etfs = []
    for ticker in tickers:
        try:
            close = today_data.get("Close", {}).get(ticker)
            volume = today_data.get("Volume", {}).get(ticker)
            open_price = today_data.get("Open", {}).get(ticker)

            if close is None or pd.isna(close) or close == 0:
                continue

            change_pct = ((close - open_price) / open_price * 100) if open_price and open_price > 0 else 0

            info = etf_list[ticker]
            etfs.append({
                "ticker": ticker,
                "name": info["name"],
                "category": info["category"],
                "close": close,
                "change_pct": change_pct,
                "volume": volume if volume and not pd.isna(volume) else 0,
            })
        except Exception:
            continue

    gainers = sorted(etfs, key=lambda x: x["change_pct"], reverse=True)[:10]
    losers = sorted(etfs, key=lambda x: x["change_pct"])[:10]
    most_active = sorted(etfs, key=lambda x: x["volume"], reverse=True)[:10]

    return gainers, losers, most_active


def get_options_data(options_tickers):
    """Fetch options data for bullish/bearish signals and unusual activity."""
    print("🎯 Fetching options data...")
    tickers = list(options_tickers.keys())

    bullish = []
    bearish = []
    unusual = []

    for ticker_symbol in tickers:
        try:
            ticker = yf.Ticker(ticker_symbol)
            # Get stock price
            hist = ticker.history(period="2d")
            if hist.empty:
                continue
            current_price = hist["Close"].iloc[-1]

            # Get options chain (nearest expiration)
            expirations = ticker.options
            if not expirations:
                continue

            # Use nearest expiration
            exp = expirations[0]
            chain = ticker.option_chain(exp)
            calls = chain.calls
            puts = chain.puts

            total_call_vol = calls["volume"].sum() if "volume" in calls.columns else 0
            total_put_vol = puts["volume"].sum() if "volume" in puts.columns else 0
            total_call_oi = calls["openInterest"].sum() if "openInterest" in calls.columns else 0
            total_put_oi = puts["openInterest"].sum() if "openInterest" in puts.columns else 0

            if pd.isna(total_call_vol):
                total_call_vol = 0
            if pd.isna(total_put_vol):
                total_put_vol = 0
            if pd.isna(total_call_oi):
                total_call_oi = 0
            if pd.isna(total_put_oi):
                total_put_oi = 0

            # Call/Put volume ratio
            call_ratio = (total_call_vol / total_call_oi) if total_call_oi > 0 else 0
            put_ratio = (total_put_vol / total_put_oi) if total_put_oi > 0 else 0

            info = options_tickers[ticker_symbol]

            entry = {
                "ticker": ticker_symbol,
                "name": info["name"],
                "category": info["category"],
                "price": current_price,
                "call_volume": total_call_vol,
                "put_volume": total_put_vol,
                "call_oi": total_call_oi,
                "put_oi": total_put_oi,
                "call_ratio": call_ratio,
                "put_ratio": put_ratio,
                "expiration": exp,
            }

            # Determine signal strength (1-3 dots)
            def signal_strength(ratio):
                if ratio >= 3.0:
                    return 3
                elif ratio >= 2.0:
                    return 2
                elif ratio >= 1.0:
                    return 1
                return 0

            # Bullish: high call volume relative to OI
            if call_ratio >= 1.0:
                entry["signal"] = signal_strength(call_ratio)
                entry["vol_ratio"] = call_ratio
                bullish.append(entry)

            # Bearish: high put volume relative to OI
            if put_ratio >= 1.0:
                entry_bear = entry.copy()
                entry_bear["signal"] = signal_strength(put_ratio)
                entry_bear["vol_ratio"] = put_ratio
                bearish.append(entry_bear)

            # Unusual: either direction, large dollar volume
            total_vol = total_call_vol + total_put_vol
            if total_vol > 10000:
                direction = "bullish" if total_call_vol > total_put_vol else "bearish"
                # Estimate dollar volume (rough)
                avg_premium = 5.0  # rough average
                est_dollar = total_vol * avg_premium * 100
                unusual.append({
                    **entry,
                    "direction": direction,
                    "total_volume": total_vol,
                    "est_dollar_volume": est_dollar,
                })

            time.sleep(1)  # Rate limit for options

        except Exception as e:
            print(f"  Options error for {ticker_symbol}: {e}")
            continue

    bullish_top10 = sorted(bullish, key=lambda x: x["vol_ratio"], reverse=True)[:10]
    bearish_top10 = sorted(bearish, key=lambda x: x["vol_ratio"], reverse=True)[:10]
    unusual_top10 = sorted(unusual, key=lambda x: x["total_volume"], reverse=True)[:10]

    return bullish_top10, bearish_top10, unusual_top10


# ── HTML Generation ────────────────────────────────────────────────────

def generate_html(index_data, gainers, unusual_vol, new_highs,
                  etf_gainers, etf_losers, etf_active,
                  opt_bullish, opt_bearish, opt_unusual):
    """Generate complete HTML dashboard."""

    def change_class(pct):
        return "change-positive" if pct >= 0 else "change-negative"

    def index_change_class(name, pct):
        # For KRW, positive = weaker won = show as red for Korean investor perspective
        if name == "원/달러":
            return "change-negative" if pct > 0 else "change-positive"
        return "change-positive" if pct >= 0 else "change-negative"

    def render_stock_rows(items, show_sector=True, show_vol_ratio=False, show_52w=False):
        rows = []
        for i, item in enumerate(items):
            rank = i + 1
            change_cls = change_class(item.get("change_pct", 0))

            sector_td = ""
            if show_sector:
                sector_kr = item.get("sector_kr", "")
                if sector_kr:
                    sector_td = f'<td class="hide-mobile"><span class="sector-tag">{sector_kr}</span></td>'
                else:
                    sector_td = '<td class="hide-mobile"></td>'

            vol_td = ""
            if show_vol_ratio:
                ratio = item.get("vol_ratio", 0)
                vol_cls = "volume-extreme" if ratio >= 4 else "volume-high"
                emoji = " 🔴" if ratio >= 4 else ""
                vol_td = f'''
                    <td class="right volume">{fmt_number(item.get("volume", 0))}</td>
                    <td class="right"><span class="volume-ratio {vol_cls}">{ratio:.1f}배{emoji}</span></td>
                '''
            elif show_52w:
                vol_td = f'''
                    <td class="right volume">{fmt_price(item.get("prev_high", 0))}</td>
                    <td class="right {change_cls}">{fmt_pct(item.get("beat_pct", 0))}</td>
                '''
            else:
                vol_td = f'<td class="right volume">{fmt_number(item.get("volume", 0))}</td>'

            rows.append(f'''
                <tr onclick="openChart('{item["ticker"]}', '{item["name"].replace("'", "")}')" style="cursor:pointer;">
                    <td class="rank">{rank}</td>
                    <td><div class="ticker-cell"><span class="ticker-symbol">{item["ticker"]}</span><span class="ticker-name">{item["name"]}</span></div></td>
                    {sector_td}
                    <td class="right price">{fmt_price(item.get("close", 0))}</td>
                    <td class="right {change_cls}">{fmt_pct(item.get("change_pct", 0))}</td>
                    {vol_td}
                </tr>
            ''')
        return "\n".join(rows)

    def render_etf_rows(items):
        rows = []
        for i, item in enumerate(items):
            rank = i + 1
            change_cls = change_class(item.get("change_pct", 0))
            rows.append(f'''
                <tr onclick="openChart('{item["ticker"]}', '{item["name"].replace("'", "")}')" style="cursor:pointer;">
                    <td class="rank">{rank}</td>
                    <td><div class="ticker-cell"><span class="ticker-symbol">{item["ticker"]}</span><span class="ticker-name">{item["name"]}</span></div></td>
                    <td><span class="etf-category">{item.get("category", "")}</span></td>
                    <td class="right price">{fmt_price(item.get("close", 0))}</td>
                    <td class="right {change_cls}">{fmt_pct(item.get("change_pct", 0))}</td>
                    <td class="right volume hide-mobile">{fmt_number(item.get("volume", 0))}</td>
                </tr>
            ''')
        return "\n".join(rows)

    def render_signal_dots(strength, color):
        dots = []
        for i in range(3):
            cls = f"active-{color}" if i < strength else "inactive"
            dots.append(f'<span class="signal-dot {cls}"></span>')
        return f'<div class="signal-dots">{"".join(dots)}</div>'

    def render_options_bullish_rows(items):
        rows = []
        for i, item in enumerate(items):
            rank = i + 1
            ratio = item.get("vol_ratio", 0)
            vol_cls = "volume-extreme" if ratio >= 3 else "volume-high"
            signal = render_signal_dots(item.get("signal", 1), "green")
            rows.append(f'''
                <tr onclick="openChart('{item["ticker"]}', '{item["name"].replace("'", "")}')" style="cursor:pointer;">
                    <td class="rank">{rank}</td>
                    <td><div class="ticker-cell"><span class="ticker-symbol">{item["ticker"]}</span><span class="ticker-name">{item["name"]}</span></div></td>
                    <td class="right price">{fmt_price(item.get("price", 0))}</td>
                    <td class="right volume">{fmt_number(item.get("call_volume", 0))}</td>
                    <td class="right"><span class="volume-ratio {vol_cls}">{ratio:.1f}배</span></td>
                    <td class="right">{signal}</td>
                </tr>
            ''')
        return "\n".join(rows)

    def render_options_bearish_rows(items):
        rows = []
        for i, item in enumerate(items):
            rank = i + 1
            ratio = item.get("vol_ratio", 0)
            vol_cls = "volume-extreme" if ratio >= 3 else "volume-high"
            signal = render_signal_dots(item.get("signal", 1), "red")
            rows.append(f'''
                <tr onclick="openChart('{item["ticker"]}', '{item["name"].replace("'", "")}')" style="cursor:pointer;">
                    <td class="rank">{rank}</td>
                    <td><div class="ticker-cell"><span class="ticker-symbol">{item["ticker"]}</span><span class="ticker-name">{item["name"]}</span></div></td>
                    <td class="right price">{fmt_price(item.get("price", 0))}</td>
                    <td class="right volume">{fmt_number(item.get("put_volume", 0))}</td>
                    <td class="right"><span class="volume-ratio {vol_cls}">{ratio:.1f}배</span></td>
                    <td class="right">{signal}</td>
                </tr>
            ''')
        return "\n".join(rows)

    def render_unusual_options_rows(items):
        rows = []
        for item in items:
            direction = item.get("direction", "bullish")
            dir_cls = "direction-bullish" if direction == "bullish" else "direction-bearish"
            dir_emoji = "🟢" if direction == "bullish" else "🔴"
            dir_text = "강세" if direction == "bullish" else "약세"
            est_dollar = item.get("est_dollar_volume", 0)

            # Generate interpretation
            if direction == "bullish":
                interp = "대규모 콜 매수" if item.get("call_volume", 0) > 50000 else "콜 거래량 증가"
            else:
                interp = "대규모 풋 매수" if item.get("put_volume", 0) > 50000 else "풋 거래량 증가"

            rows.append(f'''
                <tr onclick="openChart('{item["ticker"]}', '{item["name"].replace("'", "")}')" style="cursor:pointer;">
                    <td><div class="ticker-cell"><span class="ticker-symbol">{item["ticker"]}</span><span class="ticker-name">{item["name"]}</span></div></td>
                    <td><span class="direction-badge {dir_cls}">{dir_emoji} {dir_text}</span></td>
                    <td class="right price">{fmt_number(est_dollar)}</td>
                    <td class="right volume hide-mobile">{item.get("expiration", "N/A")}</td>
                    <td class="interpretation">{interp}</td>
                </tr>
            ''')
        return "\n".join(rows)

    # Build index bar
    index_items = []
    for name in ["S&P 500", "나스닥", "다우존스", "원/달러"]:
        d = index_data.get(name, {})
        cls = index_change_class(name, d.get("change_pct", 0))
        index_items.append(f'''
            <div class="index-item">
                <div class="label">{name}</div>
                <div>
                    <span class="value">{d.get("formatted_value", "N/A")}</span>
                    <span class="change {cls}">{d.get("formatted_change", "N/A")}</span>
                </div>
            </div>
        ''')
    index_bar_html = "\n".join(index_items)

    # Render all table rows
    gainers_html = render_stock_rows(gainers, show_sector=True)
    unusual_vol_html = render_stock_rows(unusual_vol, show_sector=False, show_vol_ratio=True)
    new_highs_html = render_stock_rows(new_highs, show_sector=True, show_52w=True)
    etf_gainers_html = render_etf_rows(etf_gainers)
    etf_losers_html = render_etf_rows(etf_losers)
    etf_active_html = render_etf_rows(etf_active)
    opt_bullish_html = render_options_bullish_rows(opt_bullish)
    opt_bearish_html = render_options_bearish_rows(opt_bearish)
    opt_unusual_html = render_unusual_options_rows(opt_unusual)

    # Generate empty state messages
    def empty_msg(data, msg="데이터를 불러오는 중 오류가 발생했습니다."):
        if not data:
            return f'<tr><td colspan="8" style="text-align:center;color:var(--text-dim);padding:24px;">{msg}</td></tr>'
        return ""

    html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🇺🇸 미국 시장 트랙커</title>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-primary: #0a0a0f;
            --bg-secondary: #12121a;
            --bg-card: #16161f;
            --bg-hover: #1e1e2a;
            --border: #2a2a3a;
            --text-primary: #e8e8f0;
            --text-secondary: #8888a0;
            --text-dim: #555568;
            --green: #00d47e;
            --green-bg: rgba(0,212,126,0.08);
            --red: #ff4d6a;
            --red-bg: rgba(255,77,106,0.08);
            --accent: #6c8aff;
            --accent-bg: rgba(108,138,255,0.08);
            --yellow: #ffd666;
            --yellow-bg: rgba(255,214,102,0.08);
        }}
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ background:var(--bg-primary); color:var(--text-primary); font-family:'Noto Sans KR',sans-serif; line-height:1.6; min-height:100vh; }}
        .container {{ max-width:1200px; margin:0 auto; padding:20px 24px; }}
        .header {{ margin-bottom:24px; }}
        .header-top {{ display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:16px; flex-wrap:wrap; gap:8px; }}
        .header-title {{ display:flex; align-items:center; gap:12px; }}
        .header-title h1 {{ font-size:24px; font-weight:700; letter-spacing:-0.5px; }}
        .update-time {{ font-family:'JetBrains Mono',monospace; font-size:13px; color:var(--text-dim); background:var(--bg-secondary); padding:6px 12px; border-radius:6px; border:1px solid var(--border); }}
        .update-time .dot {{ display:inline-block; width:6px; height:6px; background:var(--green); border-radius:50%; margin-right:6px; animation:pulse 2s infinite; }}
        @keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:0.3}} }}
        .index-bar {{ display:flex; gap:12px; margin-bottom:12px; flex-wrap:wrap; }}
        .index-item {{ background:var(--bg-secondary); border:1px solid var(--border); border-radius:8px; padding:12px 16px; flex:1; min-width:160px; }}
        .index-item .label {{ font-size:11px; font-weight:500; color:var(--text-dim); text-transform:uppercase; letter-spacing:0.5px; margin-bottom:4px; }}
        .index-item .value {{ font-family:'JetBrains Mono',monospace; font-size:18px; font-weight:600; }}
        .index-item .change {{ font-family:'JetBrains Mono',monospace; font-size:13px; font-weight:500; margin-left:6px; }}
        .color-note {{ font-size:12px; color:var(--text-dim); margin-bottom:20px; padding:8px 14px; background:var(--bg-secondary); border-radius:6px; border-left:3px solid var(--accent); display:inline-block; }}
        .color-note .green-dot {{ color:var(--green); }}
        .color-note .red-dot {{ color:var(--red); }}
        .tab-container {{ display:flex; gap:4px; margin-bottom:24px; background:var(--bg-secondary); padding:4px; border-radius:10px; border:1px solid var(--border); }}
        .tab-btn {{ flex:1; padding:12px 20px; background:transparent; border:none; border-radius:8px; color:var(--text-secondary); font-family:'Noto Sans KR',sans-serif; font-size:15px; font-weight:500; cursor:pointer; transition:all 0.25s ease; display:flex; align-items:center; justify-content:center; gap:8px; }}
        .tab-btn:hover {{ color:var(--text-primary); background:var(--bg-hover); }}
        .tab-btn.active {{ background:var(--bg-card); color:var(--text-primary); font-weight:600; box-shadow:0 2px 8px rgba(0,0,0,0.3); }}
        .tab-content {{ display:none; }}
        .tab-content.active {{ display:block; animation:fadeIn 0.3s ease; }}
        @keyframes fadeIn {{ from{{opacity:0;transform:translateY(8px)}} to{{opacity:1;transform:translateY(0)}} }}
        .section {{ margin-bottom:28px; }}
        .section-header {{ display:flex; align-items:center; gap:10px; margin-bottom:14px; padding-bottom:10px; border-bottom:1px solid var(--border); }}
        .section-icon {{ font-size:20px; }}
        .section-title {{ font-size:16px; font-weight:600; letter-spacing:-0.3px; }}
        .section-badge {{ font-size:11px; font-weight:500; padding:3px 8px; border-radius:4px; margin-left:auto; }}
        .badge-green {{ background:var(--green-bg); color:var(--green); }}
        .badge-red {{ background:var(--red-bg); color:var(--red); }}
        .badge-blue {{ background:var(--accent-bg); color:var(--accent); }}
        .badge-yellow {{ background:var(--yellow-bg); color:var(--yellow); }}
        .table-wrapper {{ overflow-x:auto; border-radius:8px; border:1px solid var(--border); background:var(--bg-card); }}
        .data-table {{ width:100%; border-collapse:collapse; font-size:14px; }}
        .data-table thead th {{ font-size:11px; font-weight:500; color:var(--text-dim); text-transform:uppercase; letter-spacing:0.5px; padding:8px 12px; text-align:left; border-bottom:1px solid var(--border); white-space:nowrap; }}
        .data-table thead th.right {{ text-align:right; }}
        .data-table tbody tr {{ border-bottom:1px solid rgba(42,42,58,0.5); transition:background 0.15s ease; }}
        .data-table tbody tr:hover {{ background:var(--bg-hover); }}
        .data-table tbody td {{ padding:10px 12px; vertical-align:middle; }}
        .data-table tbody td.right {{ text-align:right; }}
        .rank {{ font-family:'JetBrains Mono',monospace; font-size:12px; font-weight:600; color:var(--text-dim); width:32px; text-align:center; }}
        .ticker-cell {{ display:flex; flex-direction:column; gap:2px; }}
        .ticker-symbol {{ font-family:'JetBrains Mono',monospace; font-weight:600; font-size:14px; color:var(--text-primary); }}
        .ticker-name {{ font-size:12px; color:var(--text-secondary); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:180px; }}
        .sector-tag {{ font-size:11px; padding:2px 8px; border-radius:4px; background:var(--bg-secondary); border:1px solid var(--border); color:var(--text-secondary); white-space:nowrap; }}
        .price {{ font-family:'JetBrains Mono',monospace; font-weight:500; font-size:14px; }}
        .change-positive {{ color:var(--green); font-family:'JetBrains Mono',monospace; font-weight:600; }}
        .change-negative {{ color:var(--red); font-family:'JetBrains Mono',monospace; font-weight:600; }}
        .volume {{ font-family:'JetBrains Mono',monospace; font-size:13px; color:var(--text-secondary); }}
        .volume-ratio {{ font-family:'JetBrains Mono',monospace; font-weight:600; font-size:13px; }}
        .volume-high {{ color:var(--yellow); }}
        .volume-extreme {{ color:var(--red); }}
        .signal-dots {{ display:flex; gap:3px; justify-content:flex-end; }}
        .signal-dot {{ width:8px; height:8px; border-radius:50%; }}
        .signal-dot.active-green {{ background:var(--green); }}
        .signal-dot.active-red {{ background:var(--red); }}
        .signal-dot.inactive {{ background:var(--border); }}
        .direction-badge {{ font-size:12px; font-weight:600; padding:3px 10px; border-radius:4px; white-space:nowrap; }}
        .direction-bullish {{ background:var(--green-bg); color:var(--green); }}
        .direction-bearish {{ background:var(--red-bg); color:var(--red); }}
        .interpretation {{ font-size:12px; color:var(--text-secondary); }}
        .etf-category {{ font-size:11px; color:var(--accent); }}
        .footer {{ margin-top:40px; padding-top:20px; border-top:1px solid var(--border); text-align:center; font-size:12px; color:var(--text-dim); }}
        .footer a {{ color:var(--accent); text-decoration:none; }}
        /* Modal */
        .modal-overlay {{ display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.85); z-index:1000; justify-content:center; align-items:center; padding:20px; }}
        .modal-overlay.active {{ display:flex; }}
        .modal {{ background:var(--bg-card); border:1px solid var(--border); border-radius:12px; width:100%; max-width:800px; max-height:90vh; overflow:hidden; position:relative; }}
        .modal-header {{ display:flex; justify-content:space-between; align-items:center; padding:16px 20px; border-bottom:1px solid var(--border); }}
        .modal-header .ticker-info {{ display:flex; align-items:center; gap:12px; }}
        .modal-header .modal-ticker {{ font-family:'JetBrains Mono',monospace; font-size:20px; font-weight:700; }}
        .modal-header .modal-name {{ font-size:14px; color:var(--text-secondary); }}
        .modal-close {{ background:none; border:none; color:var(--text-secondary); font-size:24px; cursor:pointer; padding:4px 8px; border-radius:4px; }}
        .modal-close:hover {{ background:var(--bg-hover); color:var(--text-primary); }}
        .modal-chart {{ width:100%; height:450px; }}
        @media (max-width:768px) {{
            .container {{ padding:12px 14px; }}
            .header-title h1 {{ font-size:20px; }}
            .index-item {{ min-width:140px; padding:10px 12px; }}
            .index-item .value {{ font-size:15px; }}
            .data-table {{ font-size:13px; }}
            .data-table thead th, .data-table tbody td {{ padding:8px 8px; }}
            .ticker-name {{ max-width:120px; }}
            .tab-btn {{ font-size:14px; padding:10px 12px; }}
            .hide-mobile {{ display:none; }}
            .modal-chart {{ height:350px; }}
        }}
        @media (max-width:480px) {{
            .index-item {{ min-width:100%; }}
            .header-top {{ flex-direction:column; }}
            .modal {{ max-height:95vh; }}
            .modal-chart {{ height:300px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="header-top">
                <div class="header-title">
                    <span style="font-size:28px;">🇺🇸</span>
                    <h1>미국 시장 트랙커</h1>
                </div>
                <div class="update-time">
                    <span class="dot"></span>
                    마지막 업데이트: {UPDATE_TIME}
                </div>
            </div>
            <div class="index-bar">
                {index_bar_html}
            </div>
            <div class="color-note">
                💡 본 페이지는 미국식 색상 기준을 사용합니다: <span class="green-dot">🟢 상승</span> / <span class="red-dot">🔴 하락</span>
            </div>
        </div>

        <div class="tab-container">
            <button class="tab-btn active" onclick="switchTab('stocks')"><span style="font-size:18px;">📈</span> 주식</button>
            <button class="tab-btn" onclick="switchTab('etf')"><span style="font-size:18px;">📊</span> ETF</button>
            <button class="tab-btn" onclick="switchTab('options')"><span style="font-size:18px;">🎯</span> 옵션</button>
        </div>

        <!-- 주식 TAB -->
        <div id="tab-stocks" class="tab-content active">
            <div class="section">
                <div class="section-header">
                    <span class="section-icon">🔥</span>
                    <span class="section-title">오늘의 급등주 Top 10</span>
                    <span class="section-badge badge-green">S&P 500 + Russell 2000</span>
                </div>
                <div class="table-wrapper">
                    <table class="data-table">
                        <thead><tr><th>순위</th><th>종목</th><th class="hide-mobile">섹터</th><th class="right">종가 ($)</th><th class="right">등락률</th><th class="right">거래량</th></tr></thead>
                        <tbody>{gainers_html or empty_msg(gainers)}</tbody>
                    </table>
                </div>
            </div>
            <div class="section">
                <div class="section-header">
                    <span class="section-icon">📊</span>
                    <span class="section-title">이상 거래량 Top 10</span>
                    <span class="section-badge badge-yellow">평균 대비 급증</span>
                </div>
                <div class="table-wrapper">
                    <table class="data-table">
                        <thead><tr><th>순위</th><th>종목</th><th class="right">종가 ($)</th><th class="right">등락률</th><th class="right">오늘 거래량</th><th class="right">평균 대비</th></tr></thead>
                        <tbody>{unusual_vol_html or empty_msg(unusual_vol)}</tbody>
                    </table>
                </div>
            </div>
            <div class="section">
                <div class="section-header">
                    <span class="section-icon">🏆</span>
                    <span class="section-title">52주 신고가</span>
                    <span class="section-badge badge-blue">오늘 갱신</span>
                </div>
                <div class="table-wrapper">
                    <table class="data-table">
                        <thead><tr><th>순위</th><th>종목</th><th class="hide-mobile">섹터</th><th class="right">종가 ($)</th><th class="right">이전 최고가</th><th class="right">갱신폭</th></tr></thead>
                        <tbody>{new_highs_html or empty_msg(new_highs, "오늘 52주 신고가 갱신 종목이 없습니다.")}</tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- ETF TAB -->
        <div id="tab-etf" class="tab-content">
            <div class="section">
                <div class="section-header">
                    <span class="section-icon">🟢</span>
                    <span class="section-title">ETF 수익률 Top 10</span>
                    <span class="section-badge badge-green">오늘의 상승</span>
                </div>
                <div class="table-wrapper">
                    <table class="data-table">
                        <thead><tr><th>순위</th><th>ETF</th><th>카테고리</th><th class="right">종가 ($)</th><th class="right">등락률</th><th class="right hide-mobile">거래량</th></tr></thead>
                        <tbody>{etf_gainers_html or empty_msg(etf_gainers)}</tbody>
                    </table>
                </div>
            </div>
            <div class="section">
                <div class="section-header">
                    <span class="section-icon">🔴</span>
                    <span class="section-title">ETF 하락률 Top 10</span>
                    <span class="section-badge badge-red">오늘의 하락</span>
                </div>
                <div class="table-wrapper">
                    <table class="data-table">
                        <thead><tr><th>순위</th><th>ETF</th><th>카테고리</th><th class="right">종가 ($)</th><th class="right">등락률</th><th class="right hide-mobile">거래량</th></tr></thead>
                        <tbody>{etf_losers_html or empty_msg(etf_losers)}</tbody>
                    </table>
                </div>
            </div>
            <div class="section">
                <div class="section-header">
                    <span class="section-icon">💰</span>
                    <span class="section-title">ETF 거래량 Top 10</span>
                    <span class="section-badge badge-blue">가장 활발한 ETF</span>
                </div>
                <div class="table-wrapper">
                    <table class="data-table">
                        <thead><tr><th>순위</th><th>ETF</th><th>카테고리</th><th class="right">종가 ($)</th><th class="right">등락률</th><th class="right">거래량</th></tr></thead>
                        <tbody>{etf_active_html or empty_msg(etf_active)}</tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- 옵션 TAB -->
        <div id="tab-options" class="tab-content">
            <div class="section">
                <div class="section-header">
                    <span class="section-icon">📈</span>
                    <span class="section-title">옵션 강세 신호 Top 10</span>
                    <span class="section-badge badge-green">콜 옵션 급증</span>
                </div>
                <div class="table-wrapper">
                    <table class="data-table">
                        <thead><tr><th>순위</th><th>종목</th><th class="right">주가 ($)</th><th class="right">콜 거래량</th><th class="right">평소 대비</th><th class="right">신호강도</th></tr></thead>
                        <tbody>{opt_bullish_html or empty_msg(opt_bullish)}</tbody>
                    </table>
                </div>
            </div>
            <div class="section">
                <div class="section-header">
                    <span class="section-icon">📉</span>
                    <span class="section-title">옵션 약세 신호 Top 10</span>
                    <span class="section-badge badge-red">풋 옵션 급증</span>
                </div>
                <div class="table-wrapper">
                    <table class="data-table">
                        <thead><tr><th>순위</th><th>종목</th><th class="right">주가 ($)</th><th class="right">풋 거래량</th><th class="right">평소 대비</th><th class="right">신호강도</th></tr></thead>
                        <tbody>{opt_bearish_html or empty_msg(opt_bearish)}</tbody>
                    </table>
                </div>
            </div>
            <div class="section">
                <div class="section-header">
                    <span class="section-icon">⚡</span>
                    <span class="section-title">이상 옵션 거래</span>
                    <span class="section-badge badge-yellow">대형 거래 포착</span>
                </div>
                <div class="table-wrapper">
                    <table class="data-table">
                        <thead><tr><th>종목</th><th>방향</th><th class="right">거래규모</th><th class="right hide-mobile">만기일</th><th>해석</th></tr></thead>
                        <tbody>{opt_unusual_html or empty_msg(opt_unusual)}</tbody>
                    </table>
                </div>
            </div>
        </div>

        <div class="footer">
            <p>💡 옵션 데이터는 주식 매매 참고용 신호입니다. 투자 판단은 본인의 책임입니다.</p>
            <p style="margin-top:8px;">데이터 출처: Yahoo Finance · 업데이트: 매일 06:10 KST</p>
        </div>
    </div>

    <!-- TradingView Chart Modal -->
    <div class="modal-overlay" id="chartModal" onclick="closeModal(event)">
        <div class="modal" onclick="event.stopPropagation()">
            <div class="modal-header">
                <div class="ticker-info">
                    <span class="modal-ticker" id="modalTicker"></span>
                    <span class="modal-name" id="modalName"></span>
                </div>
                <button class="modal-close" onclick="closeChart()">&times;</button>
            </div>
            <div class="modal-chart" id="tradingview_chart"></div>
        </div>
    </div>

    <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
    <script>
        function switchTab(tabName) {{
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById('tab-' + tabName).classList.add('active');
            const map = {{ stocks: 0, etf: 1, options: 2 }};
            document.querySelectorAll('.tab-btn')[map[tabName]].classList.add('active');
        }}

        let tvWidget = null;

        function openChart(ticker, name) {{
            document.getElementById('modalTicker').textContent = ticker;
            document.getElementById('modalName').textContent = name;
            document.getElementById('chartModal').classList.add('active');
            document.body.style.overflow = 'hidden';

            // Clear previous chart
            const container = document.getElementById('tradingview_chart');
            container.innerHTML = '';

            // Create new TradingView widget
            tvWidget = new TradingView.widget({{
                "autosize": true,
                "symbol": ticker,
                "interval": "D",
                "timezone": "Asia/Seoul",
                "theme": "dark",
                "style": "1",
                "locale": "kr",
                "toolbar_bg": "#16161f",
                "enable_publishing": false,
                "allow_symbol_change": false,
                "hide_top_toolbar": false,
                "hide_legend": false,
                "save_image": false,
                "container_id": "tradingview_chart",
                "range": "12M",
                "backgroundColor": "#16161f",
                "gridColor": "#1e1e2a",
            }});
        }}

        function closeChart() {{
            document.getElementById('chartModal').classList.remove('active');
            document.body.style.overflow = '';
            const container = document.getElementById('tradingview_chart');
            container.innerHTML = '';
        }}

        function closeModal(event) {{
            if (event.target === document.getElementById('chartModal')) {{
                closeChart();
            }}
        }}

        // ESC key to close
        document.addEventListener('keydown', function(e) {{
            if (e.key === 'Escape') closeChart();
        }});
    </script>
</body>
</html>'''

    return html


# ── Main ───────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print(f"🇺🇸 미국 시장 트랙커 — {UPDATE_TIME}")
    print("=" * 60)

    # Load ticker data
    sp500 = load_json("tickers_sp500.json")
    russell = load_json("tickers_russell2000.json")
    etf_list = load_json("etf_list.json")
    options_tickers = load_json("tickers_options.json")

    # 1. Index data
    index_data = get_index_data()
    print(f"  ✅ Index data loaded")

    # 2. Stock data
    gainers, unusual_vol, new_highs = get_stock_data(sp500, russell)
    print(f"  ✅ Stocks: {len(gainers)} gainers, {len(unusual_vol)} unusual vol, {len(new_highs)} new highs")

    # 3. ETF data
    etf_gainers, etf_losers, etf_active = get_etf_data(etf_list)
    print(f"  ✅ ETFs: {len(etf_gainers)} gainers, {len(etf_losers)} losers, {len(etf_active)} active")

    # 4. Options data
    opt_bullish, opt_bearish, opt_unusual = get_options_data(options_tickers)
    print(f"  ✅ Options: {len(opt_bullish)} bullish, {len(opt_bearish)} bearish, {len(opt_unusual)} unusual")

    # 5. Generate HTML
    print("🔧 Generating HTML dashboard...")
    html = generate_html(
        index_data, gainers, unusual_vol, new_highs,
        etf_gainers, etf_losers, etf_active,
        opt_bullish, opt_bearish, opt_unusual,
    )

    output_path = os.path.join(OUTPUT_DIR, "index.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Dashboard saved to {output_path}")
    print(f"📊 Total size: {len(html):,} bytes")
    print("=" * 60)


if __name__ == "__main__":
    main()
