from datetime import datetime, timezone

from PySide6.QtWidgets import QMessageBox

from src.core.annotations import (
    add_mark,
    add_negative_marker,
    clear_marker,
    remove_last_negative_marker,
    set_crop_roi,
    set_end,
    set_marker,
    set_start,
)
from src.data.models import CropROI, Marker, VideoRecord


class AnnotationController:
    """Manages annotation operations and validation."""

    def __init__(self, parent=None) -> None:  # type: ignore[no-untyped-def]
        self.parent = parent

    def set_start(self, current_record: VideoRecord | None, position_ms: int) -> tuple[bool, str]:
        """
        Set start timestamp. Returns (success, status_message).
        """
        if current_record is None:
            return False, "No video loaded"

        proposed_start_sec = round(position_ms / 1000.0, 3)
        end_sec = current_record.annotations.end_sec
        if end_sec is not None and proposed_start_sec > end_sec:
            return False, "START not saved: cannot be after END"

        set_start(current_record, proposed_start_sec)
        return True, "Saved START timestamp"

    def set_end(self, current_record: VideoRecord | None, position_ms: int) -> tuple[bool, str]:
        """
        Set end timestamp. Returns (success, status_message).
        """
        if current_record is None:
            return False, "No video loaded"

        start_sec = current_record.annotations.start_sec
        if start_sec is None:
            return False, "END not saved: set START first"

        proposed_end_sec = round(position_ms / 1000.0, 3)
        if proposed_end_sec < start_sec:
            return False, "END not saved: cannot be before START"

        set_end(current_record, proposed_end_sec)
        return True, "Saved END timestamp"

    def add_mark(self, current_record: VideoRecord | None, position_ms: int) -> tuple[bool, str]:
        """
        Add mark timestamp. Returns (success, status_message).
        """
        if current_record is None:
            return False, "No video loaded"

        mark_sec = round(position_ms / 1000.0, 3)
        add_mark(current_record, mark_sec)
        return True, f"Saved MARK timestamp at {mark_sec:.3f}s"

    def add_marker(
        self,
        current_record: VideoRecord | None,
        x_px: float,
        y_px: float,
        x_norm: float,
        y_norm: float,
        box_w_px: int | None = None,
        box_h_px: int | None = None,
    ) -> None:
        if current_record is None:
            return

        marker = self._build_marker(current_record, x_px, y_px, x_norm, y_norm, box_w_px, box_h_px)
        set_marker(current_record, marker)

    def add_negative_marker(
        self,
        current_record: VideoRecord | None,
        x_px: float,
        y_px: float,
        x_norm: float,
        y_norm: float,
        box_w_px: int | None = None,
        box_h_px: int | None = None,
    ) -> None:
        if current_record is None:
            return

        marker = self._build_marker(current_record, x_px, y_px, x_norm, y_norm, box_w_px, box_h_px)
        add_negative_marker(current_record, marker)

    def _build_marker(
        self,
        current_record: VideoRecord,
        x_px: float,
        y_px: float,
        x_norm: float,
        y_norm: float,
        box_w_px: int | None,
        box_h_px: int | None,
    ) -> Marker:
        resolved_box_w = max(int(box_w_px), 1) if box_w_px is not None else None
        resolved_box_h = max(int(box_h_px), 1) if box_h_px is not None else None

        box_w_norm: float | None = None
        box_h_norm: float | None = None
        meta_w = current_record.metadata.width if current_record.metadata is not None else None
        meta_h = current_record.metadata.height if current_record.metadata is not None else None
        if resolved_box_w is not None and resolved_box_h is not None and meta_w and meta_h and meta_w > 0 and meta_h > 0:
            box_w_norm = round(min(max(resolved_box_w / meta_w, 0.0), 1.0), 6)
            box_h_norm = round(min(max(resolved_box_h / meta_h, 0.0), 1.0), 6)

        return Marker(
            x_px=int(round(x_px)),
            y_px=int(round(y_px)),
            x_norm=round(x_norm, 6),
            y_norm=round(y_norm, 6),
            box_w_px=resolved_box_w,
            box_h_px=resolved_box_h,
            box_w_norm=box_w_norm,
            box_h_norm=box_h_norm,
            captured_at_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        )

    def undo_marker(self, current_record: VideoRecord | None) -> tuple[bool, str]:
        if current_record is None:
            return False, "No video loaded"

        if current_record.annotations.marker is None:
            return False, "No marker to undo"

        clear_marker(current_record)
        return True, "Undid marker placement"

    def undo_negative_marker(self, current_record: VideoRecord | None) -> tuple[bool, str]:
        if current_record is None:
            return False, "No video loaded"

        if not remove_last_negative_marker(current_record):
            return False, "No negative marker to undo"

        return True, "Undid negative marker placement"

    def set_roi(
        self,
        current_record: VideoRecord | None,
        x_px: float,
        y_px: float,
        w_px: float,
        h_px: float,
        x_norm: float,
        y_norm: float,
        w_norm: float,
        h_norm: float,
    ) -> None:
        if current_record is None:
            return

        meta_w = current_record.metadata.width if current_record.metadata is not None else None
        meta_h = current_record.metadata.height if current_record.metadata is not None else None

        resolved_x_px = int(round(x_px))
        resolved_y_px = int(round(y_px))
        resolved_w_px = int(round(w_px))
        resolved_h_px = int(round(h_px))

        if meta_w is not None and meta_h is not None and meta_w > 0 and meta_h > 0:
            resolved_x_px = int(round(x_norm * meta_w))
            resolved_y_px = int(round(y_norm * meta_h))
            resolved_w_px = int(round(w_norm * meta_w))
            resolved_h_px = int(round(h_norm * meta_h))

        crop_roi = CropROI(
            x_px=resolved_x_px,
            y_px=resolved_y_px,
            w_px=resolved_w_px,
            h_px=resolved_h_px,
            x_norm=round(x_norm, 6),
            y_norm=round(y_norm, 6),
            w_norm=round(w_norm, 6),
            h_norm=round(h_norm, 6),
            captured_at_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        )
        set_crop_roi(current_record, crop_roi)

    def show_roi_error(self, message: str) -> None:
        """Show ROI validation error."""
        if self.parent is None:
            return

        QMessageBox.warning(
            self.parent,
            "Invalid ROI",
            f"{message}\n\nROI Mode is active. Press R to toggle off.",
        )
