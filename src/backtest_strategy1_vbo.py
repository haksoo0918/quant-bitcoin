# -*- coding: utf-8 -*-
"""
후보 전략 1: 래리 윌리엄스 변동성 돌파 전략 백테스터 (Volatility Breakout Strategy 1)
- 진입: 당일 시가 + (전일 고가 - 전일 저가) * K 돌파 시 매수
- 청산: 익일 09:00 시가(또는 종가) 무조건 전량 매도 (24시간 단기 보유)
- 필터: 비트코인 220일 SMA ±2% 공통 시장 필터 (상승장일 때만 매수)
- 자산 배분: 돌파 발생 종목 중 거래대금 상위 N개에 균등 분할 매수
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

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backtest")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 주요 유동성 검증 알트코인 유니버스
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


def run_strategy1_vbo_backtest(days=1000, initial_capital=10000000.0, k=0.5, btc_sma_len=220,
                                buffer_rate=0.02, max_coins=4, fee_rate=0.0004, slippage=0.0005):
    print(f"\n{'='*70}")
    print(f"📊 [후보 전략 1] 래리 윌리엄스 변동성 돌파 전략 백테스트 시작")
    print(f"• 분석 기간: 최근 {days}일 | 초기 자본: {initial_capital:,.0f} 원")
    print(f"• 변동성 돌파 계수 (K): {k:.2f} (진입가 = 시가 + 전일변동폭 * {k:.2f})")
    print(f"• 동시 보유 최대 종목 수: {max_coins}개 (각 {100/max_coins:.1f}% 균등 분할)")
    print(f"• 공통 시장 필터: 업비트 BTC {btc_sma_len}일 SMA (±{buffer_rate*100:.1f}% 노이즈 버퍼)")
    print(f"• 수수료/슬리피지: 거래당 수수료 {fee_rate*100:.2f}% + 슬리피지 {slippage*100:.2f}%")
    print(f"{'='*70}\n")

    # 1. BTC 데이터 수집
    print("▶ 1. BTC 시장 필터 일봉 데이터 수집...")
    btc_df = fetch_and_cache_candles("KRW-BTC", days_needed=days + btc_sma_len + 50)
    if btc_df is None:
        raise ValueError("BTC 데이터를 수집할 수 없습니다.")

    # 2. 알트코인 유니버스 데이터 수집
    print(f"▶ 2. 알트코인 유니버스 ({len(DEFAULT_ALTCOIN_UNIVERSE)}개 종목) 일봉 로드...")
    alt_dfs = {}
    for sym in DEFAULT_ALTCOIN_UNIVERSE:
        df = fetch_and_cache_candles(sym, days_needed=days + 50)
        if df is not None and len(df) >= 100:
            df['prev_range'] = (df['high'].shift(1) - df['low'].shift(1))
            df['target_price'] = df['open'] + df['prev_range'] * k
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
            alt_dfs[sym] = df

    # 3. 날짜 동기화 및 캘린더 생성
    btc_df['date'] = pd.to_datetime(btc_df['date'])
    btc_df['btc_sma'] = btc_df['close'].rolling(window=btc_sma_len).mean()
    btc_df['btc_upper'] = btc_df['btc_sma'] * (1 + buffer_rate)
    btc_df['btc_lower'] = btc_df['btc_sma'] * (1 - buffer_rate)
    btc_df = btc_df.set_index('date')

    test_dates = btc_df.index[-days:]

    # 4. 시뮬레이션 변수 초기화
    cash = float(initial_capital)
    equity_history = []
    trade_logs = []
    market_filter_state = "Bear"

    first_idx = btc_df.index.get_loc(test_dates[0])
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

    print(f"▶ 3. 일별 시뮬레이션 구동 (총 {len(test_dates)}일간)...")

    for current_date in test_dates:
        # A. 시장 필터 업데이트
        btc_row = btc_df.loc[current_date]
        btc_price = btc_row['close']
        if btc_price >= btc_row['btc_upper']:
            market_filter_state = "Bull"
        elif btc_price < btc_row['btc_lower']:
            market_filter_state = "Bear"

        daily_profit = 0.0
        active_trades_today = []

        # B. 상승장(Bull) 시 당일 돌파 종목 탐색
        if market_filter_state == "Bull":
            breakout_candidates = []
            for sym, df_coin in alt_dfs.items():
                if current_date in df_coin.index:
                    row = df_coin.loc[current_date]
                    target = row['target_price']
                    high = row['high']
                    open_p = row['open']
                    close_p = row['close']
                    val = row['value']

                    # 당일 고가가 목표가를 돌파한 경우 (시가가 이미 목표가 위에서 시작한 갭상승 제외)
                    if not pd.isna(target) and target > open_p and high >= target:
                        breakout_candidates.append({
                            'symbol': sym,
                            'target_price': target,
                            'close_price': close_p,
                            'value': val
                        })

            if breakout_candidates:
                # 당일 거래대금 상위 N개 선정
                breakout_candidates.sort(key=lambda x: x['value'], reverse=True)
                selected = breakout_candidates[:max_coins]
                target_alloc = cash / max_coins

                for item in selected:
                    buy_price = item['target_price'] * (1 + slippage)
                    sell_price = item['close_price'] * (1 - slippage)

                    alloc = target_alloc
                    buy_fee = alloc * fee_rate
                    net_buy = alloc - buy_fee
                    qty = net_buy / buy_price

                    sell_amount = qty * sell_price
                    sell_fee = sell_amount * fee_rate
                    net_sell = sell_amount - sell_fee

                    pnl = net_sell - alloc
                    ret = (sell_price - buy_price) / buy_price

                    daily_profit += pnl
                    trade_logs.append({
                        'date': current_date.strftime('%Y-%m-%d'),
                        'symbol': item['symbol'],
                        'buy_price': buy_price,
                        'sell_price': sell_price,
                        'amount': alloc,
                        'pnl': pnl,
                        'return': ret
                    })

        cash += daily_profit

        equity_history.append({
            'date': current_date,
            'equity': cash,
            'btc_price': btc_price,
            'market_filter': market_filter_state
        })

    # 5. 성과 지표 산출
    res_df = pd.DataFrame(equity_history)
    res_df['cum_return'] = (res_df['equity'] / initial_capital) - 1.0
    res_df['peak'] = res_df['equity'].cummax()
    res_df['drawdown'] = (res_df['equity'] - res_df['peak']) / res_df['peak']

    btc_start_price = res_df['btc_price'].iloc[0]
    res_df['btc_cum_return'] = (res_df['btc_price'] / btc_start_price) - 1.0
    res_df['btc_peak'] = res_df['btc_price'].cummax()
    res_df['btc_drawdown'] = (res_df['btc_price'] - res_df['btc_peak']) / res_df['btc_peak']

    total_days = (test_dates[-1] - test_dates[0]).days
    total_return = res_df['cum_return'].iloc[-1]
    cagr = ((1 + total_return) ** (365.25 / total_days)) - 1.0 if total_days > 0 else 0
    mdd = res_df['drawdown'].min()

    btc_total_return = res_df['btc_cum_return'].iloc[-1]
    btc_cagr = ((1 + btc_total_return) ** (365.25 / total_days)) - 1.0 if total_days > 0 else 0
    btc_mdd = res_df['btc_drawdown'].min()

    win_trades = [t for t in trade_logs if t['pnl'] > 0]
    win_rate = (len(win_trades) / len(trade_logs) * 100) if trade_logs else 0

    metrics = {
        'strategy_name': f"래리 윌리엄스 변동성 돌파 (K={k:.2f})",
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
        'win_trades': len(win_trades),
        'win_rate': win_rate,
        'k': k
    }

    # 콘솔 출력
    print("\n" + "="*70)
    print("🎯 [후보 전략 1: 래리 윌리엄스 변동성 돌파 백테스트 결과]")
    print("="*70)
    print(f"• 테스트 기간: {test_dates[0].strftime('%Y-%m-%d')} ~ {test_dates[-1].strftime('%Y-%m-%d')} ({total_days}일, 약 {total_days/365.25:.1f}년)")
    print(f"• 적용 조건: 변동성 계수 K={k:.2f} | 동시 보유 최대 {max_coins}개 | BTC 220 SMA 시장 필터")
    print(f"• 초기 자본: {initial_capital:,.0f} 원 ➔ 최종 자산: {metrics['final_equity']:,.0f} 원")
    print(f"• 전략 누적 수익률: {metrics['total_return']:+.2f}% (CAGR: {metrics['cagr']:+.2f}%)")
    print(f"• 벤치마크(BTC 단순보유): {metrics['btc_total_return']:+.2f}% (CAGR: {metrics['btc_cagr']:+.2f}%)")
    print(f"• 초과 성과: {metrics['total_return'] - metrics['btc_total_return']:+.2f}%p")
    print(f"• 전략 최대 낙폭 (MDD): {metrics['mdd']:.2f}% (BTC MDD: {metrics['btc_mdd']:.2f}%)")
    print(f"• 총 매매 횟수: {len(trade_logs)}회 (승리 {len(win_trades)}회, 승률 {win_rate:.1f}%)")
    print("="*70)

    # 6. 차트 생성
    timestamp_str = get_kst_now().strftime("%Y%m%d_%H%M%S")
    plot_filename = f"backtest_strategy1_vbo_result_{timestamp_str}.png"
    plot_path = os.path.join(OUTPUT_DIR, plot_filename)

    plt.rcParams['font.family'] = 'DejaVu Sans'
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True, gridspec_kw={'height_ratios': [2.5, 1]})

    ax1.plot(res_df['date'], (res_df['equity'] / initial_capital) * 100, label=f"Volatility Breakout (K={k}) (CAGR {metrics['cagr']:+.1f}%)", color='#16a34a', linewidth=2.0)
    ax1.plot(res_df['date'], (res_df['btc_price'] / res_df['btc_price'].iloc[0]) * 100, label=f"BTC Buy & Hold (CAGR {metrics['btc_cagr']:+.1f}%)", color='#94a3b8', linestyle='--', linewidth=1.5)
    ax1.axhline(100, color='gray', linestyle=':', alpha=0.6)
    ax1.set_title(f"Strategy 1: Volatility Breakout (K={k}) vs BTC Buy & Hold", fontsize=14, fontweight='bold', pad=12)
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

    # 7. 마크다운 보고서 생성
    report_filename = f"backtest_strategy1_vbo_report_{timestamp_str}.md"
    report_path = os.path.join(OUTPUT_DIR, report_filename)

    report = []
    report.append(f"# 📊 [후보 전략 1] 래리 윌리엄스 변동성 돌파 백테스트 성과 보고서\n")
    report.append(f"- **실행 일시**: {get_kst_now().strftime('%Y-%m-%d %H:%M:%S KST')}")
    report.append(f"- **분석 기간**: {test_dates[0].strftime('%Y-%m-%d')} ~ {test_dates[-1].strftime('%Y-%m-%d')} (총 {metrics['total_days']} 일, 약 {metrics['total_days']/365.25:.1f} 년)")
    report.append(f"- **적용 파라미터**: 변동성 돌파 계수 **K={k:.2f}**, 최대 분할 **{max_coins}개 종목**, BTC **220일 SMA** 공통 시장 필터")
    report.append(f"- **시작 자산**: {metrics['initial_capital']:,.0f} 원 ➔ **최종 자산**: {metrics['final_equity']:,.0f} 원\n")
    report.append(f"---\n")

    report.append(f"## 1. 종합 성과 지표 비교\n")
    report.append(f"| 평가 지표 | 변동성 돌파 전략 (K={k:.2f}) | BTC 단순 보유 (Buy & Hold) | 초과 성과 |")
    report.append(f"| :--- | :---: | :---: | :---: |")
    report.append(f"| **누적 수익률** | **{metrics['total_return']:+.2f}%** | {metrics['btc_total_return']:+.2f}% | **{metrics['total_return'] - metrics['btc_total_return']:+.2f}%p** |")
    report.append(f"| **연평균 성장률 (CAGR)** | **{metrics['cagr']:.2f}%** | {metrics['btc_cagr']:.2f}% | **{metrics['cagr'] - metrics['btc_cagr']:+.2f}%p** |")
    report.append(f"| **최대 낙폭 (MDD)** | **{metrics['mdd']:.2f}%** | {metrics['btc_mdd']:.2f}% | **{metrics['btc_mdd'] - metrics['mdd']:+.2f}%p** (방어) |")
    report.append(f"| **총 거래 횟수** | **{metrics['total_trades']} 회** | - | - |")
    report.append(f"| **승률 (Win Rate)** | **{metrics['win_rate']:.1f}%** | - | - |\n")

    outperformance = metrics['total_return'] - metrics['btc_total_return']
    mdd_defense = metrics['btc_mdd'] - metrics['mdd']
    report.append(f"> 💡 **주요 성과 요약**: 래리 윌리엄스 변동성 돌파 전략은 당일 폭발하는 양봉 모멘텀만 향유하고 익일 아침 100% 현금화하는 단기 청산 구조로, 최대 낙폭(MDD)을 **{metrics['mdd']:.2f}%** 수준으로 통제하였습니다.\n")

    report.append(f"## 2. 자산 가치 변동 추이 차트\n")
    report.append(f"![Equity Curve]({plot_filename})\n")

    report.append(f"## 3. 주요 매매 거래 내역 요약 (최근 20건 / 총 {len(trade_logs)}건)\n")
    if trade_logs:
        report.append(f"| 거래 일자 | 종목명 | 매수가(돌파가) | 매도가(익일시가) | 거래 금액 | 실현 손익 | 손익률 |")
        report.append(f"| :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
        for log in trade_logs[-20:]:
            report.append(f"| {log['date']} | {log['symbol'].replace('KRW-', '')} | {log['buy_price']:,.1f} 원 | {log['sell_price']:,.1f} 원 | {log['amount']:,.0f} 원 | {log['pnl']:+,.0f} 원 | {log['return']*100:+.2f}% |")

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(report))

    print(f"✓ 자산 곡선 차트 저장 완료: {plot_path}")
    print(f"✓ 상세 백테스트 보고서 저장 완료: {report_path}\n")

    return metrics, report_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="후보 전략 1: 래리 윌리엄스 변동성 돌파 전략 백테스터")
    parser.add_argument('--days', type=int, default=1000, help='백테스트 분석 일수 (기본값: 1000)')
    parser.add_argument('--capital', type=float, default=10000000.0, help='시작 원금 (기본값: 10,000,000 원)')
    parser.add_argument('--k', type=float, default=0.5, help='변동성 돌파 계수 K (기본값: 0.5)')
    parser.add_argument('--max-coins', type=int, default=4, help='동시 분할 종목 수 (기본값: 4)')
    parser.add_argument('--btc-sma', type=int, default=220, help='BTC 시장 필터 SMA 기간 (기본값: 220)')
    parser.add_argument('--slippage', type=float, default=0.0005, help='슬리피지 비율 (기본값: 0.05%%)')
    parser.add_argument('--fee', type=float, default=0.0004, help='수수료율 (기본값: 0.04%%)')
    args = parser.parse_args()

    run_strategy1_vbo_backtest(
        days=args.days,
        initial_capital=args.capital,
        k=args.k,
        max_coins=args.max_coins,
        btc_sma_len=args.btc_sma,
        slippage=args.slippage,
        fee_rate=args.fee
    )
