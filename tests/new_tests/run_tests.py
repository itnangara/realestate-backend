#!/usr/bin/env python3
"""Run all tests and report results"""
import sys
import subprocess
import os

# Change to backend directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Run pytest with verbose output
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
    capture_output=True,
    text=True
)

# Print output
print("STDOUT:")
print(result.stdout)
print("\nSTDERR:")
print(result.stderr)
print(f"\nExit code: {result.returncode}")

sys.exit(result.returncode)

