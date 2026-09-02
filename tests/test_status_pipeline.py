import unittest
import os
import json
import tempfile
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from main import build_chart_series, export_web_status_json, auto_push_status_json


class TestStatusPipeline(unittest.TestCase):
    def setUp(self):
        dates = [datetime(2026, 1, 1) + timedelta(days=i) for i in range(250)]
        np.random.seed(42)
        btc_prices = 100000000 + np.cumsum(np.random.randn(250) * 1000000)
        eth_prices = 3000000 + np.cumsum(np.random.randn(250) * 50000)
        
        self.btc_df = pd.DataFrame({
            'open': btc_prices * 0.99,
            'high': btc_prices * 1.02,
            'low': btc_prices * 0.98,
            'close': btc_prices,
            'volume': 1000.0
        }, index=dates)
        
        self.eth_df = pd.DataFrame({
            'open': eth_prices * 0.99,
            'high': eth_prices * 1.02,
            'low': eth_prices * 0.98,
            'close': eth_prices,
            'volume': 5000.0
        }, index=dates)

    def test_build_chart_series_structure(self):
        chart_data = build_chart_series(self.btc_df, self.eth_df, chart_count=60)
        self.assertIsNotNone(chart_data)
        self.assertIn("dates", chart_data)
        self.assertIn("btc", chart_data)
        self.assertIn("eth", chart_data)
        self.assertIn("bithumb", chart_data)
        
        self.assertEqual(len(chart_data["dates"]), 60)
        self.assertEqual(len(chart_data["btc"]["closes"]), 60)
        self.assertEqual(len(chart_data["btc"]["sma"]), 60)
        self.assertEqual(len(chart_data["btc"]["upper"]), 60)
        self.assertEqual(len(chart_data["btc"]["lower"]), 60)
        
        self.assertEqual(len(chart_data["eth"]["closes"]), 60)
        self.assertEqual(len(chart_data["eth"]["sma"]), 60)
        self.assertEqual(len(chart_data["eth"]["upper"]), 60)
        self.assertEqual(len(chart_data["eth"]["lower"]), 60)
        
        self.assertEqual(len(chart_data["bithumb"]["supertrend"]), 60)
        self.assertEqual(len(chart_data["bithumb"]["direction"]), 60)
        
        for d in chart_data["bithumb"]["direction"]:
            self.assertIn(d, [1, -1])

    def test_build_chart_series_short_data(self):
        # Even with short data, it should not crash
        short_btc = self.btc_df.iloc[-30:]
        short_eth = self.eth_df.iloc[-30:]
        chart_data = build_chart_series(short_btc, short_eth, chart_count=60)
        self.assertIsNotNone(chart_data)
        self.assertEqual(len(chart_data["dates"]), 30)

    def test_export_web_status_json(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            temp_path = tf.name
            
        try:
            sample_payload = {
                "updated_at": "2026-09-01T09:05:00+09:00",
                "mode": "live",
                "upbit": {"btc": {"status": "bull"}},
                "chart": {"dates": ["09-01"], "btc": {"closes": [100000000]}}
            }
            
            export_web_status_json(sample_payload, file_path=temp_path)
            
            self.assertTrue(os.path.exists(temp_path))
            with open(temp_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                
            self.assertEqual(loaded["mode"], "live")
            self.assertIn("chart", loaded)
            self.assertEqual(loaded["chart"]["btc"]["closes"], [100000000])
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_auto_push_status_json_handles_exceptions(self):
        success = auto_push_status_json(target_file="docs/data/status.json", skip_push=True)
        self.assertTrue(success)


if __name__ == "__main__":
    unittest.main()
