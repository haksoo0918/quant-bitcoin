# -*- coding: utf-8 -*-
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

# Windows 콘솔 출력 인코딩 설정 (UTF-8 강제)
if sys.stdout and sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# 전략 고정 상수
BTC_BUFFER = 0.02          # BTC 200 SMA ±2% 버퍼
ETH_ATR_MULTIPLIER = 1.5   # ETH ATR 채널 승수
UPBIT_MIN_ORDER_KRW = 5000 # 업비트 최소 주문 금액
FEE_RATE = 0.0005          # 업비트 일반 주문 수수료율 (0.05%)

def get_kst_now():
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    return utc_now + datetime.timedelta(hours=9)

def fetch_and_cache_candles(market, days_needed):
    """
    업비트 API를 활용하여 지정한 코인의 과거 일봉 데이터를 역추적 페이징으로 다운로드하고 CSV로 캐싱합니다.
    """
    cache_dir = "data"
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)
        
    cache_file = os.path.join(cache_dir, f"{market}_daily.csv")
    
    # 캐시 파일이 존재하고 오늘 생성된 경우 바로 읽어옴
    if os.path.exists(cache_file):
        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(cache_file))
        now = datetime.datetime.now()
        if mtime.date() == now.date():
            df = pd.read_csv(cache_file)
            if len(df) >= days_needed:
                print(f"[{market}] 오늘 날짜의 캐시 파일 발견. 로컬에서 데이터를 로드합니다. (총 {len(df)}일분)")
                return df

    print(f"[{market}] 업비트 API로부터 과거 {days_needed}일 분량의 일봉 데이터를 수집합니다...")
    candles = []
    to_date = None
    
    while len(candles) < days_needed:
        url = f"https://api.upbit.com/v1/candles/days?market={market}&count=200"
        if to_date:
            url += f"&to={to_date}"
        
        try:
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                print(f"[{market}] API 호출 실패: {response.status_code} - {response.text}")
                break
                
            data = response.json()
            if not data:
                break
                
            candles.extend(data)
            # 수집된 가장 오래된 캔들의 시간을 다음 루프의 to_date로 지정
            oldest_time = data[-1]['candle_date_time_utc']
            to_date = oldest_time + "Z"
            
            print(f"  -> {len(candles)}일분 수집 완료... (최고 과거 데이터 일시: {oldest_time})")
            time.sleep(0.1) # 호출율 제한 방지
        except Exception as e:
            print(f"[{market}] 요청 중 오류 발생: {e}")
            break
            
    if not candles:
        raise ValueError(f"[{market}] 데이터를 전혀 수집하지 못했습니다.")
        
    # DataFrame 변환 및 전처리
    df = pd.DataFrame(candles)
    df = df[['candle_date_time_kst', 'opening_price', 'high_price', 'low_price', 'trade_price', 'candle_acc_trade_volume']]
    df.columns = ['date', 'open', 'high', 'low', 'close', 'volume']
    
    # 중복 제거 및 시간 순서(과거 -> 현재)로 정렬
    df = df.drop_duplicates(subset=['date']).sort_values('date').reset_index(drop=True)
    
    # CSV 저장
    df.to_csv(cache_file, index=False)
    print(f"[{market}] {len(df)}일의 데이터를 {cache_file} 파일로 캐시 저장 완료.")
    return df

def run_simulation(btc_df, eth_df, btc_sma_len, eth_sma_len, initial_capital=10000000.0):
    """
    지정한 파라미터 조건으로 백테스트 시뮬레이션을 수행합니다.
    """
    # 1. 지표 연산
    btc_df = btc_df.copy()
    eth_df = eth_df.copy()
    
    btc_df['sma'] = btc_df['close'].rolling(window=btc_sma_len).mean()
    
    eth_df['sma'] = eth_df['close'].rolling(window=eth_sma_len).mean()
    # True Range (TR) 및 ATR(14) 계산
    eth_df['tr'] = np.maximum(
        eth_df['high'] - eth_df['low'],
        np.maximum(
            np.abs(eth_df['high'] - eth_df['close'].shift(1)),
            np.abs(eth_df['low'] - eth_df['close'].shift(1))
        )
    )
    eth_df['atr_14'] = eth_df['tr'].rolling(window=14).mean()
    
    # 날짜를 기준으로 정렬 및 병합하여 두 자산의 동시 시뮬레이션 환경 구축
    merged_df = pd.merge(
        btc_df[['date', 'open', 'close', 'sma']],
        eth_df[['date', 'open', 'high', 'low', 'close', 'sma', 'atr_14']],
        on='date', suffixes=('_btc', '_eth')
    ).sort_values('date').reset_index(drop=True)
    
    # 이동평균 및 ATR 계산에 필요한 최소 인덱스 탐색
    start_idx = max(btc_sma_len, eth_sma_len) + 1
    if start_idx >= len(merged_df):
        raise ValueError("이동평균 기간에 비해 제공된 과거 데이터가 부족합니다.")
        
    # 초기 상태 값 세팅
    cash = initial_capital
    btc_qty = 0.0
    eth_qty = 0.0
    
    btc_signal = 'cash'
    eth_signal = 'cash'
    
    portfolio_history = []
    bh_history = []
    trade_logs = []
    
    # 벤치마크(Buy & Hold 50:50) 초기 매수 수량 고정
    btc_start_price = merged_df.loc[start_idx, 'open_btc']
    eth_start_price = merged_df.loc[start_idx, 'open_eth']
    bh_btc_qty = (initial_capital * 0.5 * (1 - FEE_RATE)) / btc_start_price
    bh_eth_qty = (initial_capital * 0.5 * (1 - FEE_RATE)) / eth_start_price
    bh_start_cash = initial_capital - (bh_btc_qty * btc_start_price / (1 - FEE_RATE)) - (bh_eth_qty * eth_start_price / (1 - FEE_RATE))
    
    for i in range(start_idx, len(merged_df)):
        row = merged_df.iloc[i]
        prev_row = merged_df.iloc[i - 1]
        
        date_str = row['date']
        
        # 현재 일자 09:00 KST 시가 (실행 단가)
        btc_p = row['open_btc']
        eth_p = row['open_eth']
        
        # 1. 어제 완료 봉 기준 지표 로드 (Look-ahead Bias 방지)
        btc_sma = prev_row['sma_btc']
        btc_close_prev = prev_row['close_btc']
        
        eth_sma = prev_row['sma_eth']
        eth_atr = prev_row['atr_14']
        eth_close_prev = prev_row['close_eth']
        
        # 2. 개별 추세 신호 판단 (버퍼 히스테리시스 모방)
        # BTC
        btc_upper = btc_sma * (1 + BTC_BUFFER)
        btc_lower = btc_sma * (1 - BTC_BUFFER)
        if btc_signal == 'cash':
            if btc_close_prev >= btc_upper:
                btc_signal = 'hold'
        else: # btc_signal == 'hold'
            if btc_close_prev < btc_lower:
                btc_signal = 'cash'
                
        # ETH
        eth_upper = eth_sma + (eth_atr * ETH_ATR_MULTIPLIER)
        eth_lower = eth_sma - (eth_atr * ETH_ATR_MULTIPLIER)
        if eth_signal == 'cash':
            if eth_close_prev >= eth_upper:
                eth_signal = 'hold'
        else: # eth_signal == 'hold'
            if eth_close_prev < eth_lower:
                eth_signal = 'cash'
                
        # 3. 현재 자산 가치 총합 계산
        current_btc_val = btc_qty * btc_p
        current_eth_val = eth_qty * eth_p
        total_value = cash + current_btc_val + current_eth_val
        
        # 4. 목표 평가 금액 계산
        target_btc_val = 0.5 * total_value if btc_signal == 'hold' else 0.0
        target_eth_val = 0.5 * total_value if eth_signal == 'hold' else 0.0
        
        # 양방향 보유 지속 시 비중 편차 밴드(±10%p) 리밸런싱 예외 적용
        is_holding_btc = current_btc_val >= UPBIT_MIN_ORDER_KRW
        is_holding_eth = current_eth_val >= UPBIT_MIN_ORDER_KRW
        
        if btc_signal == 'hold' and eth_signal == 'hold' and is_holding_btc and is_holding_eth:
            btc_weight = current_btc_val / total_value
            if 0.40 <= btc_weight <= 0.60:
                # 밴드 내에 존재하면 거래 없음
                target_btc_val = current_btc_val
                target_eth_val = current_eth_val
                
        # 5. 거래 집행 (선매도 후매수)
        diff_btc = target_btc_val - current_btc_val
        diff_eth = target_eth_val - current_eth_val
        
        # 5.1 선매도 (차이액이 음수인 자산 매도)
        # BTC 매도
        if diff_btc < 0:
            sell_qty = -diff_btc / btc_p
            if target_btc_val == 0.0:
                # 전량 청산
                sell_qty = btc_qty
                
            sell_amount = sell_qty * btc_p
            if sell_amount >= UPBIT_MIN_ORDER_KRW:
                cash_received = sell_amount * (1 - FEE_RATE)
                cash += cash_received
                btc_qty -= sell_qty
                trade_logs.append(f"{date_str[:10]} | [매도] 업비트 BTC: {sell_amount:,.0f}원 ({sell_qty:.6f}개) | 수수료: {sell_amount * FEE_RATE:,.0f}원")
                
        # ETH 매도
        if diff_eth < 0:
            sell_qty = -diff_eth / eth_p
            if target_eth_val == 0.0:
                # 전량 청산
                sell_qty = eth_qty
                
            sell_amount = sell_qty * eth_p
            if sell_amount >= UPBIT_MIN_ORDER_KRW:
                cash_received = sell_amount * (1 - FEE_RATE)
                cash += cash_received
                eth_qty -= sell_qty
                trade_logs.append(f"{date_str[:10]} | [매도] 업비트 ETH: {sell_amount:,.0f}원 ({sell_qty:.6f}개) | 수수료: {sell_amount * FEE_RATE:,.0f}원")
                
        # 5.2 후매수 (차이액이 양수인 자산 매수)
        # BTC 매수
        diff_btc = target_btc_val - (btc_qty * btc_p)
        if diff_btc > 0:
            buy_amount = min(diff_btc, cash * 0.999) # 호가 슬리피지 방지용 가용 현금 버퍼
            if buy_amount >= UPBIT_MIN_ORDER_KRW:
                buy_qty = (buy_amount * (1 - FEE_RATE)) / btc_p
                cash -= buy_amount
                btc_qty += buy_qty
                trade_logs.append(f"{date_str[:10]} | [매수] 업비트 BTC: {buy_amount:,.0f}원 ({buy_qty:.6f}개) | 수수료: {buy_amount * FEE_RATE:,.0f}원")
                
        # ETH 매수
        diff_eth = target_eth_val - (eth_qty * eth_p)
        if diff_eth > 0:
            buy_amount = min(diff_eth, cash * 0.999)
            if buy_amount >= UPBIT_MIN_ORDER_KRW:
                buy_qty = (buy_amount * (1 - FEE_RATE)) / eth_p
                cash -= buy_amount
                eth_qty += buy_qty
                trade_logs.append(f"{date_str[:10]} | [매수] 업비트 ETH: {buy_amount:,.0f}원 ({buy_qty:.6f}개) | 수수료: {buy_amount * FEE_RATE:,.0f}원")
                
        # 6. 당일 거래 후 최종 총 평가 자산 기록
        end_portfolio_value = cash + (btc_qty * btc_p) + (eth_qty * eth_p)
        portfolio_history.append((date_str, end_portfolio_value))
        
        # 단순 보유(Buy & Hold) 벤치마크 평가 자산 기록
        bh_val = bh_start_cash + (bh_btc_qty * btc_p) + (bh_eth_qty * eth_p)
        bh_history.append((date_str, bh_val))
        
    return portfolio_history, bh_history, trade_logs

def calculate_metrics(history, bh_history):
    """
    백테스트 결과 시계열을 바탕으로 수익률, CAGR, MDD 등의 핵심 투자 지표를 산출합니다.
    """
    df = pd.DataFrame(history, columns=['date', 'value'])
    bh_df = pd.DataFrame(bh_history, columns=['date', 'value'])
    
    # 1. 누적 수익률
    init_val = df['value'].iloc[0]
    final_val = df['value'].iloc[-1]
    total_return = (final_val - init_val) / init_val * 100
    
    bh_init_val = bh_df['value'].iloc[0]
    bh_final_val = bh_df['value'].iloc[-1]
    bh_total_return = (bh_final_val - bh_init_val) / bh_init_val * 100
    
    # 2. CAGR (연평균 수익률)
    start_date = pd.to_datetime(df['date'].iloc[0])
    end_date = pd.to_datetime(df['date'].iloc[-1])
    years = (end_date - start_date).days / 365.25
    cagr = ((final_val / init_val) ** (1 / years) - 1) * 100 if years > 0 else 0.0
    bh_cagr = ((bh_final_val / bh_init_val) ** (1 / years) - 1) * 100 if years > 0 else 0.0
    
    # 3. MDD (최대 낙폭)
    df['peak'] = df['value'].cummax()
    df['drawdown'] = (df['value'] - df['peak']) / df['peak'] * 100
    mdd = df['drawdown'].min()
    
    bh_df['peak'] = bh_df['value'].cummax()
    bh_df['drawdown'] = (bh_df['value'] - bh_df['peak']) / bh_df['peak'] * 100
    bh_mdd = bh_df['drawdown'].min()
    
    return {
        "start_date": df['date'].iloc[0][:10],
        "end_date": df['date'].iloc[-1][:10],
        "years": round(years, 2),
        "initial_capital": init_val,
        "final_value": final_val,
        "total_return": round(total_return, 2),
        "cagr": round(cagr, 2),
        "mdd": round(mdd, 2),
        "bh_total_return": round(bh_total_return, 2),
        "bh_cagr": round(bh_cagr, 2),
        "bh_mdd": round(bh_mdd, 2)
    }

def save_plot(portfolio_history, bh_history):
    """
    Matplotlib을 사용하여 누적 자산 곡선을 벤치마크와 비교하여 이미지(backtest_result.png)로 저장합니다.
    """
    dates = [x[0][:10] for x in portfolio_history]
    values = [x[1] for x in portfolio_history]
    bh_values = [x[1] for x in bh_history]
    
    # 날짜 스트링을 datetime 객체로 변환
    plot_dates = [datetime.datetime.strptime(d, "%Y-%m-%d") for d in dates]
    
    plt.figure(figsize=(12, 6))
    plt.plot(plot_dates, values, label="Quant Strategy", color="#1f77b4", linewidth=2.5)
    plt.plot(plot_dates, bh_values, label="Buy & Hold (50:50)", color="#7f7f7f", linestyle="--", linewidth=1.5)
    
    plt.title("Portfolio Equity Curve Comparison (Upbit KRW)", fontsize=14, fontweight="bold")
    plt.xlabel("Date", fontsize=12)
    plt.ylabel("Portfolio Value (KRW)", fontsize=12)
    plt.grid(True, linestyle=":", alpha=0.6)
    
    # 1000 단위 컴마 표기형 Y축 적용
    plt.gca().get_yaxis().set_major_formatter(plt.FuncFormatter(lambda x, loc: "{:,}".format(int(x))))
    
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.gca().xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    plt.gcf().autofmt_xdate()
    plt.legend(fontsize=11)
    
    plt.tight_layout()
    plt.savefig("backtest_result.png", dpi=150)
    plt.close()
    print("[시각화] 누적 자산 곡선 차트를 'backtest_result.png'에 저장했습니다.")

def save_markdown_report(metrics, btc_sma, eth_sma, trade_logs):
    """
    백테스트 결과 성과 분석 보고서를 'backtest_report.md' 마크다운 문서로 작성합니다.
    """
    report = []
    report.append(f"# 📊 업비트 KRW 시세 기반 퀀트 전략 백테스트 보고서")
    report.append(f"⏱️ **작성 일시**: {get_kst_now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"🔍 **백테스트 대상 전략**: 메인 전략 (BTC & ETH 50:50 자동 비중 조절 및 추세 추종)")
    report.append(f"⚙️ **전략 파라미터**: BTC 이동평균: **{btc_sma}일** (버퍼 ±2%) | ETH 이동평균: **{eth_sma}일** (ATR배수 1.5배)")
    
    report.append(f"\n## 1. 종합 성과 분석 결과")
    report.append(f"- **백테스트 기간**: {metrics['start_date']} ~ {metrics['end_date']} (약 {metrics['years']}년)")
    report.append(f"- **초기 가입금**: {metrics['initial_capital']:,.0f} 원")
    report.append(f"- **최종 자산 총액**: {metrics['final_value']:,.0f} 원")
    
    report.append(f"\n| 지표 | 퀀트 리밸런싱 전략 (Quant) | 단순 보유 전략 (Buy & Hold) |")
    report.append(f"| :--- | :---: | :---: |")
    report.append(f"| **누적 수익률** | **{metrics['total_return']:+.2f}%** | {metrics['bh_total_return']:+.2f}% |")
    report.append(f"| **연평균 성장률 (CAGR)** | **{metrics['cagr']:.2f}%** | {metrics['bh_cagr']:.2f}% |")
    report.append(f"| **최대 낙폭 (MDD)** | **{metrics['mdd']:.2f}%** | {metrics['bh_mdd']:.2f}% |")
    
    # 성과 평가 코멘트 추가
    outperformance = metrics['total_return'] - metrics['bh_total_return']
    mdd_defense = metrics['bh_mdd'] - metrics['mdd']
    report.append(f"\n> 💡 **주요 성과 요약**: 단순 보유 대비 **{outperformance:+.2f}%p**의 초과 수익률을 기록하였으며, 최대 낙폭(MDD) 방어 측면에서 벤치마크 대비 **{mdd_defense:.2f}%p** 만큼의 낙폭 축소 효과(자산 방어)를 달성하였습니다.")
    
    report.append(f"\n## 2. 자산 가치 변동 추이 차트")
    report.append(f"![Equity Curve](backtest_result.png)")
    
    report.append(f"\n## 3. 백테스트 기간 중 매매 거래 내역 (총 {len(trade_logs)}건)")
    if trade_logs:
        report.append(f"| 거래 일시 | 거래 구분 | 거래 금액 및 수량 | 수수료 |")
        report.append(f"| :---: | :---: | :--- | :---: |")
        for log in trade_logs:
            # 파싱하여 표 형식으로 출력
            parts = [p.strip() for p in log.split('|')]
            date = parts[0]
            type_action = "🔵 매수" if "[매수]" in parts[1] else "🔴 매도"
            desc = parts[1].replace("[매수] ", "").replace("[매도] ", "")
            fee = parts[2].replace("수수료:", "").strip()
            report.append(f"| {date} | {type_action} | {desc} | {fee} |")
    else:
        report.append("- 백테스트 기간 중 신호 변화에 따른 매매 거래가 발생하지 않았습니다.")
        
    # 파일 쓰기
    with open("backtest_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    print("백테스트 마크다운 성과 분석 보고서를 'backtest_report.md'에 저장했습니다.")

def run_optimization(btc_df, eth_df, initial_capital=10000000.0):
    """
    이동평균 기간 조합을 변경해 가며 모든 백테스트 조합을 연산하고, 랭킹을 출력하는 파라미터 최적화 모드입니다.
    """
    btc_sma_candidates = [50, 80, 100, 120, 150, 180, 200, 220]
    eth_sma_candidates = [50, 80, 100, 120, 150, 160, 180, 200]
    
    print("\n=======================================================")
    print("🚀 전략 파라미터 최적화(Grid Search) 연산을 개시합니다.")
    print(f"  - BTC SMA 후보군: {btc_sma_candidates}")
    print(f"  - ETH SMA 후보군: {eth_sma_candidates}")
    print(f"  - 총 연산 조합 수: {len(btc_sma_candidates) * len(eth_sma_candidates)}개")
    print("=======================================================")
    
    results = []
    
    for b_sma in btc_sma_candidates:
        for e_sma in eth_sma_candidates:
            try:
                p_hist, bh_hist, _ = run_simulation(btc_df, eth_df, b_sma, e_sma, initial_capital)
                metrics = calculate_metrics(p_hist, bh_hist)
                results.append({
                    "btc_sma": b_sma,
                    "eth_sma": e_sma,
                    "total_return": metrics['total_return'],
                    "cagr": metrics['cagr'],
                    "mdd": metrics['mdd']
                })
            except Exception as e:
                # 연산 불가능한 구간 스킵
                continue
                
    # 누적 수익률 기준 내림차순 정렬
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values(by='total_return', ascending=False).reset_index(drop=True)
    
    print("\n🏆 **전략 파라미터 연산 수익률 랭킹 상위 15개 조합**")
    print("--------------------------------------------------------------------------------")
    print("| 순위 | BTC SMA | ETH SMA | 누적 수익률 | CAGR (연평균) | MDD (최대 낙폭) |")
    print("--------------------------------------------------------------------------------")
    for idx, row in results_df.head(15).iterrows():
        print(f"| {idx+1:^4} | {int(row['btc_sma']):^7} | {int(row['eth_sma']):^7} | {row['total_return']:>+10.2f}% | {row['cagr']:>10.2f}% | {row['mdd']:>12.2f}% |")
    print("--------------------------------------------------------------------------------")
    
    # 랭킹 결과를 파일로도 기록 저장
    report = []
    report.append("# 🏆 퀀트 전략 이동평균선 파라미터 최적화 보고서")
    report.append(f"⏱️ **연산 일시**: {get_kst_now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"\n모든 이동평균선(SMA) 조합에 따른 연산 결과 전체 랭킹 테이블입니다.")
    report.append(f"\n| 순위 | BTC SMA 기간 | ETH SMA 기간 | 누적 수익률 | CAGR (연평균) | MDD (최대 낙폭) |")
    report.append(f"| :---: | :---: | :---: | :---: | :---: | :---: |")
    for idx, row in results_df.iterrows():
        report.append(f"| {idx+1} | {int(row['btc_sma'])}일 | {int(row['eth_sma'])}일 | {row['total_return']:+.2f}% | {row['cagr']:.2f}% | {row['mdd']:.2f}% |")
        
    with open("backtest_optimization_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    print("\n최적화 보고서가 'backtest_optimization_report.md'에 저장되었습니다.")

def main():
    parser = argparse.ArgumentParser(description="Upbit KRW Quant Strategy Backtester")
    parser.add_argument("--btc-sma", type=int, default=200, help="BTC SMA window length (default: 200)")
    parser.add_argument("--eth-sma", type=int, default=150, help="ETH SMA window length (default: 150)")
    parser.add_argument("--days", type=int, default=1500, help="Number of historical days to backtest (default: 1500)")
    parser.add_argument("--optimize", action="store_true", help="Run parameter optimization grid search")
    parser.add_argument("--capital", type=float, default=10000000.0, help="Initial capital in KRW (default: 10,000,000)")
    
    args = parser.parse_args()
    
    # 데이터 수집 (안정적 연산을 위해 필요한 백테스트 일수보다 250일 더 긁어옴 - SMA 연산용 예비 기간)
    days_to_fetch = args.days + 250
    
    try:
        btc_df = fetch_and_cache_candles("KRW-BTC", days_to_fetch)
        eth_df = fetch_and_cache_candles("KRW-ETH", days_to_fetch)
    except Exception as e:
        print(f"데이터 다운로드 중 오류 발생: {e}")
        return
        
    if args.optimize:
        run_optimization(btc_df, eth_df, args.capital)
    else:
        print(f"\n=======================================================")
        print(f"📈 퀀트 전략 백테스트 시뮬레이션을 시작합니다. ({args.days}일)")
        print(f"  - BTC SMA: {args.btc_sma}일 (버퍼 ±2%)")
        print(f"  - ETH SMA: {args.eth_sma}일 (ATR 1.5배)")
        print(f"  - 초기 자산: {args.capital:,.0f} KRW")
        print("=======================================================")
        
        try:
            p_hist, bh_hist, logs = run_simulation(btc_df, eth_df, args.btc_sma, args.eth_sma, args.capital)
            metrics = calculate_metrics(p_hist, bh_hist)
            
            # 최종 지표 콘솔 요약 출력
            print("\n🏁 백테스트 완료! 요약 성과 분석 지표:")
            print(f"  - 시작일 ~ 종료일: {metrics['start_date']} ~ {metrics['end_date']} (약 {metrics['years']}년)")
            print(f"  - 최종 포트폴리오 가치: {metrics['final_value']:,.0f} KRW")
            print(f"  - 전략 누적 수익률: {metrics['total_return']:+.2f}% | 단순보유: {metrics['bh_total_return']:+.2f}%")
            print(f"  - 전략 CAGR: {metrics['cagr']:.2f}% | 단순보유: {metrics['bh_cagr']:.2f}%")
            print(f"  - 전략 MDD: {metrics['mdd']:.2f}% | 단순보유: {metrics['bh_mdd']:.2f}%")
            print("-------------------------------------------------------")
            
            # 성과 지표 기록 및 플로팅
            save_plot(p_hist, bh_hist)
            save_markdown_report(metrics, args.btc_sma, args.eth_sma, logs)
            
        except Exception as e:
            print(f"시뮬레이션 연산 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()
