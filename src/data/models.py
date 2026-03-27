from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Marker:
    x_px: int
    y_px: int
    x_norm: float
    y_norm: float
    captured_at_utc: str


@dataclass
class CropROI:
    x_px: int
    y_px: int
    w_px: int
    h_px: int
    x_norm: float
    y_norm: float
    w_norm: float
    h_norm: float
    captured_at_utc: str


@dataclass
class AnnotationState:
    start_sec: Optional[float] = None
    end_sec: Optional[float] = None
    marker: Optional[Marker] = None
    negative_markers: list[Marker] = field(default_factory=list)
    crop_roi: Optional[CropROI] = None
    last_position_ms: int = 0


@dataclass
class VideoMetadata:
    file_name: str
    relative_path: str
    file_size_bytes: int
    modified_time_utc: str
    duration_ms: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None


@dataclass
class VideoRecord:
    schema_version: int = 1
    updated_at_utc: str = ""
    metadata: Optional[VideoMetadata] = None
    annotations: AnnotationState = field(default_factory=AnnotationState)
