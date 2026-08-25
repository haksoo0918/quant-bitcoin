# -*- coding: utf-8 -*-
"""
서브 전략: 알트코인 상대 모멘텀 2.0 백테스트 시뮬레이터 (Altcoin Momentum 2.0 Backtester)
- 공통 시장 필터: 업비트 BTC 220일 SMA ±2% 노이즈 버퍼 (하락장 시 100% 현금화)
- 개별 추세 필터: 코인 가격 >= 개별 N일 SMA (하락 추세 역배열 종목 원천 차단)
- 개별 손절 장치: 매수가 대비 -X% 하락 시 즉시 당일 손절 매도 (폭락 방어)
- 동적 현금 관리: 조건 충족 종목이 부족할 경우 잔여 비중 100% 현금 보존
- 주간 리밸런싱: 매주 월요일 09:00, 최근 7일 거래대금 TOP 10 중 모멘텀 TOP N 종목 선정
"""
import os
import sys
import time
import datetime
import argparse
import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Windows 콘솔 UTF-8 출력 강제
if sys.stdout and sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# 백테스트 산출물 저장 디렉토리
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backtest")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 주요 유동성 검증 알트코인 유니버스 (과거 데이터 안정성이 확보된 주요 KRW 마켓 종목군)
DEFAULT_ALTCOIN_UNIVERSE = [
    'KRW-XRP', 'KRW-SOL', 'KRW-DOGE', 'KRW-ADA', 'KRW-AVAX',
    'KRW-NEAR', 'KRW-SUI', 'KRW-APT', 'KRW-STX', 'KRW-ETC',
    'KRW-DOT', 'KRW-BCH', 'KRW-LINK', 'KRW-TRX', 'KRW-SEI',
    'KRW-TIA', 'KRW-ARB', 'KRW-OP', 'KRW-XLM', 'KRW-WLD',
    'KRW-ICP', 'KRW-HBAR', 'KRW-FIL', 'KRW-SAND', 'KRW-MANA',
    'KRW-AXS', 'KRW-CHZ', 'KRW-SHIB', 'KRW-PEPE', 'KRW-POL',
    'KRW-AAVE', 'KRW-ATOM', 'KRW-ALGO', 'KRW-EOS', 'KRW-FLOW',
    'KRW-NEO', 'KRW-QTUM', 'KRW-XTZ', 'KRW-THETA', 'KRW-ZIL'
]


def get_kst_now():
    utc_now = datetime.timezone.utc
    return datetime.datetime.now(utc_now) + datetime.timedelta(hours=9)


def fetch_and_cache_candles(market, days_needed=1500):
    """
    업비트/빗썸 과거 일봉 데이터를 다운로드하고 CSV로 캐싱합니다.
    """
    cache_dir = "data"
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"{market}_daily.csv")

    if os.path.exists(cache_file):
        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(cache_file))
        now = datetime.datetime.now()
        if mtime.date() == now.date():
            df = pd.read_csv(cache_file)
            if len(df) >= days_needed:
                return df

    candles = []
    to_date = None

    while len(candles) < days_needed:
        url = f"https://api.upbit.com/v1/candles/days?market={market}&count=200"
        if to_date:
            url += f"&to={to_date}"

        try:
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                break
            data = response.json()
            if not data:
                break
            candles.extend(data)
            oldest_time = data[-1]['candle_date_time_utc']
            to_date = oldest_time + "Z"
            time.sleep(0.08)
        except Exception:
            break

    if not candles:
        return None

    df = pd.DataFrame(candles)
    df = df[['candle_date_time_kst', 'opening_price', 'high_price', 'low_price', 'trade_price', 'candle_acc_trade_volume', 'candle_acc_trade_price']]
    df.columns = ['date', 'open', 'high', 'low', 'close', 'volume', 'value']
    df['date'] = df['date'].apply(lambda x: str(x).split('T')[0])
    df = df.drop_duplicates(subset=['date']).sort_values('date').reset_index(drop=True)
    df.to_csv(cache_file, index=False)
    return df


def run_altcoin_backtest(days=1000, initial_capital=10000000.0, btc_sma_len=220, buffer_rate=0.02,
                         trend_sma=20, stop_loss=0.08, momentum_window=21, volume_window=7,
                         top_volume_count=10, select_count=4, fee_rate=0.0004, slippage=0.0005):
    """
    알트코인 상대 모멘텀 2.0 전략 시뮬레이션
    """
    print(f"\n{'='*70}")
    print(f"📊 [서브 전략] 빗썸 알트코인 상대 모멘텀 2.0 백테스트 시작")
    print(f"• 분석 기간: 최근 {days}일 | 초기 자본: {initial_capital:,.0f} 원")
    print(f"• 공통 시장 필터: 업비트 BTC {btc_sma_len}일 SMA (±{buffer_rate*100:.1f}% 노이즈 버퍼)")
    print(f"• 개별 추세 필터: {'알트코인 >= ' + str(trend_sma) + '일 SMA' if trend_sma > 0 else '미적용'}")
    print(f"• 개별 손절 장치: {'-' + str(stop_loss*100) + '% 하락 시 즉시 손절' if stop_loss > 0 else '미적용'}")
    print(f"• 종목 선정: 최근 {volume_window}일 거래대금 TOP {top_volume_count} 중 {momentum_window}일 수익률 TOP {select_count}")
    print(f"• 수수료/슬리피지: 거래당 수수료 {fee_rate*100:.2f}% + 슬리피지 {slippage*100:.2f}%")
    print(f"{'='*70}\n")

    # 1. BTC 데이터 수집 (시장 필터용)
    print("▶ 1. BTC 시장 필터 일봉 데이터 수집 중...")
    btc_df = fetch_and_cache_candles("KRW-BTC", days_needed=days + btc_sma_len + 50)
    if btc_df is None or len(btc_df) < (btc_sma_len + 50):
        raise ValueError("BTC 과거 데이터를 충분히 수집하지 못했습니다.")

    # 2. 알트코인 유니버스 데이터 수집
    print(f"▶ 2. 알트코인 유니버스 ({len(DEFAULT_ALTCOIN_UNIVERSE)}개 종목) 일봉 수집 및 전처리...")
    alt_dfs = {}
    for sym in DEFAULT_ALTCOIN_UNIVERSE:
        df = fetch_and_cache_candles(sym, days_needed=days + max(trend_sma, momentum_window) + 50)
        if df is not None and len(df) >= 100:
            alt_dfs[sym] = df
        else:
            pass

    # 3. 날짜 동기화 및 캘린더 생성
    btc_df['date'] = pd.to_datetime(btc_df['date'])
    btc_df['btc_sma'] = btc_df['close'].rolling(window=btc_sma_len).mean()
    btc_df['btc_upper'] = btc_df['btc_sma'] * (1 + buffer_rate)
    btc_df['btc_lower'] = btc_df['btc_sma'] * (1 - buffer_rate)

    test_dates = btc_df['date'].iloc[-days:].reset_index(drop=True)
    
    # 4. 시뮬레이션 상태 변수 초기화
    cash = float(initial_capital)
    holdings = {} # { 'KRW-XRP': { 'qty': float, 'buy_price': float, 'buy_date': date, 'peak_price': float } }
    equity_history = []
    trade_logs = []

    # 시장 필터 히스테리시스 상태 추적
    market_filter_state = "Bear"
    
    first_idx = btc_df[btc_df['date'] == test_dates.iloc[0]].index[0]
    for idx in range(first_idx - 1, -1, -1):
        c = btc_df['close'].iloc[idx]
        u = btc_df['btc_upper'].iloc[idx]
        l = btc_df['btc_lower'].iloc[idx]
        if c >= u:
            market_filter_state = "Bull"
            break
        elif c < l:
            market_filter_state = "Bear"
            break

    print(f"▶ 3. 일별 시뮬레이션 구동 시작 (총 {len(test_dates)}일간)...")

    price_maps = {}
    for sym, df in alt_dfs.items():
        df_temp = df.copy()
        df_temp['date'] = pd.to_datetime(df_temp['date'])
        if trend_sma > 0:
            df_temp['trend_sma'] = df_temp['close'].rolling(window=trend_sma).mean()
        else:
            df_temp['trend_sma'] = 0.0
        df_temp = df_temp.set_index('date')
        price_maps[sym] = df_temp

    stop_loss_count = 0

    for current_date in test_dates:
        # A. 당일 BTC 시장 필터 업데이트
        btc_row = btc_df[btc_df['date'] == current_date].iloc[0]
        btc_price = btc_row['close']
        btc_upper = btc_row['btc_upper']
        btc_lower = btc_row['btc_lower']

        if btc_price >= btc_upper:
            market_filter_state = "Bull"
        elif btc_price < btc_lower:
            market_filter_state = "Bear"

        is_monday = (current_date.weekday() == 0)

        # B. 개별 종목 손절(Stop-Loss) 일일 체크
        if stop_loss > 0 and len(holdings) > 0:
            for sym, pos in list(holdings.items()):
                df_coin = price_maps.get(sym)
                if df_coin is not None and current_date in df_coin.index:
                    curr_close = df_coin.loc[current_date, 'close']
                    loss_rate = (curr_close - pos['buy_price']) / pos['buy_price']
                    if loss_rate <= -stop_loss:
                        # 손절 매도 집행
                        sell_price = curr_close * (1 - slippage)
                        sell_val = pos['qty'] * sell_price
                        fee = sell_val * fee_rate
                        net_val = sell_val - fee
                        cash += net_val
                        ret = (sell_price - pos['buy_price']) / pos['buy_price']
                        trade_logs.append({
                            'date': current_date.strftime('%Y-%m-%d'),
                            'type': '매도(개별 손절 Stop-Loss)',
                            'symbol': sym,
                            'price': sell_price,
                            'qty': pos['qty'],
                            'amount': sell_val,
                            'fee': fee,
                            'return': ret
                        })
                        del holdings[sym]
                        stop_loss_count += 1

        # C. 하락장(Bear) 전환 시 전량 매도 (100% 현금화)
        if market_filter_state == "Bear" and len(holdings) > 0:
            for sym, pos in list(holdings.items()):
                df_coin = price_maps.get(sym)
                if df_coin is not None and current_date in df_coin.index:
                    sell_price = df_coin.loc[current_date, 'close'] * (1 - slippage)
                    sell_val = pos['qty'] * sell_price
                    fee = sell_val * fee_rate
                    net_val = sell_val - fee
                    cash += net_val
                    ret = (sell_price - pos['buy_price']) / pos['buy_price']
                    trade_logs.append({
                        'date': current_date.strftime('%Y-%m-%d'),
                        'type': '매도(하락장 청산)',
                        'symbol': sym,
                        'price': sell_price,
                        'qty': pos['qty'],
                        'amount': sell_val,
                        'fee': fee,
                        'return': ret
                    })
            holdings = {}

        # D. 상승장(Bull) 시 주간 리밸런싱 (월요일 09:00 또는 Bear->Bull 전환 첫 진입)
        elif market_filter_state == "Bull" and (is_monday or len(holdings) == 0):
            candidates = []
            for sym, df_coin in price_maps.items():
                if current_date in df_coin.index:
                    hist = df_coin.loc[:current_date]
                    if len(hist) >= max(volume_window, momentum_window, trend_sma) + 1:
                        curr_p = hist['close'].iloc[-1]
                        # 1) 개별 추세 필터: 현재가 >= Trend SMA 검증
                        if trend_sma > 0:
                            sma_val = hist['trend_sma'].iloc[-1]
                            if pd.isna(sma_val) or curr_p < sma_val:
                                continue # 하락 추세 종목 탈락

                        avg_val = hist['value'].iloc[-volume_window:].mean()
                        ret_m = (curr_p - hist['close'].iloc[-momentum_window-1]) / hist['close'].iloc[-momentum_window-1]
                        
                        candidates.append({
                            'symbol': sym,
                            'avg_val_7d': avg_val,
                            'return_momentum': ret_m,
                            'current_price': curr_p
                        })

            target_coins = []
            if len(candidates) > 0:
                # 2) 거래대금 상위 N개 추출 후 모멘텀 수익률 정렬
                candidates.sort(key=lambda x: x['avg_val_7d'], reverse=True)
                top_vol = candidates[:top_volume_count]
                top_vol.sort(key=lambda x: x['return_momentum'], reverse=True)
                # 모멘텀이 양수인 종목만 매수
                pos_momentum = [c for c in top_vol if c['return_momentum'] > 0]
                target_coins = [c['symbol'] for c in pos_momentum[:select_count]]

            # 3) 기존 보유 코인 중 탈락 종목 매도
            for sym, pos in list(holdings.items()):
                if sym not in target_coins:
                    df_coin = price_maps.get(sym)
                    if df_coin is not None and current_date in df_coin.index:
                        sell_price = df_coin.loc[current_date, 'close'] * (1 - slippage)
                        sell_val = pos['qty'] * sell_price
                        fee = sell_val * fee_rate
                        net_val = sell_val - fee
                        cash += net_val
                        ret = (sell_price - pos['buy_price']) / pos['buy_price']
                        trade_logs.append({
                            'date': current_date.strftime('%Y-%m-%d'),
                            'type': '매도(종목 교체)',
                            'symbol': sym,
                            'price': sell_price,
                            'qty': pos['qty'],
                            'amount': sell_val,
                            'fee': fee,
                            'return': ret
                        })
                        del holdings[sym]

            # 4) 총 평가자산 계산 후 목표 1/N 비중으로 신규/리밸런싱 매수
            current_total_equity = cash
            for sym, pos in holdings.items():
                df_coin = price_maps.get(sym)
                if df_coin is not None and current_date in df_coin.index:
                    current_total_equity += pos['qty'] * df_coin.loc[current_date, 'close']

            target_per_coin = current_total_equity / select_count

            for sym in target_coins:
                df_coin = price_maps.get(sym)
                if df_coin is not None and current_date in df_coin.index:
                    curr_p = df_coin.loc[current_date, 'close']
                    buy_p = curr_p * (1 + slippage)
                    
                    if sym not in holdings:
                        order_amt = min(cash, target_per_coin)
                        if order_amt >= 5000:
                            fee = order_amt * fee_rate
                            net_amt = order_amt - fee
                            qty = net_amt / buy_p
                            cash -= order_amt
                            holdings[sym] = {
                                'qty': qty,
                                'buy_price': buy_p,
                                'buy_date': current_date,
                                'peak_price': buy_p
                            }
                            trade_logs.append({
                                'date': current_date.strftime('%Y-%m-%d'),
                                'type': '매수(신규 진입)',
                                'symbol': sym,
                                'price': buy_p,
                                'qty': qty,
                                'amount': order_amt,
                                'fee': fee,
                                'return': 0.0
                            })

        # E. 당일 총 자산 평가액 기록
        coin_valuation = 0.0
        for sym, pos in holdings.items():
            df_coin = price_maps.get(sym)
            if df_coin is not None and current_date in df_coin.index:
                coin_valuation += pos['qty'] * df_coin.loc[current_date, 'close']

        total_equity = cash + coin_valuation
        equity_history.append({
            'date': current_date,
            'equity': total_equity,
            'cash': cash,
            'holdings_count': len(holdings),
            'market_filter': market_filter_state,
            'btc_price': btc_price
        })

    # 5. 성과 지표 산출
    res_df = pd.DataFrame(equity_history)
    res_df['daily_return'] = res_df['equity'].pct_change().fillna(0)
    res_df['cum_return'] = (res_df['equity'] / initial_capital) - 1.0
    res_df['peak'] = res_df['equity'].cummax()
    res_df['drawdown'] = (res_df['equity'] - res_df['peak']) / res_df['peak']

    btc_start_price = res_df['btc_price'].iloc[0]
    res_df['btc_cum_return'] = (res_df['btc_price'] / btc_start_price) - 1.0
    res_df['btc_peak'] = res_df['btc_price'].cummax()
    res_df['btc_drawdown'] = (res_df['btc_price'] - res_df['btc_peak']) / res_df['btc_peak']

    total_days = (test_dates.iloc[-1] - test_dates.iloc[0]).days
    total_return = res_df['cum_return'].iloc[-1]
    cagr = ((1 + total_return) ** (365.25 / total_days)) - 1.0 if total_days > 0 else 0
    mdd = res_df['drawdown'].min()

    btc_total_return = res_df['btc_cum_return'].iloc[-1]
    btc_cagr = ((1 + btc_total_return) ** (365.25 / total_days)) - 1.0 if total_days > 0 else 0
    btc_mdd = res_df['btc_drawdown'].min()

    sell_trades = [t for t in trade_logs if '매도' in t['type']]
    win_trades = [t for t in sell_trades if t['return'] > 0]
    win_rate = (len(win_trades) / len(sell_trades) * 100) if sell_trades else 0

    metrics = {
        'total_days': total_days,
        'initial_capital': initial_capital,
        'final_equity': res_df['equity'].iloc[-1],
        'total_return': total_return * 100,
        'cagr': cagr * 100,
        'mdd': mdd * 100,
        'btc_total_return': btc_total_return * 100,
        'btc_cagr': btc_cagr * 100,
        'btc_mdd': btc_mdd * 100,
        'total_trades': len(trade_logs),
        'sell_trades': len(sell_trades),
        'win_trades': len(win_trades),
        'win_rate': win_rate,
        'stop_loss_count': stop_loss_count,
        'trend_sma': trend_sma,
        'stop_loss': stop_loss,
        'momentum_window': momentum_window
    }

    # 콘솔 출력
    print("\n" + "="*70)
    print("🎯 [서브 전략 2.0: 빗썸 알트코인 상대 모멘텀 백테스트 결과]")
    print("="*70)
    print(f"• 테스트 기간: {test_dates.iloc[0].strftime('%Y-%m-%d')} ~ {test_dates.iloc[-1].strftime('%Y-%m-%d')} ({total_days}일, 약 {total_days/365.25:.1f}년)")
    print(f"• 적용 필터: 개별 {trend_sma}일 SMA 추세 필터 | 손절선 -{stop_loss*100:.1f}% (손절 발생: {stop_loss_count}회) | 모멘텀 {momentum_window}일")
    print(f"• 초기 자본: {initial_capital:,.0f} 원 ➔ 최종 자산: {metrics['final_equity']:,.0f} 원")
    print(f"• 전략 누적 수익률: {metrics['total_return']:+.2f}% (CAGR: {metrics['cagr']:+.2f}%)")
    print(f"• 벤치마크(BTC 단순보유): {metrics['btc_total_return']:+.2f}% (CAGR: {metrics['btc_cagr']:+.2f}%)")
    print(f"• 초과 성과: {metrics['total_return'] - metrics['btc_total_return']:+.2f}%p")
    print(f"• 전략 최대 낙폭 (MDD): {metrics['mdd']:.2f}% (BTC MDD: {metrics['btc_mdd']:.2f}%)")
    print(f"• 총 매매 횟수: {len(trade_logs)}회 (매도 완료 {len(sell_trades)}회, 승률 {win_rate:.1f}%)")
    print("="*70)

    # 6. 차트 생성 및 저장
    timestamp_str = get_kst_now().strftime("%Y%m%d_%H%M%S")
    plot_filename = f"backtest_altcoin_result_{timestamp_str}.png"
    plot_path = os.path.join(OUTPUT_DIR, plot_filename)

    generate_altcoin_chart(res_df, plot_path, metrics)

    # 7. 마크다운 보고서 생성 및 저장
    report_filename = f"backtest_altcoin_report_{timestamp_str}.md"
    report_path = os.path.join(OUTPUT_DIR, report_filename)

    generate_altcoin_report(res_df, trade_logs, metrics, plot_filename, report_path)

    return metrics, report_path


def generate_altcoin_chart(df, save_path, metrics):
    plt.rcParams['font.family'] = 'DejaVu Sans'
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True, gridspec_kw={'height_ratios': [2.5, 1]})

    ax1.plot(df['date'], (df['equity'] / metrics['initial_capital']) * 100, label=f"Altcoin Momentum 2.0 (CAGR {metrics['cagr']:+.1f}%)", color='#0284c7', linewidth=2.0)
    ax1.plot(df['date'], (df['btc_price'] / df['btc_price'].iloc[0]) * 100, label=f"BTC Buy & Hold (CAGR {metrics['btc_cagr']:+.1f}%)", color='#94a3b8', linestyle='--', linewidth=1.5)
    
    ax1.axhline(100, color='gray', linestyle=':', alpha=0.6)
    ax1.set_title("Altcoin Relative Momentum 2.0 Strategy vs BTC Buy & Hold", fontsize=14, fontweight='bold', pad=12)
    ax1.set_ylabel("Normalized Equity (Base = 100)", fontsize=11)
    ax1.grid(True, linestyle='--', alpha=0.4)
    ax1.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.9)

    ax2.plot(df['date'], df['drawdown'] * 100, label=f"Strategy Drawdown (MDD {metrics['mdd']:.1f}%)", color='#dc2626', linewidth=1.5)
    ax2.plot(df['date'], df['btc_drawdown'] * 100, label=f"BTC Drawdown (MDD {metrics['btc_mdd']:.1f}%)", color='#94a3b8', linestyle='--', linewidth=1.0)
    ax2.fill_between(df['date'], df['drawdown'] * 100, 0, color='#dc2626', alpha=0.15)
    
    ax2.set_ylabel("Drawdown (%)", fontsize=11)
    ax2.set_xlabel("Date", fontsize=11)
    ax2.grid(True, linestyle='--', alpha=0.4)
    ax2.legend(loc='lower left', frameon=True, facecolor='white', framealpha=0.9)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

    plt.tight_layout()
    plt.savefig(save_path, dpi=300)
    plt.close()


def generate_altcoin_report(df, trade_logs, metrics, plot_filename, save_path):
    report = []
    report.append(f"# 📊 [서브 전략 2.0] 빗썸 알트코인 상대 모멘텀 백테스트 성과 보고서\n")
    report.append(f"- **실행 일시**: {get_kst_now().strftime('%Y-%m-%d %H:%M:%S KST')}")
    report.append(f"- **분석 기간**: {df['date'].iloc[0].strftime('%Y-%m-%d')} ~ {df['date'].iloc[-1].strftime('%Y-%m-%d')} (총 {metrics['total_days']} 일, 약 {metrics['total_days']/365.25:.1f} 년)")
    report.append(f"- **적용 필터**: 개별 **{metrics['trend_sma']}일 SMA 추세 필터**, 손절선 **-{metrics['stop_loss']*100:.1f}%**, 모멘텀 **{metrics['momentum_window']}일**")
    report.append(f"- **시작 자산**: {metrics['initial_capital']:,.0f} 원 ➔ **최종 자산**: {metrics['final_equity']:,.0f} 원\n")
    report.append(f"---\n")

    report.append(f"## 1. 종합 성과 지표 비교\n")
    report.append(f"| 평가 지표 | 알트코인 모멘텀 2.0 전략 | BTC 단순 보유 (Buy & Hold) | 초과 성과 |")
    report.append(f"| :--- | :---: | :---: | :---: |")
    report.append(f"| **누적 수익률** | **{metrics['total_return']:+.2f}%** | {metrics['btc_total_return']:+.2f}% | **{metrics['total_return'] - metrics['btc_total_return']:+.2f}%p** |")
    report.append(f"| **연평균 성장률 (CAGR)** | **{metrics['cagr']:.2f}%** | {metrics['btc_cagr']:.2f}% | **{metrics['cagr'] - metrics['btc_cagr']:+.2f}%p** |")
    report.append(f"| **최대 낙폭 (MDD)** | **{metrics['mdd']:.2f}%** | {metrics['btc_mdd']:.2f}% | **{metrics['btc_mdd'] - metrics['mdd']:+.2f}%p** (방어) |")
    report.append(f"| **총 거래 횟수** | **{metrics['total_trades']} 회** (매도 {metrics['sell_trades']} 회, 손절 {metrics['stop_loss_count']} 회) | - | - |")
    report.append(f"| **청산 승률 (Win Rate)** | **{metrics['win_rate']:.1f}%** | - | - |\n")

    outperformance = metrics['total_return'] - metrics['btc_total_return']
    mdd_defense = metrics['btc_mdd'] - metrics['mdd']
    report.append(f"> 💡 **주요 성과 요약**: 개별 추세 필터 및 손절선 도입으로 최대 낙폭(MDD)을 **{metrics['mdd']:.2f}%** 수준으로 대폭 방어하였으며, 벤치마크 대비 **{mdd_defense:.2f}%p** 만큼의 낙폭 축소 효과를 기록하였습니다.\n")

    report.append(f"## 2. 자산 가치 변동 추이 차트\n")
    report.append(f"![Equity Curve]({plot_filename})\n")

    report.append(f"## 3. 주요 매매 거래 내역 요약 (최근 {min(len(trade_logs), 20)}건 / 총 {len(trade_logs)}건)\n")
    if trade_logs:
        report.append(f"| 거래 일자 | 거래 구분 | 종목명 | 체결 가격 | 거래 금액 | 실현 손익률 |")
        report.append(f"| :---: | :---: | :---: | :---: | :---: | :---: |")
        for log in trade_logs[-20:]:
            ret_str = f"{log['return']*100:+.2f}%" if '매도' in log['type'] else "-"
            report.append(f"| {log['date']} | {log['type']} | {log['symbol'].replace('KRW-', '')} | {log['price']:,.1f} 원 | {log['amount']:,.0f} 원 | {ret_str} |")
    
    with open(save_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="빗썸 알트코인 상대 모멘텀 2.0 퀀트 전략 백테스터")
    parser.add_argument('--days', type=int, default=1000, help='백테스트 분석 일수 (기본값: 1000)')
    parser.add_argument('--capital', type=float, default=10000000.0, help='시작 원금 (기본값: 10,000,000 원)')
    parser.add_argument('--btc-sma', type=int, default=220, help='BTC 시장 필터 SMA 기간 (기본값: 220)')
    parser.add_argument('--trend-sma', type=int, default=20, help='개별 알트코인 추세 필터 SMA 기간 (기본값: 20, 0=미적용)')
    parser.add_argument('--stop-loss', type=float, default=0.08, help='개별 종목 손절선 비율 (기본값: 0.08 = -8%%, 0.0=미적용)')
    parser.add_argument('--momentum-window', type=int, default=21, help='모멘텀 산출 기간 일수 (기본값: 21)')
    parser.add_argument('--slippage', type=float, default=0.0005, help='슬리피지 비율 (기본값: 0.05%%)')
    parser.add_argument('--fee', type=float, default=0.0004, help='수수료율 (기본값: 0.04%%)')
    args = parser.parse_args()

    run_altcoin_backtest(
        days=args.days,
        initial_capital=args.capital,
        btc_sma_len=args.btc_sma,
        trend_sma=args.trend_sma,
        stop_loss=args.stop_loss,
        momentum_window=args.momentum_window,
        slippage=args.slippage,
        fee_rate=args.fee
    )
