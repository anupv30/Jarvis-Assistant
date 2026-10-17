"""
Harmless Math Operations Test File
Used for testing Jarvis autonomous Git commit and voice-activated revert.
"""

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

def power(base: float, exp: float) -> float:
    return base ** exp

if __name__ == "__main__":
    print("Testing Math Operations:")
    print(f"10 + 5 = {add(10, 5)}")
    print(f"10 - 5 = {subtract(10, 5)}")
    print(f"10 * 5 = {multiply(10, 5)}")
    print(f"10 / 5 = {divide(10, 5)}")
    print(f"2 ^ 8  = {power(2, 8)}")
