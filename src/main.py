# -*- coding: utf-8 -*-
"""
암호화폐 듀얼 모멘텀 퀀트 자동매매 봇
- 메인 전략: 업비트 BTC/ETH 듀얼 모멘텀 및 50:50 분할 리밸런싱
- 서브 전략: 빗썸 BTC vs ETH 최근 30일 상대 모멘텀 100% 스위칭
"""

import os
import sys
import time
import json
import logging
import argparse
from datetime import datetime, timezone, timedelta
import pandas as pd
import requests

# 환경 변수 로드 (varlock / python-dotenv)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from config import (
    UPBIT_ACCESS_KEY, UPBIT_SECRET_KEY,
    BITHUMB_ACCESS_KEY, BITHUMB_SECRET_KEY,
    DISCORD_WEBHOOK_URL,
    UPBIT_MIN_ORDER_KRW, BITHUMB_MIN_ORDER_KRW, DRY_RUN,
    BTC_SMA_LEN, ETH_SMA_LEN, BTC_BUFFER, ETH_ATR_MULTIPLIER,
    MAIN_RATIO_BAND, USE_ALTCOIN_STRATEGY
)
from bithumb_api import BithumbClient
import pyupbit

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)


def get_kst_now():
    """현재 한국 표준시(KST) 반환"""
    utc_now = datetime.now(timezone.utc)
    return utc_now + timedelta(hours=9)


def send_discord_message(content):
    """디스코드 웹훅으로 알림 메시지 발송"""
    if not DISCORD_WEBHOOK_URL:
        logging.warning("디스코드 웹훅 URL이 설정되어 있지 않습니다. 알림 전송을 건너뜁니다.")
        return

    payload = {"content": content}
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(DISCORD_WEBHOOK_URL, data=json.dumps(payload), headers=headers, timeout=10)
        if response.status_code in [200, 204]:
            logging.info("디스코드 알림 발송 성공")
        else:
            logging.error(f"디스코드 알림 발송 실패 (상태 코드: {response.status_code}): {response.text}")
    except Exception as e:
        logging.error(f"디스코드 알림 발송 중 예외 발생: {e}")


def calculate_btc_indicators(df, sma_len=BTC_SMA_LEN, buffer_rate=BTC_BUFFER):
    """
    BTC 지표 및 공통 시장 필터 상태(히스테리시스 역순 탐색) 계산
    """
    df = df.copy()
    df['sma'] = df['close'].rolling(window=sma_len).mean()
    
    current_price = df['close'].iloc[-1]
    sma = df['sma'].iloc[-1]
    upper_buffer = sma * (1 + buffer_rate)
    lower_buffer = sma * (1 - buffer_rate)
    
    if current_price >= upper_buffer:
        market_filter_state = "Bull"
        status = "bull"
        status_label = "상승 추세 돌파"
    elif current_price < lower_buffer:
        market_filter_state = "Bear"
        status = "bear"
        status_label = "하락 추세 이탈"
    else:
        status = "buffer"
        status_label = "버퍼 구간 대기"
        market_filter_state = "Bear"
        for t in range(2, len(df)):
            close_t = df['close'].iloc[-t]
            sma_t = df['sma'].iloc[-t]
            if pd.isna(sma_t):
                break
            if close_t >= sma_t * (1 + buffer_rate):
                market_filter_state = "Bull"
                break
            elif close_t < sma_t * (1 - buffer_rate):
                market_filter_state = "Bear"
                break
                
    return {
        "current_price": current_price,
        "sma": sma,
        "upper_buffer": upper_buffer,
        "lower_buffer": lower_buffer,
        "status": status,
        "status_label": status_label,
        "market_filter_state": market_filter_state
    }


def calculate_eth_indicators(df, sma_len=ETH_SMA_LEN, atr_len=14, atr_multiplier=ETH_ATR_MULTIPLIER):
    """
    ETH 지표 및 채널 밴드 돌파 상태 계산
    """
    df = df.copy()
    df['sma'] = df['close'].rolling(window=sma_len).mean()
    
    prev_close = df['close'].shift(1)
    tr1 = df['high'] - df['low']
    tr2 = (df['high'] - prev_close).abs()
    tr3 = (df['low'] - prev_close).abs()
    df['tr'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df['atr_14'] = df['tr'].rolling(window=atr_len).mean()
    
    current_price = df['close'].iloc[-1]
    sma = df['sma'].iloc[-1]
    atr_14 = df['atr_14'].iloc[-1]
    upper_band = sma + (atr_14 * atr_multiplier)
    lower_band = sma - (atr_14 * atr_multiplier)
    
    if current_price >= upper_band:
        status = "bull"
        status_label = "상승 채널 돌파"
    elif current_price < lower_band:
        status = "bear"
        status_label = "하락 밴드 이탈"
    else:
        status = "neutral"
        status_label = "밴드 내 중립"
        
    return {
        "current_price": current_price,
        "sma": sma,
        "atr_14": atr_14,
        "upper_band": upper_band,
        "lower_band": lower_band,
        "status": status,
        "status_label": status_label
    }


def calculate_supertrend(df, period=7, multiplier=3.5):
    """
    SuperTrend(슈퍼트렌드) 지표 연산
    """
    df_calc = df.copy()
    high = df_calc['high']
    low = df_calc['low']
    close = df_calc['close']
    prev_close = close.shift(1)
    
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    
    hl2 = (high + low) / 2.0
    basic_upper = hl2 + (multiplier * atr)
    basic_lower = hl2 - (multiplier * atr)
    
    final_upper = basic_upper.copy()
    final_lower = basic_lower.copy()
    direction = pd.Series(index=df_calc.index, dtype=int)
    supertrend = pd.Series(index=df_calc.index, dtype=float)
    
    n = len(df_calc)
    for i in range(period, n):
        if basic_upper.iloc[i] < final_upper.iloc[i-1] or close.iloc[i-1] > final_upper.iloc[i-1]:
            final_upper.iloc[i] = basic_upper.iloc[i]
        else:
            final_upper.iloc[i] = final_upper.iloc[i-1]
            
        if basic_lower.iloc[i] > final_lower.iloc[i-1] or close.iloc[i-1] < final_lower.iloc[i-1]:
            final_lower.iloc[i] = basic_lower.iloc[i]
        else:
            final_lower.iloc[i] = final_lower.iloc[i-1]
            
        if i == period:
            direction.iloc[i] = 1 if close.iloc[i] > final_upper.iloc[i] else -1
        else:
            if direction.iloc[i-1] == 1:
                direction.iloc[i] = -1 if close.iloc[i] < final_lower.iloc[i] else 1
            else:
                direction.iloc[i] = 1 if close.iloc[i] > final_upper.iloc[i] else -1
                
        supertrend.iloc[i] = final_lower.iloc[i] if direction.iloc[i] == 1 else final_upper.iloc[i]
        
    df_calc['supertrend'] = supertrend
    df_calc['supertrend_direction'] = direction
    return df_calc


def calculate_bithumb_eth_indicators(df, sma_len=50, st_period=7, st_multiplier=3.5):
    """
    빗썸 서브 전략 (이더리움 SuperTrend + 50일 SMA 추세 추종) 지표 및 방향성 연산
    """
    df_st = calculate_supertrend(df, period=st_period, multiplier=st_multiplier)
    df_st['sma50'] = df_st['close'].rolling(window=sma_len).mean()
    
    sma50 = float(df_st['sma50'].iloc[-1])
    supertrend_val = float(df_st['supertrend'].iloc[-1])
    direction_val = int(df_st['supertrend_direction'].iloc[-1])
    supertrend_trend = "BULL" if direction_val == 1 else "BEAR"
    
    current_price = float(df_st['close'].iloc[-1])
    is_above_sma = current_price >= sma50
    
    if is_above_sma and supertrend_trend == "BULL":
        action = "BUY"
        status_label = "상승 추세 (ETH 100% 매수)"
    else:
        action = "SELL"
        status_label = "하락/약세장 (100% 현금화)"
        
    return {
        "current_price": current_price,
        "sma50": sma50,
        "supertrend_val": supertrend_val,
        "supertrend_trend": supertrend_trend,
        "is_above_sma": is_above_sma,
        "action": action,
        "status_label": status_label
    }


def fetch_upbit_candles(market, count=250):
    """업비트 일봉 데이터 조회"""
    df = pyupbit.get_ohlcv(market, interval="day", count=count)
    if df is None or len(df) == 0:
        raise ValueError(f"업비트 {market} 일봉 데이터를 가져올 수 없습니다.")
    return df


def fetch_upbit_current_price(market):
    """업비트 현재가 단건 조회"""
    price = pyupbit.get_current_price(market)
    if price is None:
        raise ValueError(f"업비트 {market} 현재가를 가져올 수 없습니다.")
    return float(price)


def fetch_upbit_balances(upbit_client, is_dry_run=False):
    """업비트 계좌 잔고 목록 조회"""
    if is_dry_run and not (UPBIT_ACCESS_KEY and UPBIT_SECRET_KEY):
        return [
            {"currency": "KRW", "balance": "10000000.0", "locked": "0.0", "avg_buy_price": "0"},
            {"currency": "BTC", "balance": "0.0", "locked": "0.0", "avg_buy_price": "0"},
            {"currency": "ETH", "balance": "0.0", "locked": "0.0", "avg_buy_price": "0"}
        ]
    balances = upbit_client.get_balances()
    if isinstance(balances, dict) and "error" in balances:
        raise ValueError(f"업비트 잔고 조회 실패: {balances.get('error')}")
    return balances


def fetch_bithumb_ticker_all():
    """빗썸 전체 코인 현재가 및 거래대금 조회"""
    url = "https://api.bithumb.com/public/ticker/ALL_KRW"
    resp = requests.get(url, timeout=10)
    if resp.status_code != 200:
        raise ValueError(f"빗썸 전체 티커 조회 실패 (상태 코드: {resp.status_code})")
    data = resp.json()
    if data.get("status") != "0000":
        raise ValueError(f"빗썸 전체 티커 응답 에러: {data.get('message')}")
    return data.get("data", {})


def fetch_bithumb_balances(bithumb_client, is_dry_run=False):
    """빗썸 계좌 잔고 조회"""
    if is_dry_run and not (BITHUMB_ACCESS_KEY and BITHUMB_SECRET_KEY):
        return [
            {"currency": "KRW", "balance": "10000000.0", "locked": "0.0", "avg_buy_price": "0"},
            {"currency": "BTC", "balance": "0.0", "locked": "0.0", "avg_buy_price": "0"},
            {"currency": "ETH", "balance": "0.0", "locked": "0.0", "avg_buy_price": "0"}
        ]
    return bithumb_client.get_balances()


def export_web_status_json(data_dict, file_path="docs/data/status.json"):
    """PWA 웹 대시보드 연동용 status.json 파일 저장"""
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data_dict, f, ensure_ascii=False, indent=2)
        logging.info(f"PWA 대시보드 상태 데이터 저장 완료: {file_path}")
    except Exception as e:
        logging.error(f"PWA 대시보드 상태 데이터 저장 실패: {e}")


def run_signal_briefing(kst_now, use_alt_strategy=USE_ALTCOIN_STRATEGY):
    """
    GitHub Actions 및 --signal-only 실행 모드:
    순수 공개 API 시세 데이터만으로 시장 지표, 업비트/빗썸 방향성 신호 브리핑을 디스코드로 전송.
    """
    logging.info("=== [GitHub Actions 시그널 브리핑 모드 가동] ===")
    
    # 1. 업비트 일봉 시세 및 지표 계산
    btc_df = fetch_upbit_candles("KRW-BTC", count=BTC_SMA_LEN + 35)
    btc_current_price = fetch_upbit_current_price("KRW-BTC")
    btc_df.iloc[-1, btc_df.columns.get_loc('close')] = btc_current_price
    btc_ind = calculate_btc_indicators(btc_df, sma_len=BTC_SMA_LEN, buffer_rate=BTC_BUFFER)
    
    btc_sma = btc_ind["sma"]
    btc_upper = btc_ind["upper_buffer"]
    btc_lower = btc_ind["lower_buffer"]
    market_filter_state = btc_ind["market_filter_state"]

    if btc_ind["status"] == "bull":
        btc_status_str = f"🟢 **[매수 유지 / 신규 진입]** ({btc_ind['status_label']})"
        btc_guide = "BTC 50% 비중 매수 또는 보유 유지"
    elif btc_ind["status"] == "bear":
        btc_status_str = f"🔴 **[매도 / 현금화 관망]** ({btc_ind['status_label']})"
        btc_guide = "BTC 전량 매도 및 현금(KRW) 확보"
    else:
        btc_status_str = f"⏳ **[버퍼 구간 대기]** ({btc_ind['status_label']})"
        btc_guide = "기존 보유 상태 유지 (신규 진입 자제)"

    # 2. ETH 일봉 시세 및 지표 계산
    eth_df = fetch_upbit_candles("KRW-ETH", count=max(200, ETH_SMA_LEN + 50))
    eth_current_price = fetch_upbit_current_price("KRW-ETH")
    eth_df.iloc[-1, eth_df.columns.get_loc('close')] = eth_current_price
    eth_ind = calculate_eth_indicators(eth_df, sma_len=ETH_SMA_LEN, atr_len=14, atr_multiplier=ETH_ATR_MULTIPLIER)

    eth_sma = eth_ind["sma"]
    eth_atr_14 = eth_ind["atr_14"]
    eth_upper_band = eth_ind["upper_band"]
    eth_lower_band = eth_ind["lower_band"]

    if eth_ind["status"] == "bull":
        eth_status_str = f"🟢 **[매수 유지 / 신규 진입]** ({eth_ind['status_label']})"
        eth_guide = "ETH 50% 비중 매수 또는 보유 유지"
    elif eth_ind["status"] == "bear":
        eth_status_str = f"🔴 **[매도 / 현금화 관망]** ({eth_ind['status_label']})"
        eth_guide = "ETH 전량 매도 및 현금(KRW) 확보"
    else:
        eth_status_str = f"🔍 **[밴드 내 중립]** ({eth_ind['status_label']})"
        eth_guide = "기존 보유 상태 유지 (신규 진입 자제)"

    # 3. 빗썸 서브 전략 (이더리움 SuperTrend + 50일 SMA 추세 추종)
    bithumb_report_lines = []
    bithumb_data = {}
    if use_alt_strategy:
        bithumb_eth_ind = calculate_bithumb_eth_indicators(eth_df, sma_len=50, st_period=7, st_multiplier=3.5)
        eth_p = float(bithumb_eth_ind["current_price"])
        eth_sma50 = float(bithumb_eth_ind["sma50"])
        st_val = float(bithumb_eth_ind["supertrend_val"])
        st_trend = bithumb_eth_ind["supertrend_trend"]
        is_above_sma = bithumb_eth_ind["is_above_sma"]
        bithumb_action = bithumb_eth_ind["action"]

        if bithumb_action == "BUY":
            target_signal = "🟢 **[이더리움 (ETH) 100% 매수/보유]** (SuperTrend 상승 & 50일 SMA 돌파)"
            bithumb_guide = "빗썸 이더리움 100% 매수 또는 보유 유지"
            target_coin = "ETH"
            target_coin_name = "이더리움 (ETH)"
        else:
            target_signal = "🔴 **[100% 원화 현금화 관망]** (SuperTrend 하락 또는 50일 SMA 이탈)"
            bithumb_guide = "보유 이더리움 전량 매도 후 100% 현금(KRW) 보존"
            target_coin = "KRW"
            target_coin_name = "원화 현금 (KRW)"

        bithumb_report_lines.append(f"• **이더리움 (ETH)**: {eth_p:,.0f} 원")
        bithumb_report_lines.append(f"  - 50일 이평: {eth_sma50:,.0f} 원 ({'상회 🟢' if is_above_sma else '하회 🔴'}) | SuperTrend(7, 3.5): {st_val:,.0f} 원 ({st_trend})")
        bithumb_report_lines.append(f"• **전략 방향성 신호**: {target_signal}")

        bithumb_data = {
            "enabled": True,
            "strategy_name": "이더리움 SuperTrend + 50일 SMA 추세 추종",
            "target_coin": target_coin,
            "target_coin_name": target_coin_name,
            "target_signal": target_signal,
            "current_price": eth_p,
            "sma50": eth_sma50,
            "supertrend_val": st_val,
            "supertrend_trend": st_trend,
            "is_above_sma": is_above_sma,
            "action": bithumb_action,
            "guide": bithumb_guide
        }
    else:
        bithumb_report_lines.append("• **상태**: 비활성화됨 (Disabled)")
        bithumb_guide = "서브 전략 미사용"
        bithumb_data = {"enabled": False, "guide": bithumb_guide}

    # 4. 디스코드 메시지 구성
    report = []
    report.append("📢 **[GitHub Actions] 퀀트 전략 일일 방향성 시그널 브리핑**")
    report.append(f"⏱️ **기준 일시**: {kst_now.strftime('%Y-%m-%d %H:%M')} KST")
    report.append("==================================")
    report.append("\n🔵 **메인 전략 (업비트 - BTC & ETH 50:50)**")
    report.append(f"• **BTC (220일 SMA)**: {btc_current_price:,.0f} 원")
    report.append(f"  - 기준 이평: {btc_sma:,.0f} 원 (상한: {btc_upper:,.0f} / 하한: {btc_lower:,.0f})")
    report.append(f"  - 전략 방향성: {btc_status_str}")
    report.append(f"• **ETH (50일 SMA + 1.5 ATR)**: {eth_current_price:,.0f} 원")
    report.append(f"  - 기준 이평: {eth_sma:,.0f} 원 (상한밴드: {eth_upper_band:,.0f} / 하한밴드: {eth_lower_band:,.0f})")
    report.append(f"  - 전략 방향성: {eth_status_str}")
    
    report.append("\n🟢 **서브 전략 (빗썸 - 이더리움 SuperTrend + 50일 SMA)**")
    report.extend(bithumb_report_lines)
    
    report.append("\n💡 **모바일 직접 매매 가이드 요약**")
    report.append(f"• **업비트**: {btc_guide} / {eth_guide}")
    report.append(f"• **빗썸**: {bithumb_guide}")
    report.append("==================================")
    
    send_discord_message("\n".join(report))
    logging.info("GitHub Actions 시그널 브리핑 디스코드 전송 완료.")

    # 5. PWA 웹 대시보드용 status.json 파일 내보내기
    status_data = {
        "updated_at": kst_now.isoformat(),
        "updated_at_formatted": kst_now.strftime("%Y-%m-%d %H:%M:%S KST"),
        "mode": "signal",
        "upbit": {
            "btc": {
                "current_price": float(btc_current_price),
                "sma": float(btc_sma),
                "sma_len": BTC_SMA_LEN,
                "upper_buffer": float(btc_upper),
                "lower_buffer": float(btc_lower),
                "status": "bull" if btc_current_price >= btc_upper else ("bear" if btc_current_price < btc_lower else "buffer"),
                "status_label": "상승 추세 돌파" if btc_current_price >= btc_upper else ("하락 추세 이탈" if btc_current_price < btc_lower else "버퍼 구간 대기"),
                "guide": btc_guide
            },
            "eth": {
                "current_price": float(eth_current_price),
                "sma": float(eth_sma),
                "sma_len": ETH_SMA_LEN,
                "atr_14": float(eth_atr_14),
                "upper_band": float(eth_upper_band),
                "lower_band": float(eth_lower_band),
                "status": "bull" if eth_current_price >= eth_upper_band else ("bear" if eth_current_price < eth_lower_band else "neutral"),
                "status_label": "상승 채널 돌파" if eth_current_price >= eth_upper_band else ("하락 밴드 이탈" if eth_current_price < eth_lower_band else "밴드 내 중립"),
                "guide": eth_guide
            }
        },
        "bithumb": bithumb_data,
        "guides": {
            "upbit": f"{btc_guide} / {eth_guide}",
            "bithumb": bithumb_guide
        }
    }
    export_web_status_json(status_data)


def run_live_trading(kst_now, is_dry_run=False, use_alt_strategy=USE_ALTCOIN_STRATEGY):
    """
    로컬 실거래 또는 모의매매 실행 함수
    """
    mode_label = "모의매매(Dry-Run)" if is_dry_run else "실거래 자동매매"
    logging.info(f"=== [로컬 {mode_label} 모드 가동] ===")
    
    # 1. 거래소 클라이언트 초기화
    upbit = pyupbit.Upbit(UPBIT_ACCESS_KEY, UPBIT_SECRET_KEY) if (UPBIT_ACCESS_KEY and UPBIT_SECRET_KEY) else None
    bithumb = BithumbClient(dry_run=is_dry_run)
    
    # 2. 업비트 시세 및 지표 연산
    btc_df = fetch_upbit_candles("KRW-BTC", count=BTC_SMA_LEN + 35)
    btc_current_price = fetch_upbit_current_price("KRW-BTC")
    btc_df.iloc[-1, btc_df.columns.get_loc('close')] = btc_current_price
    btc_ind = calculate_btc_indicators(btc_df, sma_len=BTC_SMA_LEN, buffer_rate=BTC_BUFFER)
    
    btc_sma = btc_ind["sma"]
    market_filter_state = btc_ind["market_filter_state"]
    
    eth_df = fetch_upbit_candles("KRW-ETH", count=max(200, ETH_SMA_LEN + 50))
    eth_current_price = fetch_upbit_current_price("KRW-ETH")
    eth_df.iloc[-1, eth_df.columns.get_loc('close')] = eth_current_price
    eth_ind = calculate_eth_indicators(eth_df, sma_len=ETH_SMA_LEN, atr_len=14, atr_multiplier=ETH_ATR_MULTIPLIER)
    
    eth_sma = eth_ind["sma"]
    eth_atr_14 = eth_ind["atr_14"]
    eth_upper_band = eth_ind["upper_band"]
    eth_lower_band = eth_ind["lower_band"]
    
    # 2.1 업비트 잔고 현황 조회
    upbit_balances_raw = fetch_upbit_balances(upbit, is_dry_run=is_dry_run)
    upbit_krw = 0.0
    upbit_btc_bal = 0.0
    upbit_eth_bal = 0.0
    
    for asset in upbit_balances_raw:
        curr = asset.get("currency")
        bal = float(asset.get("balance", 0.0)) + float(asset.get("locked", 0.0))
        if curr == "KRW":
            upbit_krw = bal
        elif curr == "BTC":
            upbit_btc_bal = bal
        elif curr == "ETH":
            upbit_eth_bal = bal
            
    is_holding_btc = (upbit_btc_bal * btc_current_price) >= UPBIT_MIN_ORDER_KRW
    is_holding_eth = (upbit_eth_bal * eth_current_price) >= UPBIT_MIN_ORDER_KRW
    
    # 2.2 목표 포지션 결정
    if not is_holding_btc:
        btc_target_state = 'hold' if btc_current_price >= btc_sma * (1 + BTC_BUFFER) else 'cash'
    else:
        btc_target_state = 'cash' if btc_current_price < btc_sma * (1 - BTC_BUFFER) else 'hold'
        
    if not is_holding_eth:
        eth_target_state = 'hold' if eth_current_price >= eth_upper_band else 'cash'
    else:
        eth_target_state = 'cash' if eth_current_price < eth_lower_band else 'hold'

    logging.info(f"판정 결과 - BTC: {btc_target_state} | ETH: {eth_target_state} | 공통 시장 필터: {market_filter_state}")

    # 3. 업비트 주문 집행
    upbit_order_history = []
    
    # 3.1 선매도 처리
    if btc_target_state == 'cash' and is_holding_btc:
        val = upbit_btc_bal * btc_current_price
        logging.info(f"[업비트 매도] BTC 청산 (수량: {upbit_btc_bal:.8f}, 금액: {val:,.0f}원)")
        if not is_dry_run and upbit:
            try:
                order_res = upbit.sell_market_order("KRW-BTC", upbit_btc_bal)
                upbit_order_history.append(f"✅ 업비트 BTC 청산: {val:,.0f}원 ({upbit_btc_bal:.4f} BTC)")
            except Exception as e:
                upbit_order_history.append(f"❌ 업비트 BTC 매도 실패: {e}")
        else:
            upbit_order_history.append(f"📝 [모의 주문] 업비트 BTC 청산: {val:,.0f}원 ({upbit_btc_bal:.4f} BTC)")
        time.sleep(2)
        
    if eth_target_state == 'cash' and is_holding_eth:
        val = upbit_eth_bal * eth_current_price
        logging.info(f"[업비트 매도] ETH 청산 (수량: {upbit_eth_bal:.8f}, 금액: {val:,.0f}원)")
        if not is_dry_run and upbit:
            try:
                order_res = upbit.sell_market_order("KRW-ETH", upbit_eth_bal)
                upbit_order_history.append(f"✅ 업비트 ETH 청산: {val:,.0f}원 ({upbit_eth_bal:.4f} ETH)")
            except Exception as e:
                upbit_order_history.append(f"❌ 업비트 ETH 매도 실패: {e}")
        else:
            upbit_order_history.append(f"📝 [모의 주문] 업비트 ETH 청산: {val:,.0f}원 ({upbit_eth_bal:.4f} ETH)")
        time.sleep(2)

    # 3.2 매수 및 리밸런싱 처리
    total_upbit_value = upbit_krw + (upbit_btc_bal * btc_current_price) + (upbit_eth_bal * eth_current_price)
    
    # 두 자산 모두 보유 시 리밸런싱 확인
    if btc_target_state == 'hold' and eth_target_state == 'hold' and is_holding_btc and is_holding_eth:
        btc_val = upbit_btc_bal * btc_current_price
        eth_val = upbit_eth_bal * eth_current_price
        total_coins_val = btc_val + eth_val
        if total_coins_val > 0:
            btc_weight = btc_val / total_coins_val
            if abs(btc_weight - 0.5) > MAIN_RATIO_BAND:
                logging.info(f"[업비트 리밸런싱 발동] 현재 BTC 비중 {btc_weight*100:.1f}%")
                target_val_per_coin = total_coins_val * 0.5
                if btc_weight > 0.5:
                    excess_btc = (btc_val - target_val_per_coin) / btc_current_price
                    if not is_dry_run and upbit:
                        try:
                            upbit.sell_market_order("KRW-BTC", excess_btc)
                            upbit_order_history.append(f"✅ 업비트 BTC 일부 매도: {(btc_val - target_val_per_coin):,.0f}원")
                        except Exception as e:
                            upbit_order_history.append(f"❌ 업비트 BTC 리밸런싱 실패: {e}")
                else:
                    excess_eth = (eth_val - target_val_per_coin) / eth_current_price
                    if not is_dry_run and upbit:
                        try:
                            upbit.sell_market_order("KRW-ETH", excess_eth)
                            upbit_order_history.append(f"✅ 업비트 ETH 일부 매도: {(eth_val - target_val_per_coin):,.0f}원")
                        except Exception as e:
                            upbit_order_history.append(f"❌ 업비트 ETH 리밸런싱 실패: {e}")
                time.sleep(2)

    # 신규 매수 처리
    for coin, target_st, is_held in [("BTC", btc_target_state, is_holding_btc), ("ETH", eth_target_state, is_holding_eth)]:
        if target_st == 'hold' and not is_held:
            target_alloc = total_upbit_value * 0.5
            buy_amount = min(target_alloc, upbit_krw * 0.995)
            if buy_amount >= UPBIT_MIN_ORDER_KRW:
                logging.info(f"[업비트 매수] {coin} 신규 매수 (금액: {buy_amount:,.0f}원)")
                if not is_dry_run and upbit:
                    try:
                        upbit.buy_market_order(f"KRW-{coin}", buy_amount)
                        upbit_order_history.append(f"✅ 업비트 {coin} 매수: {buy_amount:,.0f}원")
                        upbit_krw -= buy_amount
                    except Exception as e:
                        upbit_order_history.append(f"❌ 업비트 {coin} 매수 실패: {e}")
                else:
                    upbit_order_history.append(f"📝 [모의 주문] 업비트 {coin} 매수: {buy_amount:,.0f}원")
                    upbit_krw -= buy_amount
                time.sleep(2)

    # 4. 빗썸 매매 실행 (서브 전략: 이더리움 SuperTrend + 50일 SMA 추세 추종)
    bithumb_krw = 0.0
    bithumb_eth_bal = 0.0
    bithumb_eth_avg = 0.0
    total_bithumb_value = 0.0
    bithumb_order_history = []
    bithumb_action = "SELL"

    if use_alt_strategy:
        logging.info("=== [빗썸 이더리움 SuperTrend 추세 추종 매매 프로세스 가동] ===")
        bithumb_balances_raw = fetch_bithumb_balances(bithumb, is_dry_run=is_dry_run)
        bithumb_ticker_data = fetch_bithumb_ticker_all()

        bithumb_eth_p = float(bithumb_ticker_data.get("ETH", {}).get("closing_price", eth_current_price))

        for asset in bithumb_balances_raw:
            curr = asset.get("currency")
            bal = float(asset.get("balance", 0.0)) + float(asset.get("locked", 0.0))
            avg_buy = float(asset.get("avg_buy_price", 0.0))
            if bal <= 0:
                continue

            if curr == "KRW":
                bithumb_krw = bal
            elif curr == "ETH":
                bithumb_eth_bal = bal
                bithumb_eth_avg = avg_buy
            elif curr == "BTC":
                # 과거 잔여 BTC가 있을 경우 정리 청산
                btc_p_val = float(bithumb_ticker_data.get("BTC", {}).get("closing_price", btc_current_price))
                if bal * btc_p_val >= BITHUMB_MIN_ORDER_KRW:
                    val = bal * btc_p_val
                    logging.info(f"[빗썸 잔여 정리] 구버전 BTC 청산 (금액: {val:,.0f}원)")
                    if not is_dry_run:
                        try:
                            bithumb.sell_market_order("KRW-BTC", bal)
                            bithumb_order_history.append(f"✅ 빗썸 잔여 BTC 청산: {val:,.0f}원")
                        except Exception as e:
                            bithumb_order_history.append(f"❌ 빗썸 BTC 청산 실패: {e}")
                    else:
                        bithumb_order_history.append(f"📝 [모의 주문] 빗썸 잔여 BTC 청산: {val:,.0f}원")

        total_bithumb_value = bithumb_krw + (bithumb_eth_bal * bithumb_eth_p)

        # 4.1 이더리움 SuperTrend + 50일 SMA 지표 연산
        bithumb_eth_ind = calculate_bithumb_eth_indicators(eth_df, sma_len=50, st_period=7, st_multiplier=3.5)
        bithumb_action = bithumb_eth_ind["action"]

        logging.info(f"빗썸 ETH 분석: 현재가 {bithumb_eth_p:,.0f}원 | 50일 SMA {bithumb_eth_ind['sma50']:,.0f}원 | SuperTrend {bithumb_eth_ind['supertrend_val']:,.0f}원 ({bithumb_eth_ind['supertrend_trend']}) | 판정: {bithumb_action}")

        # 4.2 매매 집행
        # A. 약세/하락장 (SELL) -> 보유 ETH 전량 매도 (100% 현금화)
        if bithumb_action == "SELL":
            if bithumb_eth_bal * bithumb_eth_p >= BITHUMB_MIN_ORDER_KRW:
                val = bithumb_eth_bal * bithumb_eth_p
                logging.info(f"[빗썸 약세장 청산] ETH 매도 (수량: {bithumb_eth_bal:.8f}, 금액: {val:,.0f}원)")
                if not is_dry_run:
                    try:
                        order_res = bithumb.sell_market_order("KRW-ETH", bithumb_eth_bal)
                        bithumb_order_history.append(f"✅ 빗썸 ETH 청산 (100% 현금화): {val:,.0f}원 ({bithumb_eth_bal:.4f} ETH)")
                    except Exception as e:
                        bithumb_order_history.append(f"❌ 빗썸 ETH 청산 실패: {e}")
                else:
                    bithumb_order_history.append(f"📝 [모의 주문] 빗썸 ETH 청산 (100% 현금화): {val:,.0f}원 ({bithumb_eth_bal:.4f} ETH)")
                time.sleep(2)

        # B. 상승 추세 (BUY) -> 가용 KRW로 ETH 100% 매수
        elif bithumb_action == "BUY":
            if not is_dry_run:
                try:
                    bithumb_krw = bithumb.get_balance("KRW")
                except Exception:
                    pass

            buy_amount = bithumb_krw * 0.995
            if buy_amount >= BITHUMB_MIN_ORDER_KRW:
                logging.info(f"[빗썸 100% 집중 매수] ETH 매수 (금액: {buy_amount:,.0f}원)")
                if not is_dry_run:
                    try:
                        order_res = bithumb.buy_market_order("KRW-ETH", buy_amount)
                        bithumb_order_history.append(f"✅ 빗썸 ETH 100% 매수: {buy_amount:,.0f}원")
                        bithumb_krw -= buy_amount
                    except Exception as e:
                        bithumb_order_history.append(f"❌ 빗썸 ETH 매수 실패: {e}")
                else:
                    bithumb_order_history.append(f"📝 [모의 주문] 빗썸 ETH 100% 매수: {buy_amount:,.0f}원")
                    bithumb_krw -= buy_amount

    else:
        logging.info("=== [빗썸 매매 제어 프로세스 비활성화] ===")

    # 5. 최종 잔고 업데이트 조회 및 디스코드 리포트 발송
    logging.info("=== [최종 포트폴리오 리포트 전송 시작] ===")
    
    # 5.1 업비트 최종 잔고 파싱
    upbit_balances_raw = fetch_upbit_balances(upbit, is_dry_run=is_dry_run)
    upbit_balances = {}
    for asset in upbit_balances_raw:
        curr = asset.get("currency")
        bal = float(asset.get("balance", 0.0)) + float(asset.get("locked", 0.0))
        avg_buy = float(asset.get("avg_buy_price", 0.0))
        if bal > 0 or curr == "KRW":
            upbit_balances[curr] = {"balance": bal, "avg_buy": avg_buy}
            
    upbit_krw_fin = upbit_balances.get("KRW", {}).get("balance", 0.0)
    btc_bal_fin = upbit_balances.get("BTC", {}).get("balance", 0.0)
    eth_bal_fin = upbit_balances.get("ETH", {}).get("balance", 0.0)
    btc_price_fin = fetch_upbit_current_price("KRW-BTC")
    eth_price_fin = fetch_upbit_current_price("KRW-ETH")
    
    btc_val_fin = btc_bal_fin * btc_price_fin
    eth_val_fin = eth_bal_fin * eth_price_fin
    total_upbit_fin = upbit_krw_fin + btc_val_fin + eth_val_fin

    # 5.2 빗썸 최종 잔고 파싱
    bithumb_krw_fin = 0.0
    bithumb_eth_bal_fin = 0.0
    bithumb_eth_avg_fin = 0.0
    total_bithumb_fin = 0.0
    
    if use_alt_strategy:
        bithumb_balances_raw = fetch_bithumb_balances(bithumb, is_dry_run=is_dry_run)
        bithumb_ticker_fin = fetch_bithumb_ticker_all()
        
        for asset in bithumb_balances_raw:
            curr = asset.get("currency")
            bal = float(asset.get("balance", 0.0)) + float(asset.get("locked", 0.0))
            avg_buy = float(asset.get("avg_buy_price", 0.0))
            if bal <= 0:
                continue
                
            if curr == "KRW":
                bithumb_krw_fin = bal
            elif curr == "ETH":
                bithumb_eth_bal_fin = bal
                bithumb_eth_avg_fin = avg_buy
                    
        bithumb_eth_val_fin = bithumb_eth_bal_fin * float(bithumb_ticker_fin.get("ETH", {}).get("closing_price", eth_price_fin))
        total_bithumb_fin = bithumb_krw_fin + bithumb_eth_val_fin

    # 5.3 디스코드 본문 포맷팅
    upbit_btc_return = ((btc_price_fin - upbit_balances.get("BTC", {}).get("avg_buy", 0.0)) / upbit_balances.get("BTC", {}).get("avg_buy", 1.0)) * 100 if btc_bal_fin > 0 else 0.0
    upbit_eth_return = ((eth_price_fin - upbit_balances.get("ETH", {}).get("avg_buy", 0.0)) / upbit_balances.get("ETH", {}).get("avg_buy", 1.0)) * 100 if eth_bal_fin > 0 else 0.0

    report = []
    if is_dry_run:
        report.append("⚡ **[로컬 모의매매] 모의 주문 체결 및 포트폴리오 잔고 보고서**")
    else:
        report.append("⚡ **[로컬 자동매매] 실거래 주문 체결 및 포트폴리오 잔고 보고서**")
    report.append(f"⏱️ **실행 일시**: {kst_now.strftime('%Y-%m-%d %H:%M')} KST")
    report.append("==================================")
    
    report.append("\n🔵 **메인 전략 (업비트 - BTC & ETH 50:50)**")
    report.append(f"• **총 자산 가치**: {total_upbit_fin:,.0f} 원")
    report.append(f"• **보유 현금 (KRW)**: {upbit_krw_fin:,.0f} 원 ({upbit_krw_fin/total_upbit_fin*100:.1f}%)")
    
    if btc_bal_fin > 0:
        report.append(f"• **BTC**: {btc_val_fin:,.0f} 원 ({btc_val_fin/total_upbit_fin*100:.1f}%) | 평단 {upbit_balances['BTC']['avg_buy']:,.0f} | 수익률 {upbit_btc_return:+.2f}%")
    else:
        report.append("• **BTC**: 미보유 (현금화)")
        
    if eth_bal_fin > 0:
        report.append(f"• **ETH**: {eth_val_fin:,.0f} 원 ({eth_val_fin/total_upbit_fin*100:.1f}%) | 평단 {upbit_balances['ETH']['avg_buy']:,.0f} | 수익률 {upbit_eth_return:+.2f}%")
    else:
        report.append("• **ETH**: 미보유 (현금화)")
        
    report.append("\n🟢 **서브 전략 (빗썸 - 이더리움 SuperTrend + 50일 SMA)**")
    if use_alt_strategy:
        st_badge = "🟢 매수 유지 (ETH 100%)" if bithumb_action == "BUY" else "🔴 100% 원화 현금화 관망"
        report.append(f"• **전략 방향성**: {st_badge}")
        report.append(f"• **총 자산 가치**: {total_bithumb_fin:,.0f} 원")
        if total_bithumb_fin > 0:
            report.append(f"• **보유 현금 (KRW)**: {bithumb_krw_fin:,.0f} 원 ({bithumb_krw_fin/total_bithumb_fin*100:.1f}%)")
            if bithumb_eth_bal_fin > 0:
                eth_ret = ((eth_price_fin - bithumb_eth_avg_fin)/bithumb_eth_avg_fin)*100 if bithumb_eth_avg_fin > 0 else 0.0
                report.append(f"• **ETH**: {bithumb_eth_val_fin:,.0f} 원 ({bithumb_eth_val_fin/total_bithumb_fin*100:.1f}%) | 평단 {bithumb_eth_avg_fin:,.0f} | 수익률 {eth_ret:+.2f}%")
            else:
                report.append("• **코인 포지션**: 미보유 (100% 현금화 관망)")
        else:
            report.append(f"• **보유 현금 (KRW)**: {bithumb_krw_fin:,.0f} 원 (0.0%)")
    else:
        report.append("• **상태**: 비활성화됨 (Disabled)")

    # 5.4 당일 매매 내역 요약 추가
    report.append("\n🛠️ **당일 실거래 체결 내역**" if not is_dry_run else "\n🛠️ **당일 모의 매매 체결 내역**")
    all_orders = upbit_order_history + bithumb_order_history
    if all_orders:
        for order in all_orders:
            report.append(f"• {order}")
    else:
        report.append("• 추천 매매 시그널 없음 (기존 포지션 유지)")
        
    report.append("\n==================================")
    
    send_discord_message("\n".join(report))
    logging.info("매매 및 잔고 리포팅이 무사히 완료되었습니다.")


def main():
    kst_now = get_kst_now()
    logging.info(f"퀀트 매매 시스템 기동 - 실행 시각 (KST): {kst_now.strftime('%Y-%m-%d %H:%M:%S')}")
    
    parser = argparse.ArgumentParser(
        description="암호화폐 퀀트 매매 봇 (Upbit BTC/ETH 듀얼 모멘텀 + Bithumb BTC/ETH 100%% 스위칭)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
실행 예시:
  python src/main.py --signal-only      # 시그널 방향성 브리핑만 실행 (API 키 불필요)
  python src/main.py --dry-run          # 로컬 모의 매매 시뮬레이션
  python src/main.py --live             # 로컬 실거래 자동 매수/매도 주문 집행
  python src/main.py --live --no-alt    # 빗썸 서브 전략 제외하고 업비트 메인만 실거래
        """
    )
    
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--mode", "-m", choices=["signal", "dry-run", "live"], default=None,
                            help="실행 모드 지정 (signal: 시그널 브리핑, dry-run: 모의매매, live: 실거래)")
    mode_group.add_argument("--signal-only", "-s", action="store_true",
                            help="시그널 브리핑 전용 모드 (API 키 및 잔고 조회 없이 방향성 분석만 수행)")
    mode_group.add_argument("--dry-run", "-d", action="store_true",
                            help="모의 매매(Dry-Run) 모드 (실제 주문 없이 가상 체결 및 리포팅)")
    mode_group.add_argument("--live", "-l", action="store_true",
                            help="실거래(Live Trading) 모드 (실제 계좌 잔고 조회 및 거래소 주문 집행)")
    
    parser.add_argument("--no-alt", action="store_true",
                        help="빗썸 서브 전략을 비활성화하고 업비트 메인 전략만 실행")
    
    args = parser.parse_args()
    
    # 실행 모드 판정
    is_github_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    
    if args.mode == "signal" or args.signal_only or (is_github_actions and args.mode is None and not args.dry_run and not args.live):
        target_mode = "signal"
    elif args.mode == "live" or args.live:
        target_mode = "live"
    elif args.mode == "dry-run" or args.dry_run:
        target_mode = "dry-run"
    else:
        target_mode = "dry-run" if DRY_RUN else "signal"
        
    use_alt = not args.no_alt if args.no_alt else USE_ALTCOIN_STRATEGY
    
    logging.info(f"선택된 실행 모드: [{target_mode}] | 빗썸 서브 전략 활성화: [{use_alt}]")
    
    if target_mode == "signal":
        run_signal_briefing(kst_now, use_alt_strategy=use_alt)
    elif target_mode == "dry-run":
        run_live_trading(kst_now, is_dry_run=True, use_alt_strategy=use_alt)
    elif target_mode == "live":
        run_live_trading(kst_now, is_dry_run=False, use_alt_strategy=use_alt)


if __name__ == "__main__":
    main()
