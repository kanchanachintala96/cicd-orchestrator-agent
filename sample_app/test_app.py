import unittest
from app import add, subtract, multiply, divide, factorial


class TestAdd(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(add(2, 3), 5)

    def test_negative(self):
        self.assertEqual(add(-1, -1), -2)

    def test_zero(self):
        self.assertEqual(add(0, 0), 0)


class TestSubtract(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(subtract(10, 4), 6)

    def test_result_negative(self):
        self.assertEqual(subtract(1, 5), -4)


class TestMultiply(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(multiply(3, 4), 12)

    def test_by_zero(self):
        self.assertEqual(multiply(100, 0), 0)


class TestDivide(unittest.TestCase):
    def test_basic(self):
        self.assertAlmostEqual(divide(10, 4), 2.5)

    def test_divide_by_zero(self):
        with self.assertRaises(ValueError):
            divide(5, 0)


class TestFactorial(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(factorial(0), 1)

    def test_one(self):
        self.assertEqual(factorial(1), 1)

    def test_five(self):
        self.assertEqual(factorial(5), 120)

    def test_negative(self):
        with self.assertRaises(ValueError):
            factorial(-1)

    def test_non_integer(self):
        with self.assertRaises(ValueError):
            factorial(3.5)


if __name__ == "__main__":
    unittest.main()
