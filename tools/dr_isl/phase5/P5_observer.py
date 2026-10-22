"""Incremental bounded JUnit/results plus failing IDs, reusing the read-only hook."""
from pathlib import Path
from P2_observer import *
from P2_observer import pytest_runtest_logreport as original_report

_failures = set()


def pytest_runtest_logreport(report):
    original_report(report)
    if report.failed:
        _failures.add(report.nodeid)
    elif report.when == "call" and report.passed:
        _failures.discard(report.nodeid)
    Path(__file__).with_name("P5_FAILING_TESTS.incremental.txt").write_text(
        "".join(node + "\n" for node in sorted(_failures)))
