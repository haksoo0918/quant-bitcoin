# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv

# .env 파일이 프로젝트 루트에 존재할 경우 자동 로드
load_dotenv()

# ==========================================
# [시스템 제어 및 환경 설정]
# ==========================================

# 1. 깃허브 액션 환경 감지
IS_GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS", "").lower() == "true"

# 2. 시그널 브리핑 전용 모드 여부
# - GitHub Actions에서는 자동으로 True가 되어 API 키 및 잔고 조회 없이 순수 방향성 시그널만 발송합니다.
# - 로컬에서도 SIGNAL_ONLY=true 환경변수로 방향성 시그널만 테스트할 수 있습니다.
SIGNAL_ONLY = IS_GITHUB_ACTIONS or (os.getenv("SIGNAL_ONLY", "false").lower() == "true")

# 3. 모의 투자 실행 여부 (드라이런)
# - SIGNAL_ONLY 모드일 때는 주문을 실행하지 않으므로 항상 True로 처리됩니다.
# - 로컬 실거래 실행 시에는 기본 False로 작동하며, DRY_RUN=true 설정 시 안전 모의 매매로 동작합니다.
DRY_RUN = True if SIGNAL_ONLY else (os.getenv("DRY_RUN", "false").lower() == "true")

# 4. 빗썸 서브 전략 (이더리움 SuperTrend + 50일 SMA 추세 추종) 실행 여부
# - True: 업비트(BTC/ETH 50:50) 전략과 빗썸(이더리움 SuperTrend 추세 추종) 전략을 모두 동시에 실행합니다.
# - False: 빗썸 연동 및 거래를 완전히 비활성화하고, 업비트 메인 전략만 실행합니다.
USE_BITHUMB_STRATEGY = True
USE_ALTCOIN_STRATEGY = USE_BITHUMB_STRATEGY  # 하위 호환성 유지 별칭


# ==========================================
# [보안 정보 설정] - API 키 및 디스코드 주소
# ==========================================
# API 키와 디스코드 주소는 보안을 위해 환경 변수(run_bot.bat)로부터 읽어옵니다.
UPBIT_ACCESS_KEY = os.getenv("UPBIT_ACCESS_KEY", "")
UPBIT_SECRET_KEY = os.getenv("UPBIT_SECRET_KEY", "")
BITHUMB_ACCESS_KEY = os.getenv("BITHUMB_ACCESS_KEY", "")
BITHUMB_SECRET_KEY = os.getenv("BITHUMB_SECRET_KEY", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")


# ==========================================
# [전략 세부 운용 상수]
# ==========================================

# 메인 전략 이동평균선(SMA) 기간 설정
BTC_SMA_LEN = 220
ETH_SMA_LEN = 50

# 메인 전략 비중 밴드 범위 (목표 비중 50% 대비 ±10%p 이탈 시 리밸런싱 실행)
MAIN_RATIO_BAND = 0.10

# ETH ATR 승수 K값
ETH_ATR_MULTIPLIER = 1.5

# BTC 노이즈 필터 버퍼 (상하한 ±2% 적용)
BTC_BUFFER = 0.02

# 거래소별 원화(KRW) 마켓 최소 주문 제약 금액
UPBIT_MIN_ORDER_KRW = 5000     # 업비트 최소 주문 금액: 5,000원
BITHUMB_MIN_ORDER_KRW = 1000   # 빗썸 최소 주문 금액: 1,000원
