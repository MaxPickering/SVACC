from __future__ import annotations

from . import validation
from src.data.models import Marker, VideoRecord


def set_start(record: VideoRecord, current_time_sec: float) -> None:
    record.annotations.start_sec = round(current_time_sec, 3)


def set_end(record: VideoRecord, current_time_sec: float) -> None:
    record.annotations.end_sec = round(current_time_sec, 3)


def set_marker(record: VideoRecord, marker: Marker) -> None:
    record.annotations.marker = marker


def validate_start_end(record: VideoRecord) -> str | None:
    return validation.validate_start_end(
        record.annotations.start_sec,
        record.annotations.end_sec,
    )
