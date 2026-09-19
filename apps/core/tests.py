from decimal import Decimal
from django.test import TestCase
from apps.core.utils import parse_decimal, parse_int

class UtilsTestCase(TestCase):
    def test_parse_decimal_valid(self):
        self.assertEqual(parse_decimal("15.50"), Decimal("15.50"))
        self.assertEqual(parse_decimal("15,50"), Decimal("15.50"))
        self.assertEqual(parse_decimal("0"), Decimal("0"))

    def test_parse_decimal_empty_or_invalid(self):
        self.assertEqual(parse_decimal(""), Decimal("0.00"))
        self.assertEqual(parse_decimal(None), Decimal("0.00"))
        self.assertEqual(parse_decimal("invalid"), Decimal("0.00"))
        self.assertEqual(parse_decimal("", default="10.00"), Decimal("10.00"))

    def test_parse_int_valid(self):
        self.assertEqual(parse_int("45"), 45)
        self.assertEqual(parse_int("0"), 0)

    def test_parse_int_empty_or_invalid(self):
        self.assertEqual(parse_int(""), 0)
        self.assertEqual(parse_int(None, default=45), 45)
        self.assertEqual(parse_int("abc", default=30), 30)
