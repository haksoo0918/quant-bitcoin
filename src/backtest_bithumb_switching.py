# -*- coding: utf-8 -*-
"""
빗썸 서브 전략: BTC vs ETH 상대 모멘텀 100% 스위칭 듀얼 모멘텀 백테스터 (BTC-ETH Dual Momentum Switching)
- 절대 모멘텀: BTC 220일 SMA(±2%) & ETH 50일 SMA(±1.5*ATR) 추세 필터
- 상대 모멘텀: 최근 N일(기본 30일) 수익률이 더 높은 1등 대장 코인에 100% 집중 투자
- 방어: 둘 다 하락 추세(Bear)일 경우 100% 현금화(KRW)
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

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backtest", "sub_switching")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_kst_now():
    utc_now = datetime.timezone.utc
    return datetime.datetime.now(utc_now) + datetime.timedelta(hours=9)


def fetch_and_cache_candles(market, days_needed=1600):
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
            time.sleep(0.05)
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


def run_bithumb_switching_backtest(days=1500, initial_capital=10000000.0, momentum_window=30,
                                   btc_sma_len=220, btc_buffer=0.02,
                                   eth_sma_len=50, eth_atr_len=14, eth_atr_mult=1.5,
                                   fee_rate=0.0004, slippage=0.0005):
    print(f"\n{'='*70}")
    print(f"📊 [빗썸 서브 전략] BTC vs ETH 상대 모멘텀 100% 스위칭 백테스트 시작")
    print(f"• 분석 기간: 최근 {days}일 | 초기 자본: {initial_capital:,.0f} 원")
    print(f"• 상대 모멘텀 비교 기간: 최근 {momentum_window}일 수익률 우위 1등 코인에 100% 집중")
    print(f"• 절대 시장 필터: BTC {btc_sma_len}일 SMA (±{btc_buffer*100:.1f}%) | ETH {eth_sma_len}일 SMA (±{eth_atr_mult:.1f}*ATR)")
    print(f"• 수수료/슬리피지: 거래당 수수료 {fee_rate*100:.2f}% + 슬리피지 {slippage*100:.2f}%")
    print(f"{'='*70}\n")

    # 1. BTC & ETH 일봉 데이터 수집
    print("▶ 1. BTC & ETH 과거 일봉 데이터 수집 중...")
    btc_df = fetch_and_cache_candles("KRW-BTC", days_needed=days + btc_sma_len + 50)
    eth_df = fetch_and_cache_candles("KRW-ETH", days_needed=days + btc_sma_len + 50)

    if btc_df is None or eth_df is None:
        raise ValueError("BTC 또는 ETH 데이터를 수집할 수 없습니다.")

    # 2. 지표 연산
    btc_df['date'] = pd.to_datetime(btc_df['date'])
    btc_df['btc_sma'] = btc_df['close'].rolling(window=btc_sma_len).mean()
    btc_df['btc_upper'] = btc_df['btc_sma'] * (1 + btc_buffer)
    btc_df['btc_lower'] = btc_df['btc_sma'] * (1 - btc_buffer)
    btc_df['btc_mom'] = btc_df['close'].pct_change(periods=momentum_window)
    btc_df = btc_df.set_index('date')

    eth_df['date'] = pd.to_datetime(eth_df['date'])
    eth_df['eth_sma'] = eth_df['close'].rolling(window=eth_sma_len).mean()
    
    prev_c = eth_df['close'].shift(1)
    tr1 = eth_df['high'] - eth_df['low']
    tr2 = (eth_df['high'] - prev_c).abs()
    tr3 = (eth_df['low'] - prev_c).abs()
    eth_df['tr'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    eth_df['eth_atr'] = eth_df['tr'].rolling(window=eth_atr_len).mean()
    eth_df['eth_upper'] = eth_df['eth_sma'] + (eth_df['eth_atr'] * eth_atr_mult)
    eth_df['eth_lower'] = eth_df['eth_sma'] - (eth_df['eth_atr'] * eth_atr_mult)
    eth_df['eth_mom'] = eth_df['close'].pct_change(periods=momentum_window)
    eth_df = eth_df.set_index('date')

    # 공통 날짜 추출
    common_dates = btc_df.index.intersection(eth_df.index)
    test_dates = common_dates[-days:]

    # 3. 시뮬레이션 상태 초기화
    cash = float(initial_capital)
    current_holding = None # 'BTC' | 'ETH' | None
    holding_qty = 0.0
    buy_price = 0.0

    btc_filter_state = "Bear"
    eth_filter_state = "Bear"

    equity_history = []
    trade_logs = []

    # 초기 히스테리시스 탐색
    first_idx = common_dates.get_loc(test_dates[0])
    for idx in range(first_idx - 1, -1, -1):
        dt = common_dates[idx]
        b_c = btc_df.loc[dt, 'close']
        if b_c >= btc_df.loc[dt, 'btc_upper']:
            btc_filter_state = "Bull"
            break
        elif b_c < btc_df.loc[dt, 'btc_lower']:
            btc_filter_state = "Bear"
            break

    for idx in range(first_idx - 1, -1, -1):
        dt = common_dates[idx]
        e_c = eth_df.loc[dt, 'close']
        if e_c >= eth_df.loc[dt, 'eth_upper']:
            eth_filter_state = "Bull"
            break
        elif e_c < eth_df.loc[dt, 'eth_lower']:
            eth_filter_state = "Bear"
            break

    print(f"▶ 2. 일별 시뮬레이션 구동 (총 {len(test_dates)}일간, 약 {len(test_dates)/365.25:.1f}년)...")

    for current_date in test_dates:
        btc_row = btc_df.loc[current_date]
        eth_row = eth_df.loc[current_date]

        btc_p = btc_row['close']
        eth_p = eth_row['close']

        # A. 개별 절대 모멘텀(시장 필터) 갱신
        if btc_p >= btc_row['btc_upper']:
            btc_filter_state = "Bull"
        elif btc_p < btc_row['btc_lower']:
            btc_filter_state = "Bear"

        if eth_p >= eth_row['eth_upper']:
            eth_filter_state = "Bull"
        elif eth_p < eth_row['eth_lower']:
            eth_filter_state = "Bear"

        # B. 상대 모멘텀 판정 (어느 쪽이 1등 대장인가?)
        btc_mom = btc_row['btc_mom']
        eth_mom = eth_row['eth_mom']

        target_coin = None
        if btc_filter_state == "Bull" and eth_filter_state == "Bull":
            # 둘 다 상승장이면 모멘텀이 더 큰 1등 선택
            target_coin = 'BTC' if btc_mom >= eth_mom else 'ETH'
        elif btc_filter_state == "Bull":
            target_coin = 'BTC'
        elif eth_filter_state == "Bull":
            target_coin = 'ETH'
        else:
            target_coin = None # 둘 다 하락장 ➔ 100% 현금

        # C. 리밸런싱 / 스위칭 집행
        # 1) 보유 코인이 목표 코인과 다른 경우 ➔ 기존 코인 전량 매도
        if current_holding is not None and current_holding != target_coin:
            curr_sell_price = (btc_p if current_holding == 'BTC' else eth_p) * (1 - slippage)
            sell_amount = holding_qty * curr_sell_price
            fee = sell_amount * fee_rate
            net_sell = sell_amount - fee
            cash += net_sell
            ret = (curr_sell_price - buy_price) / buy_price

            reason = "하락장 현금화" if target_coin is None else f"1등 대장 스위칭 ({current_holding} ➔ {target_coin})"
            trade_logs.append({
                'date': current_date.strftime('%Y-%m-%d'),
                'type': f"매도({reason})",
                'symbol': current_holding,
                'price': curr_sell_price,
                'amount': sell_amount,
                'fee': fee,
                'return': ret
            })
            current_holding = None
            holding_qty = 0.0

        # 2) 신규 코인 100% 집중 매수
        if target_coin is not None and current_holding is None and cash >= 5000:
            curr_buy_price = (btc_p if target_coin == 'BTC' else eth_p) * (1 + slippage)
            fee = cash * fee_rate
            net_buy = cash - fee
            holding_qty = net_buy / curr_buy_price
            buy_price = curr_buy_price
            current_holding = target_coin
            
            trade_logs.append({
                'date': current_date.strftime('%Y-%m-%d'),
                'type': f"매수({target_coin} 100% 집중 탑승)",
                'symbol': target_coin,
                'price': curr_buy_price,
                'amount': cash,
                'fee': fee,
                'return': 0.0
            })
            cash = 0.0

        # D. 일별 총 자산 평가
        valuation = cash
        if current_holding == 'BTC':
            valuation += holding_qty * btc_p
        elif current_holding == 'ETH':
            valuation += holding_qty * eth_p

        equity_history.append({
            'date': current_date,
            'equity': valuation,
            'holding': current_holding if current_holding else 'CASH',
            'btc_price': btc_p,
            'eth_price': eth_p,
            'btc_mom': btc_mom,
            'eth_mom': eth_mom
        })

    # 4. 성과 지표 산출
    res_df = pd.DataFrame(equity_history)
    res_df['cum_return'] = (res_df['equity'] / initial_capital) - 1.0
    res_df['peak'] = res_df['equity'].cummax()
    res_df['drawdown'] = (res_df['equity'] - res_df['peak']) / res_df['peak']

    # BTC & ETH 벤치마크
    btc_start_price = res_df['btc_price'].iloc[0]
    res_df['btc_cum_return'] = (res_df['btc_price'] / btc_start_price) - 1.0
    res_df['btc_peak'] = res_df['btc_price'].cummax()
    res_df['btc_drawdown'] = (res_df['btc_price'] - res_df['btc_peak']) / res_df['btc_peak']

    eth_start_price = res_df['eth_price'].iloc[0]
    res_df['eth_cum_return'] = (res_df['eth_price'] / eth_start_price) - 1.0
    res_df['eth_peak'] = res_df['eth_price'].cummax()
    res_df['eth_drawdown'] = (res_df['eth_price'] - res_df['eth_peak']) / res_df['eth_peak']

    total_days = (test_dates[-1] - test_dates[0]).days
    total_return = res_df['cum_return'].iloc[-1]
    cagr = ((1 + total_return) ** (365.25 / total_days)) - 1.0 if total_days > 0 else 0
    mdd = res_df['drawdown'].min()

    btc_total_return = res_df['btc_cum_return'].iloc[-1]
    btc_cagr = ((1 + btc_total_return) ** (365.25 / total_days)) - 1.0 if total_days > 0 else 0
    btc_mdd = res_df['btc_drawdown'].min()

    eth_total_return = res_df['eth_cum_return'].iloc[-1]
    eth_cagr = ((1 + eth_total_return) ** (365.25 / total_days)) - 1.0 if total_days > 0 else 0
    eth_mdd = res_df['eth_drawdown'].min()

    sell_trades = [t for t in trade_logs if '매도' in t['type']]
    win_trades = [t for t in sell_trades if t['return'] > 0]
    win_rate = (len(win_trades) / len(sell_trades) * 100) if sell_trades else 0

    metrics = {
        'strategy_name': f"BTC vs ETH 상대 모멘텀({momentum_window}일) 100% 스위칭",
        'total_days': total_days,
        'initial_capital': initial_capital,
        'final_equity': res_df['equity'].iloc[-1],
        'total_return': total_return * 100,
        'cagr': cagr * 100,
        'mdd': mdd * 100,
        'btc_total_return': btc_total_return * 100,
        'btc_cagr': btc_cagr * 100,
        'btc_mdd': btc_mdd * 100,
        'eth_total_return': eth_total_return * 100,
        'eth_cagr': eth_cagr * 100,
        'eth_mdd': eth_mdd * 100,
        'total_trades': len(trade_logs),
        'sell_trades': len(sell_trades),
        'win_trades': len(win_trades),
        'win_rate': win_rate,
        'momentum_window': momentum_window
    }

    # 콘솔 출력
    print("\n" + "="*70)
    print("🎯 [빗썸 서브 전략: BTC vs ETH 상대 모멘텀 100% 스위칭 백테스트 결과]")
    print("="*70)
    print(f"• 테스트 기간: {test_dates[0].strftime('%Y-%m-%d')} ~ {test_dates[-1].strftime('%Y-%m-%d')} ({total_days}일, 약 {total_days/365.25:.1f}년)")
    print(f"• 상대 모멘텀: 최근 {momentum_window}일 수익률 1위 코인 100% 집중 스위칭")
    print(f"• 초기 자본: {initial_capital:,.0f} 원 ➔ 최종 자산: {metrics['final_equity']:,.0f} 원")
    print(f"• 전략 누적 수익률: {metrics['total_return']:+.2f}% (CAGR: {metrics['cagr']:+.2f}%) 🚀")
    print(f"• 벤치마크 (BTC 단순보유): {metrics['btc_total_return']:+.2f}% (CAGR: {metrics['btc_cagr']:+.2f}%)")
    print(f"• 벤치마크 (ETH 단순보유): {metrics['eth_total_return']:+.2f}% (CAGR: {metrics['eth_cagr']:+.2f}%)")
    print(f"• 전략 최대 낙폭 (MDD): {metrics['mdd']:.2f}% (BTC MDD: {metrics['btc_mdd']:.2f}%, ETH MDD: {metrics['eth_mdd']:.2f}%)")
    print(f"• 총 매매 횟수: {len(trade_logs)}회 (매도 완료 {len(sell_trades)}회, 승률 {win_rate:.1f}%)")
    print("="*70)

    # 5. 차트 생성
    timestamp_str = get_kst_now().strftime("%Y%m%d_%H%M%S")
    plot_filename = f"backtest_bithumb_switching_result_{timestamp_str}.png"
    plot_path = os.path.join(OUTPUT_DIR, plot_filename)

    plt.rcParams['font.family'] = 'DejaVu Sans'
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True, gridspec_kw={'height_ratios': [2.5, 1]})

    ax1.plot(res_df['date'], (res_df['equity'] / initial_capital) * 100, label=f"BTC/ETH Switching (CAGR {metrics['cagr']:+.1f}%)", color='#d97706', linewidth=2.2)
    ax1.plot(res_df['date'], (res_df['btc_price'] / res_df['btc_price'].iloc[0]) * 100, label=f"BTC Buy & Hold (CAGR {metrics['btc_cagr']:+.1f}%)", color='#94a3b8', linestyle='--', linewidth=1.2)
    ax1.plot(res_df['date'], (res_df['eth_price'] / res_df['eth_price'].iloc[0]) * 100, label=f"ETH Buy & Hold (CAGR {metrics['eth_cagr']:+.1f}%)", color='#cbd5e1', linestyle=':', linewidth=1.0)
    ax1.axhline(100, color='gray', linestyle=':', alpha=0.6)
    ax1.set_title(f"Bithumb Sub Strategy: BTC vs ETH Momentum Switching vs Buy & Hold", fontsize=14, fontweight='bold', pad=12)
    ax1.set_ylabel("Normalized Equity (Base = 100)", fontsize=11)
    ax1.grid(True, linestyle='--', alpha=0.4)
    ax1.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.9)

    ax2.plot(res_df['date'], res_df['drawdown'] * 100, label=f"Strategy Drawdown (MDD {metrics['mdd']:.1f}%)", color='#dc2626', linewidth=1.5)
    ax2.plot(res_df['date'], res_df['btc_drawdown'] * 100, label=f"BTC Drawdown (MDD {metrics['btc_mdd']:.1f}%)", color='#94a3b8', linestyle='--', linewidth=1.0)
    ax2.fill_between(res_df['date'], res_df['drawdown'] * 100, 0, color='#dc2626', alpha=0.15)
    ax2.set_ylabel("Drawdown (%)", fontsize=11)
    ax2.set_xlabel("Date", fontsize=11)
    ax2.grid(True, linestyle='--', alpha=0.4)
    ax2.legend(loc='lower left', frameon=True, facecolor='white', framealpha=0.9)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

    plt.tight_layout()
    plt.savefig(plot_path, dpi=300)
    plt.close()

    # 6. 마크다운 보고서 생성
    report_filename = f"backtest_bithumb_switching_report_{timestamp_str}.md"
    report_path = os.path.join(OUTPUT_DIR, report_filename)

    report = []
    report.append(f"# 📊 [빗썸 서브 전략] BTC vs ETH 상대 모멘텀 스위칭 백테스트 성과 보고서\n")
    report.append(f"- **실행 일시**: {get_kst_now().strftime('%Y-%m-%d %H:%M:%S KST')}")
    report.append(f"- **분석 기간**: {test_dates[0].strftime('%Y-%m-%d')} ~ {test_dates[-1].strftime('%Y-%m-%d')} (총 {metrics['total_days']} 일, 약 {metrics['total_days']/365.25:.1f} 년)")
    report.append(f"- **적용 파라미터**: 모멘텀 비교 기간 **{momentum_window}일**, BTC **220일 SMA(±2%)**, ETH **50일 SMA(±1.5*ATR)**")
    report.append(f"- **시작 자산**: {metrics['initial_capital']:,.0f} 원 ➔ **최종 자산**: {metrics['final_equity']:,.0f} 원\n")
    report.append(f"---\n")

    report.append(f"## 1. 종합 성과 지표 비교\n")
    report.append(f"| 평가 지표 | BTC/ETH 모멘텀 스위칭 전략 | BTC 단순 보유 | ETH 단순 보유 | 초과 성과 (vs BTC) |")
    report.append(f"| :--- | :---: | :---: | :---: | :---: |")
    report.append(f"| **누적 수익률** | **{metrics['total_return']:+.2f}%** | {metrics['btc_total_return']:+.2f}% | {metrics['eth_total_return']:+.2f}% | **{metrics['total_return'] - metrics['btc_total_return']:+.2f}%p** |")
    report.append(f"| **연평균 성장률 (CAGR)** | **{metrics['cagr']:.2f}%** | {metrics['btc_cagr']:.2f}% | {metrics['eth_cagr']:.2f}% | **{metrics['cagr'] - metrics['btc_cagr']:+.2f}%p** |")
    report.append(f"| **최대 낙폭 (MDD)** | **{metrics['mdd']:.2f}%** | {metrics['btc_mdd']:.2f}% | {metrics['eth_mdd']:.2f}% | **{metrics['btc_mdd'] - metrics['mdd']:+.2f}%p** (방어) |")
    report.append(f"| **총 거래 횟수** | **{metrics['total_trades']} 회** (매도 {metrics['sell_trades']} 회) | - | - | - |")
    report.append(f"| **청산 승률 (Win Rate)** | **{metrics['win_rate']:.1f}%** | - | - | - |\n")

    outperformance = metrics['total_return'] - metrics['btc_total_return']
    report.append(f"> 💡 **주요 성과 요약**: 최근 {momentum_window}일 상대 모멘텀이 더 강한 1등 대장 코인(BTC 또는 ETH)에 100% 집중 투자하고 하락장 시 현금화함으로써, 비트코인 단순 보유 대비 **{outperformance:+.2f}%p** 의 압도적인 초과 수익과 **{metrics['mdd']:.2f}%** 의 안정적인 최대 낙폭(MDD)을 달성하였습니다.\n")

    report.append(f"## 2. 자산 가치 변동 추이 차트\n")
    report.append(f"![Equity Curve]({plot_filename})\n")

    report.append(f"## 3. 주요 매매 거래 내역 요약 (최근 20건 / 총 {len(trade_logs)}건)\n")
    if trade_logs:
        report.append(f"| 거래 일자 | 거래 구분 | 종목명 | 체결 가격 | 거래 금액 | 실현 손익률 |")
        report.append(f"| :---: | :---: | :---: | :---: | :---: | :---: |")
        for log in trade_logs[-20:]:
            ret_str = f"{log['return']*100:+.2f}%" if '매도' in log['type'] else "-"
            report.append(f"| {log['date']} | {log['type']} | {log['symbol']} | {log['price']:,.1f} 원 | {log['amount']:,.0f} 원 | {ret_str} |")

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(report))

    print(f"✓ 자산 곡선 차트 저장 완료: {plot_path}")
    print(f"✓ 상세 백테스트 보고서 저장 완료: {report_path}\n")

    return metrics, report_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="빗썸 서브 전략: BTC vs ETH 상대 모멘텀 100% 스위칭 백테스터")
    parser.add_argument('--days', type=int, default=1500, help='백테스트 분석 일수 (기본값: 1500일)')
    parser.add_argument('--capital', type=float, default=10000000.0, help='시작 원금 (기본값: 10,000,000 원)')
    parser.add_argument('--momentum-window', type=int, default=30, help='상대 모멘텀 비교 기간 일수 (기본값: 30)')
    parser.add_argument('--btc-sma', type=int, default=220, help='BTC 시장 필터 SMA 기간 (기본값: 220)')
    parser.add_argument('--eth-sma', type=int, default=50, help='ETH 시장 필터 SMA 기간 (기본값: 50)')
    parser.add_argument('--slippage', type=float, default=0.0005, help='슬리피지 비율 (기본값: 0.05%%)')
    parser.add_argument('--fee', type=float, default=0.0004, help='수수료율 (기본값: 0.04%%)')
    args = parser.parse_args()

    run_bithumb_switching_backtest(
        days=args.days,
        initial_capital=args.capital,
        momentum_window=args.momentum_window,
        btc_sma_len=args.btc_sma,
        eth_sma_len=args.eth_sma,
        slippage=args.slippage,
        fee_rate=args.fee
    )
