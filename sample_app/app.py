"""Simple calculator module used as a sample application."""


def add(a: float, b: float) -> float:
    return a + b


def subtract(a: float, b: float) -> float:
    return a - b


def multiply(a: float, b: float) -> float:
    return a * b


def divide(a: float, b: float) -> float:
    if b == 0:
        raise ValueError("Cannot divide by zero.")
    return a / b


def factorial(n: int) -> int:
    if not isinstance(n, int) or n < 0:
        raise ValueError("factorial requires a non-negative integer.")
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result


if __name__ == "__main__":
    print("Calculator sample app")
    print(f"3 + 4 = {add(3, 4)}")
    print(f"10 / 2 = {divide(10, 2)}")
    print(f"5! = {factorial(5)}")
