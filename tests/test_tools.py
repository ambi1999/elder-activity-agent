from app.tools import calculate, get_current_time, run_tool
from datetime import date, timedelta
from app.tools import calculate, days_until, get_current_time, run_tool

def test_calculate_basic():
    assert calculate("17 * 23") == "391"
    assert calculate("(2 + 3) ** 2") == "25"
    assert calculate("-4 + 10 / 2") == "1.0"


def test_calculate_rejects_code():
    assert calculate("__import__('os').system('ls')").startswith("Error")
    assert calculate("abs(-3)").startswith("Error")


def test_calculate_errors():
    assert calculate("1 / 0") == "Error: division by zero"
    assert calculate("2 ** 100000").startswith("Error")
    assert calculate("1 +").startswith("Error")


def test_get_current_time():
    assert "UTC" in get_current_time("UTC")
    assert get_current_time("Not/AZone").startswith("Error")


def test_run_tool_unknown_and_bad_args():
    assert run_tool("nope", {}).startswith("Error")
    assert run_tool("calculate", {"wrong": "x"}).startswith("Error")

def test_days_until():
    future = (date.today() + timedelta(days=10)).isoformat()
    assert days_until(future).startswith("10 days")
    assert days_until(date.today().isoformat()).endswith("is today")
    assert days_until("not-a-date").startswith("Error")