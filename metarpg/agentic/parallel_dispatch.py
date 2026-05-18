"""Parallel fan-out dispatcher for v0.6.4 dual-Writer pipeline.

Wraps concurrent.futures.ThreadPoolExecutor with an exception-safe contract:
- One job's failure does not abort the rest.
- Results returned as {name: value_or_exception}.
- A hung future cannot block the collection of other futures.

Used by runner.py to run Bold Writer + Feasibility (batch 1) and
Safe Writers (batch 2) in parallel.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Job:
    name: str
    fn: Callable[..., Any]
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] | None = None


class ParallelTimeoutError(TimeoutError):
    """Raised when a single future exceeds its per-job timeout."""


def run_parallel(
    jobs: list[Job],
    max_workers: int = 4,
    timeout_per_future: float | None = 120.0,
) -> dict[str, Any]:
    """Run jobs in parallel. Returns {name: result} where result is the
    callable's return value, or the raised Exception object if it failed.

    If the overall batch exceeds a ceiling derived from
    *timeout_per_future*, any unfinished futures are cancelled and a
    ``ParallelTimeoutError`` is returned for those jobs.  Completed jobs
    are unaffected.

    Callers MUST check `isinstance(result, Exception)` before using.
    """
    if not jobs:
        return {}

    results: dict[str, Any] = {}
    ex = ThreadPoolExecutor(max_workers=max_workers)
    future_to_name: dict[Any, str] = {}

    try:
        for job in jobs:
            kwargs = job.kwargs or {}
            fut = ex.submit(job.fn, *job.args, **kwargs)
            future_to_name[fut] = job.name

        # Ceiling: derived from per-future timeout so tests can control it.
        # Real runs use timeout_per_future=120s → ceiling=240s.
        if timeout_per_future is not None:
            ceiling = timeout_per_future * 2
        else:
            ceiling = None

        try:
            for fut in as_completed(future_to_name, timeout=ceiling):
                name = future_to_name[fut]
                try:
                    # Future is already done, so result() returns immediately.
                    results[name] = fut.result(timeout=0)
                except Exception as exc:
                    results[name] = exc
        except TimeoutError:
            pass  # Some futures still running; handle below.
    finally:
        for fut in future_to_name:
            if not fut.done():
                fut.cancel()
        ex.shutdown(wait=False, cancel_futures=True)

    # Anything that never reached as_completed (timed out or cancelled).
    for name in (j.name for j in jobs):
        if name not in results:
            results[name] = ParallelTimeoutError(
                f"Job '{name}' did not complete within the batch ceiling"
            )

    return results
