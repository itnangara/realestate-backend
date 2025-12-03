#!/usr/bin/env python3
"""
Comprehensive test runner - runs all tests and reports results
"""
import sys
import os
import subprocess
import json
from datetime import datetime

# Change to backend directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

def run_tests():
    """Run all tests and capture results"""
    print("=" * 80)
    print("COMPREHENSIVE TEST RUNNER")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Test categories
    test_categories = [
        ("Root Tests", "tests/test_root.py"),
        ("Auth Tests", "tests/auth/"),
        ("User Tests", "tests/users/"),
        ("Property Tests", "tests/properties/"),
        ("Application Tests", "tests/applications/"),
        ("Lease Tests", "tests/leases/"),
        ("Role Tests", "tests/roles/"),
        ("Service Tests", "tests/services/"),
    ]
    
    results = {}
    total_passed = 0
    total_failed = 0
    
    for category, test_path in test_categories:
        print(f"\n{'=' * 80}")
        print(f"Running: {category}")
        print(f"{'=' * 80}")
        
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", test_path, "-v", "--tb=short"],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout per category
            )
            
            # Parse output
            output = result.stdout + result.stderr
            passed = output.count("PASSED") + output.count("passed")
            failed = output.count("FAILED") + output.count("failed")
            errors = output.count("ERROR")
            
            results[category] = {
                "status": "PASSED" if result.returncode == 0 else "FAILED",
                "exit_code": result.returncode,
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "output": output[:5000]  # First 5000 chars
            }
            
            total_passed += passed
            total_failed += failed + errors
            
            # Print summary
            status_icon = "✓" if result.returncode == 0 else "✗"
            print(f"{status_icon} {category}: {passed} passed, {failed} failed, {errors} errors")
            
            if result.returncode != 0:
                print("\nFirst 500 characters of output:")
                print(output[:500])
                
        except subprocess.TimeoutExpired:
            results[category] = {
                "status": "TIMEOUT",
                "exit_code": -1,
                "output": "Test category timed out after 5 minutes"
            }
            print(f"✗ {category}: TIMEOUT")
        except Exception as e:
            results[category] = {
                "status": "ERROR",
                "exit_code": -1,
                "output": str(e)
            }
            print(f"✗ {category}: ERROR - {e}")
    
    # Final summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Total Passed: {total_passed}")
    print(f"Total Failed: {total_failed}")
    print(f"Overall Status: {'PASSED' if total_failed == 0 else 'FAILED'}")
    print(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Write results to file
    with open("test_results.json", "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_passed": total_passed,
                "total_failed": total_failed,
                "status": "PASSED" if total_failed == 0 else "FAILED"
            },
            "results": results
        }, f, indent=2)
    
    print("\nDetailed results written to: test_results.json")
    
    return 0 if total_failed == 0 else 1

if __name__ == "__main__":
    sys.exit(run_tests())

