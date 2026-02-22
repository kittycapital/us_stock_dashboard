#!/usr/bin/env python3
"""
미국 시장 트랙커 — Daily US Market Dashboard for Korean Investors
Optimized for mobile and imweb iframe embedding.
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
OUTPUT_DIR = SCRIPT_DIR

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
    for attempt in range(retries):
        try:
            data = yf.download(tickers, period=period, progress=False, threads=True)
            return data
        except Exception as e:
            print(f"  Retry {attempt+1}/{retries}: {e}")
            time.sleep(5)
    return pd.DataFrame()


def batch_download(ticker_list, period="1d", batch_size=100):
    all_data = {}
    for i in range(0, len(ticker_list), batch_size):
        batch = ticker_list[i:i + batch_size]
        print(f"  Downloading batch {i//batch_size + 1} ({len(batch)} tickers)...")
        data = safe_download(batch, period=period)
        if not data.empty:
            if len(batch) == 1:
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
        time.sleep(2)
    return all_data


# ── Data Collection Functions ──────────────────────────────────────────

def get_index_data():
    print("📊 Fetching index data...")
    indices = {
        "^GSPC": "S&P 500",
        "^IXIC": "나스닥",
        "^DJI": "다우존스",
        "^VIX": "VIX",
        "^TNX": "US 10Y",
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

                # Format value based on type
                if name == "VIX":
                    formatted = f"{current:.2f}"
                elif name == "US 10Y":
                    formatted = f"{current:.3f}%"
                else:
                    formatted = f"{current:,.2f}"

                result[name] = {
                    "value": current,
                    "change_pct": change_pct,
                    "formatted_value": formatted,
                    "formatted_change": fmt_pct(change_pct),
                }
            elif len(hist) == 1:
                current = hist["Close"].iloc[-1]

                if name == "VIX":
                    formatted = f"{current:.2f}"
                elif name == "US 10Y":
                    formatted = f"{current:.3f}%"
                else:
                    formatted = f"{current:,.2f}"

                result[name] = {
                    "value": current,
                    "change_pct": 0,
                    "formatted_value": formatted,
                    "formatted_change": "0.00%",
                }
        except Exception as e:
            print(f"  Error fetching {symbol}: {e}")
            result[name] = {"value": 0, "change_pct": 0, "formatted_value": "N/A", "formatted_change": "N/A"}
    return result


def get_mag7_data():
    """Fetch Magnificent 7 stocks data."""
    print("💎 Fetching Mag 7 data...")
    MAG7 = {
        "AAPL": "애플",
        "MSFT": "마이크로소프트",
        "GOOGL": "알파벳",
        "AMZN": "아마존",
        "NVDA": "엔비디아",
        "META": "메타",
        "TSLA": "테슬라",
        "PLTR": "팔란티어",
    }
    tickers = list(MAG7.keys())
    result = []

    try:
        data = yf.download(tickers, period="1d", progress=False, threads=True)
        if not data.empty:
            for ticker in tickers:
                try:
                    if len(tickers) == 1:
                        close = data["Close"].iloc[-1]
                        open_p = data["Open"].iloc[-1]
                        volume = data["Volume"].iloc[-1]
                    else:
                        close = data["Close"][ticker].iloc[-1]
                        open_p = data["Open"][ticker].iloc[-1]
                        volume = data["Volume"][ticker].iloc[-1]

                    if close is None or pd.isna(close) or close == 0:
                        continue

                    change_pct = ((close - open_p) / open_p * 100) if open_p and open_p > 0 else 0

                    result.append({
                        "ticker": ticker,
                        "name": MAG7[ticker],
                        "close": close,
                        "change_pct": change_pct,
                        "volume": volume if volume and not pd.isna(volume) else 0,
                    })
                except (KeyError, IndexError):
                    continue
    except Exception as e:
        print(f"  Error fetching Mag 7: {e}")

    return result


def get_stock_data(sp500_tickers, russell_tickers):
    print("📈 Fetching stock data...")

    all_tickers = list(sp500_tickers.keys()) + list(russell_tickers.keys())
    all_tickers = list(dict.fromkeys(all_tickers))
    print(f"  Total tickers: {len(all_tickers)}")

    today_data = batch_download(all_tickers, period="1d")

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

    gainers = sorted(stocks, key=lambda x: x["change_pct"], reverse=True)[:10]
    unusual_vol = sorted(
        [s for s in stocks if s["vol_ratio"] >= 1.5],
        key=lambda x: x["vol_ratio"],
        reverse=True
    )[:10]

    print("  Checking 52-week highs...")
    high_52w_file = os.path.join(DATA_DIR, "52week_highs.json")
    try:
        with open(high_52w_file, "r") as f:
            stored_highs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        stored_highs = {}

    new_highs = []
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
                        if close >= yr_high * 0.99:
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


# ── HTML Generation ────────────────────────────────────────────────────

def generate_html(index_data, mag7_data, gainers, unusual_vol, new_highs,
                  etf_gainers, etf_losers, etf_active):

    def change_class(pct):
        return "change-positive" if pct >= 0 else "change-negative"

    def index_change_class(name, pct):
        # 원/달러: 환율 하락(원화 강세)이 긍정적 → 반전
        if name == "원/달러":
            return "change-negative" if pct > 0 else "change-positive"
        # VIX, US 10Y, 기타: 단순 등락 기준 (상승=초록)
        return "change-positive" if pct >= 0 else "change-negative"

    def render_stock_rows(items, show_sector=True, show_vol_ratio=False, show_52w=False):
        rows = []
        for i, item in enumerate(items):
            rank = i + 1
            change_cls = change_class(item.get("change_pct", 0))
            ticker = item["ticker"]
            name_escaped = item["name"].replace("'", "\\'")

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
                emoji = "" if ratio >= 4 else ""
                vol_td = f'''
                    <td class="right volume hide-mobile">{fmt_number(item.get("volume", 0))}</td>
                    <td class="right"><span class="volume-ratio {vol_cls}">{ratio:.1f}배{emoji}</span></td>
                '''
            elif show_52w:
                vol_td = f'''
                    <td class="right hide-mobile">{fmt_price(item.get("prev_high", 0))}</td>
                    <td class="right {change_cls}">{fmt_pct(item.get("beat_pct", 0))}</td>
                '''
            else:
                vol_td = f'<td class="right volume hide-mobile">{fmt_number(item.get("volume", 0))}</td>'

            rows.append(f'''
                <tr data-ticker="{ticker}" onclick="selectTicker('{ticker}', '{name_escaped}')" style="cursor:pointer;">
                    <td class="rank">{rank}</td>
                    <td><div class="ticker-cell"><span class="ticker-symbol">{ticker}</span><span class="ticker-name">{item["name"]}</span></div></td>
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
            ticker = item["ticker"]
            name_escaped = item["name"].replace("'", "\\'")
            rows.append(f'''
                <tr data-ticker="{ticker}" onclick="selectTicker('{ticker}', '{name_escaped}')" style="cursor:pointer;">
                    <td class="rank">{rank}</td>
                    <td><div class="ticker-cell"><span class="ticker-symbol">{ticker}</span><span class="ticker-name hide-mobile">{item["name"]}</span></div></td>
                    <td><span class="etf-category">{item.get("category", "")}</span></td>
                    <td class="right price">{fmt_price(item.get("close", 0))}</td>
                    <td class="right {change_cls}">{fmt_pct(item.get("change_pct", 0))}</td>
                    <td class="right volume hide-mobile">{fmt_number(item.get("volume", 0))}</td>
                </tr>
            ''')
        return "\n".join(rows)

    # Build index bar (6 items)
    index_items = []
    for name in ["S&P 500", "나스닥", "다우존스", "VIX", "US 10Y", "원/달러"]:
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

    # Render Mag 7 cards
    mag7_cards = []
    for i, item in enumerate(mag7_data):
        ticker = item["ticker"]
        name_escaped = item["name"].replace("'", "\\'")
        change_pct = item.get("change_pct", 0)
        change_cls = "up" if change_pct >= 0 else "down"
        mag7_cards.append(f'''
        <div class="mag7-card" onclick="selectTicker('{ticker}', '{name_escaped}')">
          <div class="mag7-card-top"><span class="mag7-ticker">{ticker}</span><span class="mag7-name">{item["name"]}</span></div>
          <div class="mag7-price">{fmt_price(item.get("close", 0))}</div>
          <div class="mag7-change {change_cls}">{fmt_pct(change_pct)}</div>
          <div class="mag7-vol">Vol {fmt_number(item.get("volume", 0))}</div>
        </div>''')
    mag7_html = "\n".join(mag7_cards)

    # Render all table rows
    gainers_html = render_stock_rows(gainers, show_sector=True)
    unusual_vol_html = render_stock_rows(unusual_vol, show_sector=False, show_vol_ratio=True)
    new_highs_html = render_stock_rows(new_highs, show_sector=True, show_52w=True)
    etf_gainers_html = render_etf_rows(etf_gainers)
    etf_losers_html = render_etf_rows(etf_losers)
    etf_active_html = render_etf_rows(etf_active)

    def empty_msg(data, msg="데이터를 불러오는 중 오류가 발생했습니다."):
        if not data:
            return f'<tr><td colspan="6" style="text-align:center;color:var(--text-dim);padding:24px;">{msg}</td></tr>'
        return ""

    html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no">
<title>미국 시장 트랙커 | Herdvibe</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<script src="https://t1.kakaocdn.net/kakao_js_sdk/2.7.1/kakao.min.js" crossorigin="anonymous" async></script>
<style>
:root{{
  --hv-primary:#3b82f6;--hv-primary-light:#60a5fa;--hv-primary-dark:#2563eb;
  --hv-primary-glow:rgba(59,130,246,0.12);
  --hv-up:#22c55e;--hv-up-bg:rgba(34,197,94,0.1);
  --hv-down:#ef4444;--hv-down-bg:rgba(239,68,68,0.1);
  --hv-warning:#f59e0b;--hv-warning-bg:rgba(245,158,11,0.1);
  --hv-neutral:#6b7280;
  --hv-bg-base:#000;--hv-bg-surface:#0a0a0a;--hv-bg-card:#111;
  --hv-bg-card-hover:#181818;--hv-bg-elevated:#1a1a1a;
  --hv-text-primary:#e5e5e5;--hv-text-secondary:#8a8a8a;
  --hv-text-tertiary:#555;--hv-text-muted:#3a3a3a;
  --hv-border:rgba(255,255,255,0.06);--hv-border-strong:rgba(255,255,255,0.12);
  --hv-font-display:'Plus Jakarta Sans',sans-serif;
  --hv-font-body:'Noto Sans KR',-apple-system,BlinkMacSystemFont,sans-serif;
  --hv-font-mono:'JetBrains Mono','SF Mono',monospace;
  --hv-radius-sm:6px;--hv-radius-md:10px;--hv-radius-lg:14px;
  --hv-shadow-sm:0 1px 3px rgba(0,0,0,.5);--hv-shadow-lg:0 8px 32px rgba(0,0,0,.7);
  --hv-transition-fast:150ms ease;--hv-transition:250ms ease;
  --hv-max-width:1280px;--hv-header-height:60px;
  --green:#22c55e;--green-bg:rgba(34,197,94,0.1);
  --red:#ef4444;--red-bg:rgba(239,68,68,0.1);
  --accent:#3b82f6;--accent-bg:rgba(59,130,246,0.12);
  --yellow:#f59e0b;--yellow-bg:rgba(245,158,11,0.1);
}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html{{font-size:16px;scroll-behavior:smooth;-webkit-font-smoothing:antialiased;height:100%}}
body{{font-family:var(--hv-font-body);background:var(--hv-bg-base);color:var(--hv-text-primary);line-height:1.6;min-height:100%;overflow-y:auto;-webkit-overflow-scrolling:touch}}
::selection{{background:var(--hv-primary);color:#fff}}
::-webkit-scrollbar{{width:5px;height:5px}}
::-webkit-scrollbar-track{{background:var(--hv-bg-base)}}
::-webkit-scrollbar-thumb{{background:#333;border-radius:3px}}
.hv-header{{position:sticky;top:0;z-index:100;height:var(--hv-header-height);background:rgba(0,0,0,.92);backdrop-filter:blur(20px) saturate(180%);-webkit-backdrop-filter:blur(20px) saturate(180%);border-bottom:1px solid var(--hv-border);display:flex;align-items:center;padding:0 24px}}
.hv-header-inner{{width:100%;max-width:var(--hv-max-width);margin:0 auto;display:flex;align-items:center;justify-content:space-between;gap:16px}}
.hv-logo{{display:flex;align-items:center;gap:10px;font-family:var(--hv-font-display);font-weight:800;font-size:1.15rem;color:var(--hv-text-primary);text-decoration:none;white-space:nowrap;letter-spacing:-.02em}}
.hv-logo-mark{{width:28px;height:28px;background:linear-gradient(135deg,var(--hv-primary),#6366f1);border-radius:7px;flex-shrink:0}}
.hv-header-center{{display:flex;flex-direction:column;min-width:0}}
.hv-header-center h1{{font-family:var(--hv-font-display);font-size:.938rem;font-weight:600;color:var(--hv-text-primary);white-space:nowrap}}
.hv-header-category{{font-size:.7rem;color:var(--hv-text-tertiary);font-weight:500;text-transform:uppercase;letter-spacing:.08em}}
.hv-header-right{{display:flex;align-items:center;gap:8px;flex-shrink:0}}
.hv-update-badge{{font-family:var(--hv-font-mono);font-size:.688rem;color:var(--hv-text-tertiary);white-space:nowrap;display:flex;align-items:center;gap:6px}}
.hv-live-dot{{width:5px;height:5px;background:var(--green);border-radius:50%;animation:pulse 2s infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.3}}}}
.container{{max-width:var(--hv-max-width);margin:0 auto;padding:16px 24px 48px}}
.index-bar{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px}}
.index-item{{background:var(--hv-bg-card);border:1px solid var(--hv-border);border-radius:var(--hv-radius-md);padding:12px 14px;transition:border-color .2s}}
.index-item:hover{{border-color:var(--hv-border-strong)}}
.index-item .label{{font-size:10px;font-weight:500;color:var(--hv-text-muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}}
.index-item .value{{font-family:var(--hv-font-mono);font-size:15px;font-weight:700;color:var(--hv-text-primary)}}
.index-item .change{{font-family:var(--hv-font-mono);font-size:11px;font-weight:600;margin-left:6px}}
.color-note{{font-size:11px;color:var(--hv-text-secondary);margin-bottom:16px;padding:8px 14px;background:var(--hv-bg-card);border-radius:var(--hv-radius-sm);border-left:3px solid var(--accent)}}
.chart-section{{margin-bottom:16px}}
.chart-header{{display:flex;align-items:center;gap:10px;margin-bottom:8px}}
.chart-ticker{{font-family:var(--hv-font-mono);font-size:18px;font-weight:700;color:var(--hv-text-primary)}}
.chart-name{{font-size:12px;color:var(--hv-text-secondary)}}
.chart-container{{background:var(--hv-bg-card);border:1px solid var(--hv-border);border-radius:var(--hv-radius-lg);overflow:hidden;height:260px}}
.tab-container{{display:flex;gap:3px;margin-bottom:16px;background:var(--hv-bg-card);padding:4px;border-radius:var(--hv-radius-md);border:1px solid var(--hv-border)}}
.tab-btn{{flex:1;padding:10px 12px;background:transparent;border:none;border-radius:var(--hv-radius-sm);color:var(--hv-text-tertiary);font-family:var(--hv-font-body);font-size:13px;font-weight:600;cursor:pointer;transition:all .2s;display:flex;align-items:center;justify-content:center;gap:6px;-webkit-tap-highlight-color:transparent}}
.tab-btn:hover{{color:var(--hv-text-secondary)}}
.tab-btn.active{{background:var(--hv-bg-elevated);color:var(--hv-text-primary);box-shadow:var(--hv-shadow-sm)}}
.tab-content{{display:none}}
.tab-content.active{{display:block}}
.section{{margin-bottom:20px}}
.section-header{{display:flex;align-items:center;gap:8px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid var(--hv-border);justify-content:center}}
.section-icon{{font-size:14px}}
.section-title{{font-size:14px;font-weight:700;color:var(--hv-text-primary)}}
.section-badge{{font-size:9px;font-weight:600;padding:3px 8px;border-radius:4px;margin-left:auto;white-space:nowrap;font-family:var(--hv-font-mono);letter-spacing:.3px}}
.badge-green{{background:var(--green-bg);color:var(--green)}}
.badge-red{{background:var(--red-bg);color:var(--red)}}
.badge-blue{{background:var(--accent-bg);color:var(--accent)}}
.badge-yellow{{background:var(--yellow-bg);color:var(--yellow)}}
.table-wrapper{{border-radius:var(--hv-radius-lg);border:1px solid var(--hv-border);background:var(--hv-bg-card);overflow:hidden;overflow-x:auto;-webkit-overflow-scrolling:touch;position:relative}}
.data-table{{width:100%;border-collapse:collapse;font-size:12px;table-layout:fixed}}
.data-table thead th{{font-family:var(--hv-font-mono);font-size:9px;font-weight:600;color:var(--hv-text-muted);text-transform:uppercase;letter-spacing:.6px;padding:10px 8px;text-align:left;border-bottom:1px solid var(--hv-border);white-space:nowrap;background:var(--hv-bg-surface)}}
.data-table thead th.right{{text-align:right}}
.data-table tbody tr{{border-bottom:1px solid var(--hv-border);transition:background .12s}}
.data-table tbody tr:last-child{{border-bottom:none}}
.data-table tbody tr:hover,.data-table tbody tr:active{{background:var(--hv-bg-card-hover)}}
.data-table tbody tr.selected{{background:var(--accent-bg);border-left:3px solid var(--accent)}}
.data-table tbody td{{padding:10px 8px;vertical-align:middle}}
.data-table tbody td.right{{text-align:right}}
.rank{{font-family:var(--hv-font-mono);font-size:10px;font-weight:700;color:var(--hv-text-muted);width:22px;text-align:center}}
.ticker-cell{{display:flex;flex-direction:column;gap:2px;min-width:0}}
.ticker-symbol{{font-family:var(--hv-font-mono);font-weight:700;font-size:12px;color:var(--hv-text-primary)}}
.ticker-name{{font-size:10px;color:var(--hv-text-secondary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.sector-tag{{font-size:9px;padding:2px 6px;border-radius:4px;background:rgba(255,255,255,0.04);color:var(--hv-text-secondary);font-weight:500}}
.price{{font-family:var(--hv-font-mono);font-weight:600;font-size:12px;color:var(--hv-text-primary)}}
.change-positive{{color:var(--green);font-family:var(--hv-font-mono);font-weight:700;font-size:12px}}
.change-negative{{color:var(--red);font-family:var(--hv-font-mono);font-weight:700;font-size:12px}}
.volume{{font-family:var(--hv-font-mono);font-size:10px;color:var(--hv-text-secondary)}}
.volume-ratio{{font-family:var(--hv-font-mono);font-weight:700;font-size:11px}}
.volume-high{{color:var(--yellow)}}
.volume-extreme{{color:var(--red)}}
.etf-category{{font-size:9px;color:var(--accent);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:80px;display:inline-block;font-weight:500}}
.hv-share-bar{{display:flex;align-items:center;justify-content:space-between;padding:12px 24px;border:1px solid var(--hv-border);border-radius:var(--hv-radius-lg);background:var(--hv-bg-surface);margin-top:24px}}
.hv-share-bar-preview{{font-size:.75rem;color:var(--hv-text-tertiary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:50%;font-family:var(--hv-font-mono)}}
.hv-share-bar-preview span{{color:var(--hv-text-secondary);font-weight:500}}
.hv-share-bar-buttons{{display:flex;align-items:center;gap:6px;flex-shrink:0}}
.share-btn{{display:inline-flex;align-items:center;gap:6px;padding:7px 14px;border-radius:6px;font-size:.75rem;font-weight:600;font-family:var(--hv-font-body);cursor:pointer;transition:all var(--hv-transition-fast);border:1px solid var(--hv-border-strong);background:var(--hv-bg-card);color:#999;white-space:nowrap}}
.share-btn:hover{{transform:translateY(-1px);box-shadow:var(--hv-shadow-sm);color:var(--hv-text-primary)}}
.share-btn svg{{flex-shrink:0}}
.share-btn--x:hover{{border-color:#fff;color:#fff;background:#111}}
.share-btn--kakao:hover{{border-color:#FEE500;color:#191919;background:#FEE500}}
.share-btn--tg:hover{{border-color:#26A5E4;color:#fff;background:rgba(38,165,228,.15)}}
.share-btn--ig:hover{{border-color:#E4405F;color:#fff;background:rgba(228,64,95,.15)}}
.share-btn--copy:hover{{border-color:var(--hv-primary);color:var(--hv-primary-light);background:var(--hv-primary-glow)}}
.toast-wrap{{position:fixed;bottom:20px;right:20px;z-index:200;display:flex;flex-direction:column;gap:8px}}
.toast{{background:var(--hv-bg-elevated);border:1px solid var(--hv-border-strong);border-radius:var(--hv-radius-md);padding:10px 18px;font-size:.788rem;color:var(--hv-text-primary);box-shadow:var(--hv-shadow-lg);animation:toastIn .3s ease;border-left:3px solid var(--green)}}
@keyframes toastIn{{from{{opacity:0;transform:translateY(12px)}}to{{opacity:1;transform:translateY(0)}}}}
.hv-footer{{border-top:1px solid var(--hv-border);padding:24px;margin-top:32px}}
.hv-footer-inner{{max-width:var(--hv-max-width);margin:0 auto;display:flex;flex-direction:column;align-items:center;gap:10px;text-align:center}}
.hv-footer-brand{{font-family:var(--hv-font-display);font-weight:700;font-size:.938rem;color:var(--hv-text-primary)}}
.hv-footer-links{{display:flex;gap:24px;flex-wrap:wrap;justify-content:center}}
.hv-footer-links a{{font-size:.788rem;color:var(--hv-text-tertiary);text-decoration:none}}
.hv-footer-links a:hover{{color:var(--hv-text-primary)}}
.hv-footer-note{{font-size:.7rem;color:var(--hv-text-muted);max-width:550px;line-height:1.6}}
.mag7-section{{margin-bottom:20px}}
.mag7-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}}
.mag7-card{{background:var(--hv-bg-card);border:1px solid var(--hv-border);border-radius:var(--hv-radius-md);padding:14px 16px;cursor:pointer;transition:all .2s;position:relative;overflow:hidden}}
.mag7-card:hover{{border-color:var(--hv-border-strong);transform:translateY(-1px);box-shadow:var(--hv-shadow-sm)}}
.mag7-card.selected{{border-color:var(--accent);background:var(--accent-bg)}}
.mag7-card-top{{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}}
.mag7-ticker{{font-family:var(--hv-font-mono);font-size:13px;font-weight:700;color:var(--hv-text-primary)}}
.mag7-name{{font-size:9px;color:var(--hv-text-tertiary);font-weight:500}}
.mag7-price{{font-family:var(--hv-font-mono);font-size:15px;font-weight:700;color:var(--hv-text-primary);margin-bottom:2px}}
.mag7-change{{font-family:var(--hv-font-mono);font-size:12px;font-weight:700}}
.mag7-change.up{{color:var(--green)}}
.mag7-change.down{{color:var(--red)}}
.mag7-vol{{font-family:var(--hv-font-mono);font-size:9px;color:var(--hv-text-muted);margin-top:4px}}
.hide-mobile{{display:none}}
@media(min-width:600px){{
  .container{{padding:20px 24px 48px}}
  .index-bar{{grid-template-columns:repeat(6,1fr)}}
  .index-item .value{{font-size:16px}}
  .chart-container{{height:320px}}
  .chart-ticker{{font-size:20px}}
  .data-table{{font-size:13px}}
  .data-table thead th{{padding:10px 12px;font-size:10px}}
  .data-table tbody td{{padding:12px 10px}}
  .ticker-symbol{{font-size:13px}}
  .ticker-name{{font-size:11px}}
  .price{{font-size:13px}}
  .change-positive,.change-negative{{font-size:13px}}
  .section-title{{font-size:15px}}
  .hide-mobile{{display:table-cell}}
  .etf-category{{max-width:none}}
}}
@media(min-width:900px){{
  .chart-container{{height:360px}}
}}
@media(max-width:600px){{
  :root{{--hv-header-height:52px}}
  .hv-header{{padding:0 14px}}
  .hv-update-badge{{display:none}}
  .container{{padding:12px 14px 40px}}
  .index-item{{padding:10px 12px}}
  .index-item .value{{font-size:14px}}
  .chart-container{{height:240px}}
  .mag7-grid{{grid-template-columns:repeat(2,1fr)}}
  .mag7-card{{padding:10px 12px}}
  .mag7-price{{font-size:13px}}
  .hv-share-bar{{flex-direction:column;gap:10px;align-items:stretch;padding:12px 14px}}
  .hv-share-bar-preview{{max-width:100%}}
  .hv-share-bar-buttons{{justify-content:center;flex-wrap:wrap}}
  .share-btn span.label-text{{display:none}}
  .share-btn{{padding:8px 10px}}
  .hv-footer{{padding:16px}}
}}
</style>
</head>
<body>
<header class="hv-header">
  <div class="hv-header-inner">
    <div class="hv-header-center">
      <h1 style="text-align:center">미국 시장 트랙커</h1>
      <span class="hv-header-category">US MARKET · STOCKS · ETF</span>
    </div>
    <div class="hv-header-right">
      <div class="hv-update-badge"><span class="hv-live-dot"></span><span>{UPDATE_TIME}</span></div>
    </div>
  </div>
</header>
<div class="container">
  <div class="index-bar">{index_bar_html}</div>
  <div class="color-note">미국식 색상: <span style="color:var(--green)">상승</span> / <span style="color:var(--red)">하락</span></div>
  <div class="chart-section">
    <div class="chart-header">
      <span class="chart-ticker" id="chartTicker">SPY</span>
      <span class="chart-name" id="chartName">SPDR S&P 500</span>
    </div>
    <div class="chart-container" id="tradingview_chart"></div>
  </div>
  <div class="tab-container">
    <button class="tab-btn active" onclick="switchTab('stocks')">개별 주식</button>
    <button class="tab-btn" onclick="switchTab('etf')">ETF</button>
  </div>
  <div id="tab-stocks" class="tab-content active">
    <div class="section mag7-section">
      <div class="section-header"><span class="section-title">주요 주식</span><span class="section-badge badge-blue">TOP 8</span></div>
      <div class="mag7-grid">{mag7_html}</div>
    </div>
    <div class="section">
      <div class="section-header"><span class="section-title">급등주 Top 10</span><span class="section-badge badge-green">오늘</span></div>
      <div class="table-wrapper"><table class="data-table"><thead><tr><th style="width:24px">#</th><th>종목</th><th class="hide-mobile">섹터</th><th class="right" style="width:70px">종가</th><th class="right" style="width:60px">등락</th><th class="right hide-mobile">거래량</th></tr></thead><tbody>{gainers_html or empty_msg(gainers)}</tbody></table></div>
    </div>
    <div class="section">
      <div class="section-header"><span class="section-title">이상 거래량</span><span class="section-badge badge-yellow">급증</span></div>
      <div class="table-wrapper"><table class="data-table"><thead><tr><th style="width:24px">#</th><th>종목</th><th class="right" style="width:70px">종가</th><th class="right" style="width:60px">등락</th><th class="right hide-mobile">거래량</th><th class="right" style="width:55px">배율</th></tr></thead><tbody>{unusual_vol_html or empty_msg(unusual_vol)}</tbody></table></div>
    </div>
    <div class="section">
      <div class="section-header"><span class="section-title">52주 신고가</span><span class="section-badge badge-blue">갱신</span></div>
      <div class="table-wrapper"><table class="data-table"><thead><tr><th style="width:24px">#</th><th>종목</th><th class="hide-mobile">섹터</th><th class="right" style="width:70px">종가</th><th class="right hide-mobile">이전고가</th><th class="right" style="width:60px">갱신</th></tr></thead><tbody>{new_highs_html or empty_msg(new_highs, "오늘 신고가 종목 없음")}</tbody></table></div>
    </div>
  </div>
  <div id="tab-etf" class="tab-content">
    <div class="section">
      <div class="section-header"><span class="section-title">ETF 상승 Top 10</span><span class="section-badge badge-green">오늘</span></div>
      <div class="table-wrapper"><table class="data-table"><thead><tr><th style="width:24px">#</th><th>ETF</th><th>카테고리</th><th class="right" style="width:70px">종가</th><th class="right" style="width:60px">등락</th><th class="right hide-mobile">거래량</th></tr></thead><tbody>{etf_gainers_html or empty_msg(etf_gainers)}</tbody></table></div>
    </div>
    <div class="section">
      <div class="section-header"><span class="section-title">ETF 하락 Top 10</span><span class="section-badge badge-red">오늘</span></div>
      <div class="table-wrapper"><table class="data-table"><thead><tr><th style="width:24px">#</th><th>ETF</th><th>카테고리</th><th class="right" style="width:70px">종가</th><th class="right" style="width:60px">등락</th><th class="right hide-mobile">거래량</th></tr></thead><tbody>{etf_losers_html or empty_msg(etf_losers)}</tbody></table></div>
    </div>
    <div class="section">
      <div class="section-header"><span class="section-title">ETF 거래량 Top 10</span><span class="section-badge badge-blue">활발</span></div>
      <div class="table-wrapper"><table class="data-table"><thead><tr><th style="width:24px">#</th><th>ETF</th><th>카테고리</th><th class="right" style="width:70px">종가</th><th class="right" style="width:60px">등락</th><th class="right hide-mobile">거래량</th></tr></thead><tbody>{etf_active_html or empty_msg(etf_active)}</tbody></table></div>
    </div>
  </div>
  <div class="hv-share-bar">
    <div class="hv-share-bar-preview"><span>미국 시장 트랙커</span> — herdvibe.com</div>
    <div class="hv-share-bar-buttons">
      <button class="share-btn share-btn--x" onclick="doShare('twitter')"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg><span class="label-text">트위터</span></button>
      <button class="share-btn share-btn--kakao" onclick="doShare('kakao')"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 3C6.477 3 2 6.463 2 10.691c0 2.724 1.8 5.112 4.508 6.458l-1.148 4.265a.5.5 0 0 0 .764.533l4.94-3.26c.304.02.612.03.936.03 5.523 0 10-3.462 10-7.735C22 6.463 17.523 3 12 3z"/></svg><span class="label-text">카카오톡</span></button>
      <button class="share-btn share-btn--tg" onclick="doShare('telegram')"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.479.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/></svg><span class="label-text">텔레그램</span></button>
      <button class="share-btn share-btn--ig" onclick="doShare('instagram',this)"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"/></svg><span class="label-text">인스타</span></button>
      <button class="share-btn share-btn--copy" onclick="doShare('link',this)"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg><span class="label-text">링크 복사</span></button>
    </div>
  </div>
</div>
<script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
<script>
var SHARE_URL='https://herdvibe.com/15';
var SHARE_TITLE='미국 시장 트랙커 — 급등주 · ETF · 거래량 | Herdvibe';
function ensureKakao(){{try{{if(typeof Kakao!=='undefined'&&!Kakao.isInitialized())Kakao.init('a43ed7b39fac35458f4f9df925a279b5');return typeof Kakao!=='undefined'&&Kakao.isInitialized();}}catch(e){{return false;}}}}
function copyToClipboard(t){{try{{window.parent.postMessage({{type:'clipboard',text:t}},'*');}}catch(e){{}}try{{navigator.clipboard.writeText(t);}}catch(e){{}}}}
function flashCopied(btn){{if(!btn)return;var o=btn.innerHTML;btn.style.background='#22c55e';btn.style.color='#fff';btn.style.borderColor='#22c55e';var hl=btn.querySelector('.label-text');btn.innerHTML='<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round"><path d="M5 13l4 4L19 7"/></svg>'+(hl?'<span class="label-text" style="color:#fff">복사됨!</span>':'');setTimeout(function(){{btn.style.background='';btn.style.color='';btn.style.borderColor='';btn.innerHTML=o;}},2000);}}
function toast(m){{var c=document.querySelector('.toast-wrap');if(!c){{c=document.createElement('div');c.className='toast-wrap';document.body.appendChild(c);}}var t=document.createElement('div');t.className='toast';t.textContent=m;c.appendChild(t);setTimeout(function(){{t.style.opacity='0';t.style.transform='translateY(12px)';t.style.transition='.3s';setTimeout(function(){{t.remove();}},300);}},3000);}}
function doShare(p,btn){{var u=SHARE_URL,t=encodeURIComponent(SHARE_TITLE),eu=encodeURIComponent(u);switch(p){{case'twitter':window.open('https://twitter.com/intent/tweet?text='+t+'&url='+eu,'_blank');break;case'telegram':window.open('https://t.me/share/url?url='+eu+'&text='+t,'_blank');break;case'kakao':if(!ensureKakao()){{copyToClipboard(u);toast('링크 복사완료!');}}else try{{Kakao.Share.sendDefault({{objectType:'feed',content:{{title:'미국 시장 트랙커',description:'급등주 · ETF · 거래량 분석',imageUrl:'https://raw.githubusercontent.com/kittycapital/kittycapital.github.io/main/assets/herdvibe-og.png',link:{{mobileWebUrl:u,webUrl:u}}}},buttons:[{{title:'대시보드 보기',link:{{mobileWebUrl:u,webUrl:u}}}}]}});}}catch(e){{copyToClipboard(u);toast('링크 복사완료!');}}break;case'instagram':copyToClipboard(u);flashCopied(btn);toast('링크 복사완료! 인스타그램에 붙여넣기 하세요');break;case'link':copyToClipboard(u);flashCopied(btn);toast('링크가 복사되었습니다');break;}}}}
ensureKakao();
let currentTicker='SPY';
function switchTab(tabName){{
  document.querySelectorAll('.tab-content').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  document.getElementById('tab-'+tabName).classList.add('active');
  document.querySelectorAll('.tab-btn')[tabName==='stocks'?0:1].classList.add('active');
  sendHeight();
}}
function selectTicker(ticker,name){{
  if(ticker===currentTicker)return;
  currentTicker=ticker;
  document.getElementById('chartTicker').textContent=ticker;
  document.getElementById('chartName').textContent=name;
  document.querySelectorAll('.data-table tbody tr').forEach(row=>{{
    row.classList.toggle('selected',row.dataset.ticker===ticker);
  }});
  loadChart(ticker);
  document.querySelector('.chart-section').scrollIntoView({{behavior:'smooth',block:'start'}});
}}
function loadChart(ticker){{
  var container=document.getElementById('tradingview_chart');
  container.innerHTML='';
  new TradingView.widget({{
    "autosize":true,"symbol":ticker,"interval":"D","timezone":"Asia/Seoul",
    "theme":"dark","style":"1","locale":"kr","toolbar_bg":"#111111",
    "enable_publishing":false,"allow_symbol_change":false,
    "hide_top_toolbar":false,"hide_legend":false,"save_image":false,
    "container_id":"tradingview_chart","range":"12M",
    "backgroundColor":"#111111","gridColor":"#181818"
  }});
}}
document.addEventListener('DOMContentLoaded',function(){{loadChart('SPY');setTimeout(sendHeight,500);}});
var _lastH=0,_ht;
function sendHeight(){{clearTimeout(_ht);_ht=setTimeout(function(){{var h=document.documentElement.scrollHeight;if(Math.abs(h-_lastH)>5){{_lastH=h;try{{window.parent.postMessage({{type:'resize',height:h,id:'hvUSMarket'}},'*');window.parent.postMessage({{height:h,id:'hvUSMarket'}},'*');}}catch(e){{}}}}}},120);}}
window.addEventListener('load',function(){{sendHeight();setTimeout(sendHeight,500);setTimeout(sendHeight,2000);}});
window.addEventListener('resize',sendHeight);
new ResizeObserver(sendHeight).observe(document.body);
new MutationObserver(sendHeight).observe(document.body,{{childList:true,subtree:true}});
</script>
</body>
</html>'''

    return html


# ── Main ───────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print(f"미국 시장 트랙커 — {UPDATE_TIME}")
    print("=" * 60)

    sp500 = load_json("tickers_sp500.json")
    russell = load_json("tickers_russell2000.json")
    etf_list = load_json("etf_list.json")

    index_data = get_index_data()
    print(f"  ✅ Index data loaded")

    mag7_data = get_mag7_data()
    print(f"  ✅ Mag 7: {len(mag7_data)} stocks loaded")

    gainers, unusual_vol, new_highs = get_stock_data(sp500, russell)
    print(f"  ✅ Stocks: {len(gainers)} gainers, {len(unusual_vol)} unusual vol, {len(new_highs)} new highs")

    etf_gainers, etf_losers, etf_active = get_etf_data(etf_list)
    print(f"  ✅ ETFs: {len(etf_gainers)} gainers, {len(etf_losers)} losers, {len(etf_active)} active")

    print("🔧 Generating HTML dashboard...")
    html = generate_html(
        index_data, mag7_data, gainers, unusual_vol, new_highs,
        etf_gainers, etf_losers, etf_active,
    )

    output_path = os.path.join(OUTPUT_DIR, "index.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Dashboard saved to {output_path}")
    print(f"📊 Total size: {len(html):,} bytes")
    print("=" * 60)


if __name__ == "__main__":
    main()
