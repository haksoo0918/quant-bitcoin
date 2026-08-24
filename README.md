# 📈 암호화폐 퀀트 매매 시그널 알림 시스템 (업비트 & 빗썸)

이 프로젝트는 지정 거래소 API를 활용하여 메인 전략(업비트) 및 서브 전략(빗썸) 포트폴리오의 리밸런싱 방향(시그널)을 자동으로 분석하고, 추천 매매 제안 내역과 자산 현황을 디스코드 웹훅으로 매일 전송하는 퀀트 시그널 알림 시스템입니다. 

거래소 API의 '조회' 권한만 사용하여 작동하므로, 고정 IP 등록 제약 없이 GitHub Actions(깃허브 액션) 환경에서 매일 무료로 24시간 안정적으로 자동 구동됩니다.

---

## 📂 파일 구성 및 기능

```
quant-bitcoin/
├── docs/                         # PWA 웹 대시보드 및 GitHub Pages 배포 루트
│   ├── index.html                # 반응형 웹 대시보드 SPA
│   ├── manifest.json             # PWA 매니페스트 설정
│   ├── service-worker.js         # PWA 오프라인 캐싱 서비스 워커
│   ├── icons/                    # PWA 앱 아이콘
│   └── data/status.json          # 최신 일일 전략 상태 데이터
├── run_bot.bat                   # 윈도우 로컬 실행 래퍼 배치 파일
├── run_bot.example.bat           # 로컬 실행 배치 파일 템플릿
├── requirements.txt              # 파이썬 의존성 패키지 목록
├── PRD.md                        # 상품 요구사항 정의서
├── CHANGELOG.md                  # 버전 변경 이력 문서
├── scripts/                      # 편의 유틸리티 스크립트
│   ├── setup_scheduler.bat       # Windows 작업 스케줄러 일일 자동실행 등록기
│   └── remove_scheduler.bat      # Windows 작업 스케줄러 등록 해제기
├── backtest/                     # 백테스트 실행 결과물 저장 폴더 (보고서, 차트 이미지)
└── src/                          # 소스 코드 폴더
    ├── config.py                 # 전역 상수 및 시스템 제어 설정 파일
    ├── indicators.py             # 공통 기술적 지표(SMA, ATR, 버퍼, 히스테리시스) 연산 모듈
    ├── discord_bot.py            # 디스코드 리포트 메시지 포맷팅 및 전송 봇
    ├── bithumb_api.py            # 빗썸 v1 REST API 연동 클라이언트 클래스
    ├── test_monday.py            # 빗썸 월요일 상승장 종목 선정 로직 독립 테스트 스크립트
    ├── backtest.py               # 과거 데이터 기반 퀀트 전략 백테스트 연산 스크립트
    └── main.py                   # 메인 오케스트레이터 및 시그널 계산/리포팅 로직
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

### 2. 서브 전략 (빗썸)
* **대상 자산**: 빗썸 원화(KRW) 마켓의 알트코인 (BTC, ETH 제외)
* **공통 시장 필터 (업비트 BTC 기준)**:
  * 상승장 판정: `현재가 >= 220일 SMA * 1.02`
  * 하락장 판정: `현재가 < 220일 SMA * 0.98`
  * 버퍼 구간(Standby): 가격이 버퍼 범위 내에 있을 경우, 과거 일봉 데이터를 역순으로 탐색하여 최근에 결정된 시장 상태를 현재 상태로 계승(유지)합니다.
* **매일 점검 (09:05 KST)**:
  * 공통 시장 필터가 **하락장** 일 경우, 요일에 상관없이 보유한 모든 알트코인을 즉시 전량 시장가 매도하여 안전하게 현금화(KRW)합니다.
* **주간 리밸런싱 (매주 월요일 09:05 KST)**:
  * 공통 시장 필터가 **상승장** 일 때만 실행합니다.
  * 종목 선정 단계:
    1. 최근 7일 평균 거래대금 상위 10개 종목 추출
    2. 선별된 10개 종목 중 최근 14일 수익률(상대 모멘텀) 상위 4개 종목 최종 선정
  * 매매 실행: 선정된 4개 종목에 빗썸 서브 자산의 각 25%씩 동일 비중(1/N)으로 매수합니다. (기존 종목 중 탈락한 종목은 전량 매도 후 교체)

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

### 2. PWA 웹 대시보드 & GitHub Pages 연동

별도의 유료 웹 서버 없이 **GitHub Pages** 무료 호스팅을 통해 모바일 및 PC 브라우저에서 실시간 전략 상태 대시보드를 열람하고, 모바일 홈 화면에 **PWA 앱(바로가기)** 으로 설치하여 편리하게 이용할 수 있습니다.

#### 1) GitHub Pages 활성화 방법
1. 저장소 상단 메뉴의 **[Settings]** 클릭
2. 왼쪽 사이드바의 **[Pages]** 클릭
3. **Build and deployment** -> **Source** 항목에서 **Deploy from a branch** 선택
4. **Branch** 를 **`main`**, 폴더를 **`/docs`** 로 설정한 후 **[Save]** 클릭
5. 수 분 내로 `https://<사용자아이디>.github.io/<저장소이름>/` 주소로 웹 대시보드가 오픈됩니다.

#### 2) 대시보드 주요 기능
* **종합 매매 행동 가이드**: 오늘의 업비트(BTC/ETH) 및 빗썸(알트코인) 즉시 행동 요약
* **업비트 50:50 듀얼 모멘텀**: BTC(220일 SMA ±2%) 및 ETH(50일 SMA ± 1.5 ATR) 현재가, 기준 채널 지표, 상태 뱃지 표시
* **빗썸 알트코인 모멘텀**: 공통 시장 필터(상승장/하락장) 및 매주 월요일 자동 갱신되는 추천 4대 알트코인 랭킹
* **장중 실시간 새로고침**: 우측 상단 `새로고침` 버튼 클릭 시 업비트 공개 시세 API를 실시간 호출하여 현재가 및 이탈 여부 즉시 갱신
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

* **부가 옵션: 빗썸 알트코인 제외 (업비트 메인만 단독 실행)**:
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

* **Windows 작업 스케줄러 자동 실행 등록 (로컬 24시간 무인 매매)**:
  `scripts/setup_scheduler.bat`을 실행하면 매일 오전 09:05 KST에 `run_bot.bat --live`가 자동으로 실행되도록 Windows 작업 스케줄러에 즉시 등록됩니다. (해제 시 `scripts/remove_scheduler.bat` 실행)

---

### 4. 로컬 백테스트 및 파라미터 최적화 실행

실제 업비트 과거 일봉 데이터를 다운로드하여 전략 수익률을 검증하거나 이동평균 최적 기간을 도출할 수 있습니다. (다운로드한 데이터는 `data/` 디렉토리에 캐싱됩니다.)

* **단일 조건 백테스트 수행 (성과 보고서 및 차트 이미지 자동 생성)**:
  ```bash
  python src/backtest.py --btc-sma 220 --eth-sma 50 --days 1500
  ```
  * **슬리피지(Slippage) 보수적 반영**: `--slippage 0.05` (0.05% 슬리피지 추가) 옵션을 부여하여 시장가 체결 오차를 반영한 정밀 백테스트를 수행할 수 있습니다.
    ```bash
    python src/backtest.py --btc-sma 220 --eth-sma 50 --slippage 0.05
    ```
  * 실행 완료 시 **`backtest/`** 폴더에 **`backtest_report_YYYYMMDD_HHMMSS.md`** 상세 보고서와 **`backtest_result_YYYYMMDD_HHMMSS.png`** 자산 변동 추이 차트가 타임스탬프와 함께 자동 생성됩니다.
  * **리밸런싱 미적용 모드 (독립 자산 운용)**: `--no-rebalance` 옵션을 추가하면 비중 조절 거래 없이 두 자산을 독립 운용하는 시뮬레이션을 수행합니다.
    ```bash
    python src/backtest.py --btc-sma 220 --eth-sma 50 --no-rebalance
    ```
  
* **전체 이동평균선 조합 파라미터 최적화 (Grid Search)**:
  ```bash
  python src/backtest.py --optimize
  ```
  * 연산 완료 시 모든 SMA 조합의 성과가 분석되어 누적 수익률이 높은 순서로 정렬된 **`backtest/backtest_optimization_report_YYYYMMDD_HHMMSS.md`** 보고서가 생성되며, 상위 15개 최적 조합이 콘솔 창에 랭킹 표로 출력됩니다.
  * **리밸런싱 미적용 최적화**: `--no-rebalance` 옵션을 함께 추가하면 리밸런싱 없는 독립 자산 기준의 최적 파라미터 조합 랭킹 보고서인 **`backtest/backtest_optimization_report_no_rebalance_YYYYMMDD_HHMMSS.md`** 가 생성됩니다.
    ```bash
    python src/backtest.py --optimize --no-rebalance
    ```

