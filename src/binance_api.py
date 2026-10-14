# -*- coding: utf-8 -*-
"""
바이낸스(Binance) 현물 REST API 연동 클라이언트 모듈.
- 일봉 시세(Klines) 조회 (Public)
- 실시간 가격(Ticker Price) 조회 (Public)
- 계좌 잔고(Account Balances) 조회 (Private, HMAC-SHA256)
- 시장가 매수/매도 주문 집행 (Private, HMAC-SHA256)
"""
import time
import hmac
import hashlib
import math
import requests
import logging
import pandas as pd
from urllib.parse import urlencode

from config import BINANCE_ACCESS_KEY, BINANCE_SECRET_KEY, DRY_RUN

logger = logging.getLogger(__name__)


class BinanceClient:
    def __init__(self, access_key=None, secret_key=None, dry_run=None):
        self.access_key = access_key or BINANCE_ACCESS_KEY
        self.secret_key = secret_key or BINANCE_SECRET_KEY
        self.dry_run = dry_run if dry_run is not None else DRY_RUN
        self.base_url = "https://api.binance.com"
        self._symbol_filters = {}

    def _get_signature(self, params: dict) -> str:
        """HMAC-SHA256 서명 생성"""
        query_string = urlencode(params)
        return hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    def _get_headers(self) -> dict:
        """Private API 호출용 헤더"""
        return {
            "X-MBX-APIKEY": self.access_key,
            "Content-Type": "application/x-www-form-urlencoded"
        }

    def _send_signed_request(self, method: str, endpoint: str, params: dict = None) -> dict:
        """서명이 포함된 비공개 요청 전송 (재시도 로직 포함)"""
        if not self.access_key or not self.secret_key:
            raise ValueError("바이낸스 API Key 또는 Secret이 설정되지 않았습니다.")

        params = params.copy() if params else {}
        params['timestamp'] = int(time.time() * 1000)
        params['recvWindow'] = 5000
        params['signature'] = self._get_signature(params)

        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()

        for attempt in range(3):
            try:
                if method.upper() == 'GET':
                    res = requests.get(url, headers=headers, params=params, timeout=10)
                elif method.upper() == 'POST':
                    res = requests.post(url, headers=headers, data=params, timeout=10)
                else:
                    raise ValueError(f"지원하지 않는 HTTP 메서드: {method}")

                if res.status_code == 200:
                    return res.json()
                elif res.status_code == 400:
                    # 파라미터 에러 등은 즉시 예외
                    raise Exception(f"바이낸스 요청 오류 [HTTP 400]: {res.text}")
                else:
                    logger.warning(f"바이낸스 요청 실패 (시도 {attempt+1}/3, 상태 {res.status_code}): {res.text}")
                    time.sleep(1)
            except requests.RequestException as e:
                logger.warning(f"바이낸스 통신 예외 발생 (시도 {attempt+1}/3): {e}")
                time.sleep(1)

        raise Exception(f"바이낸스 요청 최종 실패: {endpoint}")

    # ==========================================
    # Public API (시세 조회)
    # ==========================================

    def get_current_price(self, symbol: str) -> float:
        """
        현재 티커 가격을 조회합니다. (예: 'BTCUSDT', 'ETHUSDT')
        """
        url = f"{self.base_url}/api/v3/ticker/price"
        params = {"symbol": symbol}
        try:
            res = requests.get(url, params=params, timeout=10)
            if res.status_code == 200:
                return float(res.json()['price'])
            raise Exception(f"바이낸스 시세 조회 실패: {res.text}")
        except Exception as e:
            logger.error(f"[{symbol}] 시세 조회 중 오류: {e}")
            raise

    def get_daily_candles(self, symbol: str, limit: int = 250) -> pd.DataFrame:
        """
        최근 일봉(1d) 캔들 데이터를 조회하여 DataFrame으로 반환합니다.
        바이낸스 일봉은 UTC 00:00(09:00 KST)에 마감됩니다.
        """
        url = f"{self.base_url}/api/v3/klines"
        params = {
            "symbol": symbol,
            "interval": "1d",
            "limit": limit
        }
        for attempt in range(3):
            try:
                res = requests.get(url, params=params, timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    records = []
                    for k in data:
                        records.append({
                            'time': int(k[0]),
                            'open': float(k[1]),
                            'high': float(k[2]),
                            'low': float(k[3]),
                            'close': float(k[4]),
                            'volume': float(k[5])
                        })
                    df = pd.DataFrame(records)
                    return df
                time.sleep(1)
            except Exception as e:
                logger.warning(f"[{symbol}] 캔들 조회 실패 (시도 {attempt+1}/3): {e}")
                time.sleep(1)

        raise Exception(f"[{symbol}] 일봉 캔들 조회 최종 실패")

    # ==========================================
    # Private API (잔고 조회 & 주문)
    # ==========================================

    def get_balances(self) -> dict:
        """
        전체 잔고 중 보유 수량(free + locked > 0)이 있는 자산 목록을 딕셔너리로 반환합니다.
        반환 예시: {'USDT': {'free': 100.0, 'locked': 0.0, 'total': 100.0}, ...}
        """
        if self.dry_run:
            # 모의매매 가상 잔고
            return {
                'USDT': {'free': 10000.0, 'locked': 0.0, 'total': 10000.0},
                'BTC': {'free': 0.0, 'locked': 0.0, 'total': 0.0},
                'ETH': {'free': 0.0, 'locked': 0.0, 'total': 0.0}
            }

        res = self._send_signed_request('GET', '/api/v3/account')
        balances = {}
        for b in res.get('balances', []):
            free = float(b.get('free', 0.0))
            locked = float(b.get('locked', 0.0))
            total = free + locked
            if total > 0.0000001:
                balances[b['asset']] = {
                    'free': free,
                    'locked': locked,
                    'total': total
                }
        return balances

    def get_balance(self, asset: str) -> float:
        """특정 자산의 사용 가능한(free) 잔고 수량을 반환합니다."""
        balances = self.get_balances()
        return balances.get(asset, {}).get('free', 0.0)

    def get_symbol_step_size(self, symbol: str) -> float:
        """심볼의 최소 주문 수량 단위(stepSize)를 조회합니다."""
        if symbol in self._symbol_filters:
            return self._symbol_filters[symbol]

        try:
            url = f"{self.base_url}/api/v3/exchangeInfo"
            res = requests.get(url, params={"symbol": symbol}, timeout=10)
            if res.status_code == 200:
                data = res.json()
                for f in data['symbols'][0]['filters']:
                    if f['filterType'] == 'LOT_SIZE':
                        step = float(f['stepSize'])
                        self._symbol_filters[symbol] = step
                        return step
        except Exception as e:
            logger.warning(f"[{symbol}] stepSize 조회 실패 ({e}), 기본값 사용")

        # 기본값 (안전 버퍼)
        default_step = 0.00001 if "BTC" in symbol else 0.0001
        self._symbol_filters[symbol] = default_step
        return default_step

    def _floor_to_step(self, qty: float, step: float) -> float:
        """수량을 stepSize에 맞추어 내림(floor)합니다."""
        precision = max(0, int(round(-math.log10(step))))
        factor = 10 ** precision
        return math.floor(qty * factor) / factor

    def buy_market(self, symbol: str, quote_order_qty: float) -> dict:
        """
        시장가 매수 주문 (금액 기준 매수, quoteOrderQty)
        - symbol: 'BTCUSDT', 'ETHUSDT'
        - quote_order_qty: 투입할 USDT 금액
        """
        if self.dry_run:
            logger.info(f"[DRY-RUN] 바이낸스 {symbol} 시장가 매수 주문 가상 체결 (투입: ${quote_order_qty:,.2f} USDT)")
            return {
                "symbol": symbol,
                "orderId": 99999999,
                "status": "FILLED",
                "cummulativeQuoteQty": str(quote_order_qty),
                "side": "BUY"
            }

        params = {
            "symbol": symbol,
            "side": "BUY",
            "type": "MARKET",
            "quoteOrderQty": f"{quote_order_qty:.2f}"
        }
        logger.info(f"[LIVE] 바이낸스 {symbol} 시장가 매수 요청 (금액: ${quote_order_qty:.2f} USDT)")
        return self._send_signed_request('POST', '/api/v3/order', params)

    def sell_market(self, symbol: str, quantity: float) -> dict:
        """
        시장가 매도 주문 (수량 기준 매도)
        - symbol: 'BTCUSDT', 'ETHUSDT'
        - quantity: 매도할 코인 수량 (stepSize에 맞추어 자동 내림)
        """
        step = self.get_symbol_step_size(symbol)
        adjusted_qty = self._floor_to_step(quantity, step)

        if adjusted_qty <= 0:
            logger.warning(f"[{symbol}] 유효 주문 수량이 0 이하이므로 매도 주문을 취소합니다.")
            return {}

        # 수량 포맷팅
        precision = max(0, int(round(-math.log10(step))))
        qty_str = f"{adjusted_qty:.{precision}f}"

        if self.dry_run:
            logger.info(f"[DRY-RUN] 바이낸스 {symbol} 시장가 매도 주문 가상 체결 (수량: {qty_str})")
            return {
                "symbol": symbol,
                "orderId": 99999999,
                "status": "FILLED",
                "executedQty": qty_str,
                "side": "SELL"
            }

        params = {
            "symbol": symbol,
            "side": "SELL",
            "type": "MARKET",
            "quantity": qty_str
        }
        logger.info(f"[LIVE] 바이낸스 {symbol} 시장가 매도 요청 (수량: {qty_str})")
        return self._send_signed_request('POST', '/api/v3/order', params)
