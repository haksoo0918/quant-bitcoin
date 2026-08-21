# -*- coding: utf-8 -*-
import os
import sys

# Windows 콘솔 출력 인코딩 오류 방지 (UTF-8 강제 설정)
if sys.stdout and sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
if sys.stderr and sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

import time
import datetime
import logging
import functools
import requests
import pandas as pd
import numpy as np
import pyupbit
from config import (
    UPBIT_ACCESS_KEY, UPBIT_SECRET_KEY,
    BITHUMB_ACCESS_KEY, BITHUMB_SECRET_KEY,
    MAIN_RATIO_BAND, ETH_ATR_MULTIPLIER, BTC_BUFFER,
    UPBIT_MIN_ORDER_KRW, BITHUMB_MIN_ORDER_KRW, DRY_RUN,
    USE_ALTCOIN_STRATEGY
)
from bithumb_api import BithumbClient
from discord_bot import send_discord_message

# KST(한국 시간) 변환 유틸리티
def get_kst_now():
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    return utc_now + datetime.timedelta(hours=9)

# --- 로깅 설정 일원화 및 분기 처리 ---
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 기존에 등록된 모든 핸들러 제거 (중복 출력 방지)
for h in logger.handlers[:]:
    logger.removeHandler(h)

formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

# 1. 기본 콘솔(화면) 출력 설정
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

# 2. 깃허브 액션이 아닌 '로컬 실행' 시에만 월별 파일 로그 추가 생성
if not os.getenv("GITHUB_ACTIONS"):
    kst_now = get_kst_now()
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # 월별로 구분하여 로그 파일 생성 (예: logs/trading_log_2026-08.log)
    log_filename = os.path.join(log_dir, f"trading_log_{kst_now.strftime('%Y-%m')}.log")
    file_handler = logging.FileHandler(log_filename, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

# API 에러 재시도 및 디스코드 경보 데코레이터
def retry_api_call(retries=3, delay=3):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(1, retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logging.warning(f"API {func.__name__} 호출 실패 (시도 {attempt}/{retries}): {e}")
                    if attempt == retries:
                        # 3회 실패 시 디스코드 비상 알림 전송 및 예외 발생
                        error_msg = f"🚨 **[비상] API 호출 최종 실패**\n함수: `{func.__name__}`\n에러: {e}"
                        send_discord_message(error_msg)
                        raise e
                    time.sleep(delay)
        return wrapper
    return decorator

# --- 빗썸 관련 유틸리티 ---

def bithumb_candles_to_df(candles_list):
    """
    빗썸 raw 캔들 목록을 업비트 데이터프레임 구조와 동일하게 변환합니다.
    """
    df = pd.DataFrame(candles_list)
    # 오래된 순(오름차순)으로 정렬
    df = df.iloc[::-1].reset_index(drop=True)
    df = df.rename(columns={
        "opening_price": "open",
        "high_price": "high",
        "low_price": "low",
        "trade_price": "close",
        "candle_acc_trade_price": "value",
        "candle_acc_trade_volume": "volume"
    })
    for col in ["open", "high", "low", "close", "value", "volume"]:
        if col in df.columns:
            df[col] = df[col].astype(float)
    return df

# --- 데이터 조회 함수 (데코레이터 적용) ---

@retry_api_call(retries=3, delay=3)
def fetch_upbit_candles(market, count=230):
    logging.info(f"업비트 {market} 일봉 조회 중... (조회 개수: {count})")
    df = pyupbit.get_ohlcv(market, interval="day", count=count)
    if df is None or df.empty:
        raise Exception(f"업비트 {market} 일봉 데이터를 가져올 수 없습니다.")
    return df

@retry_api_call(retries=3, delay=3)
def fetch_upbit_current_price(market):
    price = pyupbit.get_current_price(market)
    if price is None:
        raise Exception(f"업비트 {market} 현재가 조회 실패")
    return price

@retry_api_call(retries=3, delay=3)
def fetch_bithumb_ticker_all():
    logging.info("빗썸 전체 티커 시세 조회 중...")
    url = "https://api.bithumb.com/public/ticker/ALL_KRW"
    response = requests.get(url, timeout=10)
    if response.status_code != 200:
        raise Exception(f"빗썸 티커 조회 실패 (상태 코드: {response.status_code})")
    data = response.json()
    if data.get("status") != "0000":
        raise Exception(f"빗썸 티커 데이터 에러: {data.get('message')}")
    return data.get("data", {})

@retry_api_call(retries=3, delay=3)
def fetch_bithumb_candles(bithumb_client, market, count=16):
    return bithumb_client.get_ohlcv(market, count=count)

@retry_api_call(retries=3, delay=3)
def fetch_upbit_balances(upbit_client):
    if DRY_RUN and not (UPBIT_ACCESS_KEY and UPBIT_SECRET_KEY):
        logging.info("[드라이런] 가상의 업비트 잔고 정보를 설정합니다.")
        return [
            {"currency": "KRW", "balance": "10000000", "locked": "0"},
            {"currency": "BTC", "balance": "0.05", "locked": "0", "avg_buy_price": "80000000"},
            {"currency": "ETH", "balance": "1.0", "locked": "0", "avg_buy_price": "4500000"}
        ]
    return upbit_client.get_balances()

@retry_api_call(retries=3, delay=3)
def fetch_bithumb_balances(bithumb_client):
    if DRY_RUN and not (BITHUMB_ACCESS_KEY and BITHUMB_SECRET_KEY):
        logging.info("[드라이런] 가상의 빗썸 잔고 정보를 설정합니다.")
        return [
            {"currency": "KRW", "balance": "5000000", "locked": "0"},
            {"currency": "XRP", "balance": "500.0", "locked": "0", "avg_buy_price": "800"}
        ]
    return bithumb_client.get_balances()


def main():
    kst_now = get_kst_now()
    logging.info(f"퀀트 매매 시스템 기동 - 실행 시각 (KST): {kst_now.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 디스코드 채널 전송용 로그 버퍼
    action_logs = []
    
    # 1. 거래소 클라이언트 객체 생성
    upbit = None
    if UPBIT_ACCESS_KEY and UPBIT_SECRET_KEY:
        upbit = pyupbit.Upbit(UPBIT_ACCESS_KEY, UPBIT_SECRET_KEY)
    elif not DRY_RUN:
        logging.error("업비트 API 키가 설정되지 않았습니다. 프로그램을 안전 종료합니다.")
        send_discord_message("🚨 **[비상] 업비트 API 키 누락으로 프로그램 종료**")
        sys.exit(1)

    bithumb = BithumbClient()
    if not (BITHUMB_ACCESS_KEY and BITHUMB_SECRET_KEY) and not DRY_RUN:
        logging.error("빗썸 API 키가 설정되지 않았습니다. 프로그램을 안전 종료합니다.")
        send_discord_message("🚨 **[비상] 빗썸 API 키 누락으로 프로그램 종료**")
        sys.exit(1)

    # 2. 업비트 (메인 전략) 지표 계산 및 시그널 도출
    logging.info("=== [업비트 메인 전략 시그널 계산 시작] ===")
    
    # 2.1 BTC 지표 계산
    btc_df = fetch_upbit_candles("KRW-BTC", count=230)
    btc_df['sma_200'] = btc_df['close'].rolling(window=200).mean()
    
    # 오늘 시점 (가장 최근 미완성 일봉인 마지막 행 제외, 전일 완료 일봉 기준)
    btc_sma_200 = btc_df['sma_200'].iloc[-2]
    btc_current_price = fetch_upbit_current_price("KRW-BTC")
    
    # 2.2 ETH 지표 계산
    eth_df = fetch_upbit_candles("KRW-ETH", count=200)
    eth_df['sma_150'] = eth_df['close'].rolling(window=150).mean()
    # True Range (TR) 및 ATR(14) 계산
    prev_close = eth_df['close'].shift(1)
    tr1 = eth_df['high'] - eth_df['low']
    tr2 = (eth_df['high'] - prev_close).abs()
    tr3 = (eth_df['low'] - prev_close).abs()
    eth_df['tr'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    eth_df['atr_14'] = eth_df['tr'].rolling(window=14).mean()
    
    eth_sma_150 = eth_df['sma_150'].iloc[-2]
    eth_atr_14 = eth_df['atr_14'].iloc[-2]
    eth_current_price = fetch_upbit_current_price("KRW-ETH")
    
    # 2.3 잔고 현황 조회
    upbit_balances_raw = fetch_upbit_balances(upbit)
    
    # 계좌 잔고 파싱
    upbit_balances = {}
    for asset in upbit_balances_raw:
        curr = asset.get("currency")
        bal = float(asset.get("balance", 0.0)) + float(asset.get("locked", 0.0))
        avg_buy = float(asset.get("avg_buy_price", 0.0))
        if bal > 0 or curr == "KRW":
            upbit_balances[curr] = {"balance": bal, "avg_buy": avg_buy}
            
    upbit_krw = upbit_balances.get("KRW", {}).get("balance", 0.0)
    btc_bal = upbit_balances.get("BTC", {}).get("balance", 0.0)
    eth_bal = upbit_balances.get("ETH", {}).get("balance", 0.0)
    
    btc_val = btc_bal * btc_current_price
    eth_val = eth_bal * eth_current_price
    total_upbit_value = upbit_krw + btc_val + eth_val
    
    # 보유 상태 판정 (업비트 주문 최소 한도 5,000원 기준)
    is_holding_btc = btc_val >= UPBIT_MIN_ORDER_KRW
    is_holding_eth = eth_val >= UPBIT_MIN_ORDER_KRW
    
    # 2.4 추세 필터 신호 판정
    # BTC 신호
    if not is_holding_btc:
        btc_target_state = 'hold' if btc_current_price >= btc_sma_200 * (1 + BTC_BUFFER) else 'cash'
    else:
        btc_target_state = 'cash' if btc_current_price < btc_sma_200 * (1 - BTC_BUFFER) else 'hold'
        
    # ETH 신호
    eth_upper_band = eth_sma_150 + (eth_atr_14 * ETH_ATR_MULTIPLIER)
    eth_lower_band = eth_sma_150 - (eth_atr_14 * ETH_ATR_MULTIPLIER)
    if not is_holding_eth:
        eth_target_state = 'hold' if eth_current_price >= eth_upper_band else 'cash'
    else:
        eth_target_state = 'cash' if eth_current_price < eth_lower_band else 'hold'

    logging.info(f"BTC 현재가: {btc_current_price:,.0f} KRW | SMA(200): {btc_sma_200:,.0f} KRW (버퍼상한: {btc_sma_200 * (1 + BTC_BUFFER):,.0f}, 하한: {btc_sma_200 * (1 - BTC_BUFFER):,.0f})")
    logging.info(f"ETH 현재가: {eth_current_price:,.0f} KRW | SMA(150): {eth_sma_150:,.0f} KRW (상한밴드: {eth_upper_band:,.0f}, 하한밴드: {eth_lower_band:,.0f})")
    logging.info(f"판정 결과 - BTC: {btc_target_state} | ETH: {eth_target_state}")

    # 3. 빗썸 공통 시장 필터 판정 및 히스테리시스(역순 탐색) 처리
    logging.info("=== [빗썸 공통 시장 필터 계산 시작] ===")
    
    # 오늘 기준 필터 판단
    btc_upper_limit = btc_sma_200 * (1 + BTC_BUFFER)
    btc_lower_limit = btc_sma_200 * (1 - BTC_BUFFER)
    
    if btc_current_price >= btc_upper_limit:
        market_filter_state = "Bull"  # 상승장
    elif btc_current_price < btc_lower_limit:
        market_filter_state = "Bear"  # 하락장
    else:
        # 버퍼 구간 내(Standby)에 들어왔을 경우: 과거 데이터를 역순으로 탐색하여 상태 결정
        logging.info("현재가가 공통 시장 필터 버퍼 범위 내에 존재합니다. 과거 데이터를 추적합니다.")
        market_filter_state = "Bear"  # 매칭되는 과거 상태가 없을 시 보수적 관점에서 하락장 기본값 설정
        
        # 1일 전(index -2)부터 역방향 탐색. 인덱스는 -3, -4 ... 순서로 거슬러 올라감
        # df 크기가 230이므로 충분히 탐색 가능
        found_state = False
        for t in range(2, len(btc_df)):
            close_t = btc_df['close'].iloc[-t]
            # row -t의 시점에서 rolling 200 SMA를 구하려면, 그 행을 기준으로 200일 이전 데이터가 필요
            sma_t = btc_df['sma_200'].iloc[-t]
            if pd.isna(sma_t):
                break
                
            upper_t = sma_t * (1 + BTC_BUFFER)
            lower_t = sma_t * (1 - BTC_BUFFER)
            
            if close_t >= upper_t:
                market_filter_state = "Bull"
                found_state = True
                logging.info(f"{t-1}일 전 완료 봉 기준 상승장 기록 확인 (종가: {close_t:,.0f} >= {upper_t:,.0f})")
                break
            elif close_t < lower_t:
                market_filter_state = "Bear"
                found_state = True
                logging.info(f"{t-1}일 전 완료 봉 기준 하락장 기록 확인 (종가: {close_t:,.0f} < {lower_t:,.0f})")
                break
        
        if not found_state:
            logging.warning("과거 200일 데이터 내에서 버퍼를 벗어난 확실한 상태 기록을 찾지 못했습니다. 기본값인 하락장(Bear) 상태를 유지합니다.")

    logging.info(f"최종 공통 시장 필터 상태: {market_filter_state}")

    # 4. 업비트 매매 실행 (메인 전략)
    logging.info("=== [업비트 매매 제어 프로세스 가동] ===")
    
    # 각 코인의 목표 평가 금액 계산
    target_btc_val = 0.5 * total_upbit_value if btc_target_state == 'hold' else 0.0
    target_eth_val = 0.5 * total_upbit_value if eth_target_state == 'hold' else 0.0
    
    # 비중 밴드 리밸런싱 적용 조건 점검 (둘 다 기존에 확실하게 보유 중이고 계속 유지할 경우에만 밴드 점검)
    if btc_target_state == 'hold' and eth_target_state == 'hold' and is_holding_btc and is_holding_eth:
        btc_weight = btc_val / total_upbit_value
        # 비중이 목표 비중(50%) 대비 10%p 초과로 벗어났는지 확인 (즉, 40% 미만 혹은 60% 초과)
        if 0.40 <= btc_weight <= 0.60:
            logging.info(f"두 자산 모두 보유 중이나, 비중 편차가 리밸런싱 밴드 내에 있음 (BTC 비중: {btc_weight * 100:.2f}%). 리밸런싱을 건너뜁니다.")
            # 오늘 타겟 금액을 현재 평가 금액으로 맞추어 거래가 발생하지 않도록 강제
            target_btc_val = btc_val
            target_eth_val = eth_val
        else:
            logging.info(f"비중 편차가 리밸런싱 밴드를 초과함 (BTC 비중: {btc_weight * 100:.2f}%). 50:50 재조정 거래를 진행합니다.")

    # 4.1 선매도 프로세스 실행 (음의 차이액 발생 자산 매도)
    upbit_order_history = []
    
    for coin, target_v, current_v, bal, price in [
        ("BTC", target_btc_val, btc_val, btc_bal, btc_current_price),
        ("ETH", target_eth_val, eth_val, eth_bal, eth_current_price)
    ]:
        diff_v = target_v - current_v
        if diff_v < 0:
            # 매도 결정
            if target_v == 0.0:
                # 전량 청산
                sell_qty = bal
            else:
                # 일부 비중 재조정 매도
                sell_qty = abs(diff_v) / price
            
            sell_amount_krw = sell_qty * price
            if sell_amount_krw >= UPBIT_MIN_ORDER_KRW:
                logging.info(f"[업비트 매도] KRW-{coin} 매도 진행 (수량: {sell_qty:.8f}, 금액: {sell_amount_krw:,.0f}원)")
                if not DRY_RUN and upbit is not None:
                    try:
                        # 소수점 오차로 잔여 수량이 부족할 우려를 방지하기 위해 전량 매도인 경우 잔고 전체 지정
                        if target_v == 0.0:
                            order_res = upbit.sell_market_order(f"KRW-{coin}", bal)
                        else:
                            order_res = upbit.sell_market_order(f"KRW-{coin}", sell_qty)
                        logging.info(f"매도 주문 성공: {order_res}")
                        upbit_order_history.append(f"✅ 업비트 {coin} 매도: {sell_amount_krw:,.0f}원 ({sell_qty:.6f}개)")
                    except Exception as e:
                        logging.error(f"업비트 {coin} 매도 에러: {e}")
                        upbit_order_history.append(f"❌ 업비트 {coin} 매도 실패: {e}")
                else:
                    upbit_order_history.append(f"📝 [추천 주문] 업비트 {coin} 매도: {sell_amount_krw:,.0f}원 ({sell_qty:.6f}개)")
                time.sleep(2)
            else:
                logging.info(f"업비트 {coin} 매도 요청 금액({sell_amount_krw:,.0f}원)이 최소 주문 금액(5,000원) 미만입니다. 스킵합니다.")

    # 4.2 매매 후 업비트 원화 잔고 리프레시
    if not DRY_RUN and upbit is not None:
        try:
            upbit_krw = upbit.get_balance("KRW")
        except Exception as e:
            logging.error(f"원화 잔고 조회 에러: {e}")

    # 4.3 후매수 프로세스 실행 (양의 차이액 발생 자산 매수)
    # BTC, ETH 순서로 검사
    for coin, target_v, current_v, price in [
        ("BTC", target_btc_val, btc_val, btc_current_price),
        ("ETH", target_eth_val, eth_val, eth_current_price)
    ]:
        diff_v = target_v - current_v
        if diff_v > 0:
            # 수수료 고려 및 잔고 가용성 보장을 위해 99.5% 비율 적용 안전장치
            buy_amount = min(diff_v, upbit_krw * 0.995)
            if buy_amount >= UPBIT_MIN_ORDER_KRW:
                logging.info(f"[업비트 매수] KRW-{coin} 매수 진행 (금액: {buy_amount:,.0f}원)")
                if not DRY_RUN and upbit is not None:
                    try:
                        order_res = upbit.buy_market_order(f"KRW-{coin}", buy_amount)
                        logging.info(f"매수 주문 성공: {order_res}")
                        upbit_order_history.append(f"✅ 업비트 {coin} 매수: {buy_amount:,.0f}원")
                        upbit_krw -= buy_amount
                    except Exception as e:
                        logging.error(f"업비트 {coin} 매수 에러: {e}")
                        upbit_order_history.append(f"❌ 업비트 {coin} 매수 실패: {e}")
                else:
                    upbit_order_history.append(f"📝 [추천 주문] 업비트 {coin} 매수: {buy_amount:,.0f}원")
                    upbit_krw -= buy_amount
                time.sleep(2)
            else:
                logging.info(f"업비트 {coin} 매수 요청 금액({buy_amount:,.0f}원)이 최소 주문 금액(5,000원) 미만입니다. 스킵합니다.")

    # 5. 빗썸 매매 실행 (서브 전략)
    bithumb_krw = 0.0
    bithumb_alts_val = 0.0
    bithumb_alts_balances = {}
    bithumb_alts_avg_prices = {}
    total_bithumb_value = 0.0
    bithumb_order_history = []

    if USE_ALTCOIN_STRATEGY:
        logging.info("=== [빗썸 매매 제어 프로세스 가동] ===")
        bithumb_balances_raw = fetch_bithumb_balances(bithumb)
        bithumb_ticker_data = fetch_bithumb_ticker_all()

        bithumb_krw = 0.0
        bithumb_alts_val = 0.0
        bithumb_alts_balances = {}
        bithumb_alts_avg_prices = {}

        for asset in bithumb_balances_raw:
            curr = asset.get("currency")
            bal = float(asset.get("balance", 0.0)) + float(asset.get("locked", 0.0))
            avg_buy = float(asset.get("avg_buy_price", 0.0))
            if bal <= 0:
                continue

            if curr == "KRW":
                bithumb_krw = bal
            elif curr in ("BTC", "ETH"):
                # 서브 전략에서 BTC/ETH 제외
                continue
            else:
                coin_info = bithumb_ticker_data.get(curr, {})
                price = float(coin_info.get("closing_price", 0.0)) if coin_info else 0.0
                if price > 0:
                    val = bal * price
                    bithumb_alts_val += val
                    bithumb_alts_balances[f"KRW-{curr}"] = bal
                    bithumb_alts_avg_prices[f"KRW-{curr}"] = avg_buy

        total_bithumb_value = bithumb_krw + bithumb_alts_val
        bithumb_order_history = []

        # 5.2 시나리오별 주문 프로세스 실행
        is_monday = kst_now.weekday() == 0

        # 하락장(Bear) 시나리오: 전체 청산 (요일 무관)
        if market_filter_state == "Bear":
            logging.info("공통 시장 필터가 '하락장'입니다. 빗썸의 모든 알트코인을 매도하여 안전하게 현금화합니다.")
            for market, bal in bithumb_alts_balances.items():
                curr = market.replace("KRW-", "")
                coin_info = bithumb_ticker_data.get(curr, {})
                price = float(coin_info.get("closing_price", 0.0)) if coin_info else 0.0
                val = bal * price

                if val >= BITHUMB_MIN_ORDER_KRW:
                    logging.info(f"[빗썸 하락장 청산] {market} 매도 (수량: {bal:.8f}, 대략 금액: {val:,.0f}원)")
                    if not DRY_RUN:
                        try:
                            order_res = bithumb.sell_market_order(market, bal)
                            logging.info(f"빗썸 매도 성공: {order_res}")
                            bithumb_order_history.append(f"✅ 빗썸 {curr} 청산: {val:,.0f}원 ({bal:.4f}개)")
                        except Exception as e:
                            logging.error(f"빗썸 {curr} 매도 에러: {e}")
                            bithumb_order_history.append(f"❌ 빗썸 {curr} 청산 실패: {e}")
                    else:
                        bithumb_order_history.append(f"📝 [추천 주문] 빗썸 {curr} 청산: {val:,.0f}원 ({bal:.4f}개)")
                    time.sleep(2)
                else:
                    logging.info(f"빗썸 {market} 청산 보류: 평가액이 최소 주문 금액 미만입니다.")

        # 상승장(Bull) + 월요일 시나리오: 종목 교체 및 25% N분할 리밸런싱 실행
        elif market_filter_state == "Bull" and is_monday:
            logging.info("공통 시장 필터가 '상승장'이고 오늘이 월요일입니다. 주간 리밸런싱 및 종목 교체를 진행합니다.")

            # 1. 거래대금 7일 평균 상위 10개 종목 추출
            # 빗썸 티커에서 전체 후보군 정렬
            volume_list = []
            for coin, info in bithumb_ticker_data.items():
                if coin in ("date", "BTC", "ETH"):
                    continue
                acc_value = float(info.get("acc_trade_value_24H", 0.0))
                volume_list.append((f"KRW-{coin}", acc_value))

            volume_list.sort(key=lambda x: x[1], reverse=True)
            # 상위 30개 후보로 필터링하여 일봉 조회 API 횟수 최적화
            top_30_candidates = [item[0] for item in volume_list[:30]]

            altcoin_stats = []
            logging.info("빗썸 상위 거래 대금 후보군 분석 시작...")
            for market in top_30_candidates:
                try:
                    # count=16 (오늘 0, 어제 1 ~ 14일 전 14, 15일 전 15)
                    candles = fetch_bithumb_candles(bithumb, market, count=16)
                    if len(candles) < 16:
                        continue

                    df_c = bithumb_candles_to_df(candles)

                    # 7일 평균 거래 대금 (index -8 ~ -2)
                    avg_val_7d = df_c['value'].iloc[-8:-1].mean()

                    # 14일 상대 모멘텀 수익률 (오늘 close / 14일전 close - 1)
                    curr_p = df_c['close'].iloc[-1]
                    p_14d_ago = df_c['close'].iloc[-15]
                    ret_14d = (curr_p - p_14d_ago) / p_14d_ago

                    altcoin_stats.append({
                        "market": market,
                        "avg_value_7d": avg_val_7d,
                        "return_14d": ret_14d,
                        "price": curr_p
                    })
                    time.sleep(0.05)
                except Exception as e:
                    logging.warning(f"빗썸 {market} 지표 연산 중 에러 발생: {e}")

            # 7일 평균 거래 대금 기준 정렬 및 상위 10개 추출
            altcoin_stats.sort(key=lambda x: x['avg_value_7d'], reverse=True)
            top_10_by_volume = altcoin_stats[:10]

            # 상위 10개 중 최근 14일 수익률 상위 4개 종목 최종 선정
            top_10_by_volume.sort(key=lambda x: x['return_14d'], reverse=True)
            target_coins_stats = top_10_by_volume[:4]
            target_coins = [x['market'] for x in target_coins_stats]

            logging.info("=== [최종 선정 서브 전략 4대 알트코인] ===")
            for i, coin_stat in enumerate(target_coins_stats):
                logging.info(f"{i+1}위: {coin_stat['market']} | 14일 수익률: {coin_stat['return_14d']*100:.2f}% | 7일 평균거래액: {coin_stat['avg_value_7d']/1e8:.2f}억")

            # 종목당 목표 보유 가치 (총자산의 25%)
            target_coin_value = 0.25 * total_bithumb_value
            logging.info(f"빗썸 총자산 평가액: {total_bithumb_value:,.0f}원 | 목표 종목당 비중(25%): {target_coin_value:,.0f}원")

            # A. 선매도: 미선정 종목 일괄 청산 및 비중 초과 목표 종목 부분 매도
            # 미선정 종목 매도
            for market, bal in bithumb_alts_balances.items():
                curr = market.replace("KRW-", "")
                if market not in target_coins:
                    coin_info = bithumb_ticker_data.get(curr, {})
                    price = float(coin_info.get("closing_price", 0.0)) if coin_info else 0.0
                    val = bal * price
                    if val >= BITHUMB_MIN_ORDER_KRW:
                        logging.info(f"[빗썸 종목교체 매도] {market} 청산 (금액: {val:,.0f}원)")
                        if not DRY_RUN:
                            try:
                                order_res = bithumb.sell_market_order(market, bal)
                                logging.info(f"빗썸 매도 성공: {order_res}")
                                bithumb_order_history.append(f"✅ 빗썸 {curr} 교체 매도: {val:,.0f}원")
                            except Exception as e:
                                logging.error(f"빗썸 {curr} 매도 에러: {e}")
                                bithumb_order_history.append(f"❌ 빗썸 {curr} 교체 매도 실패: {e}")
                        else:
                            bithumb_order_history.append(f"📝 [추천 주문] 빗썸 {curr} 교체 매도: {val:,.0f}원")
                        time.sleep(2)

            # 목표 종목 중 비중 초과분 부분 매도
            for coin_stat in target_coins_stats:
                market = coin_stat['market']
                curr = market.replace("KRW-", "")
                curr_price = coin_stat['price']
                current_bal = bithumb_alts_balances.get(market, 0.0)
                current_v = current_bal * curr_price

                if current_bal > 0 and current_v > target_coin_value:
                    excess_val = current_v - target_coin_value
                    qty_to_sell = excess_val / curr_price
                    if excess_val >= BITHUMB_MIN_ORDER_KRW:
                        logging.info(f"[빗썸 비중조절 매도] {market} 일부 매도 (금액: {excess_val:,.0f}원)")
                        if not DRY_RUN:
                            try:
                                order_res = bithumb.sell_market_order(market, qty_to_sell)
                                logging.info(f"빗썸 부분 매도 성공: {order_res}")
                                bithumb_order_history.append(f"✅ 빗썸 {curr} 비중 축소: {excess_val:,.0f}원")
                            except Exception as e:
                                logging.error(f"빗썸 {curr} 매도 에러: {e}")
                                bithumb_order_history.append(f"❌ 빗썸 {curr} 비중 축소 실패: {e}")
                        else:
                            bithumb_order_history.append(f"📝 [추천 주문] 빗썸 {curr} 비중 축소: {excess_val:,.0f}원")
                        time.sleep(2)

            # B. 매매 후 빗썸 원화 잔고 리프레시
            if not DRY_RUN:
                try:
                    bithumb_krw = bithumb.get_balance("KRW")
                except Exception as e:
                    logging.error(f"빗썸 원화 잔고 조회 에러: {e}")

            # C. 후매수: 목표 종목 중 비중 부족분 매수
            for coin_stat in target_coins_stats:
                market = coin_stat['market']
                curr = market.replace("KRW-", "")
                curr_price = coin_stat['price']
                current_bal = bithumb_alts_balances.get(market, 0.0)
                current_v = current_bal * curr_price

                if current_v < target_coin_value:
                    shortage_val = target_coin_value - current_v
                    buy_amount = min(shortage_val, bithumb_krw * 0.995)
                    if buy_amount >= BITHUMB_MIN_ORDER_KRW:
                        logging.info(f"[빗썸 비중조절 매수] {market} 매수 진행 (금액: {buy_amount:,.0f}원)")
                        if not DRY_RUN:
                            try:
                                order_res = bithumb.buy_market_order(market, buy_amount)
                                logging.info(f"빗썸 매수 성공: {order_res}")
                                bithumb_order_history.append(f"✅ 빗썸 {curr} 추가 매수: {buy_amount:,.0f}원")
                                bithumb_krw -= buy_amount
                            except Exception as e:
                                logging.error(f"빗썸 {curr} 매수 에러: {e}")
                                bithumb_order_history.append(f"❌ 빗썸 {curr} 매수 실패: {e}")
                        else:
                            bithumb_order_history.append(f"📝 [추천 주문] 빗썸 {curr} 추가 매수: {buy_amount:,.0f}원")
                            bithumb_krw -= buy_amount
                        time.sleep(2)

        # 상승장(Bull)이나 월요일이 아님: 거래 미발생 대기
        else:
            logging.info("공통 시장 필터가 '상승장'이지만 월요일이 아니므로 종목 교체/리밸런싱을 진행하지 않고 홀딩합니다.")

    else:
        logging.info("=== [빗썸 매매 제어 프로세스 비활성화] ===")

    # 6. 최종 잔고 업데이트 조회 및 디스코드 리포트 발송
    logging.info("=== [최종 포트폴리오 리포트 전송 시작] ===")
    
    # 6.1 최신 잔고 정보 업데이트
    upbit_balances_raw = fetch_upbit_balances(upbit)
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

    # 6.2 빗썸 최종 잔고 파싱
    bithumb_krw_fin = 0.0
    bithumb_alts_val_fin = 0.0
    bithumb_alts_final_list = []
    total_bithumb_fin = 0.0
    
    if USE_ALTCOIN_STRATEGY:
        bithumb_balances_raw = fetch_bithumb_balances(bithumb)
        bithumb_ticker_fin = fetch_bithumb_ticker_all()
        
        for asset in bithumb_balances_raw:
            curr = asset.get("currency")
            bal = float(asset.get("balance", 0.0)) + float(asset.get("locked", 0.0))
            avg_buy = float(asset.get("avg_buy_price", 0.0))
            if bal <= 0:
                continue
                
            if curr == "KRW":
                bithumb_krw_fin = bal
            elif curr in ("BTC", "ETH"):
                continue
            else:
                coin_info = bithumb_ticker_fin.get(curr, {})
                price = float(coin_info.get("closing_price", 0.0)) if coin_info else 0.0
                if price > 0:
                    val = bal * price
                    bithumb_alts_val_fin += val
                    # 수익률 계산
                    ret = 0.0
                    if avg_buy > 0:
                        ret = ((price - avg_buy) / avg_buy) * 100
                    bithumb_alts_final_list.append({
                        "currency": curr,
                        "balance": bal,
                        "price": price,
                        "value": val,
                        "avg_buy": avg_buy,
                        "return": ret
                    })
                    
        total_bithumb_fin = bithumb_krw_fin + bithumb_alts_val_fin

    # 6.3 디스코드 본문 포맷팅
    # 업비트 자산 현황
    upbit_btc_return = ((btc_price_fin - upbit_balances.get("BTC", {}).get("avg_buy", 0.0)) / upbit_balances.get("BTC", {}).get("avg_buy", 1.0)) * 100 if btc_bal_fin > 0 else 0.0
    upbit_eth_return = ((eth_price_fin - upbit_balances.get("ETH", {}).get("avg_buy", 0.0)) / upbit_balances.get("ETH", {}).get("avg_buy", 1.0)) * 100 if eth_bal_fin > 0 else 0.0

    report = []
    report.append("📊 **일일 포트폴리오 매매 시그널 보고서**")
    report.append(f"⏱️ **실행 일시**: {kst_now.strftime('%Y-%m-%d %H:%M')}")
    report.append("==================================")
    
    report.append("\n🔵 **메인 전략 (업비트 - BTC & ETH)**")
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
        
    report.append("\n🟢 **서브 전략 (빗썸 - 알트코인)**")
    if USE_ALTCOIN_STRATEGY:
        report.append(f"• **시장 필터 상태**: `{market_filter_state}` (최근 확정 기준)")
        report.append(f"• **총 자산 가치**: {total_bithumb_fin:,.0f} 원")
        if total_bithumb_fin > 0:
            report.append(f"• **보유 현금 (KRW)**: {bithumb_krw_fin:,.0f} 원 ({bithumb_krw_fin/total_bithumb_fin*100:.1f}%)")
        else:
            report.append(f"• **보유 현금 (KRW)**: {bithumb_krw_fin:,.0f} 원 (0.0%)")
        
        if bithumb_alts_final_list:
            for alt in bithumb_alts_final_list:
                report.append(f"• **{alt['currency']}**: {alt['value']:,.0f} 원 ({alt['value']/total_bithumb_fin*100:.1f}%) | 평단 {alt['avg_buy']:,.2f} | 수익률 {alt['return']:+.2f}%")
        else:
            report.append("• **알트코인**: 미보유 (현금화)")
    else:
        report.append("• **상태**: 비활성화됨 (Disabled)")

    # 6.4 당일 매매 내역 요약 추가
    report.append("\n🛠️ **당일 리밸런싱 추천 시그널**")
    all_orders = upbit_order_history + bithumb_order_history
    if all_orders:
        for order in all_orders:
            report.append(f"• {order}")
    else:
        report.append("• 추천 매매 시그널 없음 (기존 포지션 유지)")
        
    report.append("\n==================================")
    
    # 디스코드 보고서 발송
    full_report_text = "\n".join(report)
    send_discord_message(full_report_text)
    
    logging.info("매매 및 잔고 리포팅이 무사히 완료되었습니다.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.critical(f"시스템 예외 발생으로 메인 루프 중단: {e}")
        sys.exit(1)
