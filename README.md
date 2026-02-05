# 🇺🇸 미국 시장 트랙커

매일 아침 06:10 KST 자동 업데이트되는 미국 시장 대시보드.  
한국 투자자를 위한 미국 주식 / ETF / 옵션 시장 트래킹 도구.

## 📊 기능

### 주식 탭
- **🔥 오늘의 급등주 Top 10** — S&P 500 + Russell 2000 기준
- **📊 이상 거래량 Top 10** — 20일 평균 대비 거래량 급증 종목
- **🏆 52주 신고가** — 오늘 52주 최고가를 갱신한 종목

### ETF 탭
- **🟢 ETF 수익률 Top 10** — 한국어 카테고리 포함
- **🔴 ETF 하락률 Top 10**
- **💰 ETF 거래량 Top 10**

### 옵션 탭
- **📈 옵션 강세 신호** — 콜 옵션 거래량 급증 (매수 신호)
- **📉 옵션 약세 신호** — 풋 옵션 거래량 급증 (매도 신호)
- **⚡ 이상 옵션 거래** — 대형 옵션 거래 포착

### 차트
- 모든 종목 클릭 시 **TradingView 1년 차트** 팝업

## 🚀 설정 방법

1. 이 저장소를 Fork 합니다
2. Settings → Pages → Source: `main` branch 선택
3. Settings → Actions → General → Workflow permissions: "Read and write permissions" 선택
4. Actions 탭에서 workflow 활성화
5. 수동 실행: Actions → "Update US Market Tracker" → "Run workflow"

## 📁 구조

```
├── generate_dashboard.py    # 메인 스크립트
├── index.html               # 생성된 대시보드 (자동)
├── requirements.txt
├── data/
│   ├── tickers_sp500.json       # S&P 500 종목 목록
│   ├── tickers_russell2000.json # Russell 2000 종목 목록
│   ├── tickers_options.json     # 옵션 모니터링 50종목
│   ├── etf_list.json            # ETF 200종목 + 한국어 카테고리
│   └── 52week_highs.json        # 52주 최고가 추적 (자동 생성)
└── .github/workflows/
    └── update.yml               # 매일 06:10 KST 자동 실행
```

## ⏰ 업데이트 스케줄

- **매일 06:10 KST** (월~금) 자동 실행
- US 시장 마감 후 데이터 수집
- GitHub Pages로 자동 배포

## 🛠 수동 실행

```bash
pip install -r requirements.txt
python generate_dashboard.py
```

## 📝 참고

- 💡 미국식 색상 기준: 🟢 상승 / 🔴 하락
- 데이터 출처: Yahoo Finance
- 옵션 데이터는 주식 매매 참고용 신호입니다
- 투자 판단은 본인의 책임입니다
