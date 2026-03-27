from __future__ import annotations


def validate_start_end(start_sec: float | None, end_sec: float | None) -> str | None:
    if start_sec is None or end_sec is None:
        return None
    if end_sec < start_sec:
        return "END is before START."
    return None
