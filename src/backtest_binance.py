# -*- coding: utf-8 -*-
"""
바이낸스(Binance) USDT 마켓 일봉 데이터 기반 메인 전략(BTC & ETH 50:50 동적 리밸런싱) 백테스트 스크립트.
- 데이터 소스: Binance Public REST API (https://api.binance.com/api/v3/klines)
- 전략:
  - BTC: N일 SMA ± Buffer% 추세 필터
  - ETH: M일 SMA ± K배 ATR(14) 채널 필터
  - 리밸런싱: 50:50 목표 비중, 유휴 현금(USDT) 투입 및 편차 리밸런싱
"""
import os
import sys
import time
import datetime
import argparse
import requests
import pandas as pd
import numpy as np

# 콘솔 출력 UTF-8
if sys.stdout and sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backtest", "binance")
os.makedirs(OUTPUT_DIR, exist_ok=True)
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(CACHE_DIR, exist_ok=True)

# 바이낸스 현물 기본 수수료율: 일반 0.1% (BNB 사용 시 0.075%)
BINANCE_FEE_RATE = 0.0010
BINANCE_MIN_ORDER_USDT = 5.0 # 바이낸스 최소 주문액 ($5)


def fetch_binance_daily_candles(symbol: str, start_year: int = 2021) -> pd.DataFrame:
    """
    바이낸스 공식 REST API를 통해 지정 연도부터 현재까지의 일봉 데이터를 수집하고 CSV로 캐싱합니다.
    """
    cache_file = os.path.join(CACHE_DIR, f"BINANCE_{symbol}_daily.csv")
    now = datetime.datetime.now()

    if os.path.exists(cache_file):
        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(cache_file))
        if mtime.date() == now.date():
            df = pd.read_csv(cache_file)
            print(f"[{symbol}] 오늘 생성된 캐시 데이터 로드 완료 ({len(df)}개 일봉)")
            return df

    print(f"[{symbol}] 바이낸스 API로부터 {start_year}년부터 일봉 데이터를 수집합니다...")
    
    # 시작 시간 (밀리초)
    start_dt = datetime.datetime(start_year, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
    start_ts = int(start_dt.timestamp() * 1000)
    
    all_klines = []
    current_start = start_ts
    
    while True:
        url = "https://api.binance.com/api/v3/klines"
        params = {
            "symbol": symbol,
            "interval": "1d",
            "startTime": current_start,
            "limit": 1000
        }
        
        try:
            res = requests.get(url, params=params, timeout=10)
            if res.status_code != 200:
                print(f"[{symbol}] API 호출 오류 ({res.status_code}): {res.text}")
                break
                
            data = res.json()
            if not data:
                break
                
            all_klines.extend(data)
            last_open_time = data[-1][0]
            
            # 1000개 미만이면 최신 데이터까지 도달한 것
            if len(data) < 1000:
                break
                
            # 다음 루프는 마지막 캔들 다음 날부터
            current_start = last_open_time + (24 * 60 * 60 * 1000)
            time.sleep(0.1) # Rate limit 준수
            print(f"  -> {len(all_klines)}개 수집 중... (진행 일자: {datetime.datetime.fromtimestamp(last_open_time/1000, tz=datetime.timezone.utc).strftime('%Y-%m-%d')})")
        except Exception as e:
            print(f"[{symbol}] 데이터 수집 중 예외 발생: {e}")
            break
            
    if not all_klines:
        raise ValueError(f"[{symbol}] 바이낸스 데이터를 수집하지 못했습니다.")
        
    records = []
    for k in all_klines:
        open_time = datetime.datetime.fromtimestamp(k[0] / 1000, tz=datetime.timezone.utc)
        date_str = open_time.strftime('%Y-%m-%d')
        records.append({
            'date': date_str,
            'open': float(k[1]),
            'high': float(k[2]),
            'low': float(k[3]),
            'close': float(k[4]),
            'volume': float(k[5])
        })
        
    df = pd.DataFrame(records)
    df = df.drop_duplicates(subset=['date']).sort_values('date').reset_index(drop=True)
    df.to_csv(cache_file, index=False)
    print(f"[{symbol}] 총 {len(df)}개 일봉 데이터 수집 및 캐시 완료: {cache_file}")
    return df


def run_binance_simulation(btc_df, eth_df, btc_sma_len=220, btc_buffer=0.02, 
                           eth_sma_len=50, eth_atr_mult=1.5, initial_capital=10000.0,
                           fee_rate=BINANCE_FEE_RATE):
    """
    바이낸스 USDT 마켓 메인 전략(BTC & ETH 50:50 동적 리밸런싱) 시뮬레이션
    """
    btc_df = btc_df.copy()
    eth_df = eth_df.copy()
    
    # BTC 지표 연산
    btc_df['sma'] = btc_df['close'].rolling(window=btc_sma_len).mean()
    
    # ETH 지표 연산 (SMA + ATR)
    eth_df['sma'] = eth_df['close'].rolling(window=eth_sma_len).mean()
    eth_df['tr'] = np.maximum(
        eth_df['high'] - eth_df['low'],
        np.maximum(
            np.abs(eth_df['high'] - eth_df['close'].shift(1)),
            np.abs(eth_df['low'] - eth_df['close'].shift(1))
        )
    )
    eth_df['atr_14'] = eth_df['tr'].rolling(window=14).mean()
    
    # 날짜 기준 병합
    merged = pd.merge(
        btc_df[['date', 'open', 'close', 'sma']],
        eth_df[['date', 'open', 'high', 'low', 'close', 'sma', 'atr_14']],
        on='date', suffixes=('_btc', '_eth')
    ).sort_values('date').reset_index(drop=True)
    
    start_idx = max(btc_sma_len, eth_sma_len) + 1
    if start_idx >= len(merged):
        return None
        
    # 벤치마크 (Buy & Hold 50:50)
    btc_start_p = merged.loc[start_idx, 'open_btc']
    eth_start_p = merged.loc[start_idx, 'open_eth']
    bh_btc_qty = (initial_capital * 0.5 * (1 - fee_rate)) / btc_start_p
    bh_eth_qty = (initial_capital * 0.5 * (1 - fee_rate)) / eth_start_p
    
    cash = float(initial_capital)
    btc_qty = 0.0
    eth_qty = 0.0
    
    btc_signal = 'cash'
    eth_signal = 'cash'
    
    portfolio_history = []
    bh_history = []
    trade_count = 0
    win_trades = 0
    trade_history = []
    
    # 트레이드 추적용
    last_btc_buy_price = 0.0
    last_eth_buy_price = 0.0
    
    for i in range(start_idx, len(merged)):
        row = merged.iloc[i]
        prev_row = merged.iloc[i - 1]
        
        # 1. 시그널 판정 (전일 종가 기준)
        # BTC
        prev_btc_close = prev_row['close_btc']
        prev_btc_sma = prev_row['sma_btc']
        upper_btc = prev_btc_sma * (1.0 + btc_buffer)
        lower_btc = prev_btc_sma * (1.0 - btc_buffer)
        
        if prev_btc_close > upper_btc:
            new_btc_sig = 'hold'
        elif prev_btc_close < lower_btc:
            new_btc_sig = 'cash'
        else:
            new_btc_sig = btc_signal
            
        # ETH
        prev_eth_close = prev_row['close_eth']
        prev_eth_sma = prev_row['sma_eth']
        prev_eth_atr = prev_row['atr_14']
        upper_eth = prev_eth_sma + (eth_atr_mult * prev_eth_atr)
        lower_eth = prev_eth_sma - (eth_atr_mult * prev_eth_atr)
        
        if prev_eth_close > upper_eth:
            new_eth_sig = 'hold'
        elif prev_eth_close < lower_eth:
            new_eth_sig = 'cash'
        else:
            new_eth_sig = eth_signal
            
        # 2. 당일 시가(Open)로 매매 실행
        curr_open_btc = row['open_btc']
        curr_open_eth = row['open_eth']
        
        # (1) 매도(선청산) 처리
        if btc_signal == 'hold' and new_btc_sig == 'cash' and btc_qty > 0:
            sell_amt = btc_qty * curr_open_btc * (1 - fee_rate)
            cash += sell_amt
            trade_count += 1
            if curr_open_btc > last_btc_buy_price:
                win_trades += 1
            btc_qty = 0.0
            
        if eth_signal == 'hold' and new_eth_sig == 'cash' and eth_qty > 0:
            sell_amt = eth_qty * curr_open_eth * (1 - fee_rate)
            cash += sell_amt
            trade_count += 1
            if curr_open_eth > last_eth_buy_price:
                win_trades += 1
            eth_qty = 0.0
            
        # (2) 포트폴리오 리밸런싱 및 신규 매수
        # 현재 평가액 산출
        curr_btc_eval = btc_qty * curr_open_btc
        curr_eth_eval = eth_qty * curr_open_eth
        total_eval = cash + curr_btc_eval + curr_eth_eval
        
        # 목표 비중: 각 코인이 hold 신호일 때 50%
        target_btc_val = total_eval * 0.5 if new_btc_sig == 'hold' else 0.0
        target_eth_val = total_eval * 0.5 if new_eth_sig == 'hold' else 0.0
        
        # 비대 비중 부분 매도 리밸런싱 (+10%p 초과 편차 시)
        if new_btc_sig == 'hold' and curr_btc_eval > (total_eval * 0.60):
            excess = curr_btc_eval - target_btc_val
            sell_qty = excess / curr_open_btc
            if excess >= BINANCE_MIN_ORDER_USDT:
                cash += excess * (1 - fee_rate)
                btc_qty -= sell_qty
                
        if new_eth_sig == 'hold' and curr_eth_eval > (total_eval * 0.60):
            excess = curr_eth_eval - target_eth_val
            sell_qty = excess / curr_open_eth
            if excess >= BINANCE_MIN_ORDER_USDT:
                cash += excess * (1 - fee_rate)
                eth_qty -= sell_qty
                
        # 매수(현금 투입 & 리밸런싱)
        if new_btc_sig == 'hold':
            curr_btc_eval = btc_qty * curr_open_btc
            needed_btc = target_btc_val - curr_btc_eval
            if needed_btc >= BINANCE_MIN_ORDER_USDT and cash >= BINANCE_MIN_ORDER_USDT:
                buy_amt = min(needed_btc, cash)
                actual_buy = buy_amt * (1 - fee_rate)
                btc_qty += actual_buy / curr_open_btc
                cash -= buy_amt
                last_btc_buy_price = curr_open_btc
                if btc_signal == 'cash':
                    trade_count += 1
                    
        if new_eth_sig == 'hold':
            curr_eth_eval = eth_qty * curr_open_eth
            needed_eth = target_eth_val - curr_eth_eval
            if needed_eth >= BINANCE_MIN_ORDER_USDT and cash >= BINANCE_MIN_ORDER_USDT:
                buy_amt = min(needed_eth, cash)
                actual_buy = buy_amt * (1 - fee_rate)
                eth_qty += actual_buy / curr_open_eth
                cash -= buy_amt
                last_eth_buy_price = curr_open_eth
                if eth_signal == 'cash':
                    trade_count += 1
                    
        btc_signal = new_btc_sig
        eth_signal = new_eth_sig
        
        # 일말(종가) 기준 평가액 기록
        close_btc = row['close_btc']
        close_eth = row['close_eth']
        daily_total = cash + (btc_qty * close_btc) + (eth_qty * close_eth)
        portfolio_history.append({'date': row['date'], 'value': daily_total})
        
        daily_bh = (bh_btc_qty * close_btc) + (bh_eth_qty * close_eth)
        bh_history.append({'date': row['date'], 'value': daily_bh})
        
    p_df = pd.DataFrame(portfolio_history)
    b_df = pd.DataFrame(bh_history)
    
    # 성과 지표 계산
    days = len(p_df)
    years = days / 365.25
    final_val = p_df['value'].iloc[-1]
    total_ret = ((final_val - initial_capital) / initial_capital) * 100.0
    cagr = (((final_val / initial_capital) ** (1.0 / years)) - 1.0) * 100.0 if years > 0 else 0.0
    
    # MDD
    p_df['peak'] = p_df['value'].cummax()
    p_df['dd'] = (p_df['value'] - p_df['peak']) / p_df['peak'] * 100.0
    mdd = p_df['dd'].min()
    
    # BH 성과
    bh_final = b_df['value'].iloc[-1]
    bh_ret = ((bh_final - initial_capital) / initial_capital) * 100.0
    bh_cagr = (((bh_final / initial_capital) ** (1.0 / years)) - 1.0) * 100.0 if years > 0 else 0.0
    b_df['peak'] = b_df['value'].cummax()
    b_df['dd'] = (b_df['value'] - b_df['peak']) / b_df['peak'] * 100.0
    bh_mdd = b_df['dd'].min()
    
    calmar = cagr / abs(mdd) if abs(mdd) > 0 else 0.0
    win_rate = (win_trades / trade_count * 100.0) if trade_count > 0 else 0.0
    
    return {
        'start_date': p_df['date'].iloc[0],
        'end_date': p_df['date'].iloc[-1],
        'days': days,
        'years': round(years, 2),
        'initial_capital': initial_capital,
        'final_val': round(final_val, 2),
        'total_ret': round(total_ret, 2),
        'cagr': round(cagr, 2),
        'mdd': round(mdd, 2),
        'calmar': round(calmar, 2),
        'trade_count': trade_count,
        'win_rate': round(win_rate, 1),
        'bh_final': round(bh_final, 2),
        'bh_ret': round(bh_ret, 2),
        'bh_cagr': round(bh_cagr, 2),
        'bh_mdd': round(bh_mdd, 2)
    }


def main():
    parser = argparse.ArgumentParser(description="Binance USDT Main Strategy Backtest")
    parser.add_argument("--start-year", type=int, default=2021, help="Start year for data")
    args = parser.parse_args()
    
    btc_df = fetch_binance_daily_candles("BTCUSDT", start_year=args.start_year)
    eth_df = fetch_binance_daily_candles("ETHUSDT", start_year=args.start_year)
    
    print("\n" + "=" * 75)
    print("1. [업비트 기존 파라미터 적용] 바이낸스(USDT) 백테스트")
    print("   BTC: 220일 SMA ± 2% / ETH: 50일 SMA ± 1.5 ATR(14)")
    print("=" * 75)
    
    base_res = run_binance_simulation(btc_df, eth_df, btc_sma_len=220, btc_buffer=0.02,
                                     eth_sma_len=50, eth_atr_mult=1.5)
    
    if base_res:
        print(f"테스트 기간: {base_res['start_date']} ~ {base_res['end_date']} (약 {base_res['years']}년)")
        print(f"전략 최종 자산: ${base_res['final_val']:,} (누적 수익률: {base_res['total_ret']:+}%)")
        print(f"전략 연평균 성장률(CAGR): {base_res['cagr']}% | 최대 낙폭(MDD): {base_res['mdd']}%")
        print(f"Calmar Ratio: {base_res['calmar']} | 총 거래 횟수: {base_res['trade_count']}회 (승률: {base_res['win_rate']}%)")
        print("-" * 75)
        print(f"벤치마크(단순 보유 50:50) 최종 자산: ${base_res['bh_final']:,} (누적: {base_res['bh_ret']:+}%)")
        print(f"벤치마크 CAGR: {base_res['bh_cagr']}% | MDD: {base_res['bh_mdd']}%")
        print("=" * 75)
        
    print("\n2. [바이낸스 차트 최적 파라미터 탐색 그리드 서치 진행 중...]")
    btc_smas = [180, 200, 220]
    btc_buffers = [0.015, 0.02, 0.025]
    eth_smas = [40, 50, 60]
    eth_atrs = [1.2, 1.5, 1.8]
    
    results = []
    for bs in btc_smas:
        for bb in btc_buffers:
            for es in eth_smas:
                for ea in eth_atrs:
                    res = run_binance_simulation(btc_df, eth_df, bs, bb, es, ea)
                    if res:
                        res['btc_sma'] = bs
                        res['btc_buf'] = bb
                        res['eth_sma'] = es
                        res['eth_atr'] = ea
                        results.append(res)
                        
    res_df = pd.DataFrame(results)
    # Calmar ratio 기준으로 상위 5개 선별
    top_calmar = res_df.sort_values(by=['calmar', 'total_ret'], ascending=False).head(5)
    
    print("\n[Calmar Ratio(수익/MDD) 상위 5개 파라미터 조합]")
    for idx, row in top_calmar.iterrows():
        print(f"- BTC(SMA {row['btc_sma']}, 버퍼 {row['btc_buf']*100:.1f}%) / ETH(SMA {row['eth_sma']}, ATR {row['eth_atr']}배)")
        print(f"  누적수익률: {row['total_ret']:+}% | CAGR: {row['cagr']}% | MDD: {row['mdd']}% | Calmar: {row['calmar']}")
    print("=" * 75)

if __name__ == "__main__":
    main()
