package com.example;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class CalculatorTest {

    private final Calculator calc = new Calculator();

    // ── add ───────────────────────────────────────────────────────────────────
    @Test void addPositive()  { assertEquals(7.0,  calc.add(3, 4)); }
    @Test void addNegative()  { assertEquals(-1.0, calc.add(-3, 2)); }
    @Test void addZero()      { assertEquals(5.0,  calc.add(5, 0)); }

    // ── subtract ──────────────────────────────────────────────────────────────
    @Test void subtractBasic()    { assertEquals(1.0,  calc.subtract(3, 2)); }
    @Test void subtractNegative() { assertEquals(-5.0, calc.subtract(0, 5)); }

    // ── multiply ──────────────────────────────────────────────────────────────
    @Test void multiplyBasic()  { assertEquals(12.0, calc.multiply(3, 4)); }
    @Test void multiplyByZero() { assertEquals(0.0,  calc.multiply(5, 0)); }

    // ── divide ────────────────────────────────────────────────────────────────
    @Test void divideBasic() { assertEquals(5.0, calc.divide(10, 2)); }
    @Test void divideByZero() {
        assertThrows(IllegalArgumentException.class, () -> calc.divide(10, 0));
    }

    // ── factorial ─────────────────────────────────────────────────────────────
    @Test void factorialFive()     { assertEquals(120, calc.factorial(5)); }
    @Test void factorialOne()      { assertEquals(1,   calc.factorial(1)); }
    @Test void factorialZero()     { assertEquals(1,   calc.factorial(0)); }
    @Test void factorialNegative() {
        assertThrows(IllegalArgumentException.class, () -> calc.factorial(-1));
    }
}
