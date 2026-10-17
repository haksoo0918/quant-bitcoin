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
import csv
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
    BINANCE_ACCESS_KEY, BINANCE_SECRET_KEY,
    DISCORD_WEBHOOK_URL,
    UPBIT_MIN_ORDER_KRW, BITHUMB_MIN_ORDER_KRW, BINANCE_MIN_ORDER_USDT, DRY_RUN,
    BTC_SMA_LEN, ETH_SMA_LEN, BTC_BUFFER, ETH_ATR_MULTIPLIER,
    BINANCE_BTC_SMA_LEN, BINANCE_BTC_BUFFER, BINANCE_ETH_SMA_LEN, BINANCE_ETH_ATR_MULTIPLIER,
    MAIN_RATIO_BAND, USE_ALTCOIN_STRATEGY, USE_BINANCE_STRATEGY
)
from bithumb_api import BithumbClient
from binance_api import BinanceClient
import pyupbit

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)


def fetch_usd_krw_rate() -> float:
    """
    실시간 USD/KRW 환율을 조회합니다. (실패 시 기본 fallback 1,380.0원 적용)
    """
    try:
        url = "https://open.er-api.com/v6/latest/USD"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            rates = res.json().get("rates", {})
            if "KRW" in rates:
                krw_rate = float(rates["KRW"])
                logging.info(f"실시간 USD/KRW 환율 조회 성공: {krw_rate:,.1f}원")
                return krw_rate
    except Exception as e:
        logging.warning(f"실시간 환율 조회 실패 ({e}), fallback 환율(1,380원) 적용")
    return 1380.0



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


def build_chart_series(btc_df, eth_df, chart_count=60):
    """PWA 대시보드 인터랙티브 차트용 60일 시계열 데이터 생성"""
    try:
        import numpy as np
        btc_closes = btc_df['close'].tolist()
        eth_closes = eth_df['close'].tolist()
        
        # BTC 지표
        btc_sma = btc_df['close'].rolling(window=220).mean().tolist()
        btc_upper = [s * 1.02 if pd.notnull(s) else None for s in btc_sma]
        btc_lower = [s * 0.98 if pd.notnull(s) else None for s in btc_sma]
        
        # ETH 지표
        eth_sma = eth_df['close'].rolling(window=50).mean().tolist()
        hl = eth_df['high'] - eth_df['low']
        hc = (eth_df['high'] - eth_df['close'].shift()).abs()
        lc = (eth_df['low'] - eth_df['close'].shift()).abs()
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        atr14 = tr.rolling(window=14).mean().tolist()
        
        eth_upper = [(s + (a * 1.5)) if (pd.notnull(s) and pd.notnull(a)) else None for s, a in zip(eth_sma, atr14)]
        eth_lower = [(s - (a * 1.5)) if (pd.notnull(s) and pd.notnull(a)) else None for s, a in zip(eth_sma, atr14)]
        
        # ETH SuperTrend (7, 3.5)
        st_atr = tr.rolling(window=7).mean()
        hl2 = (eth_df['high'] + eth_df['low']) / 2.0
        basic_upper = hl2 + (3.5 * st_atr)
        basic_lower = hl2 - (3.5 * st_atr)
        final_upper = basic_upper.copy()
        final_lower = basic_lower.copy()
        supertrend = pd.Series(index=eth_df.index, dtype=float)
        direction = pd.Series(index=eth_df.index, dtype=int)
        
        for i in range(len(eth_df)):
            if i < 7:
                continue
            c = eth_df['close'].iloc[i]
            prev_c = eth_df['close'].iloc[i - 1]
            if basic_upper.iloc[i] < final_upper.iloc[i - 1] or prev_c > final_upper.iloc[i - 1]:
                final_upper.iloc[i] = basic_upper.iloc[i]
            else:
                final_upper.iloc[i] = final_upper.iloc[i - 1]
            if basic_lower.iloc[i] > final_lower.iloc[i - 1] or prev_c < final_lower.iloc[i - 1]:
                final_lower.iloc[i] = basic_lower.iloc[i]
            else:
                final_lower.iloc[i] = final_lower.iloc[i - 1]
            if i == 7:
                dir_val = 1 if c > final_upper.iloc[i] else -1
            else:
                prev_dir = direction.iloc[i - 1]
                dir_val = -1 if (prev_dir == 1 and c < final_lower.iloc[i]) else (1 if (prev_dir == -1 and c > final_upper.iloc[i]) else prev_dir)
            direction.iloc[i] = dir_val
            supertrend.iloc[i] = final_lower.iloc[i] if dir_val == 1 else final_upper.iloc[i]
            
        dates = [d.strftime('%m-%d') for d in btc_df.index[-chart_count:]]
        
        return {
            "dates": dates,
            "btc": {
                "closes": btc_closes[-chart_count:],
                "sma": [round(x, 2) if x is not None and not np.isnan(x) else None for x in btc_sma[-chart_count:]],
                "upper": [round(x, 2) if x is not None and not np.isnan(x) else None for x in btc_upper[-chart_count:]],
                "lower": [round(x, 2) if x is not None and not np.isnan(x) else None for x in btc_lower[-chart_count:]]
            },
            "eth": {
                "closes": eth_closes[-chart_count:],
                "sma": [round(x, 2) if x is not None and not np.isnan(x) else None for x in eth_sma[-chart_count:]],
                "upper": [round(x, 2) if x is not None and not np.isnan(x) else None for x in eth_upper[-chart_count:]],
                "lower": [round(x, 2) if x is not None and not np.isnan(x) else None for x in eth_lower[-chart_count:]]
            },
            "bithumb": {
                "closes": eth_closes[-chart_count:],
                "sma": [round(x, 2) if x is not None and not np.isnan(x) else None for x in eth_sma[-chart_count:]],
                "supertrend": [round(x, 2) if not np.isnan(x) else None for x in supertrend.iloc[-chart_count:].tolist()],
                "direction": [int(x) if not np.isnan(x) else 1 for x in direction.iloc[-chart_count:].tolist()]
            }
        }
    except Exception as e:
        logging.error(f"차트 시계열 데이터 생성 실패: {e}")
        return None



def record_trade_history(*args, **kwargs):
    """체결된 거래 내역을 data/trade_history.csv 파일에 누적 기록합니다."""
    try:
        # Positional arguments unpacking
        if len(args) == 10:
            timestamp, exchange, symbol, side, reason, price, quantity, amount, currency, total_asset = args
        elif len(args) == 9:
            exchange, symbol, side, reason, price, quantity, amount, currency, total_asset = args
            timestamp = None
        else:
            timestamp = kwargs.get("timestamp")
            exchange = kwargs.get("exchange", "")
            symbol = kwargs.get("symbol", "")
            side = kwargs.get("side", "")
            reason = kwargs.get("reason", "")
            price = float(kwargs.get("price", 0.0))
            quantity = float(kwargs.get("quantity", 0.0))
            amount = float(kwargs.get("amount", 0.0))
            currency = kwargs.get("currency", "KRW")
            total_asset = float(kwargs.get("total_asset", 0.0))

        # Override with kwargs if provided
        timestamp = kwargs.get("timestamp", timestamp)
        exchange = kwargs.get("exchange", exchange)
        symbol = kwargs.get("symbol", symbol)
        side = kwargs.get("side", side)
        reason = kwargs.get("reason", reason)
        price = float(kwargs.get("price", price))
        quantity = float(kwargs.get("quantity", quantity))
        amount = float(kwargs.get("amount", amount))
        currency = kwargs.get("currency", currency)
        total_asset = float(kwargs.get("total_asset", total_asset))
        csv_path = kwargs.get("csv_path", None)

        if not timestamp:
            timestamp = get_kst_now().strftime("%Y-%m-%d %H:%M:%S")

        if not csv_path:
            csv_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
            os.makedirs(csv_dir, exist_ok=True)
            csv_path = os.path.join(csv_dir, "trade_history.csv")
        else:
            os.makedirs(os.path.dirname(os.path.abspath(csv_path)), exist_ok=True)

        headers = ["timestamp", "exchange", "symbol", "side", "reason", "price", "quantity", "amount", "currency", "total_asset"]
        file_has_content = os.path.exists(csv_path) and os.path.getsize(csv_path) > 0

        with open(csv_path, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            if not file_has_content:
                writer.writeheader()
            writer.writerow({
                "timestamp": timestamp,
                "exchange": exchange,
                "symbol": symbol,
                "side": side,
                "reason": reason,
                "price": f"{price:.2f}" if currency == "USDT" else f"{price:,.0f}".replace(",", ""),
                "quantity": f"{quantity:.8f}".rstrip("0").rstrip("."),
                "amount": f"{amount:.2f}" if currency == "USDT" else f"{amount:,.0f}".replace(",", ""),
                "currency": currency,
                "total_asset": f"{total_asset:.2f}" if currency == "USDT" else f"{total_asset:,.0f}".replace(",", "")
            })
        logging.info(f"거래 기록 누적 저장 완료: [{exchange}] {symbol} {side} {amount} {currency}")
    except Exception as e:
        logging.warning(f"trade_history.csv 저장 실패: {e}")


def load_recent_trade_history(limit: int = 20, csv_path: str = None) -> list:
    """data/trade_history.csv 에서 최근 체결 내역을 역순(최신순)으로 최대 limit개 조회합니다."""
    if not csv_path:
        csv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "trade_history.csv")
    if not os.path.exists(csv_path):
        return []
    records = []
    try:
        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append(row)
        return records[-limit:][::-1]
    except Exception as e:
        logging.warning(f"trade_history.csv 읽기 실패: {e}")
        return []


def record_asset_history(
    date_str: str = None,
    grand_total_krw: float = 0.0,
    upbit_total_krw: float = 0.0,
    bithumb_total_krw: float = 0.0,
    binance_total_usdt: float = 0.0,
    binance_total_krw: float = 0.0,
    usd_krw_rate: float = 1380.0,
    csv_path: str = None
):
    """일별 3대 거래소 통합 총자산 및 거래소별 자산 현황을 data/asset_history.csv에 기록(동일 일자 Upsert)합니다."""
    try:
        if not date_str:
            date_str = get_kst_now().strftime("%Y-%m-%d")

        if not csv_path:
            csv_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
            os.makedirs(csv_dir, exist_ok=True)
            csv_path = os.path.join(csv_dir, "asset_history.csv")
        else:
            os.makedirs(os.path.dirname(os.path.abspath(csv_path)), exist_ok=True)

        headers = [
            "date",
            "grand_total_krw",
            "upbit_total_krw",
            "bithumb_total_krw",
            "binance_total_usdt",
            "binance_total_krw",
            "usd_krw_rate"
        ]

        rows = []
        if os.path.exists(csv_path) and os.path.getsize(csv_path) > 0:
            with open(csv_path, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    if r.get("date"):
                        rows.append(r)

        if binance_total_krw <= 0 and binance_total_usdt > 0:
            binance_total_krw = binance_total_usdt * usd_krw_rate
        if grand_total_krw <= 0:
            grand_total_krw = upbit_total_krw + bithumb_total_krw + binance_total_krw

        new_row = {
            "date": date_str,
            "grand_total_krw": f"{grand_total_krw:.0f}",
            "upbit_total_krw": f"{upbit_total_krw:.0f}",
            "bithumb_total_krw": f"{bithumb_total_krw:.0f}",
            "binance_total_usdt": f"{binance_total_usdt:.2f}",
            "binance_total_krw": f"{binance_total_krw:.0f}",
            "usd_krw_rate": f"{usd_krw_rate:.2f}"
        }

        updated = False
        for i, r in enumerate(rows):
            if r.get("date") == date_str:
                rows[i] = new_row
                updated = True
                break
        if not updated:
            rows.append(new_row)

        rows.sort(key=lambda x: x.get("date", ""))

        with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)

        logging.info(f"일별 자산 현황 기록 완료: [{date_str}] 통합 총자산 {grand_total_krw:,.0f}원")
    except Exception as e:
        logging.warning(f"asset_history.csv 저장 실패: {e}")


def load_asset_history(limit: int = 60, csv_path: str = None) -> list:
    """data/asset_history.csv 에서 최근 limit일간의 일자별 자산 추이 데이터를 오름차순으로 조회합니다."""
    if not csv_path:
        csv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "asset_history.csv")
    if not os.path.exists(csv_path):
        return []
    records = []
    try:
        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append({
                    "date": row.get("date", ""),
                    "grand_total_krw": float(row.get("grand_total_krw", 0) or 0),
                    "upbit_total_krw": float(row.get("upbit_total_krw", 0) or 0),
                    "bithumb_total_krw": float(row.get("bithumb_total_krw", 0) or 0),
                    "binance_total_usdt": float(row.get("binance_total_usdt", 0) or 0),
                    "binance_total_krw": float(row.get("binance_total_krw", 0) or 0),
                    "usd_krw_rate": float(row.get("usd_krw_rate", 1380.0) or 1380.0)
                })
        return records[-limit:]
    except Exception as e:
        logging.warning(f"asset_history.csv 읽기 실패: {e}")
        return []


def export_web_status_json(data_dict, file_path=None):
    """PWA 웹 대시보드 연동용 status.json 파일 저장 (최근 거래 이력 및 일별 자산 추이 자동 포함)"""
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if not file_path:
            file_path = os.path.join(base_dir, "docs", "data", "status.json")

        data_dict["trade_history"] = load_recent_trade_history(limit=20)
        asset_hist = load_asset_history(limit=60)
        data_dict["asset_history"] = asset_hist

        if "portfolio" not in data_dict and asset_hist:
            latest = asset_hist[-1]
            prev = asset_hist[-2] if len(asset_hist) >= 2 else latest
            diff_krw = latest["grand_total_krw"] - prev["grand_total_krw"]
            diff_pct = (diff_krw / prev["grand_total_krw"] * 100.0) if prev["grand_total_krw"] > 0 else 0.0
            data_dict["portfolio"] = {
                "date": latest["date"],
                "grand_total_krw": latest["grand_total_krw"],
                "upbit_total_krw": latest["upbit_total_krw"],
                "bithumb_total_krw": latest["bithumb_total_krw"],
                "binance_total_usdt": latest["binance_total_usdt"],
                "binance_total_krw": latest["binance_total_krw"],
                "usd_krw_rate": latest["usd_krw_rate"],
                "daily_change_krw": round(diff_krw, 0),
                "daily_change_pct": round(diff_pct, 2)
            }

        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data_dict, f, ensure_ascii=False, indent=2)
        logging.info(f"PWA 대시보드 상태 데이터 저장 완료: {file_path}")
    except Exception as e:
        logging.error(f"PWA 대시보드 상태 데이터 저장 실패: {e}")


def auto_push_status_json(target_file=None, skip_push=False):
    """
    PWA 웹 대시보드 데이터(status.json) 및 trade_history.csv, asset_history.csv를 GitHub에 자동 커밋 & 푸시.
    오류가 발생하더라도 매매 봇 프로세스가 중단되지 않도록 안전하게 예외 처리.
    """
    if skip_push:
        logging.info("status.json GitHub 자동 푸시 스킵")
        return True

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not target_file:
        target_file = os.path.join(base_dir, "docs", "data", "status.json")

    try:
        import subprocess
        # 1. git add (status.json, trade_history.csv, asset_history.csv 동반 추가)
        add_res = subprocess.run(
            ["git", "add", "docs/data/status.json", "data/trade_history.csv", "data/asset_history.csv"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False
        )
        if add_res.returncode != 0:
            logging.warning(f"git add 실패: {add_res.stderr.strip()}")
            return False

        # 2. git commit (변경 사항이 없을 경우 대비)
        today_str = datetime.now().strftime("%Y-%m-%d")
        commit_res = subprocess.run(
            ["git", "commit", "-m", f"data: 일일 대시보드 상태 및 차트 시계열 자동 갱신 ({today_str})"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False
        )
        if commit_res.returncode != 0:
            # nothing to commit인 경우는 정상 상태로 간주
            if "nothing to commit" in commit_res.stdout or "clean" in commit_res.stdout:
                logging.info("status.json 변경 사항 없음 (이미 최신 상태)")
                return True
            logging.warning(f"git commit 실패: {commit_res.stderr.strip()}")
            return False

        # 3. 원격 최신 변경사항 동기화 (PC에서 문서/대시보드만 푸시한 경우 충돌 방지)
        pull_res = subprocess.run(
            ["git", "pull", "--rebase", "-X", "theirs", "origin", "main"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False
        )
        if pull_res.returncode != 0:
            logging.warning(f"git pull --rebase 경고 (푸시 계속 시도): {pull_res.stderr.strip()}")

        # 4. git push
        push_res = subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=base_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False
        )
        if push_res.returncode == 0:
            logging.info("🚀 PWA 대시보드 status.json GitHub 자동 푸시 완료")
            return True
        else:
            logging.warning(f"git push 실패: {push_res.stderr.strip()}")
            return False

    except Exception as e:
        logging.warning(f"status.json 자동 푸시 중 예외 발생 (매매는 정상 유지): {e}")
        return False


def run_signal_briefing(kst_now, use_alt_strategy=USE_ALTCOIN_STRATEGY, use_binance_strategy=USE_BINANCE_STRATEGY):
    """
    GitHub Actions 및 --signal-only 실행 모드:
    순수 공개 API 시세 데이터만으로 시장 지표, 업비트/빗썸/바이낸스 방향성 신호 브리핑을 디스코드로 전송.
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

    # 4. 바이낸스 메인 전략 (BTCUSDT & ETHUSDT 50:50 동적 리밸런싱)
    binance_report_lines = []
    binance_data = {}
    binance_guide = "바이낸스 미사용"
    usd_krw_rate = fetch_usd_krw_rate()

    if use_binance_strategy:
        try:
            binance_client = BinanceClient(dry_run=True)
            # 일봉 캔들 조회
            bin_btc_df = binance_client.get_daily_candles("BTCUSDT", limit=BINANCE_BTC_SMA_LEN + 35)
            bin_eth_df = binance_client.get_daily_candles("ETHUSDT", limit=max(200, BINANCE_ETH_SMA_LEN + 50))
            
            bin_btc_price = binance_client.get_current_price("BTCUSDT")
            bin_eth_price = binance_client.get_current_price("ETHUSDT")
            
            bin_btc_df.iloc[-1, bin_btc_df.columns.get_loc('close')] = bin_btc_price
            bin_eth_df.iloc[-1, bin_eth_df.columns.get_loc('close')] = bin_eth_price
            
            bin_btc_ind = calculate_btc_indicators(bin_btc_df, sma_len=BINANCE_BTC_SMA_LEN, buffer_rate=BINANCE_BTC_BUFFER)
            bin_eth_ind = calculate_eth_indicators(bin_eth_df, sma_len=BINANCE_ETH_SMA_LEN, atr_len=14, atr_multiplier=BINANCE_ETH_ATR_MULTIPLIER)
            
            if bin_btc_ind["status"] == "bull":
                bin_btc_str = f"🟢 **[매수 유지 / 신규 진입]** ({bin_btc_ind['status_label']})"
                bin_btc_guide = "BTC 50% 비중 매수 또는 보유 유지"
            elif bin_btc_ind["status"] == "bear":
                bin_btc_str = f"🔴 **[매도 / USDT 관망]** ({bin_btc_ind['status_label']})"
                bin_btc_guide = "BTC 전량 매도 및 USDT 현금 확보"
            else:
                bin_btc_str = f"⏳ **[버퍼 구간 대기]** ({bin_btc_ind['status_label']})"
                bin_btc_guide = "기존 보유 상태 유지 (신규 진입 자제)"
                
            if bin_eth_ind["status"] == "bull":
                bin_eth_str = f"🟢 **[매수 유지 / 신규 진입]** ({bin_eth_ind['status_label']})"
                bin_eth_guide = "ETH 50% 비중 매수 또는 보유 유지"
            elif bin_eth_ind["status"] == "bear":
                bin_eth_str = f"🔴 **[매도 / USDT 관망]** ({bin_eth_ind['status_label']})"
                bin_eth_guide = "ETH 전량 매도 및 USDT 현금 확보"
            else:
                bin_eth_str = f"🔍 **[밴드 내 중립]** ({bin_eth_ind['status_label']})"
                bin_eth_guide = "기존 보유 상태 유지 (신규 진입 자제)"
                
            binance_guide = f"{bin_btc_guide} / {bin_eth_guide}"
            
            binance_report_lines.append(f"• **환율 기준**: 1 USD = {usd_krw_rate:,.1f} 원")
            binance_report_lines.append(f"• **BTCUSDT ({BINANCE_BTC_SMA_LEN}일 SMA)**: ${bin_btc_price:,.2f} (약 {bin_btc_price * usd_krw_rate:,.0f}원)")
            binance_report_lines.append(f"  - 기준 이평: ${bin_btc_ind['sma']:,.2f} (상한: ${bin_btc_ind['upper_buffer']:,.2f} / 하한: ${bin_btc_ind['lower_buffer']:,.2f})")
            binance_report_lines.append(f"  - 전략 방향성: {bin_btc_str}")
            binance_report_lines.append(f"• **ETHUSDT ({BINANCE_ETH_SMA_LEN}일 SMA + {BINANCE_ETH_ATR_MULTIPLIER} ATR)**: ${bin_eth_price:,.2f} (약 {bin_eth_price * usd_krw_rate:,.0f}원)")
            binance_report_lines.append(f"  - 기준 이평: ${bin_eth_ind['sma']:,.2f} (상한밴드: ${bin_eth_ind['upper_band']:,.2f} / 하한밴드: ${bin_eth_ind['lower_band']:,.2f})")
            binance_report_lines.append(f"  - 전략 방향성: {bin_eth_str}")
            
            binance_data = {
                "enabled": True,
                "usd_krw_rate": usd_krw_rate,
                "btc": {
                    "current_price": bin_btc_price,
                    "sma": bin_btc_ind['sma'],
                    "status": bin_btc_ind['status'],
                    "status_label": bin_btc_ind['status_label'],
                    "guide": bin_btc_guide
                },
                "eth": {
                    "current_price": bin_eth_price,
                    "sma": bin_eth_ind['sma'],
                    "status": bin_eth_ind['status'],
                    "status_label": bin_eth_ind['status_label'],
                    "guide": bin_eth_guide
                },
                "guide": binance_guide
            }
        except Exception as e:
            logging.error(f"바이낸스 시그널 조회 중 오류: {e}")
            binance_report_lines.append(f"• ⚠️ 바이낸스 시세 조회 실패: {e}")
            binance_data = {"enabled": False, "error": str(e)}
    else:
        binance_report_lines.append("• **상태**: 비활성화됨 (Disabled)")
        binance_data = {"enabled": False, "guide": "바이낸스 전략 미사용"}

    # 5. 디스코드 메시지 구성
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
    
    if use_binance_strategy:
        report.append("\n🟡 **메인 전략 (바이낸스 - BTC & ETH 50:50)**")
        report.extend(binance_report_lines)
    
    report.append("\n💡 **모바일 직접 매매 가이드 요약**")
    report.append(f"• **업비트**: {btc_guide} / {eth_guide}")
    report.append(f"• **빗썸**: {bithumb_guide}")
    if use_binance_strategy:
        report.append(f"• **바이낸스**: {binance_guide}")
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
        },
        "chart": build_chart_series(btc_df, eth_df)
    }
    export_web_status_json(status_data)
    auto_push_status_json()


def run_live_trading(kst_now, is_dry_run=False, use_alt_strategy=USE_ALTCOIN_STRATEGY, use_binance_strategy=USE_BINANCE_STRATEGY):
    """
    로컬 실거래 또는 모의매매 실행 함수
    """
    mode_label = "모의매매(Dry-Run)" if is_dry_run else "실거래 자동매매"
    logging.info(f"=== [로컬 {mode_label} 모드 가동] ===")
    
    # 1. 거래소 클라이언트 초기화
    upbit = pyupbit.Upbit(UPBIT_ACCESS_KEY, UPBIT_SECRET_KEY) if (UPBIT_ACCESS_KEY and UPBIT_SECRET_KEY) else None
    bithumb = BithumbClient(dry_run=is_dry_run)
    binance = BinanceClient(dry_run=is_dry_run)
    
    # 2. 업비트 시세 및 지표 연산
    btc_df = fetch_upbit_candles("KRW-BTC", count=BTC_SMA_LEN + 35)
    btc_current_price = fetch_upbit_current_price("KRW-BTC")
    btc_df.iloc[-1, btc_df.columns.get_loc('close')] = btc_current_price
    btc_ind = calculate_btc_indicators(btc_df, sma_len=BTC_SMA_LEN, buffer_rate=BTC_BUFFER)
    
    btc_sma = btc_ind["sma"]
    btc_upper = btc_ind["upper_buffer"]
    btc_lower = btc_ind["lower_buffer"]
    btc_status = btc_ind["status"]
    btc_status_label = btc_ind["status_label"]
    market_filter_state = btc_ind["market_filter_state"]
    
    if btc_status == "bull":
        btc_guide = "BTC 50% 비중 매수 또는 보유 유지"
    elif btc_status == "bear":
        btc_guide = "BTC 전량 매도 및 현금(KRW) 확보"
    else:
        btc_guide = "기존 보유 상태 유지 (신규 진입 자제)"
    
    eth_df = fetch_upbit_candles("KRW-ETH", count=max(200, ETH_SMA_LEN + 50))
    eth_current_price = fetch_upbit_current_price("KRW-ETH")
    eth_df.iloc[-1, eth_df.columns.get_loc('close')] = eth_current_price
    eth_ind = calculate_eth_indicators(eth_df, sma_len=ETH_SMA_LEN, atr_len=14, atr_multiplier=ETH_ATR_MULTIPLIER)
    
    eth_sma = eth_ind["sma"]
    eth_atr_14 = eth_ind["atr_14"]
    eth_upper_band = eth_ind["upper_band"]
    eth_lower_band = eth_ind["lower_band"]
    eth_status = eth_ind["status"]
    eth_status_label = eth_ind["status_label"]
    
    if eth_status == "bull":
        eth_guide = "ETH 50% 비중 매수 또는 보유 유지"
    elif eth_status == "bear":
        eth_guide = "ETH 전량 매도 및 현금(KRW) 확보"
    else:
        eth_guide = "기존 보유 상태 유지 (신규 진입 자제)"
    
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
                record_trade_history(kst_now.strftime("%Y-%m-%d %H:%M:%S"), "UPBIT", "BTC", "SELL", "TREND_SELL", btc_current_price, upbit_btc_bal, val, "KRW", total_upbit_value if 'total_upbit_value' in locals() else val)
                upbit_btc_bal = 0.0
            except Exception as e:
                upbit_order_history.append(f"❌ 업비트 BTC 매도 실패: {e}")
        else:
            upbit_order_history.append(f"📝 [모의 주문] 업비트 BTC 청산: {val:,.0f}원 ({upbit_btc_bal:.4f} BTC)")
            upbit_btc_bal = 0.0
        time.sleep(2)
        
    if eth_target_state == 'cash' and is_holding_eth:
        val = upbit_eth_bal * eth_current_price
        logging.info(f"[업비트 매도] ETH 청산 (수량: {upbit_eth_bal:.8f}, 금액: {val:,.0f}원)")
        if not is_dry_run and upbit:
            try:
                order_res = upbit.sell_market_order("KRW-ETH", upbit_eth_bal)
                upbit_order_history.append(f"✅ 업비트 ETH 청산: {val:,.0f}원 ({upbit_eth_bal:.4f} ETH)")
                record_trade_history(kst_now.strftime("%Y-%m-%d %H:%M:%S"), "UPBIT", "ETH", "SELL", "TREND_SELL", eth_current_price, upbit_eth_bal, val, "KRW", total_upbit_value if 'total_upbit_value' in locals() else val)
                upbit_eth_bal = 0.0
            except Exception as e:
                upbit_order_history.append(f"❌ 업비트 ETH 매도 실패: {e}")
        else:
            upbit_order_history.append(f"📝 [모의 주문] 업비트 ETH 청산: {val:,.0f}원 ({upbit_eth_bal:.4f} ETH)")
            upbit_eth_bal = 0.0
        time.sleep(2)

    # 실거래 모드일 경우 선매도 체결 후 실제 가용 잔고(KRW, BTC, ETH) 전수 재조회하여 자산 뻥튀기 원천 차단
    if not is_dry_run and upbit:
        try:
            balances_synced = fetch_upbit_balances(upbit, is_dry_run=False)
            for asset in balances_synced:
                curr = asset.get("currency")
                bal = float(asset.get("balance", 0.0)) + float(asset.get("locked", 0.0))
                if curr == "KRW":
                    upbit_krw = bal
                elif curr == "BTC":
                    upbit_btc_bal = bal
                elif curr == "ETH":
                    upbit_eth_bal = bal
        except Exception as e:
            logging.warning(f"업비트 잔고 재동기화 실패: {e}")

    # 3.2 총 평가 자산 및 목표치 산출
    btc_val = upbit_btc_bal * btc_current_price
    eth_val = upbit_eth_bal * eth_current_price
    total_upbit_value = upbit_krw + btc_val + eth_val

    # 목표 자산 평가액 설정 (BTC 50%, ETH 50% 분할 전략: hold일 때 총자산의 50%, cash일 때 0%)
    target_val_btc = total_upbit_value * 0.5 if btc_target_state == 'hold' else 0.0
    target_val_eth = total_upbit_value * 0.5 if eth_target_state == 'hold' else 0.0

    # 3.3 비중 초과 자산 리밸런싱 매도 (총자산 대비 허용 상한인 60% = 50% + 10%p 초과 시 매도하여 현금 50% 회수)
    # 단독 상승장이든, 동시 상승장이든 상관없이 총자산 기준 60%를 초과한 비대 포지션은 목표치(50%)까지 매도
    if btc_target_state == 'hold' and total_upbit_value > 0:
        btc_weight = btc_val / total_upbit_value
        if btc_weight > (0.5 + MAIN_RATIO_BAND):
            excess_val = btc_val - target_val_btc
            excess_btc = excess_val / btc_current_price
            if excess_val >= UPBIT_MIN_ORDER_KRW:
                logging.info(f"[업비트 BTC 비중 초과 매도] 총자산 비중: {btc_weight*100:.1f}%, 초과액: {excess_val:,.0f}원")
                if not is_dry_run and upbit:
                    try:
                        upbit.sell_market_order("KRW-BTC", excess_btc)
                        upbit_order_history.append(f"⚖️ 업비트 BTC 비중 축소: {excess_val:,.0f}원")
                        record_trade_history(kst_now.strftime("%Y-%m-%d %H:%M:%S"), "UPBIT", "BTC", "SELL", "REBALANCE_SELL", btc_current_price, excess_btc, excess_val, "KRW", total_upbit_value)
                        upbit_btc_bal -= excess_btc
                        upbit_krw += excess_val * 0.9995
                    except Exception as e:
                        upbit_order_history.append(f"❌ 업비트 BTC 리밸런싱 실패: {e}")
                else:
                    upbit_order_history.append(f"📝 [모의 주문] 업비트 BTC 비중 축소: {excess_val:,.0f}원")
                    upbit_btc_bal -= excess_btc
                    upbit_krw += excess_val * 0.9995
                time.sleep(2)

    if eth_target_state == 'hold' and total_upbit_value > 0:
        eth_weight = eth_val / total_upbit_value
        if eth_weight > (0.5 + MAIN_RATIO_BAND):
            excess_val = eth_val - target_val_eth
            excess_eth = excess_val / eth_current_price
            if excess_val >= UPBIT_MIN_ORDER_KRW:
                logging.info(f"[업비트 ETH 비중 초과 매도] 총자산 비중: {eth_weight*100:.1f}%, 초과액: {excess_val:,.0f}원")
                if not is_dry_run and upbit:
                    try:
                        upbit.sell_market_order("KRW-ETH", excess_eth)
                        upbit_order_history.append(f"⚖️ 업비트 ETH 비중 축소: {excess_val:,.0f}원")
                        record_trade_history(kst_now.strftime("%Y-%m-%d %H:%M:%S"), "UPBIT", "ETH", "SELL", "REBALANCE_SELL", eth_current_price, excess_eth, excess_val, "KRW", total_upbit_value)
                        upbit_eth_bal -= excess_eth
                        upbit_krw += excess_val * 0.9995
                    except Exception as e:
                        upbit_order_history.append(f"❌ 업비트 ETH 리밸런싱 실패: {e}")
                else:
                    upbit_order_history.append(f"📝 [모의 주문] 업비트 ETH 비중 축소: {excess_val:,.0f}원")
                    upbit_eth_bal -= excess_eth
                    upbit_krw += excess_val * 0.9995
                time.sleep(2)

    # 실거래 모드일 경우 리밸런싱 매도 후 실제 KRW 잔고 재확인
    if not is_dry_run and upbit:
        try:
            upbit_krw = float(upbit.get_balance("KRW"))
        except Exception:
            pass

    # 3.4 매수 및 유휴 현금 투입 처리 (신규 진입 및 보유 비중 부족분 추가 매수)
    # 각 코인별 필요한 추가 매수 금액 계산
    needed_btc = max(0.0, target_val_btc - (upbit_btc_bal * btc_current_price))
    needed_eth = max(0.0, target_val_eth - (upbit_eth_bal * eth_current_price))

    # 매수 순서: 목표치 미달액이 큰 코인부터 순차적으로 매수
    buy_targets = []
    if needed_btc >= UPBIT_MIN_ORDER_KRW:
        buy_targets.append(("BTC", needed_btc, "신규 매수" if not is_holding_btc else "추가 매수"))
    if needed_eth >= UPBIT_MIN_ORDER_KRW:
        buy_targets.append(("ETH", needed_eth, "신규 매수" if not is_holding_eth else "추가 매수"))

    for coin, needed_amt, action_type in buy_targets:
        if upbit_krw < UPBIT_MIN_ORDER_KRW:
            break
        
        # 가용 현금 범위 내에서 주문 금액 결정 (수수료 0.05% 감안하여 99.5% 상한)
        buy_amount = min(needed_amt, upbit_krw * 0.995)
        if buy_amount >= UPBIT_MIN_ORDER_KRW:
            logging.info(f"[업비트 {action_type}] {coin} (금액: {buy_amount:,.0f}원, 목표 필요액: {needed_amt:,.0f}원)")
            if not is_dry_run and upbit:
                try:
                    upbit.buy_market_order(f"KRW-{coin}", buy_amount)
                    upbit_order_history.append(f"✅ 업비트 {coin} {action_type}: {buy_amount:,.0f}원")
                    curr_p = btc_current_price if coin == "BTC" else eth_current_price
                    record_trade_history(kst_now.strftime("%Y-%m-%d %H:%M:%S"), "UPBIT", coin, "BUY", "TREND_BUY" if "신규" in action_type else "REBALANCE_BUY", curr_p, buy_amount / curr_p, buy_amount, "KRW", total_upbit_value)
                    if coin == "BTC":
                        upbit_btc_bal += buy_amount / curr_p
                        is_holding_btc = True
                    else:
                        upbit_eth_bal += buy_amount / curr_p
                        is_holding_eth = True
                    upbit_krw -= buy_amount
                except Exception as e:
                    upbit_order_history.append(f"❌ 업비트 {coin} {action_type} 실패: {e}")
            else:
                upbit_order_history.append(f"📝 [모의 주문] 업비트 {coin} {action_type}: {buy_amount:,.0f}원")
                curr_p = btc_current_price if coin == "BTC" else eth_current_price
                if coin == "BTC":
                    upbit_btc_bal += buy_amount / curr_p
                    is_holding_btc = True
                else:
                    upbit_eth_bal += buy_amount / curr_p
                    is_holding_eth = True
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
                        record_trade_history(kst_now.strftime("%Y-%m-%d %H:%M:%S"), "BITHUMB", "ETH", "SELL", "TREND_SELL", bithumb_eth_p, bithumb_eth_bal, val, "KRW", total_bithumb_value)
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
                        record_trade_history(kst_now.strftime("%Y-%m-%d %H:%M:%S"), "BITHUMB", "ETH", "BUY", "TREND_BUY", bithumb_eth_p, buy_amount / bithumb_eth_p, buy_amount, "KRW", total_bithumb_value)
                        bithumb_krw -= buy_amount
                    except Exception as e:
                        bithumb_order_history.append(f"❌ 빗썸 ETH 매수 실패: {e}")
                else:
                    bithumb_order_history.append(f"📝 [모의 주문] 빗썸 ETH 100% 매수: {buy_amount:,.0f}원")
                    bithumb_krw -= buy_amount

        bithumb_guide = "이더리움 100% 매수 집중 보유 🟢" if bithumb_action == "BUY" else "100% 원화 현금화 안전 관망 🔴"
        bithumb_data = {
            "enabled": True,
            "strategy_name": "이더리움 SuperTrend + 50일 SMA 추세 추종",
            "current_price": float(bithumb_eth_p),
            "sma50": float(bithumb_eth_ind["sma50"]),
            "supertrend_val": float(bithumb_eth_ind["supertrend_val"]),
            "supertrend_trend": bithumb_eth_ind["supertrend_trend"],
            "is_above_sma": bool(bithumb_eth_ind["is_above_sma"]),
            "action": bithumb_action,
            "guide": bithumb_guide
        }

    else:
        logging.info("=== [빗썸 매매 제어 프로세스 비활성화] ===")
        bithumb_guide = "서브 전략 미사용"
        bithumb_data = {"enabled": False, "guide": bithumb_guide}

    # 4.5 바이낸스 메인 전략 (BTCUSDT & ETHUSDT 50:50 동적 리밸런싱) 매매 프로세스
    binance_order_history = []
    binance_data = {}
    binance_guide = "바이낸스 전략 미사용"
    usd_krw_rate = fetch_usd_krw_rate()
    bin_btc_price = 0.0
    bin_eth_price = 0.0

    if use_binance_strategy:
        logging.info("=== [바이낸스 메인 전략 매매 제어 프로세스 가동] ===")
        try:
            # 바이낸스 일봉 캔들 조회 및 지표 연산
            bin_btc_df = binance.get_daily_candles("BTCUSDT", limit=BINANCE_BTC_SMA_LEN + 35)
            bin_eth_df = binance.get_daily_candles("ETHUSDT", limit=max(200, BINANCE_ETH_SMA_LEN + 50))

            bin_btc_price = binance.get_current_price("BTCUSDT")
            bin_eth_price = binance.get_current_price("ETHUSDT")

            bin_btc_df.iloc[-1, bin_btc_df.columns.get_loc('close')] = bin_btc_price
            bin_eth_df.iloc[-1, bin_eth_df.columns.get_loc('close')] = bin_eth_price

            bin_btc_ind = calculate_btc_indicators(bin_btc_df, sma_len=BINANCE_BTC_SMA_LEN, buffer_rate=BINANCE_BTC_BUFFER)
            bin_eth_ind = calculate_eth_indicators(bin_eth_df, sma_len=BINANCE_ETH_SMA_LEN, atr_len=14, atr_multiplier=BINANCE_ETH_ATR_MULTIPLIER)

            # 잔고 현황 조회
            bin_balances = binance.get_balances()
            binance_usdt = bin_balances.get("USDT", {}).get("free", 0.0)
            binance_btc_bal = bin_balances.get("BTC", {}).get("total", 0.0)
            binance_eth_bal = bin_balances.get("ETH", {}).get("total", 0.0)

            # 실거래 시 잡코인 정리 (BTC, ETH, USDT, BNB 외의 자산이 5 USDT 이상 있을 경우 시장가 매도 정리)
            if not is_dry_run:
                for asset_name, asset_info in list(bin_balances.items()):
                    if asset_name not in ["USDT", "BTC", "ETH", "BNB"]:
                        asset_qty = asset_info.get("free", 0.0)
                        pair = f"{asset_name}USDT"
                        try:
                            asset_p = binance.get_current_price(pair)
                            asset_val = asset_qty * asset_p
                            if asset_val >= BINANCE_MIN_ORDER_USDT:
                                logging.info(f"[바이낸스 잡코인 정리] {asset_name} 매도 (금액: ${asset_val:.2f} USDT)")
                                binance.sell_market(pair, asset_qty)
                                binance_order_history.append(f"✅ 바이낸스 잔여 {asset_name} 정리 매도: ${asset_val:.2f} USDT")
                                time.sleep(1)
                        except Exception as e:
                            logging.debug(f"{asset_name} 정리 시도 스킵: {e}")
                # 정리 후 가용 USDT 잔고 갱신
                binance_usdt = binance.get_balance("USDT")

            is_holding_bin_btc = (binance_btc_bal * bin_btc_price) >= BINANCE_MIN_ORDER_USDT
            is_holding_bin_eth = (binance_eth_bal * bin_eth_price) >= BINANCE_MIN_ORDER_USDT

            # 목표 포지션 결정
            if not is_holding_bin_btc:
                bin_btc_target = 'hold' if bin_btc_price >= bin_btc_ind['upper_buffer'] else 'cash'
            else:
                bin_btc_target = 'cash' if bin_btc_price < bin_btc_ind['lower_buffer'] else 'hold'

            if not is_holding_bin_eth:
                bin_eth_target = 'hold' if bin_eth_price >= bin_eth_ind['upper_band'] else 'cash'
            else:
                bin_eth_target = 'cash' if bin_eth_price < bin_eth_ind['lower_band'] else 'hold'

            logging.info(f"바이낸스 판정 - BTC: {bin_btc_target} | ETH: {bin_eth_target}")

            # (1) 선매도 처리
            if bin_btc_target == 'cash' and is_holding_bin_btc:
                val = binance_btc_bal * bin_btc_price
                logging.info(f"[바이낸스 매도] BTC 청산 (수량: {binance_btc_bal:.6f}, 금액: ${val:.2f})")
                try:
                    binance.sell_market("BTCUSDT", binance_btc_bal)
                    binance_order_history.append(f"✅ 바이낸스 BTC 청산: ${val:,.2f} USDT ({binance_btc_bal:.6f} BTC)")
                    if not is_dry_run:
                        record_trade_history(kst_now.strftime("%Y-%m-%d %H:%M:%S"), "BINANCE", "BTC", "SELL", "TREND_SELL", bin_btc_price, binance_btc_bal, val, "USDT", (binance_usdt + val) if 'binance_usdt' in locals() else val)
                    binance_btc_bal = 0.0
                except Exception as e:
                    binance_order_history.append(f"❌ 바이낸스 BTC 매도 실패: {e}")
                time.sleep(1)

            if bin_eth_target == 'cash' and is_holding_bin_eth:
                val = binance_eth_bal * bin_eth_price
                logging.info(f"[바이낸스 매도] ETH 청산 (수량: {binance_eth_bal:.4f}, 금액: ${val:.2f})")
                try:
                    binance.sell_market("ETHUSDT", binance_eth_bal)
                    binance_order_history.append(f"✅ 바이낸스 ETH 청산: ${val:,.2f} USDT ({binance_eth_bal:.4f} ETH)")
                    if not is_dry_run:
                        record_trade_history(kst_now.strftime("%Y-%m-%d %H:%M:%S"), "BINANCE", "ETH", "SELL", "TREND_SELL", bin_eth_price, binance_eth_bal, val, "USDT", (binance_usdt + val) if 'binance_usdt' in locals() else val)
                    binance_eth_bal = 0.0
                except Exception as e:
                    binance_order_history.append(f"❌ 바이낸스 ETH 매도 실패: {e}")
                time.sleep(1)

            if not is_dry_run:
                binance_usdt = binance.get_balance("USDT")

            # (2) 총 평가 자산 및 목표 비중 산출
            binance_btc_val = binance_btc_bal * bin_btc_price
            binance_eth_val = binance_eth_bal * bin_eth_price
            total_binance_value = binance_usdt + binance_btc_val + binance_eth_val

            target_val_bin_btc = total_binance_value * 0.5 if bin_btc_target == 'hold' else 0.0
            target_val_bin_eth = total_binance_value * 0.5 if bin_eth_target == 'hold' else 0.0

            # (3) 비중 초과 리밸런싱 매도 (총자산 대비 허용 상한인 60% = 50% + 10%p 초과 시 매도하여 USDT 50% 회수)
            # 단독 상승장이든, 동시 상승장이든 상관없이 총자산 기준 60%를 초과한 비대 포지션은 목표치(50%)까지 매도
            if bin_btc_target == 'hold' and total_binance_value > 0:
                btc_weight = binance_btc_val / total_binance_value
                if btc_weight > (0.5 + MAIN_RATIO_BAND):
                    excess = binance_btc_val - target_val_bin_btc
                    excess_qty = excess / bin_btc_price
                    if excess >= BINANCE_MIN_ORDER_USDT:
                        try:
                            binance.sell_market("BTCUSDT", excess_qty)
                            binance_order_history.append(f"⚖️ 바이낸스 BTC 비중 축소: ${excess:,.2f} USDT")
                            if not is_dry_run:
                                record_trade_history(kst_now.strftime("%Y-%m-%d %H:%M:%S"), "BINANCE", "BTC", "SELL", "REBALANCE_SELL", bin_btc_price, excess_qty, excess, "USDT", total_binance_value)
                            binance_btc_bal -= excess_qty
                            binance_usdt += excess
                        except Exception as e:
                            binance_order_history.append(f"❌ 바이낸스 BTC 리밸런싱 실패: {e}")

            if bin_eth_target == 'hold' and total_binance_value > 0:
                eth_weight = binance_eth_val / total_binance_value
                if eth_weight > (0.5 + MAIN_RATIO_BAND):
                    excess = binance_eth_val - target_val_bin_eth
                    excess_qty = excess / bin_eth_price
                    if excess >= BINANCE_MIN_ORDER_USDT:
                        try:
                            binance.sell_market("ETHUSDT", excess_qty)
                            binance_order_history.append(f"⚖️ 바이낸스 ETH 비중 축소: ${excess:,.2f} USDT")
                            if not is_dry_run:
                                record_trade_history(kst_now.strftime("%Y-%m-%d %H:%M:%S"), "BINANCE", "ETH", "SELL", "REBALANCE_SELL", bin_eth_price, excess_qty, excess, "USDT", total_binance_value)
                            binance_eth_bal -= excess_qty
                            binance_usdt += excess
                        except Exception as e:
                            binance_order_history.append(f"❌ 바이낸스 ETH 리밸런싱 실패: {e}")

            if not is_dry_run:
                binance_usdt = binance.get_balance("USDT")

            # (4) 매수 및 리밸런싱 (미체결/유휴 USDT 투입)
            if bin_btc_target == 'hold':
                binance_btc_val = binance_btc_bal * bin_btc_price
                needed = target_val_bin_btc - binance_btc_val
                if needed >= BINANCE_MIN_ORDER_USDT and binance_usdt >= BINANCE_MIN_ORDER_USDT:
                    buy_amt = min(needed, binance_usdt * 0.995)
                    if buy_amt >= BINANCE_MIN_ORDER_USDT:
                        try:
                            binance.buy_market("BTCUSDT", buy_amt)
                            binance_order_history.append(f"✅ 바이낸스 BTC 매수: ${buy_amt:,.2f} USDT")
                            if not is_dry_run:
                                record_trade_history(kst_now.strftime("%Y-%m-%d %H:%M:%S"), "BINANCE", "BTC", "BUY", "TREND_BUY" if not is_holding_bin_btc else "REBALANCE_BUY", bin_btc_price, buy_amt / bin_btc_price, buy_amt, "USDT", total_binance_value)
                            binance_usdt -= buy_amt
                        except Exception as e:
                            binance_order_history.append(f"❌ 바이낸스 BTC 매수 실패: {e}")

            if bin_eth_target == 'hold':
                binance_eth_val = binance_eth_bal * bin_eth_price
                needed = target_val_bin_eth - binance_eth_val
                if needed >= BINANCE_MIN_ORDER_USDT and binance_usdt >= BINANCE_MIN_ORDER_USDT:
                    buy_amt = min(needed, binance_usdt * 0.995)
                    if buy_amt >= BINANCE_MIN_ORDER_USDT:
                        try:
                            binance.buy_market("ETHUSDT", buy_amt)
                            binance_order_history.append(f"✅ 바이낸스 ETH 매수: ${buy_amt:,.2f} USDT")
                            if not is_dry_run:
                                record_trade_history(kst_now.strftime("%Y-%m-%d %H:%M:%S"), "BINANCE", "ETH", "BUY", "TREND_BUY" if not is_holding_bin_eth else "REBALANCE_BUY", bin_eth_price, buy_amt / bin_eth_price, buy_amt, "USDT", total_binance_value)
                            binance_usdt -= buy_amt
                        except Exception as e:
                            binance_order_history.append(f"❌ 바이낸스 ETH 매수 실패: {e}")

            bin_btc_guide = "BTC 50% 매수/보유" if bin_btc_target == 'hold' else "BTC 현금화(USDT)"
            bin_eth_guide = "ETH 50% 매수/보유" if bin_eth_target == 'hold' else "ETH 현금화(USDT)"
            binance_guide = f"{bin_btc_guide} / {bin_eth_guide}"

            binance_data = {
                "enabled": True,
                "strategy_name": "바이낸스 BTC/ETH 50:50 동적 리밸런싱",
                "usd_krw_rate": usd_krw_rate,
                "btc": {
                    "current_price": bin_btc_price,
                    "sma": bin_btc_ind['sma'],
                    "status": bin_btc_ind['status'],
                    "status_label": bin_btc_ind['status_label'],
                    "target_state": bin_btc_target
                },
                "eth": {
                    "current_price": bin_eth_price,
                    "sma": bin_eth_ind['sma'],
                    "status": bin_eth_ind['status'],
                    "status_label": bin_eth_ind['status_label'],
                    "target_state": bin_eth_target
                },
                "guide": binance_guide
            }
        except Exception as e:
            logging.error(f"바이낸스 매매 제어 중 오류: {e}")
            binance_order_history.append(f"⚠️ 바이낸스 매매 오류: {e}")
            binance_data = {"enabled": False, "error": str(e), "guide": f"오류 발생: {e}"}
    else:
        logging.info("=== [바이낸스 매매 제어 프로세스 비활성화] ===")
        binance_data = {"enabled": False, "guide": "바이낸스 전략 미사용"}

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

    # 5.3 바이낸스 최종 잔고 파싱
    binance_usdt_fin = 0.0
    binance_btc_bal_fin = 0.0
    binance_eth_bal_fin = 0.0
    binance_btc_val_fin = 0.0
    binance_eth_val_fin = 0.0
    total_binance_usdt_fin = 0.0
    total_binance_krw_fin = 0.0

    if use_binance_strategy:
        try:
            bin_balances_fin = binance.get_balances()
            binance_usdt_fin = bin_balances_fin.get("USDT", {}).get("free", 0.0)
            binance_btc_bal_fin = bin_balances_fin.get("BTC", {}).get("total", 0.0)
            binance_eth_bal_fin = bin_balances_fin.get("ETH", {}).get("total", 0.0)
            
            bin_btc_p_fin = binance.get_current_price("BTCUSDT") if bin_btc_price == 0 else bin_btc_price
            bin_eth_p_fin = binance.get_current_price("ETHUSDT") if bin_eth_price == 0 else bin_eth_price
            
            binance_btc_val_fin = binance_btc_bal_fin * bin_btc_p_fin
            binance_eth_val_fin = binance_eth_bal_fin * bin_eth_p_fin
            total_binance_usdt_fin = binance_usdt_fin + binance_btc_val_fin + binance_eth_val_fin
            total_binance_krw_fin = total_binance_usdt_fin * usd_krw_rate
        except Exception as e:
            logging.error(f"바이낸스 최종 잔고 파싱 실패: {e}")

    # 5.4 수익률 및 통합 총자산 계산
    upbit_btc_cost = btc_bal_fin * upbit_balances.get("BTC", {}).get("avg_buy", 0.0)
    upbit_eth_cost = eth_bal_fin * upbit_balances.get("ETH", {}).get("avg_buy", 0.0)
    upbit_total_invested = upbit_krw_fin + upbit_btc_cost + upbit_eth_cost
    upbit_total_ret = ((total_upbit_fin - upbit_total_invested) / upbit_total_invested * 100) if upbit_total_invested > 0 else 0.0

    upbit_btc_return = ((btc_price_fin - upbit_balances.get("BTC", {}).get("avg_buy", 0.0)) / upbit_balances.get("BTC", {}).get("avg_buy", 1.0)) * 100 if btc_bal_fin > 0 else 0.0
    upbit_eth_return = ((eth_price_fin - upbit_balances.get("ETH", {}).get("avg_buy", 0.0)) / upbit_balances.get("ETH", {}).get("avg_buy", 1.0)) * 100 if eth_bal_fin > 0 else 0.0

    bithumb_eth_cost = bithumb_eth_bal_fin * bithumb_eth_avg_fin
    bithumb_total_invested = bithumb_krw_fin + bithumb_eth_cost
    bithumb_total_ret = ((total_bithumb_fin - bithumb_total_invested) / bithumb_total_invested * 100) if bithumb_total_invested > 0 else 0.0

    grand_total_val = total_upbit_fin + (total_bithumb_fin if use_alt_strategy else 0.0) + (total_binance_krw_fin if use_binance_strategy else 0.0)
    grand_total_invested = upbit_total_invested + (bithumb_total_invested if use_alt_strategy else 0.0) + (total_binance_krw_fin if use_binance_strategy else 0.0)
    grand_total_ret = ((grand_total_val - grand_total_invested) / grand_total_invested * 100) if grand_total_invested > 0 else 0.0

    # 5.5 디스코드 본문 포맷팅
    report = []
    if is_dry_run:
        report.append("⚡ **[로컬 모의매매] 모의 주문 체결 및 포트폴리오 잔고 보고서**")
    else:
        report.append("⚡ **[실거래 자동매매] 실거래 주문 체결 및 포트폴리오 잔고 보고서**")
    report.append(f"⏱️ **실행 일시**: {kst_now.strftime('%Y-%m-%d %H:%M')} KST")
    report.append("==================================")
    
    # 통합 총자산 표시 (복수 거래소 사용 시)
    if use_alt_strategy or use_binance_strategy:
        binance_desc = f" (바이낸스 환산 포함: 1 USD = {usd_krw_rate:,.1f}원)" if use_binance_strategy else ""
        report.append(f"💰 **통합 총 자산**: {grand_total_val:,.0f} 원{binance_desc}")
    
    # 1. 업비트 메인
    report.append("\n🔵 **메인 전략 (업비트 - BTC & ETH 50:50)**")
    report.append(f"• **총 자산 가치**: {total_upbit_fin:,.0f} 원 (전체 수익률: `{upbit_total_ret:+.2f}%`)")
    report.append(f"• **보유 현금 (KRW)**: {upbit_krw_fin:,.0f} 원 ({upbit_krw_fin/total_upbit_fin*100:.1f}%)" if total_upbit_fin > 0 else f"• **보유 현금 (KRW)**: {upbit_krw_fin:,.0f} 원 (0.0%)")
    
    if btc_bal_fin > 0:
        report.append(f"• **BTC**: {btc_val_fin:,.0f} 원 ({btc_val_fin/total_upbit_fin*100:.1f}%) | 평단 {upbit_balances['BTC']['avg_buy']:,.0f} | 수익률 {upbit_btc_return:+.2f}%")
    else:
        report.append("• **BTC**: 미보유 (현금화)")
        
    if eth_bal_fin > 0:
        report.append(f"• **ETH**: {eth_val_fin:,.0f} 원 ({eth_val_fin/total_upbit_fin*100:.1f}%) | 평단 {upbit_balances['ETH']['avg_buy']:,.0f} | 수익률 {upbit_eth_return:+.2f}%")
    else:
        report.append("• **ETH**: 미보유 (현금화)")
        
    # 2. 빗썸 서브
    report.append("\n🟢 **서브 전략 (빗썸 - 이더리움 SuperTrend + 50일 SMA)**")
    if use_alt_strategy:
        st_badge = "🟢 매수 유지 (ETH 100%)" if bithumb_action == "BUY" else "🔴 100% 원화 현금화 관망"
        report.append(f"• **전략 방향성**: {st_badge}")
        report.append(f"• **총 자산 가치**: {total_bithumb_fin:,.0f} 원 (전체 수익률: `{bithumb_total_ret:+.2f}%`)")
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

    # 3. 바이낸스 메인
    if use_binance_strategy:
        report.append("\n🟡 **메인 전략 (바이낸스 - BTC & ETH 50:50)**")
        report.append(f"• **총 자산 가치**: ${total_binance_usdt_fin:,.2f} USDT (약 {total_binance_krw_fin:,.0f} 원)")
        if total_binance_usdt_fin > 0:
            report.append(f"• **보유 현금 (USDT)**: ${binance_usdt_fin:,.2f} ({binance_usdt_fin/total_binance_usdt_fin*100:.1f}%)")
            if binance_btc_bal_fin > 0:
                report.append(f"• **BTC**: ${binance_btc_val_fin:,.2f} ({binance_btc_val_fin/total_binance_usdt_fin*100:.1f}%) | {binance_btc_bal_fin:.6f} BTC")
            else:
                report.append("• **BTC**: 미보유 (USDT 현금화)")
            if binance_eth_bal_fin > 0:
                report.append(f"• **ETH**: ${binance_eth_val_fin:,.2f} ({binance_eth_val_fin/total_binance_usdt_fin*100:.1f}%) | {binance_eth_bal_fin:.4f} ETH")
            else:
                report.append("• **ETH**: 미보유 (USDT 현금화)")
        else:
            report.append(f"• **보유 현금 (USDT)**: ${binance_usdt_fin:,.2f}")

    # 5.6 당일 매매 내역 요약 추가
    report.append("\n🛠️ **당일 실거래 체결 내역**" if not is_dry_run else "\n🛠️ **당일 모의 매매 체결 내역**")
    all_orders = upbit_order_history + bithumb_order_history + binance_order_history
    if all_orders:
        for order in all_orders:
            report.append(f"• {order}")
    else:
        report.append("• 추천 매매 시그널 없음 (기존 포지션 유지)")
        
    report.append("\n==================================")
    
    send_discord_message("\n".join(report))
    logging.info("매매 및 잔고 리포팅이 무사히 완료되었습니다.")

    if not is_dry_run:
        record_asset_history(
            date_str=kst_now.strftime("%Y-%m-%d"),
            grand_total_krw=grand_total_val,
            upbit_total_krw=total_upbit_fin,
            bithumb_total_krw=total_bithumb_fin if use_alt_strategy else 0.0,
            binance_total_usdt=total_binance_usdt_fin if use_binance_strategy else 0.0,
            binance_total_krw=total_binance_krw_fin if use_binance_strategy else 0.0,
            usd_krw_rate=usd_krw_rate
        )

    # PWA 웹 대시보드용 status.json 파일 내보내기
    total_btc_qty = btc_bal_fin + (binance_btc_bal_fin if use_binance_strategy else 0.0)
    total_eth_qty = eth_bal_fin + (bithumb_eth_bal_fin if use_alt_strategy else 0.0) + (binance_eth_bal_fin if use_binance_strategy else 0.0)
    total_cash_krw = upbit_krw_fin + (bithumb_krw_fin if use_alt_strategy else 0.0) + ((binance_usdt_fin * usd_krw_rate) if use_binance_strategy else 0.0)
    total_btc_val_krw = btc_val_fin + ((binance_btc_val_fin * usd_krw_rate) if use_binance_strategy else 0.0)
    total_eth_val_krw = eth_val_fin + (bithumb_eth_val_fin if use_alt_strategy else 0.0) + ((binance_eth_val_fin * usd_krw_rate) if use_binance_strategy else 0.0)

    live_status_data = {
        "updated_at": kst_now.isoformat(),
        "updated_at_formatted": kst_now.strftime("%Y-%m-%d %H:%M:%S KST"),
        "mode": "dry-run" if is_dry_run else "live",
        "holdings": {
            "btc": {
                "total_quantity": round(total_btc_qty, 8),
                "total_val_krw": round(total_btc_val_krw, 0),
                "upbit_quantity": round(btc_bal_fin, 8),
                "binance_quantity": round(binance_btc_bal_fin if use_binance_strategy else 0.0, 8)
            },
            "eth": {
                "total_quantity": round(total_eth_qty, 8),
                "total_val_krw": round(total_eth_val_krw, 0),
                "upbit_quantity": round(eth_bal_fin, 8),
                "bithumb_quantity": round(bithumb_eth_bal_fin if use_alt_strategy else 0.0, 8),
                "binance_quantity": round(binance_eth_bal_fin if use_binance_strategy else 0.0, 8)
            },
            "cash": {
                "total_krw": round(total_cash_krw, 0),
                "upbit_krw": round(upbit_krw_fin, 0),
                "bithumb_krw": round(bithumb_krw_fin if use_alt_strategy else 0.0, 0),
                "binance_usdt": round(binance_usdt_fin if use_binance_strategy else 0.0, 2),
                "binance_krw": round((binance_usdt_fin * usd_krw_rate) if use_binance_strategy else 0.0, 0)
            }
        },
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
        "binance": binance_data,
        "guides": {
            "upbit": f"{btc_guide} / {eth_guide}",
            "bithumb": bithumb_guide,
            "binance": binance_guide
        },
        "chart": build_chart_series(btc_df, eth_df)
    }
    export_web_status_json(live_status_data)
    auto_push_status_json()


def main():
    kst_now = get_kst_now()
    logging.info(f"퀀트 매매 시스템 기동 - 실행 시각 (KST): {kst_now.strftime('%Y-%m-%d %H:%M:%S')}")
    
    parser = argparse.ArgumentParser(
        description="암호화폐 퀀트 매매 봇 (Upbit + Bithumb + Binance 3대 거래소 통합)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
실행 예시:
  python src/main.py --signal-only      # 3대 거래소 시그널 방향성 브리핑 (API 키 불필요)
  python src/main.py --dry-run          # 3대 거래소 모의 매매 시뮬레이션
  python src/main.py --live             # 3대 거래소 실거래 자동 매수/매도 주문 집행
  python src/main.py --live --no-alt    # 빗썸 제외하고 업비트/바이낸스만 실거래
  python src/main.py --live --no-binance # 바이낸스 제외하고 국내 거래소만 실거래
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
                        help="빗썸 서브 전략을 비활성화")
    parser.add_argument("--no-binance", action="store_true",
                        help="바이낸스 메인 전략을 비활성화")
    
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
    use_bin = not args.no_binance if args.no_binance else USE_BINANCE_STRATEGY
    
    logging.info(f"선택된 실행 모드: [{target_mode}] | 빗썸: [{use_alt}] | 바이낸스: [{use_bin}]")
    
    if target_mode == "signal":
        run_signal_briefing(kst_now, use_alt_strategy=use_alt, use_binance_strategy=use_bin)
    elif target_mode == "dry-run":
        run_live_trading(kst_now, is_dry_run=True, use_alt_strategy=use_alt, use_binance_strategy=use_bin)
    elif target_mode == "live":
        run_live_trading(kst_now, is_dry_run=False, use_alt_strategy=use_alt, use_binance_strategy=use_bin)


if __name__ == "__main__":
    main()

