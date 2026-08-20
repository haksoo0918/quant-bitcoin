# -*- coding: utf-8 -*-
import sys
import os
import time
import requests
import pandas as pd

# Windows 콘솔 출력 인코딩 오류 방지 (UTF-8 강제 설정)
if sys.stdout and sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# 프로젝트 설정 및 모듈 로드
from config import DRY_RUN
from bithumb_api import BithumbClient
import main

def test_rotation():
    print("==================================================")
    print("   빗썸 월요일 상승장 (종목 교체) 시뮬레이션 테스트")
    print("==================================================")
    
    # 빗썸 클라이언트 생성 (API 키가 없어도 공용 API 데이터 조회는 작동 가능)
    bithumb = BithumbClient()
    
    # 1. 빗썸 전체 티커 시세 조회
    try:
        ticker_data = main.fetch_bithumb_ticker_all()
    except Exception as e:
        print(f"❌ 빗썸 티커 조회 실패: {e}")
        return

    # 2. 거래대금 상위 정렬 및 후보 추출
    volume_list = []
    for coin, info in ticker_data.items():
        if coin in ("date", "BTC", "ETH"):
            continue
        acc_value = float(info.get("acc_trade_value_24H", 0.0))
        volume_list.append((f"KRW-{coin}", acc_value))
        
    volume_list.sort(key=lambda x: x[1], reverse=True)
    
    # 상위 30개 후보로 필터링하여 일봉 조회 API 횟수 최적화
    top_30_candidates = [item[0] for item in volume_list[:30]]
    print(f"ℹ️ 24시간 거래대금 상위 30개 알트코인 후보 추출 완료.")
    print(f"   후보 예시: {', '.join(top_30_candidates[:5])} ...")
    
    # 3. 각 후보별 캔들 조회 및 지표 연산
    altcoin_stats = []
    print("\nℹ️ 후보 종목 분석 중 (일봉 캔들 조회 및 지표 계산)...")
    
    for market in top_30_candidates:
        try:
            # count=16 (오늘 0, 어제 1 ~ 14일 전 14, 15일 전 15)
            candles = bithumb.get_ohlcv(market, count=16)
            if len(candles) < 16:
                print(f"   ⚠️ {market}: 캔들 데이터 부족 ({len(candles)}개) -> 제외")
                continue
                
            df_c = main.bithumb_candles_to_df(candles)
            
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
            time.sleep(0.05) # Rate limit 방지용 짧은 딜레이
        except Exception as e:
            print(f"   ❌ {market} 지표 연산 에러: {e}")
            
    # 7일 평균 거래 대금 기준 정렬 및 상위 10개 추출
    altcoin_stats.sort(key=lambda x: x['avg_value_7d'], reverse=True)
    top_10_by_volume = altcoin_stats[:10]
    
    # 상위 10개 중 최근 14일 수익률 상위 4개 종목 최종 선정
    top_10_by_volume.sort(key=lambda x: x['return_14d'], reverse=True)
    target_coins_stats = top_10_by_volume[:4]
    
    print("\n==================================================")
    print("   ★ 최종 선정 서브 전략 4대 알트코인 결과 ★")
    print("==================================================")
    for i, coin_stat in enumerate(target_coins_stats):
        print(f"🏆 {i+1}위: {coin_stat['market']}")
        print(f"   • 14일 상대 수익률: {coin_stat['return_14d']*100:+.2f}%")
        print(f"   • 7일 평균 거래대금: {coin_stat['avg_value_7d']/1e8:.2f} 억원")
        print(f"   • 현재가: {coin_stat['price']:,.2f} 원")
        print("--------------------------------------------------")

if __name__ == "__main__":
    test_rotation()
