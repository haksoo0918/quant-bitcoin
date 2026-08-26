# -*- coding: utf-8 -*-
"""
공통 기술적 지표 및 추세 필터 연산 모듈 (Indicators Module)
- main.py (실거래/시그널) 및 backtest.py (백테스트)에서 공통으로 호출하여 사용합니다.
"""
import pandas as pd
import numpy as np


def calculate_btc_indicators(df: pd.DataFrame, sma_len: int = 220, buffer_rate: float = 0.02):
    """
    BTC 이동평균선, 노이즈 버퍼(±buffer_rate) 및 시장 필터 상태(히스테리시스)를 연산합니다.
    
    Parameters:
        df (pd.DataFrame): 일봉 데이터 (최소 'close' 컬럼 필요)
        sma_len (int): 단순 이동평균(SMA) 기간
        buffer_rate (float): 버퍼 비율 (기본 0.02 = ±2%)
        
    Returns:
        dict:
            - sma (float): 전일 완료봉 기준 SMA
            - upper_buffer (float): 상한 버퍼 가격
            - lower_buffer (float): 하한 버퍼 가격
            - status (str): 'bull' | 'bear' | 'buffer'
            - status_label (str): 한글 상태 설명
            - market_filter_state (str): 'Bull' | 'Bear' (히스테리시스 적용 확정 상태)
    """
    df_calc = df.copy()
    df_calc['sma'] = df_calc['close'].rolling(window=sma_len).mean()
    
    # 전일 완료 일봉 기준 (미완성 당일 봉 제외: iloc[-2])
    sma = float(df_calc['sma'].iloc[-2])
    upper_buffer = sma * (1 + buffer_rate)
    lower_buffer = sma * (1 - buffer_rate)
    
    # 현재 가격 (최신 행 종가 혹은 현재가)
    current_price = float(df_calc['close'].iloc[-1])
    
    # 당일 즉시 상태 판정
    if current_price >= upper_buffer:
        status = "bull"
        status_label = "상승 추세 돌파"
        market_filter_state = "Bull"
    elif current_price < lower_buffer:
        status = "bear"
        status_label = "하락 추세 이탈"
        market_filter_state = "Bear"
    else:
        status = "buffer"
        status_label = "버퍼 구간 대기"
        
        # 버퍼 구간 (0.98 ~ 1.02) 진입: 과거 일봉을 역순 탐색하여 직전 확정 추세를 상속(히스테리시스)
        market_filter_state = "Bear"  # 디폴트 안전장치
        for t in range(2, len(df_calc)):
            close_t = df_calc['close'].iloc[-t]
            sma_t = df_calc['sma'].iloc[-t]
            if pd.isna(sma_t):
                break
            upper_t = sma_t * (1 + buffer_rate)
            lower_t = sma_t * (1 - buffer_rate)
            
            if close_t >= upper_t:
                market_filter_state = "Bull"
                break
            elif close_t < lower_t:
                market_filter_state = "Bear"
                break

    return {
        "sma": sma,
        "upper_buffer": upper_buffer,
        "lower_buffer": lower_buffer,
        "status": status,
        "status_label": status_label,
        "market_filter_state": market_filter_state
    }


def calculate_eth_indicators(df: pd.DataFrame, sma_len: int = 50, atr_len: int = 14, atr_multiplier: float = 1.5):
    """
    ETH 이동평균선 및 ATR 변동성 채널 밴드를 연산합니다.
    
    Parameters:
        df (pd.DataFrame): 일봉 데이터 ('high', 'low', 'close' 컬럼 필요)
        sma_len (int): 단순 이동평균(SMA) 기간
        atr_len (int): ATR 기간 (기본 14)
        atr_multiplier (float): ATR 승수 K값 (기본 1.5)
        
    Returns:
        dict:
            - sma (float): 전일 완료봉 기준 SMA
            - atr_14 (float): 전일 완료봉 기준 ATR
            - upper_band (float): 상한 밴드 가격
            - lower_band (float): 하한 밴드 가격
            - status (str): 'bull' | 'bear' | 'neutral'
            - status_label (str): 한글 상태 설명
    """
    df_calc = df.copy()
    df_calc['sma'] = df_calc['close'].rolling(window=sma_len).mean()
    
    prev_close = df_calc['close'].shift(1)
    tr1 = df_calc['high'] - df_calc['low']
    tr2 = (df_calc['high'] - prev_close).abs()
    tr3 = (df_calc['low'] - prev_close).abs()
    df_calc['tr'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df_calc['atr'] = df_calc['tr'].rolling(window=atr_len).mean()
    
    # 전일 완료 일봉 기준 (미완성 당일 봉 제외: iloc[-2])
    sma = float(df_calc['sma'].iloc[-2])
    atr_14 = float(df_calc['atr'].iloc[-2])
    upper_band = sma + (atr_14 * atr_multiplier)
    lower_band = sma - (atr_14 * atr_multiplier)
    
    # 현재 가격
    current_price = float(df_calc['close'].iloc[-1])
    
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
        "sma": sma,
        "atr_14": atr_14,
        "upper_band": upper_band,
        "lower_band": lower_band,
        "status": status,
        "status_label": status_label
    }


def calculate_supertrend(df: pd.DataFrame, period: int = 7, multiplier: float = 3.5):
    """
    SuperTrend(슈퍼트렌드) 지표를 연산합니다.
    
    Parameters:
        df (pd.DataFrame): 일봉 데이터 ('high', 'low', 'close' 컬럼 필요)
        period (int): ATR 기간 (기본 7)
        multiplier (float): ATR 승수 (기본 3.5)
        
    Returns:
        pd.DataFrame: 원본 DataFrame에 'supertrend', 'supertrend_direction' 컬럼이 추가된 복사본
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
        # 상한 밴드 계산
        if basic_upper.iloc[i] < final_upper.iloc[i-1] or close.iloc[i-1] > final_upper.iloc[i-1]:
            final_upper.iloc[i] = basic_upper.iloc[i]
        else:
            final_upper.iloc[i] = final_upper.iloc[i-1]
            
        # 하한 밴드 계산
        if basic_lower.iloc[i] > final_lower.iloc[i-1] or close.iloc[i-1] < final_lower.iloc[i-1]:
            final_lower.iloc[i] = basic_lower.iloc[i]
        else:
            final_lower.iloc[i] = final_lower.iloc[i-1]
            
        # 방향 판정
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


def calculate_bithumb_eth_indicators(df: pd.DataFrame, sma_len: int = 50, st_period: int = 7, st_multiplier: float = 3.5):
    """
    빗썸 서브 전략(이더리움 SuperTrend + 50일 SMA 추세 추종) 지표 및 매매 판정을 연산합니다.
    
    Parameters:
        df (pd.DataFrame): 일봉 데이터 ('high', 'low', 'close' 컬럼 필요)
        sma_len (int): 대추세 필터 SMA 기간 (기본 50일)
        st_period (int): SuperTrend ATR 기간 (기본 7일)
        st_multiplier (float): SuperTrend 승수 (기본 3.5)
        
    Returns:
        dict:
            - current_price (float): 최신 현재가
            - sma50 (float): 전일 완료봉 기준 50일 SMA
            - supertrend_val (float): 전일 완료봉 기준 SuperTrend 가격
            - supertrend_trend (str): 'BULL' | 'BEAR'
            - is_above_sma (bool): 현재가 >= 50일 SMA 여부
            - action (str): 'BUY' | 'SELL' (100% 매수/보유 vs 100% 현금화)
            - status_label (str): 한글 상태 설명
    """
    df_st = calculate_supertrend(df, period=st_period, multiplier=st_multiplier)
    df_st['sma50'] = df_st['close'].rolling(window=sma_len).mean()
    
    # 전일 완료봉 기준 지표 (iloc[-2])
    sma50 = float(df_st['sma50'].iloc[-2])
    supertrend_val = float(df_st['supertrend'].iloc[-2])
    direction_val = int(df_st['supertrend_direction'].iloc[-2])
    supertrend_trend = "BULL" if direction_val == 1 else "BEAR"
    
    # 현재 가격
    current_price = float(df_st['close'].iloc[-1])
    is_above_sma = current_price >= sma50
    
    # 매매 판정: 50일 SMA 이상이고 SuperTrend가 BULL일 때만 100% 매수/보유
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
