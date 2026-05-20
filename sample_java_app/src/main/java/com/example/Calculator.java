package com.example;

public class Calculator {

    public double add(double a, double b) {
        return a + b;
    }

    public double subtract(double a, double b) {
        return a - b;
    }

    public double multiply(double a, double b) {
        return a * b;
    }

    public double divide(double a, double b) {
        if (b == 0) throw new IllegalArgumentException("Cannot divide by zero.");
        return a / b;
    }

    public long factorial(int n) {
        if (n < 0) throw new IllegalArgumentException("factorial requires a non-negative integer.");
        long result = 1;
        for (int i = 2; i <= n; i++) result *= i;
        return result;
    }

    public static void main(String[] args) {
        Calculator calc = new Calculator();
        System.out.println("Calculator sample app");
        System.out.println("3 + 4 = " + calc.add(3, 4));
        System.out.println("10 / 2 = " + calc.divide(10, 2));
        System.out.println("5! = " + calc.factorial(5));
    }
}
