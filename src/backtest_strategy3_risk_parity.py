# -*- coding: utf-8 -*-
"""
후보 전략 3: 변동성 역가중 모멘텀 포트폴리오 백테스터 (Risk Parity Momentum Strategy 3)
- 종목 선정: 매주 월요일 09:00, 7일 거래대금 TOP 10 중 14일 수익률 TOP 4 선정
- 비중 배분: 각 종목의 최근 20일 일일 변동성(표준편차) 역수에 비례하여 동적 가중치 배분 (Risk Parity)
- 필터: 비트코인 220일 SMA ±2% 공통 시장 필터 (하락장 시 전량 현금화)
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


def run_strategy3_risk_parity_backtest(days=1000, initial_capital=10000000.0, vol_window=20,
                                       momentum_window=14, volume_window=7, select_count=4,
                                       btc_sma_len=220, buffer_rate=0.02,
                                       fee_rate=0.0004, slippage=0.0005):
    print(f"\n{'='*70}")
    print(f"📊 [후보 전략 3] 변동성 역가중 모멘텀 포트폴리오 백테스트 시작")
    print(f"• 분석 기간: 최근 {days}일 | 초기 자본: {initial_capital:,.0f} 원")
    print(f"• 변동성 산출 기간: 최근 {vol_window}일 일일 수익률 표준편차 역수 가중 (Risk Parity)")
    print(f"• 종목 선정: {volume_window}일 거래대금 TOP 10 중 {momentum_window}일 수익률 TOP {select_count}")
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
        df = fetch_and_cache_candles(sym, days_needed=days + max(vol_window, momentum_window) + 50)
        if df is not None and len(df) >= 100:
            df['ret1d'] = df['close'].pct_change()
            df['vol20'] = df['ret1d'].rolling(window=vol_window).std()
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
    holdings = {} # { 'KRW-XRP': { 'qty': float, 'buy_price': float, 'target_weight': float } }
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
        btc_row = btc_df.loc[current_date]
        btc_price = btc_row['close']
        if btc_price >= btc_row['btc_upper']:
            market_filter_state = "Bull"
        elif btc_price < btc_row['btc_lower']:
            market_filter_state = "Bear"

        is_monday = (current_date.weekday() == 0)

        # A. 하락장(Bear) 시 전량 매도 (100% 현금화)
        if market_filter_state == "Bear" and len(holdings) > 0:
            for sym, pos in list(holdings.items()):
                df_coin = alt_dfs.get(sym)
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

        # B. 상승장(Bull) 시 주간 리밸런싱 (월요일 또는 첫 진입)
        elif market_filter_state == "Bull" and (is_monday or len(holdings) == 0):
            candidates = []
            for sym, df_coin in alt_dfs.items():
                if current_date in df_coin.index:
                    hist = df_coin.loc[:current_date]
                    if len(hist) >= max(volume_window, momentum_window, vol_window) + 1:
                        curr_p = hist['close'].iloc[-1]
                        vol = hist['vol20'].iloc[-1]
                        if not pd.isna(vol) and vol > 0.001:
                            avg_val = hist['value'].iloc[-volume_window:].mean()
                            ret_14d = (curr_p - hist['close'].iloc[-momentum_window-1]) / hist['close'].iloc[-momentum_window-1]
                            candidates.append({
                                'symbol': sym,
                                'avg_val_7d': avg_val,
                                'return_14d': ret_14d,
                                'volatility': vol,
                                'inv_vol': 1.0 / vol,
                                'close': curr_p
                            })

            if len(candidates) >= select_count:
                candidates.sort(key=lambda x: x['avg_val_7d'], reverse=True)
                top_vol = candidates[:10]
                top_vol.sort(key=lambda x: x['return_14d'], reverse=True)
                selected = top_vol[:select_count]

                # 변동성 역가중치 계산: w_i = (1 / vol_i) / sum(1 / vol_k)
                sum_inv_vol = sum(c['inv_vol'] for c in selected)
                for c in selected:
                    c['weight'] = c['inv_vol'] / sum_inv_vol

                target_symbols = [c['symbol'] for c in selected]

                # 탈락 종목 매도
                for sym, pos in list(holdings.items()):
                    if sym not in target_symbols:
                        df_coin = alt_dfs.get(sym)
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

                # 총 자산 계산 후 가중치별 매수
                current_total_equity = cash
                for s, p in holdings.items():
                    df_c = alt_dfs.get(s)
                    if df_c is not None and current_date in df_c.index:
                        current_total_equity += p['qty'] * df_c.loc[current_date, 'close']

                for item in selected:
                    sym = item['symbol']
                    df_coin = alt_dfs.get(sym)
                    if df_coin is not None and current_date in df_coin.index:
                        buy_price = item['close'] * (1 + slippage)
                        target_alloc = current_total_equity * item['weight']

                        if sym not in holdings:
                            order_amt = min(cash, target_alloc)
                            if order_amt >= 5000:
                                fee = order_amt * fee_rate
                                net_amt = order_amt - fee
                                qty = net_amt / buy_price
                                cash -= order_amt
                                holdings[sym] = {
                                    'qty': qty,
                                    'buy_price': buy_price,
                                    'weight': item['weight']
                                }
                                trade_logs.append({
                                    'date': current_date.strftime('%Y-%m-%d'),
                                    'type': f"매수(변동성 역가중 비중 {item['weight']*100:.1f}%)",
                                    'symbol': sym,
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
        'strategy_name': "변동성 역가중 모멘텀 (Risk Parity)",
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
        'win_rate': win_rate
    }

    # 콘솔 출력
    print("\n" + "="*70)
    print("🎯 [후보 전략 3: 변동성 역가중 모멘텀 포트폴리오 백테스트 결과]")
    print("="*70)
    print(f"• 테스트 기간: {test_dates[0].strftime('%Y-%m-%d')} ~ {test_dates[-1].strftime('%Y-%m-%d')} ({total_days}일, 약 {total_days/365.25:.1f}년)")
    print(f"• 비중 배분 방식: 최근 {vol_window}일 일일 변동성(표준편차) 역수 가중 배분")
    print(f"• 초기 자본: {initial_capital:,.0f} 원 ➔ 최종 자산: {metrics['final_equity']:,.0f} 원")
    print(f"• 전략 누적 수익률: {metrics['total_return']:+.2f}% (CAGR: {metrics['cagr']:+.2f}%)")
    print(f"• 벤치마크(BTC 단순보유): {metrics['btc_total_return']:+.2f}% (CAGR: {metrics['btc_cagr']:+.2f}%)")
    print(f"• 초과 성과: {metrics['total_return'] - metrics['btc_total_return']:+.2f}%p")
    print(f"• 전략 최대 낙폭 (MDD): {metrics['mdd']:.2f}% (BTC MDD: {metrics['btc_mdd']:.2f}%)")
    print(f"• 총 매매 횟수: {len(trade_logs)}회 (매도 완료 {len(sell_trades)}회, 승률 {win_rate:.1f}%)")
    print("="*70)

    # 6. 차트 생성
    timestamp_str = get_kst_now().strftime("%Y%m%d_%H%M%S")
    plot_filename = f"backtest_strategy3_risk_parity_result_{timestamp_str}.png"
    plot_path = os.path.join(OUTPUT_DIR, plot_filename)

    plt.rcParams['font.family'] = 'DejaVu Sans'
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True, gridspec_kw={'height_ratios': [2.5, 1]})

    ax1.plot(res_df['date'], (res_df['equity'] / initial_capital) * 100, label=f"Risk Parity Momentum (CAGR {metrics['cagr']:+.1f}%)", color='#0ea5e9', linewidth=2.0)
    ax1.plot(res_df['date'], (res_df['btc_price'] / res_df['btc_price'].iloc[0]) * 100, label=f"BTC Buy & Hold (CAGR {metrics['btc_cagr']:+.1f}%)", color='#94a3b8', linestyle='--', linewidth=1.5)
    ax1.axhline(100, color='gray', linestyle=':', alpha=0.6)
    ax1.set_title("Strategy 3: Risk Parity Momentum vs BTC Buy & Hold", fontsize=14, fontweight='bold', pad=12)
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
    report_filename = f"backtest_strategy3_risk_parity_report_{timestamp_str}.md"
    report_path = os.path.join(OUTPUT_DIR, report_filename)

    report = []
    report.append(f"# 📊 [후보 전략 3] 변동성 역가중 모멘텀 백테스트 성과 보고서\n")
    report.append(f"- **실행 일시**: {get_kst_now().strftime('%Y-%m-%d %H:%M:%S KST')}")
    report.append(f"- **분석 기간**: {test_dates[0].strftime('%Y-%m-%d')} ~ {test_dates[-1].strftime('%Y-%m-%d')} (총 {metrics['total_days']} 일, 약 {metrics['total_days']/365.25:.1f} 년)")
    report.append(f"- **적용 파라미터**: 변동성 역가중 산출 기간 **{vol_window}일 표준편차**, 모멘텀 **{momentum_window}일**, 최대 **{select_count}개 종목**")
    report.append(f"- **시작 자산**: {metrics['initial_capital']:,.0f} 원 ➔ **최종 자산**: {metrics['final_equity']:,.0f} 원\n")
    report.append(f"---\n")

    report.append(f"## 1. 종합 성과 지표 비교\n")
    report.append(f"| 평가 지표 | 변동성 역가중 모멘텀 전략 | BTC 단순 보유 (Buy & Hold) | 초과 성과 |")
    report.append(f"| :--- | :---: | :---: | :---: |")
    report.append(f"| **누적 수익률** | **{metrics['total_return']:+.2f}%** | {metrics['btc_total_return']:+.2f}% | **{metrics['total_return'] - metrics['btc_total_return']:+.2f}%p** |")
    report.append(f"| **연평균 성장률 (CAGR)** | **{metrics['cagr']:.2f}%** | {metrics['btc_cagr']:.2f}% | **{metrics['cagr'] - metrics['btc_cagr']:+.2f}%p** |")
    report.append(f"| **최대 낙폭 (MDD)** | **{metrics['mdd']:.2f}%** | {metrics['btc_mdd']:.2f}% | **{metrics['btc_mdd'] - metrics['mdd']:+.2f}%p** (방어) |")
    report.append(f"| **총 거래 횟수** | **{metrics['total_trades']} 회** (매도 {metrics['sell_trades']} 회) | - | - |")
    report.append(f"| **청산 승률 (Win Rate)** | **{metrics['win_rate']:.1f}%** | - | - |\n")

    outperformance = metrics['total_return'] - metrics['btc_total_return']
    mdd_defense = metrics['btc_mdd'] - metrics['mdd']
    report.append(f"> 💡 **주요 성과 요약**: 변동성이 높은 고위험 알트코인의 비중을 자동으로 줄이고 안정적인 종목 비중을 늘리는 리스크 패리티 가중 배분을 통해 최대 낙폭(MDD)을 **{metrics['mdd']:.2f}%** 로 제어하였습니다.\n")

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
    parser = argparse.ArgumentParser(description="후보 전략 3: 변동성 역가중 모멘텀 포트폴리오 백테스터")
    parser.add_argument('--days', type=int, default=1000, help='백테스트 분석 일수 (기본값: 1000)')
    parser.add_argument('--capital', type=float, default=10000000.0, help='시작 원금 (기본값: 10,000,000 원)')
    parser.add_argument('--vol-window', type=int, default=20, help='변동성 산출 기간 (기본값: 20)')
    parser.add_argument('--momentum-window', type=int, default=14, help='모멘텀 기간 (기본값: 14)')
    parser.add_argument('--select-count', type=int, default=4, help='선정 종목 수 (기본값: 4)')
    parser.add_argument('--btc-sma', type=int, default=220, help='BTC 시장 필터 SMA 기간 (기본값: 220)')
    parser.add_argument('--slippage', type=float, default=0.0005, help='슬리피지 비율 (기본값: 0.05%%)')
    parser.add_argument('--fee', type=float, default=0.0004, help='수수료율 (기본값: 0.04%%)')
    args = parser.parse_args()

    run_strategy3_risk_parity_backtest(
        days=args.days,
        initial_capital=args.capital,
        vol_window=args.vol_window,
        momentum_window=args.momentum_window,
        select_count=args.select_count,
        btc_sma_len=args.btc_sma,
        slippage=args.slippage,
        fee_rate=args.fee
    )
