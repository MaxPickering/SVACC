from __future__ import annotations

from . import validation
from src.data.models import CropROI, Marker, VideoRecord


def set_start(record: VideoRecord, current_time_sec: float) -> None:
    record.annotations.start_sec = round(current_time_sec, 3)


def set_end(record: VideoRecord, current_time_sec: float) -> None:
    record.annotations.end_sec = round(current_time_sec, 3)


def add_mark(record: VideoRecord, current_time_sec: float) -> None:
    record.annotations.marks_sec.append(round(current_time_sec, 3))


def set_marker(record: VideoRecord, marker: Marker) -> None:
    record.annotations.marker = marker


def clear_marker(record: VideoRecord) -> None:
    record.annotations.marker = None


def add_negative_marker(record: VideoRecord, marker: Marker) -> None:
    record.annotations.negative_markers.append(marker)


def remove_last_negative_marker(record: VideoRecord) -> bool:
    if not record.annotations.negative_markers:
        return False
    record.annotations.negative_markers.pop()
    return True


def set_crop_roi(record: VideoRecord, crop_roi: CropROI) -> None:
    record.annotations.crop_roi = crop_roi


def validate_start_end(record: VideoRecord) -> str | None:
    return validation.validate_start_end(
        record.annotations.start_sec,
        record.annotations.end_sec,
    )
