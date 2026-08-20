# -*- coding: utf-8 -*-
import time
import uuid
import hmac
import hashlib
import jwt
import requests
import logging
from urllib.parse import urlencode
from config import BITHUMB_ACCESS_KEY, BITHUMB_SECRET_KEY, DRY_RUN

# 기본 로깅 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class BithumbClient:
    def __init__(self, access_key=None, secret_key=None):
        self.access_key = access_key or BITHUMB_ACCESS_KEY
        self.secret_key = secret_key or BITHUMB_SECRET_KEY
        self.base_url = "https://api.bithumb.com"

    def _get_headers(self, params=None):
        """
        빗썸 v1 Private API 요청을 위한 JWT 인증 헤더를 생성합니다.
        """
        payload = {
            "access_key": self.access_key,
            "nonce": str(uuid.uuid4()),
            "timestamp": int(time.time() * 1000)
        }
        
        # 파라미터가 있을 경우 쿼리 스트링으로 변환하여 SHA512 해싱 후 payload에 추가
        if params:
            # 쿼리 해싱 시 문자열 정렬 등을 보장하기 위해 쿼리 스트링으로 변환
            query_string = urlencode(params)
            query_hash = hashlib.sha512(query_string.encode("utf-8")).hexdigest()
            payload["query_hash"] = query_hash
            payload["query_hash_alg"] = "SHA512"
            
        token = jwt.encode(payload, self.secret_key, algorithm="HS256")
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        return headers

    def get_balances(self):
        """
        전체 계좌 잔고를 조회합니다.
        """
        url = f"{self.base_url}/v1/accounts"
        headers = self._get_headers()
        
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            raise Exception(f"빗썸 잔고 조회 실패 (상태 코드: {response.status_code}): {response.text}")
        return response.json()

    def get_balance(self, currency):
        """
        특정 통화(예: KRW, BTC, XRP)의 사용 가능한 잔액(balance)을 반환합니다.
        """
        balances = self.get_balances()
        for asset in balances:
            if asset.get("currency") == currency:
                return float(asset.get("balance", 0.0))
        return 0.0

    def get_balance_detail(self, currency):
        """
        특정 통화의 잔고 상세 정보(balance, locked, avg_buy_price)를 딕셔너리로 반환합니다.
        """
        balances = self.get_balances()
        for asset in balances:
            if asset.get("currency") == currency:
                return {
                    "balance": float(asset.get("balance", 0.0)),
                    "locked": float(asset.get("locked", 0.0)),
                    "avg_buy_price": float(asset.get("avg_buy_price", 0.0))
                }
        return {"balance": 0.0, "locked": 0.0, "avg_buy_price": 0.0}

    def get_markets(self):
        """
        거래 가능한 모든 마켓 정보를 가져옵니다. (공용 API)
        """
        url = f"{self.base_url}/v1/market/all"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            raise Exception(f"빗썸 마켓 목록 조회 실패 (상태 코드: {response.status_code}): {response.text}")
        return response.json()

    def get_ohlcv(self, market, count=200):
        """
        지정한 마켓의 최근 일봉 캔들 정보를 가져옵니다. (공용 API)
        반환 결과는 최신 캔들(오늘)부터 과거 캔들 순(내림차순)으로 정렬되어 있습니다.
        """
        url = f"{self.base_url}/v1/candles/days"
        params = {"market": market, "count": count}
        
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            raise Exception(f"빗썸 {market} 캔들 조회 실패 (상태 코드: {response.status_code}): {response.text}")
        return response.json()

    def buy_market_order(self, market, price):
        """
        시장가 매수 주문을 요청합니다.
        market: 마켓 심볼 (예: 'KRW-XRP')
        price: 매수 총액 (KRW 단위)
        """
        params = {
            "market": market,
            "side": "bid",
            "price": str(price),
            "ord_type": "price"
        }
        
        if DRY_RUN:
            logging.info(f"[드라이런] 빗썸 시장가 매수 주문 모의 실행: {market} - {price} KRW")
            return {"uuid": f"dryrun-buy-{uuid.uuid4()}", "side": "bid", "ord_type": "price", "price": str(price), "state": "done"}

        url = f"{self.base_url}/v1/orders"
        headers = self._get_headers(params)
        
        # POST 요청 본문은 JSON 문자열로 전송
        response = requests.post(url, json=params, headers=headers, timeout=10)
        if response.status_code not in (200, 201):
            raise Exception(f"빗썸 시장가 매수 주문 실패 (상태 코드: {response.status_code}): {response.text}")
        return response.json()

    def sell_market_order(self, market, volume):
        """
        시장가 매도 주문을 요청합니다.
        market: 마켓 심볼 (예: 'KRW-XRP')
        volume: 매도 수량
        """
        params = {
            "market": market,
            "side": "ask",
            "volume": str(volume),
            "ord_type": "market"
        }
        
        if DRY_RUN:
            logging.info(f"[드라이런] 빗썸 시장가 매도 주문 모의 실행: {market} - {volume} 수량")
            return {"uuid": f"dryrun-sell-{uuid.uuid4()}", "side": "ask", "ord_type": "market", "volume": str(volume), "state": "done"}

        url = f"{self.base_url}/v1/orders"
        headers = self._get_headers(params)
        
        response = requests.post(url, json=params, headers=headers, timeout=10)
        if response.status_code not in (200, 201):
            raise Exception(f"빗썸 시장가 매도 주문 실패 (상태 코드: {response.status_code}): {response.text}")
        return response.json()
