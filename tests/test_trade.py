import unittest
from decimal import Decimal
from unittest.mock import patch

import trade


FILTERS = {
    "tick_size": Decimal("1"), "min_price": Decimal("2480"), "max_price": Decimal("3720"),
    "step_size": Decimal("1"), "min_qty": Decimal("1"), "max_qty": Decimal("900000"),
    "min_notional": Decimal("4000"), "max_notional": Decimal("5000000000"),
}


class LimitOrderTests(unittest.TestCase):
    def test_buy_rounds_price_and_quantity_down_and_only_sends_limit(self):
        with patch("trade.symbol_filters", return_value=FILTERS), patch("trade._request", return_value={"orderId": 7}) as req:
            order = trade.place_limit_buy("3.9", "3185.9")
        self.assertEqual(order["orderId"], 7)
        self.assertEqual(req.call_args.args[0:2], ("POST", "/api/v3/order"))
        params = req.call_args.args[2]
        self.assertEqual(params["type"], "LIMIT")
        self.assertNotIn("MARKET", params.values())
        self.assertEqual(params["price"], "3185")
        self.assertEqual(params["quantity"], "3")

    def test_sell_rounds_price_up_and_quantity_down(self):
        with patch("trade.symbol_filters", return_value=FILTERS), patch("trade._request", return_value={"orderId": 8}) as req:
            trade.place_limit_sell("3.9", "3185.1")
        params = req.call_args.args[2]
        self.assertEqual(params["type"], "LIMIT")
        self.assertEqual(params["price"], "3186")
        self.assertEqual(params["quantity"], "3")

    def test_rejects_notional_below_exchange_minimum_before_request(self):
        with patch("trade.symbol_filters", return_value=FILTERS), patch("trade._request") as req:
            with self.assertRaisesRegex(ValueError, "menor al mínimo"):
                trade.place_limit_buy("1", "3185")
        req.assert_not_called()

    def test_buy_rounds_down_to_tick_even_if_requested_price_is_ask(self):
        with patch("trade.symbol_filters", return_value=FILTERS):
            quantity, price = trade._validated_order("BUY", Decimal("2"), Decimal("3185.99"))
        self.assertEqual(quantity, Decimal("2"))
        self.assertEqual(price, Decimal("3185"))


if __name__ == "__main__":
    unittest.main()
