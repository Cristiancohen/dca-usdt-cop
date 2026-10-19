import os
import unittest
from decimal import Decimal
from unittest.mock import patch

import manual_order


FILTERS = {
    "tick_size": Decimal("1"), "min_price": Decimal("2480"), "max_price": Decimal("3720"),
    "step_size": Decimal("1"), "min_qty": Decimal("1"), "max_qty": Decimal("900000"),
    "min_notional": Decimal("4000"), "max_notional": Decimal("5000000000"),
}
BOOK = {"bidPrice": "2999", "askPrice": "3001"}
ACCOUNT = {
    "canTrade": True,
    "permissions": ["SPOT"],
    "balances": [{"asset": "COP", "free": "1000000"}, {"asset": "USDT", "free": "20"}],
}
PAYLOAD = {"lado": "buy", "precio": "2900", "cantidad": "2", "timestamp": "2026-04-03T12:00:00Z"}


class ManualOrderTests(unittest.TestCase):
    def test_buy_sends_one_limit_buy_after_validation(self):
        with patch("trade.symbol_filters", return_value=FILTERS), \
             patch("trade.book_ticker", return_value=BOOK), \
             patch("trade.account", return_value=ACCOUNT), \
             patch("trade.place_limit_buy", return_value={"orderId": 12, "status": "NEW"}) as place:
            result = manual_order.execute_order(PAYLOAD)
        place.assert_called_once_with(Decimal("2"), Decimal("2900"))
        self.assertEqual(result["side"], "BUY")
        self.assertEqual(result["response"]["orderId"], 12)

    def test_sell_uses_sell_asset_balance_and_sends_limit_sell(self):
        payload = {**PAYLOAD, "lado": "sell", "precio": "3100", "cantidad": "3"}
        with patch("trade.symbol_filters", return_value=FILTERS), \
             patch("trade.book_ticker", return_value=BOOK), \
             patch("trade.account", return_value=ACCOUNT), \
             patch("trade.place_limit_sell", return_value={"orderId": 13, "status": "NEW"}) as place:
            result = manual_order.execute_order(payload)
        place.assert_called_once_with(Decimal("3"), Decimal("3100"))
        self.assertEqual(result["side"], "SELL")

    def test_insufficient_balance_blocks_order(self):
        poor = {**ACCOUNT, "balances": [{"asset": "COP", "free": "100"}]}
        with patch("trade.symbol_filters", return_value=FILTERS), \
             patch("trade.book_ticker", return_value=BOOK), \
             patch("trade.account", return_value=poor), \
             patch("trade.place_limit_buy") as place:
            with self.assertRaisesRegex(ValueError, "Saldo COP insuficiente"):
                manual_order.execute_order(PAYLOAD)
        place.assert_not_called()

    def test_crossing_buy_is_blocked(self):
        payload = {**PAYLOAD, "precio": "3001"}
        with patch("trade.symbol_filters", return_value=FILTERS), \
             patch("trade.book_ticker", return_value=BOOK), \
             patch("trade.account") as account, \
             patch("trade.place_limit_buy") as place:
            with self.assertRaisesRegex(ValueError, "cruzaría"):
                manual_order.execute_order(payload)
        account.assert_not_called()
        place.assert_not_called()

    def test_unknown_side_and_timestamp_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "lado"):
            manual_order.execute_order({**PAYLOAD, "lado": "market"})
        with self.assertRaisesRegex(ValueError, "ISO-8601"):
            manual_order.execute_order({**PAYLOAD, "timestamp": "ayer"})

    def test_run_writes_result_to_github_step_summary(self):
        payload_json = '{"lado":"buy","precio":"2900","cantidad":"2","timestamp":"2026-04-03T12:00:00Z"}'
        with patch.dict(os.environ, {"MANUAL_ORDER_PAYLOAD": payload_json}), \
             patch("manual_order.execute_order", return_value={
                 "side": "BUY", "price": Decimal("2900"), "quantity": Decimal("2"),
                 "timestamp": "2026-04-03T12:00:00+00:00", "response": {"orderId": 15, "status": "NEW"}
             }), \
             patch("manual_order._write_summary") as summary:
            self.assertEqual(manual_order.main(), 0)
        self.assertIn("Order ID", summary.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
