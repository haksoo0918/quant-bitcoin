# 변경 이력 (Changelog)

이 프로젝트의 모든 중요한 변경 사항은 이 파일에 기록됩니다.
이 프로젝트는 유의적 버전(Semantic Versioning)을 준수합니다.

---

## [1.2.1] - 2026-08-21

### Added (추가됨)
- 백테스트 성과 보고서(`backtest_report_YYYYMMDD_HHMMSS.md`), 차트 이미지(`backtest_result_YYYYMMDD_HHMMSS.png`), 최적화 보고서(`backtest_optimization_report_YYYYMMDD_HHMMSS.md`) 생성 시 실행 일시 타임스탬프를 파일명에 자동 포함하도록 파일 명명 규칙 개선.
- 마크다운 보고서 내부의 차트 이미지 링크를 동적 타임스탬프 파일명과 자동 연동하도록 보완.

## [1.2.0] - 2026-08-21

### Added (추가됨)
- **실행 환경 이원화 아키텍처 구축 (GitHub Actions vs Local PC)**:
  - **GitHub Actions**: 거래소 API Key 및 잔고 조회 없이 공개 시세 API 기반으로 시장 방향성과 모바일 매매 가이드를 브리핑하는 **시그널 전용 모드 (`SIGNAL_ONLY`)** 추가.
  - **Local PC (`run_bot.bat`)**: 실제 주문 권한 API Key를 연동하여 실계좌 잔고 조회, 전략 판단, 실제 매수/매도 주문 집행을 수행하는 **실제 자동매매 모드 (`LIVE_TRADING`)** 분리.
- **디스코드 알림 메시지 포맷 완전 분리**:
  - GitHub Actions: `📢 [GitHub Actions] 퀀트 전략 일일 방향성 시그널 브리핑` (지표 현황, 전략 방향성, 모바일 가이드)
  - Local PC: `⚡ [로컬 자동매매] 실거래 주문 체결 및 포트폴리오 잔고 보고서` (실계좌 자산, 보유 코인 수익률, 당일 주문 체결 내역)

### Changed (변경됨)
- `src/config.py`: `IS_GITHUB_ACTIONS`, `SIGNAL_ONLY`, `DRY_RUN` 환경 감지 및 모드 분기 로직 고도화.
- `.github/workflows/main.yml`: 워크플로우 실행 환경에서 불필요한 거래소 API Key 환경변수를 제거하고 `DISCORD_WEBHOOK_URL` 1개로 단일화.
- `run_bot.example.bat`: 로컬 실거래 자동매매 템플릿으로 갱신.

## [1.1.2] - 2026-08-21

### Changed (변경됨)
- 백테스트 산출물(마크다운 보고서 및 차트 이미지)의 저장 위치를 프로젝트 루트에서 `backtest/` 디렉토리로 구조화 및 분리.
- `.gitignore` 설정을 `backtest/*.md`, `backtest/*.png` 패턴으로 간소화하여 불필요한 백테스트 부산물의 Git 추적 방지.

### Fixed (수정됨)
- GitHub Actions 워크플로우(`.github/workflows/main.yml`)의 실행 액션 버전(`actions/checkout@v4.2.2`, `actions/setup-python@v5.6.0`)을 업데이트하여 Node.js 20 Deprecation 경고 해소.

### Documentation (문서화)
- `README.md` 내 최적화 파라미터(BTC 220일, ETH 50일 SMA) 및 `backtest/` 폴더 경로 설명 동기화.

## [1.1.1] - 2026-08-21

### Fixed (수정됨)
- 실거래 자동매매 봇의 지표 필터 이동평균(SMA) 파라미터를 백테스트 최적 결과인 BTC 220일, ETH 50일로 상향/하향 튜닝하여 기획 사양을 실제 매매 시스템에 동기화.
- `src/config.py`에 이평선 기간 상수(`BTC_SMA_LEN`, `ETH_SMA_LEN`)를 추출 및 분리하여 `src/main.py`에서 지표 계산 시 동적 적용되도록 리팩토링.
- 이평선 기간 변경에 맞추어 `src/main.py` 내의 캔들 수집 조회수(`count`)를 자동으로 연동 계산하도록 보완하여 데이터 부족에 따른 `IndexError` 위험 차단.

## [1.1.0] - 2026-08-21

### Added (추가됨)
- 백테스트 스크립트(`src/backtest.py`)에 `--no-rebalance` 옵션 추가 (포트폴리오 비중 재조정 없이 BTC/ETH를 각각 초기 자본 50% 분할로 개별 독립 매매하는 모드).
- 백테스트 최적화 모드(`--optimize`) 구동 시 `--no-rebalance` 옵션과의 연계를 지원하여, 리밸런싱 미적용 시의 최적 파라미터 조합 랭킹 보고서(`backtest_optimization_report_no_rebalance.md`)를 별도 산출하도록 기능 확장.
- 상품 요구사항 정의서(`PRD.md`)에 다양한 백테스트 시나리오 가변 실행 옵션들을 제품 기능 요구사항 규격으로 신규 등재.

## [1.0.0] - 2026-08-20

### Added (추가됨)
- 업비트 API 기반 메인 퀀트 매매 전략 구현 (BTC/ETH 50:50 배분 및 ±10%p 비중 밴드 리밸런싱).
- 빗썸 API 기반 서브 알트코인 모멘텀 매매 전략 구현 (공통 시장 필터에 따른 하락장 청산 및 월요일 상승장 4개 알트코인 로테이션).
- 빗썸 v1 API 규격 연동 및 JWT 인증 서명(HMAC-SHA256 및 SHA-512 해싱) 자체 구현 (`bithumb_api.py`).
- 포트폴리오 평가 금액, 종목 비중, 수익률 현황 등을 가독성 있게 요약해주는 디스코드 웹훅 알림 시스템 구축.
- 네트워크 및 API 오류 대응을 위한 최대 3회 자동 재시도 및 디스코드 비상 알림 전송 기능 (`main.py`).
- 빗썸 알트코인 선정 연산을 실시간 시세 데이터로 사전 검증할 수 있는 독립 테스트 스크립트 (`test_monday.py`).
- 무상태(Stateless) 실행 환경을 극복하기 위한 과거 일봉 데이터 역방향 탐색 기반 시장 필터 히스테리시스 로직 도입.
- 로컬 모의 매매 및 시뮬레이션을 위한 드라이런(Dry-Run) 모드 지원.
- 윈도우 스케줄러 등록 및 원클릭 로컬 구동을 위한 실행 배치 스크립트 추가 (`run_bot.bat`).
- 윈도우 환경 중심의 로컬 설치, 스케줄링 등록 가이드를 담은 `README.md` 작성.
- 빗썸 알트코인 전략 및 모의투자(DRY_RUN) 활성화 여부를 `config.py` 한 곳에서 모두 제어할 수 있는 기능 추가.
- 프로젝트 소스 코드 파일(.py)들을 `src/` 폴더로 통합 및 실행 배치 파일(`run_bot.bat`) 경로 최적화.
- GitHub Actions 기반의 '조회 전용 시그널 알림 봇'을 기본 구동 시나리오로 변경 및 워크플로우 파일 추가 (`.github/workflows/main.yml`).
- 시그널 봇 구동 컨셉에 맞추어 디스코드 보고서 제목 및 하단 매매 제안 탭 명칭(당일 주문 체결 내역 -> 당일 리밸런싱 추천 시그널)을 포함해 전반적인 텍스트 최적화 적용.
- 업비트 과거 KRW 시세 기반의 퀀트 전략 백테스트 및 파라미터 최적화(Grid Search) 연산 엔진 구현 및 시각화 리포트 기능 추가 (`src/backtest.py`).

### Fixed (수정됨)
- 윈도우 환경(CP949 인코딩)에서 `run_bot.bat` 실행 시, UTF-8 기반 한글 주석의 바이트 깨짐으로 인해 API 키 일부가 명령어로 실행되어 크래시되는 오류 수정 (주석 영문화 및 ASCII 코드 호환 스크립트로 갱신).

