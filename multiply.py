#!/usr/bin/env python3
"""
Simple Math Utility: Multiplication of Two Numbers
"""

import sys

def multiply(a: float, b: float) -> float:
    """Multiplies two numbers and returns the result."""
    return a * b

def main():
    if len(sys.argv) >= 3:
        try:
            num1 = float(sys.argv[1])
            num2 = float(sys.argv[2])
            result = multiply(num1, num2)
            print(f"{num1} * {num2} = {result}")
            return
        except ValueError:
            print("Please provide valid numerical arguments.")
            sys.exit(1)

    # Interactive mode fallback
    try:
        val1 = float(input("Enter first number: "))
        val2 = float(input("Enter second number: "))
        ans = multiply(val1, val2)
        print(f"Result: {val1} * {val2} = {ans}")
    except (ValueError, KeyboardInterrupt):
        print("\nOperation cancelled or invalid input.")

if __name__ == "__main__":
    main()
