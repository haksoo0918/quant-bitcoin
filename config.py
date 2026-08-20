# -*- coding: utf-8 -*-
import os

# 디버깅 및 시뮬레이션을 위한 드라이런(Dry-Run) 모드 설정
# True일 경우 실제 거래 주문을 거래소에 전송하지 않고 로그만 출력합니다.
# 환경 변수 DRY_RUN이 "true"이거나 "1"로 설정되어 있으면 True가 됩니다.
DRY_RUN = os.getenv("DRY_RUN", "False").lower() in ("true", "1")

# 업비트 API 키 설정 (GitHub Secrets 연동)
UPBIT_ACCESS_KEY = os.getenv("UPBIT_ACCESS_KEY", "")
UPBIT_SECRET_KEY = os.getenv("UPBIT_SECRET_KEY", "")

# 빗썸 API 키 설정 (GitHub Secrets 연동)
BITHUMB_ACCESS_KEY = os.getenv("BITHUMB_ACCESS_KEY", "")
BITHUMB_SECRET_KEY = os.getenv("BITHUMB_SECRET_KEY", "")

# 디스코드 웹훅 URL (GitHub Secrets 연동)
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# --- 전략 운용 상수 (Constants) ---

# 메인 전략 비중 밴드 범위 (목표 비중 50% 대비 ±10%p 이탈 시 리밸런싱 실행)
MAIN_RATIO_BAND = 0.10

# ETH ATR 승수 K값
ETH_ATR_MULTIPLIER = 1.5

# BTC 노이즈 필터 버퍼 (상하한 ±2% 적용)
BTC_BUFFER = 0.02

# 거래소별 원화(KRW) 마켓 최소 주문 제약 금액
UPBIT_MIN_ORDER_KRW = 5000     # 업비트 최소 주문 금액: 5,000원
BITHUMB_MIN_ORDER_KRW = 1000   # 빗썸 최소 주문 금액: 1,000원
