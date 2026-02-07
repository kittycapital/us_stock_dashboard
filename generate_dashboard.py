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


# ── HTML Generation ────────────────────────────────────────────────────

def generate_html(index_data, gainers, unusual_vol, new_highs,
                  etf_gainers, etf_losers, etf_active):
    """Generate complete HTML dashboard with chart at top."""

    def change_class(pct):
        return "change-positive" if pct >= 0 else "change-negative"

    def index_change_class(name, pct):
        if name == "원/달러":
            return "change-negative" if pct > 0 else "change-positive"
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
                    <td><div class="ticker-cell"><span class="ticker-symbol">{ticker}</span><span class="ticker-name">{item["name"]}</span></div></td>
                    <td><span class="etf-category">{item.get("category", "")}</span></td>
                    <td class="right price">{fmt_price(item.get("close", 0))}</td>
                    <td class="right {change_cls}">{fmt_pct(item.get("change_pct", 0))}</td>
                    <td class="right volume hide-mobile">{fmt_number(item.get("volume", 0))}</td>
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

    def empty_msg(data, msg="데이터를 불러오는 중 오류가 발생했습니다."):
        if not data:
            return f'<tr><td colspan="8" style="text-align:center;color:var(--text-dim);padding:24px;">{msg}</td></tr>'
        return ""

    html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
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
            --accent-bg: rgba(108,138,255,0.15);
            --yellow: #ffd666;
            --yellow-bg: rgba(255,214,102,0.08);
        }}
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        html {{ -webkit-text-size-adjust:100%; }}
        body {{ background:var(--bg-primary); color:var(--text-primary); font-family:'Noto Sans KR',sans-serif; line-height:1.6; min-height:100vh; }}
        .container {{ max-width:1200px; margin:0 auto; padding:16px 20px; }}
        
        /* Header */
        .header {{ margin-bottom:16px; }}
        .header-top {{ display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:12px; flex-wrap:wrap; gap:8px; }}
        .header-title {{ display:flex; align-items:center; gap:10px; }}
        .header-title h1 {{ font-size:22px; font-weight:700; letter-spacing:-0.5px; }}
        .update-time {{ font-family:'JetBrains Mono',monospace; font-size:12px; color:var(--text-dim); background:var(--bg-secondary); padding:5px 10px; border-radius:6px; border:1px solid var(--border); }}
        .update-time .dot {{ display:inline-block; width:6px; height:6px; background:var(--green); border-radius:50%; margin-right:6px; animation:pulse 2s infinite; }}
        @keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:0.3}} }}
        
        /* Index Bar */
        .index-bar {{ display:flex; gap:8px; margin-bottom:10px; flex-wrap:wrap; }}
        .index-item {{ background:var(--bg-secondary); border:1px solid var(--border); border-radius:8px; padding:10px 14px; flex:1; min-width:140px; }}
        .index-item .label {{ font-size:10px; font-weight:500; color:var(--text-dim); text-transform:uppercase; letter-spacing:0.5px; margin-bottom:3px; }}
        .index-item .value {{ font-family:'JetBrains Mono',monospace; font-size:16px; font-weight:600; }}
        .index-item .change {{ font-family:'JetBrains Mono',monospace; font-size:12px; font-weight:500; margin-left:5px; }}
        
        .color-note {{ font-size:11px; color:var(--text-dim); margin-bottom:16px; padding:7px 12px; background:var(--bg-secondary); border-radius:6px; border-left:3px solid var(--accent); display:inline-block; }}
        .color-note .green-dot {{ color:var(--green); }}
        .color-note .red-dot {{ color:var(--red); }}
        
        /* Chart Section */
        .chart-section {{ margin-bottom:20px; }}
        .chart-header {{ display:flex; align-items:center; gap:12px; margin-bottom:10px; }}
        .chart-ticker {{ font-family:'JetBrains Mono',monospace; font-size:20px; font-weight:700; }}
        .chart-name {{ font-size:14px; color:var(--text-secondary); }}
        .chart-container {{ background:var(--bg-card); border:1px solid var(--border); border-radius:10px; overflow:hidden; height:320px; }}
        
        /* Tabs */
        .tab-container {{ display:flex; gap:4px; margin-bottom:16px; background:var(--bg-secondary); padding:3px; border-radius:10px; border:1px solid var(--border); }}
        .tab-btn {{ flex:1; padding:10px 16px; background:transparent; border:none; border-radius:8px; color:var(--text-secondary); font-family:'Noto Sans KR',sans-serif; font-size:14px; font-weight:500; cursor:pointer; transition:all 0.2s ease; display:flex; align-items:center; justify-content:center; gap:6px; -webkit-tap-highlight-color:transparent; }}
        .tab-btn:hover {{ color:var(--text-primary); background:var(--bg-hover); }}
        .tab-btn.active {{ background:var(--bg-card); color:var(--text-primary); font-weight:600; box-shadow:0 2px 8px rgba(0,0,0,0.3); }}
        .tab-content {{ display:none; }}
        .tab-content.active {{ display:block; animation:fadeIn 0.3s ease; }}
        @keyframes fadeIn {{ from{{opacity:0;transform:translateY(8px)}} to{{opacity:1;transform:translateY(0)}} }}
        
        /* Sections */
        .section {{ margin-bottom:20px; }}
        .section-header {{ display:flex; align-items:center; gap:8px; margin-bottom:10px; padding-bottom:8px; border-bottom:1px solid var(--border); }}
        .section-icon {{ font-size:18px; }}
        .section-title {{ font-size:15px; font-weight:600; letter-spacing:-0.3px; }}
        .section-badge {{ font-size:10px; font-weight:500; padding:2px 7px; border-radius:4px; margin-left:auto; white-space:nowrap; }}
        .badge-green {{ background:var(--green-bg); color:var(--green); }}
        .badge-red {{ background:var(--red-bg); color:var(--red); }}
        .badge-blue {{ background:rgba(108,138,255,0.08); color:var(--accent); }}
        .badge-yellow {{ background:var(--yellow-bg); color:var(--yellow); }}
        
        /* Tables */
        .table-wrapper {{ overflow-x:auto; border-radius:8px; border:1px solid var(--border); background:var(--bg-card); }}
        .data-table {{ width:100%; border-collapse:collapse; font-size:13px; }}
        .data-table thead th {{ font-size:10px; font-weight:500; color:var(--text-dim); text-transform:uppercase; letter-spacing:0.5px; padding:7px 10px; text-align:left; border-bottom:1px solid var(--border); white-space:nowrap; }}
        .data-table thead th.right {{ text-align:right; }}
        .data-table tbody tr {{ border-bottom:1px solid rgba(42,42,58,0.5); transition:background 0.15s ease; }}
        .data-table tbody tr:hover {{ background:var(--bg-hover); }}
        .data-table tbody tr.selected {{ background:var(--accent-bg); border-left:3px solid var(--accent); }}
        .data-table tbody td {{ padding:8px 10px; vertical-align:middle; }}
        .data-table tbody td.right {{ text-align:right; }}
        
        .rank {{ font-family:'JetBrains Mono',monospace; font-size:11px; font-weight:600; color:var(--text-dim); width:28px; text-align:center; }}
        .ticker-cell {{ display:flex; flex-direction:column; gap:1px; }}
        .ticker-symbol {{ font-family:'JetBrains Mono',monospace; font-weight:600; font-size:13px; color:var(--text-primary); }}
        .ticker-name {{ font-size:11px; color:var(--text-secondary); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:160px; }}
        .sector-tag {{ font-size:10px; padding:2px 6px; border-radius:4px; background:var(--bg-secondary); border:1px solid var(--border); color:var(--text-secondary); white-space:nowrap; }}
        .price {{ font-family:'JetBrains Mono',monospace; font-weight:500; font-size:13px; }}
        .change-positive {{ color:var(--green); font-family:'JetBrains Mono',monospace; font-weight:600; }}
        .change-negative {{ color:var(--red); font-family:'JetBrains Mono',monospace; font-weight:600; }}
        .volume {{ font-family:'JetBrains Mono',monospace; font-size:12px; color:var(--text-secondary); }}
        .volume-ratio {{ font-family:'JetBrains Mono',monospace; font-weight:600; font-size:12px; }}
        .volume-high {{ color:var(--yellow); }}
        .volume-extreme {{ color:var(--red); }}
        .etf-category {{ font-size:10px; color:var(--accent); }}
        
        /* Footer */
        .footer {{ margin-top:24px; padding-top:16px; border-top:1px solid var(--border); text-align:center; font-size:11px; color:var(--text-dim); padding-bottom:16px; }}
        
        /* Responsive */
        @media (max-width:768px) {{
            .container {{ padding:12px 14px; }}
            .header-title h1 {{ font-size:19px; }}
            .index-item {{ min-width:130px; padding:8px 10px; }}
            .index-item .value {{ font-size:14px; }}
            .chart-container {{ height:280px; }}
            .chart-ticker {{ font-size:17px; }}
            .data-table {{ font-size:12px; }}
            .data-table thead th {{ padding:6px 8px; font-size:9px; }}
            .data-table tbody td {{ padding:7px 8px; }}
            .ticker-name {{ max-width:120px; font-size:10px; }}
            .tab-btn {{ font-size:13px; padding:9px 10px; }}
            .hide-mobile {{ display:none; }}
        }}
        @media (max-width:480px) {{
            .container {{ padding:10px; }}
            .header-top {{ flex-direction:column; }}
            .header-title h1 {{ font-size:17px; }}
            .index-item {{ min-width:calc(50% - 4px); flex:none; }}
            .chart-container {{ height:250px; }}
            .chart-ticker {{ font-size:15px; }}
            .chart-name {{ font-size:12px; }}
            .tab-btn {{ font-size:13px; padding:8px 6px; gap:4px; }}
            .ticker-name {{ max-width:100px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="header-top">
                <div class="header-title">
                    <span style="font-size:26px;">🇺🇸</span>
                    <h1>미국 시장 트랙커</h1>
                </div>
                <div class="update-time">
                    <span class="dot"></span>
                    {UPDATE_TIME}
                </div>
            </div>
            <div class="index-bar">
                {index_bar_html}
            </div>
            <div class="color-note">
                💡 미국식 색상: <span class="green-dot">🟢 상승</span> / <span class="red-dot">🔴 하락</span>
            </div>
        </div>

        <!-- Chart Section -->
        <div class="chart-section">
            <div class="chart-header">
                <span class="chart-ticker" id="chartTicker">SPY</span>
                <span class="chart-name" id="chartName">SPDR S&P 500</span>
            </div>
            <div class="chart-container" id="tradingview_chart"></div>
        </div>

        <div class="tab-container">
            <button class="tab-btn active" onclick="switchTab('stocks')"><span style="font-size:16px;">📈</span> 개별 주식</button>
            <button class="tab-btn" onclick="switchTab('etf')"><span style="font-size:16px;">📊</span> ETF</button>
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

        <div class="footer">
            <p>💡 본 데이터는 투자 참고용이며, 투자 판단은 본인의 책임입니다.</p>
            <p style="margin-top:6px;">데이터 출처: Yahoo Finance · 업데이트: 매일 06:10 KST</p>
        </div>
    </div>

    <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
    <script>
        let currentTicker = 'SPY';
        let tvWidget = null;

        function switchTab(tabName) {{
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById('tab-' + tabName).classList.add('active');
            const map = {{ stocks: 0, etf: 1 }};
            document.querySelectorAll('.tab-btn')[map[tabName]].classList.add('active');
        }}

        function selectTicker(ticker, name) {{
            if (ticker === currentTicker) return;
            currentTicker = ticker;

            // Update header
            document.getElementById('chartTicker').textContent = ticker;
            document.getElementById('chartName').textContent = name;

            // Update row highlighting
            document.querySelectorAll('.data-table tbody tr').forEach(row => {{
                row.classList.remove('selected');
                if (row.dataset.ticker === ticker) {{
                    row.classList.add('selected');
                }}
            }});

            // Reload chart
            loadChart(ticker);
            
            // Scroll to top on mobile
            if (window.innerWidth <= 768) {{
                window.scrollTo({{ top: 0, behavior: 'smooth' }});
            }}
        }}

        function loadChart(ticker) {{
            const container = document.getElementById('tradingview_chart');
            container.innerHTML = '';

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

        // Load default chart on page load
        document.addEventListener('DOMContentLoaded', function() {{
            loadChart('SPY');
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

    # 1. Index data
    index_data = get_index_data()
    print(f"  ✅ Index data loaded")

    # 2. Stock data
    gainers, unusual_vol, new_highs = get_stock_data(sp500, russell)
    print(f"  ✅ Stocks: {len(gainers)} gainers, {len(unusual_vol)} unusual vol, {len(new_highs)} new highs")

    # 3. ETF data
    etf_gainers, etf_losers, etf_active = get_etf_data(etf_list)
    print(f"  ✅ ETFs: {len(etf_gainers)} gainers, {len(etf_losers)} losers, {len(etf_active)} active")

    # 4. Generate HTML
    print("🔧 Generating HTML dashboard...")
    html = generate_html(
        index_data, gainers, unusual_vol, new_highs,
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
