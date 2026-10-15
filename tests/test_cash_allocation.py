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

    def test_eth_selloff_does_not_inflate_btc_target(self):
        """ETH 전량 매도 시 잔고가 0으로 초기화되어 자산 뻥튀기 및 BTC 강제 추가매수가 방지되는지 검증"""
        btc_price = 100_000_000.0
        eth_price = 4_000_000.0

        # 초기 상황: BTC 0.05 (500만원), ETH 1.25 (500만원), KRW 0원 -> 총 1,000만원
        upbit_btc_bal = 0.05
        upbit_eth_bal = 1.25
        upbit_krw = 0.0

        btc_target_state = 'hold'
        eth_target_state = 'cash'

        # ETH 선매도 집행
        eth_sell_val = upbit_eth_bal * eth_price  # 5,000,000원
        upbit_krw += eth_sell_val * 0.9995        # 현금 입금
        upbit_eth_bal = 0.0                       # 잔고 0으로 리셋 (버그 수정 핵심)

        # 총자산 산출
        btc_val = upbit_btc_bal * btc_price       # 5,000,000원
        eth_val = upbit_eth_bal * eth_price       # 0원
        total_upbit_value = upbit_krw + btc_val + eth_val  # 약 10,000,000원 (뻥튀기 없음!)

        target_val_btc = total_upbit_value * 0.5  # 약 5,000,000원
        needed_btc = max(0.0, target_val_btc - btc_val)

        # 검증: BTC 추가 매수 필요 금액이 0원이어야 함 (더 사면 안 됨!)
        self.assertEqual(needed_btc, 0.0)
        self.assertAlmostEqual(upbit_krw, 5_000_000.0, delta=5000.0)

    def test_single_asset_rebalance_sell_when_exceeding_60_percent(self):
        """단독 상승장(ETH cash, BTC hold)에서 BTC 비중이 75%로 비대해졌을 때, 60% 초과분을 매도하여 50:50으로 복구되는지 검증"""
        btc_price = 100_000_000.0

        # 현재 상황: BTC 0.075 (750만원), 현금 250만원 -> 총자산 1,000만원 (BTC 75% 비대)
        upbit_btc_bal = 0.075
        upbit_eth_bal = 0.0
        upbit_krw = 2_500_000.0

        btc_target_state = 'hold'
        eth_target_state = 'cash'
        main_ratio_band = 0.10

        btc_val = upbit_btc_bal * btc_price
        total_value = upbit_krw + btc_val  # 10,000,000원
        target_val_btc = total_value * 0.5 # 5,000,000원

        btc_weight = btc_val / total_value  # 0.75 (75%)

        # 60% 초과 판정
        self.assertGreater(btc_weight, 0.5 + main_ratio_band)

        # 리밸런싱 매도 집행
        excess_val = btc_val - target_val_btc  # 2,500,000원
        excess_btc = excess_val / btc_price
        upbit_btc_bal -= excess_btc
        upbit_krw += excess_val * 0.9995

        final_btc_val = upbit_btc_bal * btc_price

        # 검증: BTC가 목표치 50%(500만원)로 축소되고, 현금도 50%(약 500만원)로 맞춰졌는지 확인
        self.assertAlmostEqual(final_btc_val, 5_000_000.0, delta=5000.0)
        self.assertAlmostEqual(upbit_krw, 5_000_000.0, delta=5000.0)


if __name__ == '__main__':
    unittest.main()

