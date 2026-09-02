# 📈 암호화폐 퀀트 매매 시그널 알림 시스템 (업비트 & 빗썸)

이 프로젝트는 지정 거래소 API를 활용하여 메인 전략(업비트) 및 서브 전략(빗썸) 포트폴리오의 리밸런싱 방향(시그널)을 자동으로 분석하고, 추천 매매 제안 내역과 자산 현황을 디스코드 웹훅으로 매일 전송하는 퀀트 시그널 알림 시스템입니다. 

거래소 API의 '조회' 권한만 사용하여 작동하므로, 고정 IP 등록 제약 없이 GitHub Actions(깃허브 액션) 환경에서 매일 무료로 24시간 안정적으로 자동 구동됩니다.

---

## 📂 파일 구성 및 기능

```
quant-bitcoin/
├── docs/                         # PWA 웹 대시보드 소스 루트 (GitHub Pages 상시 서비스 중)
│   ├── index.html                # 반응형 웹 대시보드 SPA (지표 차트 & 백테스트 탭)
│   ├── manifest.json             # PWA 매니페스트 설정
│   ├── service-worker.js         # PWA 오프라인 캐싱 서비스 워커
│   ├── icons/                    # PWA 앱 아이콘
│   ├── images/                   # 백테스트 자산 성장 곡선 차트 이미지 (메인 / 서브)
│   └── data/status.json          # 최신 일일 전략 상태 데이터 (60일 시계열 차트 데이터 동봉)
├── tests/                        # TDD 단위 테스트 스위트 (pytest)
│   └── test_status_pipeline.py   # 시계열 데이터 무결성 및 자동 푸시 파이프라인 검증
├── run_bot.bat                   # 윈도우 로컬 실행 래퍼 배치 파일
├── run_bot.example.bat           # 로컬 실행 배치 파일 템플릿
├── requirements.txt              # 파이썬 의존성 패키지 목록
├── PRD.md                        # 상품 요구사항 정의서
├── CHANGELOG.md                  # 버전 변경 이력 문서
├── scripts/                      # 편의 유틸리티 스크립트
│   ├── view_dashboard.bat        # 로컬 PWA 대시보드 및 차트 원클릭 실행기
│   ├── setup_scheduler.bat       # Windows 작업 스케줄러 일일 자동실행 등록기
│   └── remove_scheduler.bat      # Windows 작업 스케줄러 등록 해제기
├── backtest/                     # 백테스트 실행 결과물 저장 폴더 (main/, sub_eth/)
└── src/                          # 소스 코드 폴더
    ├── config.py                 # 전역 상수 및 시스템 제어 설정 파일
    ├── indicators.py             # 공통 기술적 지표(SMA, ATR, SuperTrend, 버퍼, 히스테리시스) 연산 모듈
    ├── discord_bot.py            # 디스코드 리포트 메시지 포맷팅 및 전송 봇
    ├── bithumb_api.py            # 빗썸 v1 REST API 연동 클라이언트 클래스
    ├── backtest.py               # 메인 전략(업비트 BTC/ETH 50:50) 백테스트 연산 스크립트
    ├── backtest_bithumb_eth.py   # 빗썸 서브 전략(이더리움 SuperTrend + 50일 SMA) 백테스트 스크립트
    └── main.py                   # 메인 오케스트레이터 및 실거래/시그널 자동화 엔진
```

---

## ⚙️ 상세 전략 알고리즘

### 1. 메인 전략 (업비트)
* **대상 자산**: BTC, ETH (목표 비중 각 50%)
* **실행 주기**: 매일 오전 09:05 KST
* **개별 추세 필터**:
  * **BTC (상하한 ±2% 버퍼 적용)**:
    * 신규 매수 (미보유 시): `현재가 >= 220일 SMA * 1.02`
    * 매도/현금화 (보유 시): `현재가 < 220일 SMA * 0.98`
  * **ETH (14일 ATR의 1.5배 버퍼 적용)**:
    * 신규 매수 (미보유 시): `현재가 >= 50일 SMA + (ATR(14) * 1.5)`
    * 매도/현금화 (보유 시): `현재가 < 50일 SMA - (ATR(14) * 1.5)`
* **비중 밴드 리밸런싱**:
  * BTC와 ETH 모두 추세 필터를 통과하여 보유 중일 때만 평가합니다.
  * 한쪽 자산의 비중이 목표 비중(50%) 대비 10%p를 초과하여 벗어날 때(40% 미만 혹은 60% 초과)만 50:50 비중으로 재조정 매매를 수행합니다.

### 2. 서브 전략 (이더리움 SuperTrend + 50일 SMA 추세 추종)
* **대상 자산**: 이더리움(ETH)
* **전략 모델**: SuperTrend(7, 3.5) 변동성 밴드와 50일 SMA 대추세 필터를 결합한 단독 고수익/저낙폭 추세 추종 모델
* **진입/보유 조건 (100% 풀매수)**:
  * `일봉 종가 >= 50일 SMA` AND `SuperTrend(7, 3.5) == Green(상승 추세)`
  * 상승 파동을 끝까지 추종하여 자산의 **100%를 이더리움에 집중 투자/보유**
* **청산/현금화 조건 (100% 현금 보존)**:
  * `일봉 종가 < 50일 SMA` OR `SuperTrend(7, 3.5) == Red(하락 추세)`
  * 하락/약세장 진입 시 즉시 전량 매도하여 **100% 원화(KRW) 현금 보존 (MDD -25% 철저 통제)**
* **실행 주기**: 매일 09:05 KST 신호 판정 후 자동 매매 또는 관망.

---

## 🚀 실행 환경 및 사용 방법

본 시스템은 **GitHub Actions(클라우드 시그널 브리핑)** 와 **Local PC(로컬 시그널 확인, 모의매매, 실거래 자동매매)** 로 명확히 구분되어 구동됩니다.

---

### 1. GitHub Actions 자동 시그널 브리핑 (매일 09:05 KST 자동 실행)

개인 PC를 켜둘 필요 없이 깃허브 서버에서 매일 아침 전략 방향성 및 추천 매매 가이드를 디스코드로 무료 수신합니다.

* **API 키 불필요**: 공개 시세 API만 사용하므로 거래소 API 키 등록이나 잔고 조회가 필요 없습니다.
* **GitHub Secrets 등록**:
  1. 저장소 상단 메뉴의 **[Settings]** 클릭
  2. 왼쪽 사이드바의 **[Secrets and variables] -> [Actions]** 클릭
  3. **[New repository secret]** 버튼 클릭 후 **`DISCORD_WEBHOOK_URL`** 1개만 등록
* **작동 확인 및 수동 테스트**:
  * **[Actions]** -> **[Crypto Quantitative Trading Signal Bot]** -> **[Run workflow]** 를 클릭하여 즉시 테스트 가능합니다.

---

### 2. PWA 웹 대시보드 & 실시간 전략 차트 (GitHub Pages)

별도의 유료 웹 서버 없이 **GitHub Pages** 무료 호스팅을 통해 모바일 및 PC 브라우저에서 실시간 전략 상태 대시보드를 열람하고, 모바일 홈 화면에 **PWA 앱(바로가기)** 으로 설치하여 편리하게 이용할 수 있습니다.

* 🌐 **웹 대시보드 바로가기**: **[https://haksoo0918.github.io/quant-bitcoin/](https://haksoo0918.github.io/quant-bitcoin/)**
* 🖥️ **로컬 PC 실행**: `scripts/view_dashboard.bat` 더블 클릭 (로컬 `http://localhost:8000` 즉시 오픈)

#### 1) GitHub Pages 설정 안내 (저장소 기본 연동)
1. 저장소 상단 메뉴의 **[Settings]** 클릭
2. 왼쪽 사이드바의 **[Pages]** 클릭
3. **Build and deployment** -> **Source** 항목에서 **Deploy from a branch** 선택
4. **Branch** 를 **`main`**, 폴더를 **`/docs`** 로 설정한 후 **[Save]** 클릭
5. `https://haksoo0918.github.io/quant-bitcoin/` 주소로 상시 서비스가 제공됩니다.

#### 2) 대시보드 주요 기능
* **종합 매매 행동 가이드**: 오늘의 메인 전략(BTC/ETH 50:50) 및 서브 전략(이더리움 SuperTrend + 50일 SMA) 즉시 행동 요약
* **전략별 인터랙티브 시각화 차트**: 최근 60일 비트코인 220일 버퍼 채널, 이더리움 50일 ATR 채널, ETH SuperTrend 추세선 Canvas 차트 탭 제공
* **역사적 백테스트 검증 2종 탭 & 차트 이미지**: 메인 전략(4.3년, CAGR 30.36%, MDD -28.07%) 및 서브 전략(4.1년, CAGR 43.38%, MDD -31.28%)의 자산 성장 곡선 그래프 시각화
* **0.01초 즉시 렌더링 & CORS 방어**: 데스크톱 봇이 매일 아침 생성/푸시한 `status.json` 스냅샷을 1순위로 읽어 CORS 차단 없이 초고속 렌더링
* **장중 실시간 시세 조회**: 우측 상단 `실시간 시세` 버튼 클릭 시 업비트 공개 시세 API를 실시간 호출하여 현재가 및 이탈 여부 즉시 갱신
* **PWA 앱 설치 지원**: 브라우저 주소창 또는 `📲 앱 설치` 버튼을 통해 스마트폰 홈 화면에 단독 앱으로 설치 가능

---

### 3. 로컬 PC 실행 방법 (CLI 인자 및 `.env` 환경 설정)

로컬 환경에서는 API Key를 **`.env`** 파일에 안전하게 보관하고, 실행 옵션은 **CLI 명령어 인자(Arguments)** 로 직관적으로 제어합니다.

#### 1) 환경 변수 설정 (`.env`)
프로젝트 루트의 `.env.example`을 복사하여 **`.env`** 파일을 생성하고 API Key 및 웹훅 주소를 입력합니다.
```bash
cp .env.example .env
```
```env
UPBIT_ACCESS_KEY=실제_업비트_액세스키
UPBIT_SECRET_KEY=실제_업비트_시크릿키
BITHUMB_ACCESS_KEY=실제_빗썸_액세스키
BITHUMB_SECRET_KEY=실제_빗썸_시크릿키
DISCORD_WEBHOOK_URL=디스코드_웹훅_주소
```
*( `.env` 파일은 `.gitignore`에 등록되어 있어 GitHub에 업로드되지 않습니다. )*

#### 2) 목적별 CLI 실행 명령어

* **모드 A. 로컬에서 전략 방향성(시그널)만 확인 (API 키 불필요)**:
  - 거래소 API 키 없이 즉시 공개 시세를 바탕으로 오늘의 전략 방향성과 모바일 매매 가이드만 확인합니다.
  ```bash
  python src/main.py --signal-only
  # 또는 약칭: python src/main.py -s
  ```
  *(콘솔 창 및 디스코드에 `📢 [GitHub Actions] 퀀트 전략 일일 방향성 시그널 브리핑` 포맷으로 출력)*

* **모드 B. 로컬 모의 매매 테스트 (Dry-Run)**:
  - 실제 주문을 넣지 않고 가상 계좌 잔고를 바탕으로 리밸런싱 주문 시뮬레이션 및 디스코드 보고서를 확인합니다.
  ```bash
  python src/main.py --dry-run
  # 또는 약칭: python src/main.py -d
  ```
  *(콘솔 창 및 디스코드에 `⚡ [로컬 모의매매] 모의 주문 체결 및 포트폴리오 잔고 보고서` 포맷으로 출력)*

* **모드 C. 실제 자동 매수/매도 주문 집행 (Live Trading)**:
  - `.env`에 설정된 실계좌 잔고를 조회하여 비중 이탈 시 거래소에 실제 시장가 주문을 집행하고 실거래 보고서를 전송합니다.
  ```bash
  python src/main.py --live
  # 또는 약칭: python src/main.py -l
  ```
  *(거래소 실제 체결 후 `⚡ [로컬 자동매매] 실거래 주문 체결 및 포트폴리오 잔고 보고서` 전송)*

* **부가 옵션: 빗썸 서브 전략 제외 (업비트 메인만 단독 실행)**:
  ```bash
  python src/main.py --live --no-alt
  ```

* **윈도우 배치 파일 실행 (`run_bot.bat`)**:
  더블클릭 실행을 원할 경우 `run_bot.example.bat`을 복사하여 `run_bot.bat`으로 사용하거나, 터미널에서 인자를 넘겨 바로 실행할 수 있습니다:
  ```bat
  run_bot.bat --signal-only
  run_bot.bat --dry-run
  run_bot.bat --live
  ```
  * **실행 모드별 자동 종료(Pause) 분기**:
    * **스케줄러/CLI 인자 전달 시 (`run_bot.bat --live` 등)**: 매매 완료 즉시 터미널 창이 자동으로 닫힙니다 (24시간 무인 자동화).
    * **사용자 수동 더블 클릭 시 (인자 없음)**: 실행 로그를 확인할 수 있도록 `pause` 대기 상태가 유지됩니다.

* **Windows 작업 스케줄러 자동 실행 등록 (로컬 24시간 무인 매매)**:
  `scripts/setup_scheduler.bat`을 실행하면 매일 오전 09:05 KST에 `run_bot.bat --live`가 자동으로 실행되도록 Windows 작업 스케줄러에 즉시 등록됩니다. (해제 시 `scripts/remove_scheduler.bat` 실행)

---

### 4. 로컬 백테스트 및 파라미터 최적화 실행

실제 업비트 과거 일봉 데이터를 다운로드하여 전략 수익률을 검증하거나 이동평균 최적 기간을 도출할 수 있습니다. (다운로드한 데이터는 `data/` 디렉토리에 캐싱됩니다.)

#### 1) 메인 전략 (업비트 BTC/ETH 50:50) 백테스트
* **단일 조건 백테스트 수행 (성과 보고서 및 차트 이미지 자동 생성)**:
  ```bash
  python src/backtest.py --btc-sma 220 --eth-sma 50 --days 1500
  ```
  * **슬리피지(Slippage) 보수적 반영**: `--slippage 0.05` (0.05% 슬리피지 추가) 옵션을 부여하여 시장가 체결 오차를 반영한 정밀 백테스트를 수행할 수 있습니다.
    ```bash
    python src/backtest.py --btc-sma 220 --eth-sma 50 --slippage 0.05
    ```
  * 실행 완료 시 **`backtest/main/`** 폴더에 **`backtest_report_YYYYMMDD_HHMMSS.md`** 상세 보고서와 **`backtest_result_YYYYMMDD_HHMMSS.png`** 자산 변동 추이 차트가 타임스탬프와 함께 자동 생성됩니다.
  * **리밸런싱 미적용 모드 (독립 자산 운용)**: `--no-rebalance` 옵션을 추가하면 비중 조절 거래 없이 두 자산을 독립 운용하는 시뮬레이션을 수행합니다.
    ```bash
    python src/backtest.py --btc-sma 220 --eth-sma 50 --no-rebalance
    ```
  
* **전체 이동평균선 조합 파라미터 최적화 (Grid Search)**:
  ```bash
  python src/backtest.py --optimize
  ```
  * 연산 완료 시 모든 SMA 조합의 성과가 분석되어 누적 수익률이 높은 순서로 정렬된 **`backtest/main/backtest_optimization_report_YYYYMMDD_HHMMSS.md`** 보고서가 생성되며, 상위 15개 최적 조합이 콘솔 창에 랭킹 표로 출력됩니다.

#### 2) 서브 전략 (이더리움 SuperTrend + 50일 SMA) 백테스트
* **이더리움 단독 추세 추종 백테스트 수행**:
  ```bash
  python src/backtest_bithumb_eth.py --days 1500
  ```
  * **파라미터 커스텀 옵션**:
    * `--period 7`: SuperTrend ATR 기간 (기본값: 7일)
    * `--multiplier 3.5`: SuperTrend ATR 승수 (기본값: 3.5)
    * `--sma 50`: 대추세 필터 SMA 기간 (기본값: 50일)
    * `--slippage 0.0005`: 슬리피지 비율 (기본값: 0.05%)
  * 실행 완료 시 **`backtest/sub_eth/`** 폴더에 **`backtest_bithumb_eth_report_YYYYMMDD_HHMMSS.md`** 보고서와 **`backtest_bithumb_eth_result_YYYYMMDD_HHMMSS.png`** 차트가 자동 저장됩니다.

---

### 5. TDD 단위 테스트 스위트 실행 (Test Suite)

`pytest`를 통해 시계열 데이터 파이프라인 무결성, 엣지 케이스 처리, Git 자동 푸시 안정성을 검증합니다.

```bash
python -m pytest tests/
```


