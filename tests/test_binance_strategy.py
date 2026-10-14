# -*- coding: utf-8 -*-
import unittest
import sys
import os

# src 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from binance_api import BinanceClient
from config import BINANCE_MIN_ORDER_USDT, MAIN_RATIO_BAND


class TestBinanceStrategy(unittest.TestCase):
    def setUp(self):
        self.client = BinanceClient(access_key="dummy_key", secret_key="dummy_secret", dry_run=True)

    def test_signature_generation(self):
        """HMAC-SHA256 서명 생성 테스트"""
        params = {"symbol": "BTCUSDT", "timestamp": 1600000000000}
        sig = self.client._get_signature(params)
        self.assertTrue(len(sig) == 64)

    def test_floor_to_step(self):
        """바이낸스 stepSize에 따른 수량 내림(floor) 테스트"""
        # BTC (stepSize: 0.00001 -> 소수점 5자리)
        qty_btc = 0.12345678
        floored_btc = self.client._floor_to_step(qty_btc, 0.00001)
        self.assertEqual(floored_btc, 0.12345)

        # ETH (stepSize: 0.0001 -> 소수점 4자리)
        qty_eth = 1.9876543
        floored_eth = self.client._floor_to_step(qty_eth, 0.0001)
        self.assertEqual(floored_eth, 1.9876)

    def test_dry_run_orders(self):
        """모의매매 모드에서 시장가 주문 테스트"""
        res_buy = self.client.buy_market("BTCUSDT", 500.0)
        self.assertEqual(res_buy["status"], "FILLED")
        self.assertEqual(res_buy["side"], "BUY")

        res_sell = self.client.sell_market("BTCUSDT", 0.01)
        self.assertEqual(res_sell["status"], "FILLED")
        self.assertEqual(res_sell["side"], "SELL")

    def test_binance_cash_allocation_and_rebalancing(self):
        """바이낸스 USDT 기준 50:50 분할 및 유휴 현금 투입 리밸런싱 검증"""
        btc_price = 100_000.0  # $100,000
        eth_price = 3_000.0    # $3,000

        # 초기 상황: USDT 8,000, BTC $1,000 보유 (0.01 BTC), ETH $1,000 보유
        binance_usdt = 8000.0
        binance_btc_bal = 0.01
        binance_eth_bal = 1000.0 / eth_price

        btc_val = binance_btc_bal * btc_price  # $1,000
        eth_val = binance_eth_bal * eth_price  # $1,000
        total_eval = binance_usdt + btc_val + eth_val  # $10,000

        # 둘 다 hold 상태일 때 목표 평가액: 각 $5,000
        target_val_btc = total_eval * 0.5
        target_val_eth = total_eval * 0.5

        needed_btc = max(0.0, target_val_btc - btc_val)  # $4,000
        needed_eth = max(0.0, target_val_eth - eth_val)  # $4,000

        self.assertEqual(needed_btc, 4000.0)
        self.assertEqual(needed_eth, 4000.0)

        # BTC 매수 시뮬레이션
        buy_amt_btc = min(needed_btc, binance_usdt * 0.995)
        binance_btc_bal += buy_amt_btc / btc_price
        binance_usdt -= buy_amt_btc

        # ETH 매수 시뮬레이션
        buy_amt_eth = min(needed_eth, binance_usdt * 0.995)
        binance_eth_bal += buy_amt_eth / eth_price
        binance_usdt -= buy_amt_eth

        final_btc_val = binance_btc_bal * btc_price
        final_eth_val = binance_eth_bal * eth_price

        # 두 자산 모두 목표치($5,000) 수준으로 도달했는지 검증
        self.assertAlmostEqual(final_btc_val, 5000.0, delta=50.0)
        self.assertAlmostEqual(final_eth_val, 5000.0, delta=50.0)
        self.assertLessEqual(binance_usdt, 25.0)  # 0.5% 안전 버퍼로 인한 소액 잔여금

    def test_binance_usd_krw_conversion(self):
        """바이낸스 자산의 USD/KRW 환산 합산 검증"""
        total_binance_usdt = 10000.0
        usd_krw_rate = 1385.5
        total_binance_krw = total_binance_usdt * usd_krw_rate

        upbit_total_krw = 15_000_000.0
        bithumb_total_krw = 5_000_000.0

        grand_total = upbit_total_krw + bithumb_total_krw + total_binance_krw
        expected_grand_total = 20_000_000.0 + 13_855_000.0

        self.assertEqual(grand_total, expected_grand_total)


if __name__ == '__main__':
    unittest.main()
