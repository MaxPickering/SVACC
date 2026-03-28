from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .models import AnnotationState, CropROI, Marker, VideoMetadata, VideoRecord


class JsonStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _sidecar_path(self, relative_video_path: str) -> Path:
        relative = Path(relative_video_path)
        stem = relative.stem
        suffix_hash = hashlib.sha1(relative_video_path.encode("utf-8")).hexdigest()[:8]
        file_name = f"{stem}_{suffix_hash}.json"
        return self.data_dir / file_name

    def load_or_create(self, metadata: VideoMetadata) -> VideoRecord:
        sidecar = self._sidecar_path(metadata.relative_path)
        if not sidecar.exists():
            return VideoRecord(
                updated_at_utc=_utc_now(),
                metadata=metadata,
                annotations=AnnotationState(),
            )

        try:
            raw = json.loads(sidecar.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # Fall back to defaults if the sidecar is unreadable or malformed.
            return VideoRecord(
                updated_at_utc=_utc_now(),
                metadata=metadata,
                annotations=AnnotationState(),
            )

        annotations_data = raw.get("annotations", {})
        marker_data = annotations_data.get("marker")
        marker = None
        if isinstance(marker_data, dict):
            marker = Marker(
                x_px=int(marker_data.get("x_px", 0)),
                y_px=int(marker_data.get("y_px", 0)),
                x_norm=float(marker_data.get("x_norm", 0.0)),
                y_norm=float(marker_data.get("y_norm", 0.0)),
                box_w_px=_to_int_or_none(marker_data.get("box_w_px")),
                box_h_px=_to_int_or_none(marker_data.get("box_h_px")),
                box_w_norm=_to_float_or_none(marker_data.get("box_w_norm")),
                box_h_norm=_to_float_or_none(marker_data.get("box_h_norm")),
                captured_at_utc=str(marker_data.get("captured_at_utc", "")),
            )

        negative_markers: list[Marker] = []
        negative_markers_data = annotations_data.get("negative_markers", [])
        if isinstance(negative_markers_data, list):
            for item in negative_markers_data:
                if not isinstance(item, dict):
                    continue
                negative_markers.append(
                    Marker(
                        x_px=int(item.get("x_px", 0)),
                        y_px=int(item.get("y_px", 0)),
                        x_norm=float(item.get("x_norm", 0.0)),
                        y_norm=float(item.get("y_norm", 0.0)),
                        box_w_px=_to_int_or_none(item.get("box_w_px")),
                        box_h_px=_to_int_or_none(item.get("box_h_px")),
                        box_w_norm=_to_float_or_none(item.get("box_w_norm")),
                        box_h_norm=_to_float_or_none(item.get("box_h_norm")),
                        captured_at_utc=str(item.get("captured_at_utc", "")),
                    )
                )

        crop_roi_data = annotations_data.get("crop_roi")
        crop_roi = None
        if isinstance(crop_roi_data, dict):
            crop_roi = CropROI(
                x_px=int(crop_roi_data.get("x_px", 0)),
                y_px=int(crop_roi_data.get("y_px", 0)),
                w_px=int(crop_roi_data.get("w_px", 0)),
                h_px=int(crop_roi_data.get("h_px", 0)),
                x_norm=float(crop_roi_data.get("x_norm", 0.0)),
                y_norm=float(crop_roi_data.get("y_norm", 0.0)),
                w_norm=float(crop_roi_data.get("w_norm", 0.0)),
                h_norm=float(crop_roi_data.get("h_norm", 0.0)),
                captured_at_utc=str(crop_roi_data.get("captured_at_utc", "")),
            )

        marks_sec: list[float] = []
        marks_data = annotations_data.get("marks_sec", [])
        if isinstance(marks_data, list):
            for item in marks_data:
                mark_value = _to_float_or_none(item)
                if mark_value is not None:
                    marks_sec.append(round(mark_value, 3))

        annotations = AnnotationState(
            start_sec=_to_float_or_none(annotations_data.get("start_sec")),
            end_sec=_to_float_or_none(annotations_data.get("end_sec")),
            marks_sec=marks_sec,
            positive_box_width_px=_to_positive_int_or_none(annotations_data.get("positive_box_width_px")),
            positive_box_height_px=_to_positive_int_or_none(annotations_data.get("positive_box_height_px")),
            negative_box_width_px=_to_positive_int_or_none(annotations_data.get("negative_box_width_px")),
            negative_box_height_px=_to_positive_int_or_none(annotations_data.get("negative_box_height_px")),
            marker=marker,
            negative_markers=negative_markers,
            crop_roi=crop_roi,
            last_position_ms=int(annotations_data.get("last_position_ms", 0)),
        )

        loaded_metadata = raw.get("metadata", {})
        merged_metadata = VideoMetadata(
            file_name=metadata.file_name,
            relative_path=metadata.relative_path,
            file_size_bytes=metadata.file_size_bytes,
            modified_time_utc=metadata.modified_time_utc,
            duration_ms=_to_int_or_none(loaded_metadata.get("duration_ms"))
            if loaded_metadata.get("duration_ms") is not None
            else metadata.duration_ms,
            width=_to_int_or_none(loaded_metadata.get("width"))
            if loaded_metadata.get("width") is not None
            else metadata.width,
            height=_to_int_or_none(loaded_metadata.get("height"))
            if loaded_metadata.get("height") is not None
            else metadata.height,
            fps=_to_float_or_none(loaded_metadata.get("fps"))
            if loaded_metadata.get("fps") is not None
            else metadata.fps,
        )

        return VideoRecord(
            schema_version=int(raw.get("schema_version", 1)),
            updated_at_utc=str(raw.get("updated_at_utc", _utc_now())),
            metadata=merged_metadata,
            annotations=annotations,
        )

    def save(self, record: VideoRecord) -> None:
        record.updated_at_utc = _utc_now()
        sidecar = self._sidecar_path(record.metadata.relative_path)
        sidecar.write_text(json.dumps(asdict(record), indent=2), encoding="utf-8")

    def delete_for_video(self, relative_video_path: str) -> bool:
        sidecar = self._sidecar_path(relative_video_path)
        if not sidecar.exists():
            return False
        try:
            sidecar.unlink()
            return True
        except OSError:
            return False


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _to_float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_positive_int_or_none(value: object) -> int | None:
    parsed = _to_int_or_none(value)
    if parsed is None or parsed < 1:
        return None
    return parsed
