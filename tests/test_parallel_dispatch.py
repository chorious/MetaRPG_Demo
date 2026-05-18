"""Unit tests for metarpg.agentic.parallel_dispatch."""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from metarpg.agentic.parallel_dispatch import Job, ParallelTimeoutError, run_parallel


def test_three_one_second_jobs_finish_under_one_and_a_half_seconds() -> None:
    """3 mock 1s sleeps must wall-clock under 1.5s when run in parallel."""
    def slow(name: str) -> str:
        time.sleep(1.0)
        return f"done:{name}"

    jobs = [
        Job(name="a", fn=slow, args=("a",)),
        Job(name="b", fn=slow, args=("b",)),
        Job(name="c", fn=slow, args=("c",)),
    ]

    start = time.perf_counter()
    results = run_parallel(jobs, max_workers=4)
    elapsed = time.perf_counter() - start

    assert elapsed < 1.5, f"Expected parallel wall time < 1.5s, got {elapsed:.2f}s"
    assert results == {"a": "done:a", "b": "done:b", "c": "done:c"}


def test_one_failure_does_not_abort_others() -> None:
    """A raising job must not stop other jobs from completing."""
    def ok(name: str) -> str:
        return f"ok:{name}"

    def boom() -> None:
        raise ValueError("intentional")

    jobs = [
        Job(name="a", fn=ok, args=("a",)),
        Job(name="b", fn=boom),
        Job(name="c", fn=ok, args=("c",)),
    ]

    results = run_parallel(jobs, max_workers=4)
    assert results["a"] == "ok:a"
    assert results["c"] == "ok:c"
    assert isinstance(results["b"], ValueError)
    assert str(results["b"]) == "intentional"


def test_concurrent_calls_actually_overlap() -> None:
    """Track concurrency level via shared counter to confirm workers overlap."""
    in_flight = 0
    peak = 0
    lock = threading.Lock()

    def task(n: int) -> int:
        nonlocal in_flight, peak
        with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        time.sleep(0.1)
        with lock:
            in_flight -= 1
        return n

    jobs = [Job(name=f"t{i}", fn=task, args=(i,)) for i in range(4)]
    results = run_parallel(jobs, max_workers=4)

    assert peak >= 2, f"Expected concurrent execution, peak={peak}"
    assert set(results.keys()) == {"t0", "t1", "t2", "t3"}


def test_empty_jobs_list_returns_empty_dict() -> None:
    assert run_parallel([], max_workers=4) == {}


def test_kwargs_passthrough() -> None:
    def add(a: int, b: int = 0) -> int:
        return a + b

    jobs = [
        Job(name="sum1", fn=add, args=(1,), kwargs={"b": 10}),
        Job(name="sum2", fn=add, args=(2,), kwargs={"b": 20}),
    ]
    results = run_parallel(jobs, max_workers=2)
    assert results == {"sum1": 11, "sum2": 22}


def test_per_future_timeout_returns_timeout_error() -> None:
    """A slow job exceeding the batch ceiling must return ParallelTimeoutError
    while other jobs complete normally."""
    def slow() -> str:
        time.sleep(5.0)
        return "too late"

    def fast() -> str:
        return "quick"

    jobs = [
        Job(name="a", fn=fast),
        Job(name="b", fn=slow),
        Job(name="c", fn=fast),
    ]
    # ceiling = 0.3 * 2 = 0.6s; slow job (5s) will exceed it
    results = run_parallel(jobs, max_workers=4, timeout_per_future=0.3)
    assert results["a"] == "quick"
    assert results["c"] == "quick"
    assert isinstance(results["b"], ParallelTimeoutError)
    assert "b" in str(results["b"])


def test_timeout_does_not_block_other_results() -> None:
    """Total wall time must stay under ~1s even with one slow job."""
    def slow() -> str:
        time.sleep(10.0)
        return "too late"

    def fast() -> str:
        time.sleep(0.05)
        return "quick"

    jobs = [
        Job(name="slow", fn=slow),
        Job(name="f1", fn=fast),
        Job(name="f2", fn=fast),
    ]
    start = time.perf_counter()
    results = run_parallel(jobs, max_workers=4, timeout_per_future=0.3)
    elapsed = time.perf_counter() - start
    # ceiling = 0.6s; fast jobs finish in ~0.05s, then we wait up to 0.6s
    assert elapsed < 2.0, f"Expected < 2s, got {elapsed:.2f}s"
    assert results["f1"] == "quick"
    assert results["f2"] == "quick"
    assert isinstance(results["slow"], ParallelTimeoutError)


if __name__ == "__main__":
    print("=" * 60)
    print("parallel_dispatch tests")
    print("=" * 60)

    test_three_one_second_jobs_finish_under_one_and_a_half_seconds()
    print("[PASS] 3 parallel 1s jobs under 1.5s")

    test_one_failure_does_not_abort_others()
    print("[PASS] one failure does not abort others")

    test_concurrent_calls_actually_overlap()
    print("[PASS] workers actually overlap")

    test_empty_jobs_list_returns_empty_dict()
    print("[PASS] empty jobs list -> empty dict")

    test_kwargs_passthrough()
    print("[PASS] kwargs passthrough")

    print("=" * 60)
    print("All parallel_dispatch tests passed.")
