# -*- coding: utf-8 -*-
import unittest

class TestCashAllocationLogic(unittest.TestCase):
    def test_cash_allocation_with_idle_cash(self):
        """계좌에 코인이 이미 있어도 유휴 현금이 있으면 목표 비중(50%)까지 추가 매수하는지 검증"""
        btc_price = 100_000_000.0  # 1억
        eth_price = 4_000_000.0    # 4백만

        # 보유 현황: BTC 0.001 (10만원), ETH 0.025 (10만원), KRW 80만원
        upbit_btc_bal = 0.001
        upbit_eth_bal = 0.025
        upbit_krw = 800_000.0
        min_order = 5000.0

        btc_target_state = 'hold'
        eth_target_state = 'hold'

        btc_val = upbit_btc_bal * btc_price  # 100,000
        eth_val = upbit_eth_bal * eth_price  # 100,000
        total_value = upbit_krw + btc_val + eth_val  # 1,000,000

        target_val_btc = total_value * 0.5  # 500,000
        target_val_eth = total_value * 0.5  # 500,000

        needed_btc = max(0.0, target_val_btc - btc_val)  # 400,000
        needed_eth = max(0.0, target_val_eth - eth_val)  # 400,000

        self.assertEqual(needed_btc, 400_000.0)
        self.assertEqual(needed_eth, 400_000.0)

        # BTC 매수 시뮬레이션
        buy_amt_btc = min(needed_btc, upbit_krw * 0.995)
        upbit_btc_bal += buy_amt_btc / btc_price
        upbit_krw -= buy_amt_btc

        # ETH 매수 시뮬레이션
        buy_amt_eth = min(needed_eth, upbit_krw * 0.995)
        upbit_eth_bal += buy_amt_eth / eth_price
        upbit_krw -= buy_amt_eth

        final_btc_val = upbit_btc_bal * btc_price
        final_eth_val = upbit_eth_bal * eth_price

        # 검증: 두 코인 모두 목표치(약 50만원)에 도달했는지 확인
        self.assertAlmostEqual(final_btc_val, 500_000.0, delta=5000.0)
        self.assertAlmostEqual(final_eth_val, 500_000.0, delta=5000.0)
        self.assertLess(upbit_krw, min_order)  # 유휴 현금이 거의 소진되었는지 확인

    def test_single_asset_bull_market(self):
        """BTC만 상승장이고 ETH는 하락장일 때, BTC는 50%까지만 사고 50%는 현금 유지하는지 검증"""
        btc_price = 100_000_000.0
        eth_price = 4_000_000.0

        upbit_btc_bal = 0.001  # 10만원
        upbit_eth_bal = 0.0    # 0원
        upbit_krw = 900_000.0  # 90만원

        btc_target_state = 'hold'
        eth_target_state = 'cash'

        btc_val = upbit_btc_bal * btc_price  # 100,000
        eth_val = 0.0
        total_value = upbit_krw + btc_val + eth_val  # 1,000,000

        target_val_btc = total_value * 0.5  # 500,000
        target_val_eth = 0.0                # 0

        needed_btc = max(0.0, target_val_btc - btc_val)  # 400,000
        needed_eth = max(0.0, target_val_eth - eth_val)  # 0

        self.assertEqual(needed_btc, 400_000.0)
        self.assertEqual(needed_eth, 0.0)

        # BTC 매수 후 잔여 현금이 50만원 수준으로 안전하게 보존되는지 확인
        buy_amt_btc = min(needed_btc, upbit_krw * 0.995)
        upbit_btc_bal += buy_amt_btc / btc_price
        upbit_krw -= buy_amt_btc

        self.assertAlmostEqual(upbit_btc_bal * btc_price, 500_000.0, delta=5000.0)
        self.assertAlmostEqual(upbit_krw, 500_000.0, delta=5000.0)


if __name__ == '__main__':
    unittest.main()
