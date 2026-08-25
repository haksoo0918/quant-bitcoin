# -*- coding: utf-8 -*-
"""
후보 전략 2: 터틀 채널 돌파 + ATR 트레일링 스탑 백테스터 (Turtle Trend Following Strategy 2)
- 진입: 당일 종가 > 직전 20일 최고가(Donchian High) 상향 돌파 시 매수
- 청산: 진입 후 최고가(Peak Price) 대비 (ATR * K) 하락 시 트레일링 스탑 익절/손절
- 필터: 비트코인 220일 SMA ±2% 공통 시장 필터 (하락장 시 전량 현금화)
- 자산 배분: 동시 보유 최대 N개 (기본 4개, 각 25% 균등 분할)
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


def run_strategy2_turtle_backtest(days=1000, initial_capital=10000000.0, channel_len=20, atr_len=14,
                                   atr_multiplier=2.0, btc_sma_len=220, buffer_rate=0.02,
                                   max_coins=4, fee_rate=0.0004, slippage=0.0005):
    print(f"\n{'='*70}")
    print(f"📊 [후보 전략 2] 터틀 채널 돌파 + ATR 트레일링 스탑 백테스트 시작")
    print(f"• 분석 기간: 최근 {days}일 | 초기 자본: {initial_capital:,.0f} 원")
    print(f"• 채널 돌파 기간: 최근 {channel_len}일 신고가 돌파 시 진입")
    print(f"• 트레일링 스탑: 최고점 대비 {atr_multiplier:.1f} * ATR({atr_len}) 하락 시 익절/손절")
    print(f"• 동시 보유 최대 종목 수: {max_coins}개 (각 {100/max_coins:.1f}% 균등 분할)")
    print(f"• 공통 시장 필터: 업비트 BTC {btc_sma_len}일 SMA (±{buffer_rate*100:.1f}% 노이즈 버퍼)")
    print(f"• 수수료/슬리피지: 거래당 수수료 {fee_rate*100:.2f}% + 슬리피지 {slippage*100:.2f}%")
    print(f"{'='*70}\n")

    # 1. BTC 데이터 수집
    print("▶ 1. BTC 시장 필터 일봉 데이터 수집...")
    btc_df = fetch_and_cache_candles("KRW-BTC", days_needed=days + btc_sma_len + 50)
    if btc_df is None:
        raise ValueError("BTC 데이터를 수집할 수 없습니다.")

    # 2. 알트코인 유니버스 데이터 수집 및 지표 연산
    print(f"▶ 2. 알트코인 유니버스 ({len(DEFAULT_ALTCOIN_UNIVERSE)}개 종목) 일봉 및 채널/ATR 연산...")
    alt_dfs = {}
    for sym in DEFAULT_ALTCOIN_UNIVERSE:
        df = fetch_and_cache_candles(sym, days_needed=days + max(channel_len, atr_len) + 50)
        if df is not None and len(df) >= 100:
            df['prev_high_channel'] = df['high'].shift(1).rolling(window=channel_len).max()
            
            # ATR 연산
            prev_c = df['close'].shift(1)
            tr1 = df['high'] - df['low']
            tr2 = (df['high'] - prev_c).abs()
            tr3 = (df['low'] - prev_c).abs()
            df['tr'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            df['atr'] = df['tr'].rolling(window=atr_len).mean()

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
    holdings = {} # { 'KRW-XRP': { 'qty': float, 'buy_price': float, 'peak_price': float, 'buy_date': date } }
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

    trailing_stop_count = 0

    for current_date in test_dates:
        btc_row = btc_df.loc[current_date]
        btc_price = btc_row['close']
        if btc_price >= btc_row['btc_upper']:
            market_filter_state = "Bull"
        elif btc_price < btc_row['btc_lower']:
            market_filter_state = "Bear"

        # A. 보유 포지션 최고가(Peak Price) 갱신 및 ATR 트레일링 스탑 체크
        for sym, pos in list(holdings.items()):
            df_coin = alt_dfs.get(sym)
            if df_coin is not None and current_date in df_coin.index:
                row = df_coin.loc[current_date]
                curr_high = row['high']
                curr_close = row['close']
                atr_val = row['atr']

                # 최고가 갱신
                if curr_high > pos['peak_price']:
                    pos['peak_price'] = curr_high

                # 트레일링 스탑 기준 가격: 최고점 - (ATR * multiplier)
                stop_price = pos['peak_price'] - (atr_val * atr_multiplier)

                # 하락장(Bear) 전환이거나 트레일링 스탑 터치 시 매도
                if market_filter_state == "Bear" or (curr_close <= stop_price):
                    sell_price = curr_close * (1 - slippage)
                    sell_val = pos['qty'] * sell_price
                    fee = sell_val * fee_rate
                    net_val = sell_val - fee
                    cash += net_val
                    ret = (sell_price - pos['buy_price']) / pos['buy_price']
                    
                    exit_reason = '매도(하락장 청산)' if market_filter_state == "Bear" else f'매도(ATR 트레일링 스탑 - 최고점 {pos["peak_price"]:,.0f}원 대비 하락)'
                    trade_logs.append({
                        'date': current_date.strftime('%Y-%m-%d'),
                        'type': exit_reason,
                        'symbol': sym,
                        'price': sell_price,
                        'qty': pos['qty'],
                        'amount': sell_val,
                        'fee': fee,
                        'return': ret
                    })
                    del holdings[sym]
                    if market_filter_state == "Bull":
                        trailing_stop_count += 1

        # B. 상승장(Bull) 시 신규 20일 신고가 돌파 종목 탐색 및 진입
        if market_filter_state == "Bull" and len(holdings) < max_coins:
            open_slots = max_coins - len(holdings)
            breakout_candidates = []

            for sym, df_coin in alt_dfs.items():
                if sym not in holdings and current_date in df_coin.index:
                    row = df_coin.loc[current_date]
                    curr_close = row['close']
                    channel_high = row['prev_high_channel']
                    val = row['value']

                    if not pd.isna(channel_high) and curr_close > channel_high:
                        breakout_candidates.append({
                            'symbol': sym,
                            'close': curr_close,
                            'value': val
                        })

            if breakout_candidates:
                breakout_candidates.sort(key=lambda x: x['value'], reverse=True)
                selected = breakout_candidates[:open_slots]

                current_total_equity = cash
                for s, p in holdings.items():
                    df_c = alt_dfs.get(s)
                    if df_c is not None and current_date in df_c.index:
                        current_total_equity += p['qty'] * df_c.loc[current_date, 'close']

                target_per_coin = current_total_equity / max_coins

                for item in selected:
                    buy_price = item['close'] * (1 + slippage)
                    order_amt = min(cash, target_per_coin)

                    if order_amt >= 5000:
                        fee = order_amt * fee_rate
                        net_amt = order_amt - fee
                        qty = net_amt / buy_price
                        cash -= order_amt
                        holdings[item['symbol']] = {
                            'qty': qty,
                            'buy_price': buy_price,
                            'peak_price': buy_price,
                            'buy_date': current_date
                        }
                        trade_logs.append({
                            'date': current_date.strftime('%Y-%m-%d'),
                            'type': '매수(20일 신고가 돌파 진입)',
                            'symbol': item['symbol'],
                            'price': buy_price,
                            'qty': qty,
                            'amount': order_amt,
                            'fee': fee,
                            'return': 0.0
                        })

        # C. 일별 총 자산 평가액 기록
        coin_valuation = 0.0
        for sym, pos in holdings.items():
            df_coin = alt_dfs.get(sym)
            if df_coin is not None and current_date in df_coin.index:
                coin_valuation += pos['qty'] * df_coin.loc[current_date, 'close']

        total_equity = cash + coin_valuation
        equity_history.append({
            'date': current_date,
            'equity': total_equity,
            'cash': cash,
            'holdings_count': len(holdings),
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

    sell_trades = [t for t in trade_logs if '매도' in t['type']]
    win_trades = [t for t in sell_trades if t['return'] > 0]
    win_rate = (len(win_trades) / len(sell_trades) * 100) if sell_trades else 0

    metrics = {
        'strategy_name': f"터틀 채널 돌파 + ATR({atr_multiplier}x) 트레일링 스탑",
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
        'trailing_stop_count': trailing_stop_count,
        'channel_len': channel_len,
        'atr_multiplier': atr_multiplier
    }

    # 콘솔 출력
    print("\n" + "="*70)
    print("🎯 [후보 전략 2: 터틀 채널 돌파 + ATR 트레일링 스탑 백테스트 결과]")
    print("="*70)
    print(f"• 테스트 기간: {test_dates[0].strftime('%Y-%m-%d')} ~ {test_dates[-1].strftime('%Y-%m-%d')} ({total_days}일, 약 {total_days/365.25:.1f}년)")
    print(f"• 적용 조건: {channel_len}일 신고가 돌파 | 최고점 대비 -{atr_multiplier:.1f}*ATR({atr_len}) 트레일링 스탑 (발생: {trailing_stop_count}회)")
    print(f"• 초기 자본: {initial_capital:,.0f} 원 ➔ 최종 자산: {metrics['final_equity']:,.0f} 원")
    print(f"• 전략 누적 수익률: {metrics['total_return']:+.2f}% (CAGR: {metrics['cagr']:+.2f}%)")
    print(f"• 벤치마크(BTC 단순보유): {metrics['btc_total_return']:+.2f}% (CAGR: {metrics['btc_cagr']:+.2f}%)")
    print(f"• 초과 성과: {metrics['total_return'] - metrics['btc_total_return']:+.2f}%p")
    print(f"• 전략 최대 낙폭 (MDD): {metrics['mdd']:.2f}% (BTC MDD: {metrics['btc_mdd']:.2f}%)")
    print(f"• 총 매매 횟수: {len(trade_logs)}회 (매도 완료 {len(sell_trades)}회, 승률 {win_rate:.1f}%)")
    print("="*70)

    # 6. 차트 생성
    timestamp_str = get_kst_now().strftime("%Y%m%d_%H%M%S")
    plot_filename = f"backtest_strategy2_turtle_result_{timestamp_str}.png"
    plot_path = os.path.join(OUTPUT_DIR, plot_filename)

    plt.rcParams['font.family'] = 'DejaVu Sans'
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True, gridspec_kw={'height_ratios': [2.5, 1]})

    ax1.plot(res_df['date'], (res_df['equity'] / initial_capital) * 100, label=f"Turtle Trend Following (CAGR {metrics['cagr']:+.1f}%)", color='#6366f1', linewidth=2.0)
    ax1.plot(res_df['date'], (res_df['btc_price'] / res_df['btc_price'].iloc[0]) * 100, label=f"BTC Buy & Hold (CAGR {metrics['btc_cagr']:+.1f}%)", color='#94a3b8', linestyle='--', linewidth=1.5)
    ax1.axhline(100, color='gray', linestyle=':', alpha=0.6)
    ax1.set_title(f"Strategy 2: Turtle Donchian Breakout + ATR Trailing Stop vs BTC Buy & Hold", fontsize=14, fontweight='bold', pad=12)
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
    report_filename = f"backtest_strategy2_turtle_report_{timestamp_str}.md"
    report_path = os.path.join(OUTPUT_DIR, report_filename)

    report = []
    report.append(f"# 📊 [후보 전략 2] 터틀 채널 돌파 + ATR 트레일링 스탑 백테스트 성과 보고서\n")
    report.append(f"- **실행 일시**: {get_kst_now().strftime('%Y-%m-%d %H:%M:%S KST')}")
    report.append(f"- **분석 기간**: {test_dates[0].strftime('%Y-%m-%d')} ~ {test_dates[-1].strftime('%Y-%m-%d')} (총 {metrics['total_days']} 일, 약 {metrics['total_days']/365.25:.1f} 년)")
    report.append(f"- **적용 파라미터**: 채널 돌파 **{channel_len}일 신고가**, 최고점 대비 **-{atr_multiplier:.1f}*ATR({atr_len}) 트레일링 스탑**, 최대 **{max_coins}개 종목**")
    report.append(f"- **시작 자산**: {metrics['initial_capital']:,.0f} 원 ➔ **최종 자산**: {metrics['final_equity']:,.0f} 원\n")
    report.append(f"---\n")

    report.append(f"## 1. 종합 성과 지표 비교\n")
    report.append(f"| 평가 지표 | 터틀 추세 추종 전략 | BTC 단순 보유 (Buy & Hold) | 초과 성과 |")
    report.append(f"| :--- | :---: | :---: | :---: |")
    report.append(f"| **누적 수익률** | **{metrics['total_return']:+.2f}%** | {metrics['btc_total_return']:+.2f}% | **{metrics['total_return'] - metrics['btc_total_return']:+.2f}%p** |")
    report.append(f"| **연평균 성장률 (CAGR)** | **{metrics['cagr']:.2f}%** | {metrics['btc_cagr']:.2f}% | **{metrics['cagr'] - metrics['btc_cagr']:+.2f}%p** |")
    report.append(f"| **최대 낙폭 (MDD)** | **{metrics['mdd']:.2f}%** | {metrics['btc_mdd']:.2f}% | **{metrics['btc_mdd'] - metrics['mdd']:+.2f}%p** (방어) |")
    report.append(f"| **총 거래 횟수** | **{metrics['total_trades']} 회** (매도 {metrics['sell_trades']} 회, 트레일링 스탑 {trailing_stop_count} 회) | - | - |")
    report.append(f"| **청산 승률 (Win Rate)** | **{metrics['win_rate']:.1f}%** | - | - |\n")

    outperformance = metrics['total_return'] - metrics['btc_total_return']
    mdd_defense = metrics['btc_mdd'] - metrics['mdd']
    report.append(f"> 💡 **주요 성과 요약**: 20일 신고가 돌파 시에만 진입하고 최고가 대비 ATR 하락 시 익절/손절하는 터틀 추세 추종 모델을 통해 불필요한 매매를 줄이고 최대 낙폭(MDD)을 **{metrics['mdd']:.2f}%** 수준으로 방어하였습니다.\n")

    report.append(f"## 2. 자산 가치 변동 추이 차트\n")
    report.append(f"![Equity Curve]({plot_filename})\n")

    report.append(f"## 3. 주요 매매 거래 내역 요약 (최근 20건 / 총 {len(trade_logs)}건)\n")
    if trade_logs:
        report.append(f"| 거래 일자 | 거래 구분 | 종목명 | 체결 가격 | 거래 금액 | 실현 손익률 |")
        report.append(f"| :---: | :---: | :---: | :---: | :---: | :---: |")
        for log in trade_logs[-20:]:
            ret_str = f"{log['return']*100:+.2f}%" if '매도' in log['type'] else "-"
            report.append(f"| {log['date']} | {log['type']} | {log['symbol'].replace('KRW-', '')} | {log['price']:,.1f} 원 | {log['amount']:,.0f} 원 | {ret_str} |")

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(report))

    print(f"✓ 자산 곡선 차트 저장 완료: {plot_path}")
    print(f"✓ 상세 백테스트 보고서 저장 완료: {report_path}\n")

    return metrics, report_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="후보 전략 2: 터틀 채널 돌파 + ATR 트레일링 스탑 백테스터")
    parser.add_argument('--days', type=int, default=1000, help='백테스트 분석 일수 (기본값: 1000)')
    parser.add_argument('--capital', type=float, default=10000000.0, help='시작 원금 (기본값: 10,000,000 원)')
    parser.add_argument('--channel-len', type=int, default=20, help='신고가 채널 기간 (기본값: 20)')
    parser.add_argument('--atr-len', type=int, default=14, help='ATR 기간 (기본값: 14)')
    parser.add_argument('--atr-mult', type=float, default=2.0, help='ATR 트레일링 스탑 배수 (기본값: 2.0)')
    parser.add_argument('--max-coins', type=int, default=4, help='동시 보유 최대 종목 수 (기본값: 4)')
    parser.add_argument('--btc-sma', type=int, default=220, help='BTC 시장 필터 SMA 기간 (기본값: 220)')
    parser.add_argument('--slippage', type=float, default=0.0005, help='슬리피지 비율 (기본값: 0.05%%)')
    parser.add_argument('--fee', type=float, default=0.0004, help='수수료율 (기본값: 0.04%%)')
    args = parser.parse_args()

    run_strategy2_turtle_backtest(
        days=args.days,
        initial_capital=args.capital,
        channel_len=args.channel_len,
        atr_len=args.atr_len,
        atr_multiplier=args.atr_mult,
        max_coins=args.max_coins,
        btc_sma_len=args.btc_sma,
        slippage=args.slippage,
        fee_rate=args.fee
    )
