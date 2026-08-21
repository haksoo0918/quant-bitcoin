# -*- coding: utf-8 -*-
import os

# ==========================================
# [시스템 제어 설정] - 이곳 한 곳에서 모든 설정을 관리합니다.
# ==========================================

# 1. 모의 투자 실행 여부 (드라이런)
# - True: 실제 매매 주문을 넣지 않고 연산과 디스코드 알림만 보냅니다. (안전 모드)
# - False: 실제 거래소 API를 통해 실제 매매 주문을 실행합니다.
DRY_RUN = True

# 2. 빗썸 알트코인 전략 실행 여부
# - True: 업비트(BTC/ETH) 전략과 빗썸(알트코인) 전략을 모두 동시에 실행합니다.
# - False: 빗썸 연동 및 거래를 완전히 비활성화하고, 업비트 메인 전략만 실행합니다.
USE_ALTCOIN_STRATEGY = True


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
