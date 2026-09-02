# 변경 이력 (Changelog)

이 프로젝트의 모든 중요한 변경 사항은 이 파일에 기록됩니다.
이 프로젝트는 유의적 버전(Semantic Versioning)을 준수합니다.

---

## [1.8.5] - 2026-09-02

### Changed (변경됨)
- **대시보드 서브 전략 명칭 단순화 및 직관성 개선 (`docs/index.html`, `PRD.md`, `docs/service-worker.js`)**:
  - 서브 전략 타이틀, 행동 가이드 배너, 차트 탭 버튼에서 '빗썸' 수식어를 제거하고 전략 본질인 '이더리움 SuperTrend + 50일 SMA'로 일원화.
  - 서비스 워커 캐시 버전(`v1.8.5`) 갱신.

## [1.8.4] - 2026-09-02

### Fixed (수정됨)
- **실거래/모의매매 프로세스 status.json 변수 미정의 오류 수정 및 자동 푸시 인코딩 개선 (`src/main.py`, `tests/test_status_pipeline.py`)**:
  - `run_live_trading` 함수에서 `live_status_data` 생성 시 `btc_upper`, `btc_lower`, `bithumb_data` 미정의로 인해 발생하던 `NameError` 버그 수정.
  - Windows 환경(`cp949`)에서 git 커밋 한글 메시지 디코딩 시 발생하던 `UnicodeDecodeError` 방지를 위해 `subprocess.run`에 `encoding="utf-8", errors="replace"` 적용.
  - 매매 모드(Live / Dry-Run)와 무관하게 봇 실행 시 항상 `status.json`이 GitHub에 안전하게 커밋/푸시되도록 로직 개선.

## [1.8.3] - 2026-09-01

### Fixed (수정됨)
- **모바일 퍼스트 레이아웃 반응형 최적화 (`docs/index.html`, `docs/service-worker.js`)**:
  - `360px~480px` 소형 모바일 화면에서 상단 헤더 버튼, 차트 상단 탭, 차트 수치 메타바가 겹치거나 텍스트가 줄바꿈/잘리는 현상 개선.
  - 차트 수치 메타바를 모바일 친화적 2x2 그리드 레이아웃으로 개편하여 시인성 및 정렬 개선.
  - Chart.js X축 일봉 날짜 눈금 레이블을 화면 크기(`window.innerWidth < 480`)에 맞춰 동적으로 조정(`maxTicksLimit: 5`)하여 겹침 방지.
  - 서비스 워커 캐시 버전(`v1.8.3`) 갱신.

## [1.8.2] - 2026-09-01

### Fixed (수정됨)
- **GitHub Pages CORS 방어, status.json 차트 데이터 동봉 및 TDD 파이프라인 구축 (`docs/data/status.json`, `src/main.py`, `tests/test_status_pipeline.py`)**:
  - GitHub Pages 도메인(`https://*.github.io`)에서 브라우저가 업비트 API를 직접 호출할 때 발생하는 CORS 차단(`net::ERR_FAILED`) 문제를 해결하기 위해 `status.json`에 60일 시계열 차트 데이터를 동봉.
  - 매일 아침 데스크톱 봇 실행 시 `status.json`을 자동 생성하고 GitHub에 안전하게 커밋/푸시하는 `auto_push_status_json()` 함수 구현.
  - `pytest` 기반 TDD 단위 테스트 스위트(`tests/test_status_pipeline.py`) 구축 및 검증 완료 (4개 테스트 통과).

### Changed (변경됨)
- **의존성 및 설정 주석 정리 (`requirements.txt`, `src/config.py`)**:
  - 단위 테스트 프레임워크 `pytest>=8.0.0`을 `requirements.txt`에 명시.
  - `src/config.py`의 빗썸 서브 전략 주석 및 설정을 최신 '이더리움 SuperTrend + 50일 SMA' 사양으로 일원화.

## [1.8.1] - 2026-09-01

### Fixed (수정됨)
- **자바스크립트 TDZ ReferenceError 수정 및 차트 렌더링 복구 (`docs/index.html`)**:
  - 초기 테마 적용 함수(`applyTheme`) 호출 시 하단에 선언된 `currentChartInstance`를 참조하여 발생하던 `ReferenceError`를 전역 변수 최상단 배치로 완벽 해결.
  - 캐시 유효성 검증 로직을 강화하여 차트 시계열 데이터 누락 시 즉시 재연산하도록 보강.
  - 실제 브라우저 자동화(Selenium Headless Chrome) 환경을 구축하여 3종 전략 탭 차트 렌더링 및 콘솔 에러 0건 실시간 검증 완료.

## [1.8.0] - 2026-09-01

### Added (추가됨)
- **전략별 인터랙티브 Canvas 시각화 차트 뷰 (`docs/index.html`)**:
  - `Chart.js` 초경량 Canvas 엔진 연동 및 PWA 오프라인 캐싱 적용 (`service-worker.js`).
  - 모바일 터치 탭 전환 지원: `[비트코인 220일 버퍼] | [이더리움 50일 ATR] | [빗썸 SuperTrend]`.
  - 최근 60일 종가 추세선, 220일/50일 SMA 기준선, 버퍼/ATR 밴드 음영 채우기, SuperTrend 상승(🟢)/하락(🔴) 동적 세그먼트 렌더링.
  - `hs-style` 다크 모드 및 라이트 모드 컬러 자동 테마 동기화.
- **오전 9시 기준 브라우저 순수 자바스크립트 지표 연산 & 스마트 로컬 캐싱 엔진 (`docs/index.html`)**:
  - `status.json` 백엔드 의존성을 전면 제거하고, 브라우저가 업비트 공개 API로 오전 09:00 확정 일봉을 직접 수신하여 SMA, ATR, SuperTrend(7, 3.5) 연산.
  - `localStorage` 스마트 캐싱: 당일 1회만 계산 저장하여 이후 재접속 시 트래픽 0 KB, 계산 시간 0ms로 즉시 렌더링.
  - 당일 아침 봇의 실제 매매 판정과 100% 일치하며, `실시간 시세` 버튼으로 장중 현재가 실시간 동기화 지원.

## [1.7.3] - 2026-08-31

### Added (추가됨)
- **디스코드 일일 자동매매/모의매매 보고서 내 전체 평가수익률 표기 기능 (`src/main.py`)**:
  - **통합 총 자산 및 종합 수익률**: 상단에 업비트와 빗썸을 합산한 전체 총 평가 자산 및 전체 평가수익률(`grand_total_ret`) 요약 라인 신설.
  - **전략별 총 자산 평가수익률**: 업비트 메인 전략(`upbit_total_ret`) 및 빗썸 서브 전략(`bithumb_total_ret`) 각각의 총 자산 라인에 매수원금(현금 포함) 대비 전체 수익률 표기.

## [1.7.2] - 2026-08-28

### Changed (변경됨)
- **GitHub Actions 자동 스케줄 비활성화 및 수동 전용 전환 (`.github/workflows/main.yml`)**:
  - 깃허브 무료 티어 대기열 지연으로 인한 불시 알림을 방지하기 위해 `schedule` 크론 비활성화.
  - 시세 및 전략 점검은 PWA 대시보드의 실시간 시세 조회 및 로컬 정시 스케줄러(09:05 KST)를 중심으로 운영.
- **웹 대시보드 상단 안내 문구 주석 처리 (`docs/index.html`)**:
  - 상단 "매일 오전 대략 9~10시 가격 측정 및 전략 수립" 배지 영역 주석 처리.
  - 상단 행동 가이드 배너의 빗썸 서브 전략 레이블을 현재 전략명으로 일원화.
- **GitHub Pages 호스팅 비활성화 상태 문서 반영 (`PRD.md`, `README.md`)**:
  - 기획서 및 리드미에 현재 GitHub Pages 호스팅이 OFF 상태임을 명시하고, 소스 코드 및 재활성화 가이드 보존.

## [1.7.1] - 2026-08-27

### Fixed (수정됨)
- **Windows 작업 스케줄러 자동 실행 시 터미널 창 자동 종료 처리 (`run_bot.bat`, `run_bot.example.bat`)**:
  - 작업 스케줄러(`--live` 등 인자 전달)로 구동될 경우 `pause` 없이 프로세스 완료 즉시 창이 자동으로 닫히도록 조건 분기 개선.
  - 마우스 더블 클릭(인자 없음)으로 수동 실행 시에만 터미널 결과 확인을 위해 `pause` 유지.

## [1.7.0] - 2026-08-26

### Added (추가됨)
- **빗썸 서브 전략: 이더리움 SuperTrend + 50일 SMA 단독 추세 추종 전략 전면 개편 (`src/main.py`, `src/indicators.py`, `src/backtest_bithumb_eth.py`, `docs/index.html`)**:
  - **고수익/저낙폭 퀀트 모델 도입**: 이더리움(ETH)의 폭발적 상승 파동을 추종하면서 약세장 시 100% 현금화하여 MDD(-25.03%)를 극적으로 방어하는 복합 전략 이식.
  - **지표 연산 엔진 모듈화**: `calculate_supertrend(df, period=7, multiplier=3.5)` 및 `calculate_bithumb_eth_indicators()` 공통 모듈 추가.
  - **전용 백테스트 시뮬레이터 구축 (`src/backtest_bithumb_eth.py`)**: 3.6년(1,500일) 실데이터 검증 (누적 +335.97%, CAGR +51.29%, MDD -25.03%, Calmar 2.05) 및 `backtest/sub_eth/` 자동 저장 파이프라인 구축.
  - **웹 대시보드 UI 전면 개편**: 빗썸 서브 전략 카드를 이더리움 SuperTrend 추세선 및 50일 SMA 기준선 실시간 표시 카드로 전환.
  - PWA 서비스 워커 캐시 버전 `v1.7.0`으로 갱신.

## [1.6.5] - 2026-08-26

### Fixed (수정됨)
- **Windows 작업 스케줄러 배치 스크립트 인코딩 및 구문 오류 수정 (`scripts/setup_scheduler.bat`, `scripts/remove_scheduler.bat`)**:
  - `cmd.exe` 실행 시 UTF-8 한글 문자열로 인한 파싱 오류 및 스케줄러 등록 실패 현상 해결.
  - 프로젝트 루트 절대 경로 자동 탐색 및 `schtasks` 옵션 순서 안정화.

### Changed (변경됨)
- **웹 대시보드 미사용 코드 정리 및 스타일 디자인 토큰 정돈 (`docs/index.html`, `docs/service-worker.js`)**:
  - **미사용 CSS 클래스/변수 삭제**: `.icon-lg`, `.alt-item-empty`, `.alt-sub-text`, `--card-shadow-hover`, `--accent-red` 등 불필요한 스타일 코드 정리.
  - **미사용 JS 스크립트 삭제**: 과거 알트코인명 변환 딕셔너리(`COIN_NAMES`) 및 `getCoinDisplayName()` 미사용 헬퍼 함수 정리.
  - **디자인 토큰(CSS 변수) 체계화**: 하드코딩된 `border-radius` 속성을 `:root`에 정의된 `var(--radius-*)` 변수로 일응화 및 셀렉터 중복 구조 단순화.
  - PWA 서비스 워커 캐시 버전 `v1.6.5`로 갱신.
- **백테스트 디렉터리 무시 규칙 단순화 (`.gitignore`)**:
  - `backtest/` 하위 파일 확장자별 개별 규칙을 `backtest/` 전체 디렉터리 무시 규칙으로 직관화.

## [1.6.4] - 2026-08-26

### Changed (변경됨)
- **모바일 PWA 캐싱 및 자동 데이터 갱신 파이프라인 전면 개편 (`docs/service-worker.js`, `docs/index.html`)**:
  - **Network-First 캐싱 정책 도입**: `index.html` 및 `status.json`에 네트워크 우선 정책을 적용하여 스마트폰 홈 화면 바로가기 실행 시 구버전 캐시 대신 실시간 최신 버전 자동 로드 보장.
  - **앱 라이프사이클 자동 동기화**: 스마트폰 화면 복귀 및 탭 포커스(`visibilitychange`, `pageshow`, `focus`) 시 최신 전략 상태 및 업비트 실시간 시세 자동 재조회.
  - **우상단 버튼 명칭 직관화**: 기존 `새로고침` 라벨을 **`실시간 시세`** (툴팁: `거래소 실시간 시세 및 전략 신호 갱신`)로 명확히 변경.
  - PWA 서비스 워커 캐시 버전 `v1.6.4`로 갱신.

## [1.6.3] - 2026-08-26

### Changed (변경됨)
- **백테스트 디렉토리 구조 표준화 및 자동 분류 (`src/backtest.py`, `src/backtest_bithumb_switching.py`, `.gitignore`)**:
  - `backtest/main/`: 업비트 메인 50:50 전략 백테스트 보고서 및 차트 자동 저장.
  - `backtest/sub_switching/`: 빗썸 100% 스위칭 서브 전략 백테스트 보고서 및 차트 자동 저장.
  - 과거 탐색 과정에서 생성된 130여 개 알트코인 임시 파일 정리 및 `.gitignore` 하위 경로 패턴 추가.

### Fixed (수정됨)
- **웹 대시보드 서브 전략 모멘텀 비교 카드 좌측 테두리 결손 수정 (`docs/index.html`)**:
  - 비선택 코인 블록의 `borderLeft = 'none'`으로 인해 1px 기본 박스 테두리가 사라지던 현상 수정 (기본 `4px solid var(--border-color)` 유지, 1등 코인에 `4px solid var(--accent-primary)` 하이라이트 부여).
  - PWA 서비스 워커 캐시 버전 `v1.6.3`으로 갱신.

## [1.6.2] - 2026-08-26

### Added (추가됨)
- **웹 대시보드 `hs-style` 디자인 시스템 전면 적용 (`docs/index.html`, `docs/service-worker.js`)**:
  - **모던 딥 틸 & 에메랄드 포인트 컬러 팔레트**: 라이트 모드 Deep Teal(`#0d9488`), 다크 모드 Emerald Teal(`#2dd4bf`) 적용으로 시각적 피로도 감소 및 신뢰감 강화.
  - **고정폭 금융 타이포그래피**: 주요 시세, 수익률, 지표 수치에 `D2Coding` 폰트를 적용하여 가독성 및 자릿수 정렬 극대화.
  - **Lucide Icons 정밀화**: 표준 선 두께(`1.75px`) 및 시맨틱 컬러 매핑으로 정갈하고 미니멀한 UI 구축.
  - **버튼 및 인터랙션 최적화**: 8px 라운딩 및 부드러운 머티리얼 감속 전환 효과 적용.
  - PWA 서비스 워커 캐시 버전 `v1.6.2`로 갱신.

## [1.6.1] - 2026-08-25

### Fixed (수정됨)
- **웹 대시보드 앱 설치 버튼 호버 명암비 및 가독성 개선 (`docs/index.html`, `docs/service-worker.js`)**:
  - 라이트 모드에서 `.btn.btn-primary` (앱 설치 버튼) 마우스 호버 시 배경색이 밝은 회색으로 덮여 흰색 글씨가 보이지 않던 명암비 버그 수정 (`#0369a1` 딥 사이언 배경 적용).
  - PWA 서비스 워커 캐시 버전 `v1.6.1`로 갱신.

### Changed (변경됨)
- **프로젝트 전반의 과거 알트코인 잔재 문구 일괄 정비**:
  - `docs/index.html`: 헤더 부제 및 액션 가이드 라벨을 `업비트 50:50 & 빗썸 100% 스위칭`으로 최신화.
  - `docs/manifest.json`: 앱 설명 문구 최신화.
  - `README.md`: CLI 옵션 설명 최신화 (`--no-alt`: 빗썸 서브 전략 제외).
  - `src/config.py`: 서브 전략 설정 주석 최신화 (`USE_BITHUMB_STRATEGY`).

## [1.6.0] - 2026-08-25

### Added (추가됨)
- **서브 전략 알트코인 상대 모멘텀 백테스트 시뮬레이터 신설 (`src/backtest_altcoin.py`)**:
  - 빗썸/업비트 과거 1,000일 일봉 데이터를 바탕으로 BTC 220일 SMA 공통 시장 필터 및 주간 거래대금 TOP 10 / 14일 수익률 TOP 4 알트코인 4분할 교체 매매 전략 시뮬레이션 구현.
- **알트코인 4대 퀀트 후보 전략별 백테스터 스크립트 신설 및 전수 검증**:
  - `src/backtest_strategy1_vbo.py`: 래리 윌리엄스 변동성 돌파 전략 백테스터
  - `src/backtest_strategy2_turtle.py`: 터틀 20일 채널 돌파 + ATR 트레일링 스탑 백테스터 (누적 **+49.31%** 1위 달성)
  - `src/backtest_strategy3_risk_parity.py`: 변동성 역가중 Risk Parity 모멘텀 포트폴리오 백테스터 (누적 **+21.86%**)
  - `src/backtest_strategy4_mean_reversion.py`: 상승장 단기 과매도 RSI 반등 백테스터
- **빗썸 서브 전략 BTC vs ETH 상대 모멘텀 100% 스위칭 백테스터 신설 (`src/backtest_bithumb_switching.py`)**:
  - 과거 4.1년간 실데이터 기반으로 30일 모멘텀 1위 대장 코인 100% 집중 투자 및 하락장 현금화 듀얼 모멘텀 시뮬레이션 구현 (누적 **+178.08%** 달성).

### Changed (변경됨)
- **빗썸 서브 전략 실거래/시그널 엔진 전면 개편 (`src/main.py`)**:
  - 기존 4종 알트코인 매매 로직을 제거하고, BTC vs ETH 최근 30일 상대 모멘텀 1위 대장 코인 100% 집중 매수 및 하락장 현금화 듀얼 모멘텀 모델로 전환.
- **PWA 웹 대시보드 서브 전략 카드 개편 (`docs/index.html`, `docs/data/status.json`)**:
  - 알트코인 목록 대신 BTC vs ETH 30일 모멘텀 실시간 비교 및 1등 코인 집중 탑승 신호 뱃지 제공.

## [1.5.9] - 2026-08-24

### Changed (변경됨)
- **웹 대시보드 알트코인 추천 카드 UI 간소화 (`docs/index.html`)**:
  - 알트코인 종목별 카드에서 중복 텍스트인 `'25% 균등 매수'` 라벨을 제거하여 미니멀하고 직관적인 룩앤필 제공.

## [1.5.8] - 2026-08-24

### Changed (변경됨)
- **웹 대시보드 알트코인 한글 종목명 표기 및 안내 문구 개선 (`docs/index.html`)**:
  - 알트코인 추천 카드에 단순 티커(코드) 대신 **한글 코인명과 심볼 병기** (예: `퓨전니스트 (ACE)`, `에테나 (ENA)`, `마가트럼프 (TRUMP)`, `리플 (XRP)`).
  - 서브 알트코인 전략 섹션 제목에 **`빗썸 기준 상대 모멘텀`** 명시.
  - 상단 상태바 안내 문구를 **`매일 오전 대략 9~10시 가격 측정 및 전략 수립`** 으로 직관적 변경.

## [1.5.7] - 2026-08-24

### Style (스타일)
- **전체 마크다운 및 보고서 한글 볼드(`**`) 띄어쓰기 표준화**:
  - `README.md`, `PRD.md`, `CHANGELOG.md` 및 `src/backtest.py`의 모든 한글 볼드 마크다운 구문에 대해 닫는 `**` 뒤 1칸 띄어쓰기를 전면 적용하여 CommonMark/GFM 파싱 깨짐 방지.

## [1.5.6] - 2026-08-24

### Changed (변경됨)
- **웹 대시보드 전략 명칭 정돈 및 기준 데이터 출처 명시 (`docs/index.html`)**:
  - 전략 제목에서 특정 거래소명을 제거하고 **`메인 전략 (50:50 듀얼 모멘텀)`**, **`서브 알트코인 전략`** 으로 명칭 개편.
  - 하단 푸터에 시세 및 지표의 기준 데이터 소스가 **업비트 및 빗썸 공개 REST API** 임을 명시하는 안내 문구 추가.

## [1.5.5] - 2026-08-24

### Fixed (수정됨)
- **웹 대시보드 모바일 퍼스트(Mobile-First) 반응형 최적화 (`docs/index.html`)**:
  - **헤더 액션 버튼 깨짐 해결**: 모바일(`<= 640px`) 환경에서 텍스트 줄바꿈/넘침 현상을 방지하기 위해 정사각(38x38px) 컴팩트 아이콘 버튼으로 자동 전환.
  - **상태바 및 텍스트 넘침 방지**: 모바일에서 상태바 줄바꿈 및 원화 대형 금액, 행동 가이드 텍스트의 가독성/줄바꿈(`word-break: keep-all`) 최적화.
  - **알트코인 및 통계 그리드 반응형 정돈**: 모바일 화면 폭에 맞춘 최적 1열 및 3열 컴팩트 배치 적용.

## [1.5.3] - 2026-08-24

### Refactored (리팩토링)
- **웹 대시보드 인라인 스타일 전면 제거 및 클래스 기반 CSS 통일 (`docs/index.html`)**:
  - HTML 태그 및 JS 템플릿에 분산되어 있던 모든 인라인 `style="..."` 속성을 제거하고 CSS 클래스로 일원화.
  - 테마 변수 및 유지보수 편의성 확보.

## [1.5.2] - 2026-08-24

### Changed (변경됨)
- **웹 대시보드 UI/UX 디자인 전면 개편 (`docs/index.html`)**:
  - **라이트 모드 기본 적용 및 다크 모드 토글 지원**: `localStorage` 연동으로 사용자의 테마 설정을 기억하며 라이트 모드를 기본값으로 제공.
  - **타이포그래피 개선**: Google Fonts **Noto Sans KR** 폰트 패밀리 적용으로 가독성 및 세련미 향상.
  - **모던 Lucide 스타일 벡터 SVG 아이콘 적용**: 이모지 대신 일관된 선형 SVG 아이콘으로 전문적인 핀테크 대시보드 룩앤필 완성.
  - **애니메이션 최적화**: 메인 전략 카드의 불필요한 마우스 호버 바운스 애니메이션 제거로 안정적인 시각적 경험 제공.

## [1.5.0] - 2026-08-24

### Added (추가됨)
- **공통 기술적 지표 연산 모듈(`src/indicators.py`) 분리 및 모듈화**:
  - `calculate_btc_indicators`: BTC 이동평균선(SMA), 상하한 버퍼(±2%) 및 히스테리시스 과거 일봉 역순 탐색 로직 공통화.
  - `calculate_eth_indicators`: ETH 이동평균선(SMA) 및 ATR(14) 변동성 채널 밴드 연산 공통화.
  - `src/main.py`와 `src/backtest.py`에서 중복 코드를 제거하고 공통 모듈 호출로 통합.
- **백테스트 슬리피지(Slippage) 모델 지원 (`src/backtest.py`)**:
  - `--slippage` CLI 옵션 추가: 시장가 체결 오차율을 수수료(0.05%)와 함께 거래비용으로 정확히 반영.
  - 마크다운 보고서 및 최적화 그리드 서치에 슬리피지 조건 명시.
- **Windows 작업 스케줄러 등록 스크립트 추가 (`scripts/`)**:
  - `scripts/setup_scheduler.bat`: 매일 09:05 KST `run_bot.bat --live` 자동 실행을 원클릭으로 작업 스케줄러에 등록.
  - `scripts/remove_scheduler.bat`: 등록된 스케줄러 작업 안전 해제.

## [1.4.1] - 2026-08-24

### Changed (변경됨)
- PWA 웹 대시보드 및 홈 화면 바로가기용 앱 아이콘(`docs/icons/icon.svg`)을 사용자 커스텀 디자인(퀀트 차트 & 비트코인 심볼)으로 교체 및 서비스 워커 캐시 갱신.

## [1.4.0] - 2026-08-24

### Added (추가됨)
- **PWA(Progressive Web App) 기반 반응형 웹 대시보드 구축 (`docs/`)**:
  - `docs/index.html`: 다크 테마 기반의 종합 매매 행동 가이드, 업비트(BTC/ETH) 듀얼 모멘텀 지표 카드, 빗썸 알트코인 모멘텀 카드 및 백테스트 성과 요약 SPA 구현.
  - `docs/manifest.json` & `docs/service-worker.js`: 모바일/PC 홈 화면 앱 설치(PWA) 및 오프라인 캐싱 지원.
  - `docs/icons/icon.svg`: 고해상도 벡터 PWA 앱 아이콘 추가.
  - 장중 실시간 업비트 시세 조회 및 지표 새로고침 기능 탑재.
- **GitHub Pages 연동 및 일일 상태 데이터 자동 갱신 파이프라인**:
  - `src/main.py`: 전략 시그널 분석 시 웹 대시보드 연동용 최신 상태 데이터 `docs/data/status.json` 자동 내보내기 로직 구현.
  - `.github/workflows/main.yml`: 매일 09:05 KST 일일 실행 시 생성된 `docs/data/status.json`을 저장소에 자동 커밋&푸시하여 GitHub Pages 실시간 동기화.

## [1.3.0] - 2026-08-22

### Added (추가됨)
- **`.env` 기반 민감 정보(API Key, Webhook) 보안 관리 아키텍처 도입**:
  - `python-dotenv` 패키지 연동으로 `.env` 파일에서 API Key 자동 로드 지원.
  - 신규 환경 설정을 위한 템플릿 파일 `.env.example` 추가.
- **CLI 명령어 인자(`argparse`) 기반 실행 모드 제어 시스템 구축**:
  - `--signal-only` (`-s`): API Key 및 잔고 조회 없이 전략 시그널 브리핑만 실행.
  - `--dry-run` (`-d`): 가상 잔고 기반 로컬 모의 매매 시뮬레이션.
  - `--live` (`-l`): 실계좌 잔고 기반 실제 매수/매도 시장가 주문 집행.
  - `--no-alt`: 빗썸 알트코인 서브 전략 비활성화 (업비트 단독 실행).
- **실행 스크립트 간소화**:
  - `run_bot.example.bat` 및 GitHub Actions 워크플로우를 CLI 인자 전달 방식으로 간소화.

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

