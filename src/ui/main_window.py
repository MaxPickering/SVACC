from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, QUrl
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaMetaData, QMediaPlayer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QStyle,
    QStyleOptionSlider,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from src.core.annotations import (
    add_negative_marker,
    set_crop_roi,
    set_end,
    set_marker,
    set_start,
)
from src.core.video_discovery import list_videos
from src.data.json_store import JsonStore
from src.data.models import CropROI, Marker, VideoMetadata, VideoRecord
from src.ui.video_widget import ClickableVideoWidget


class TimelineSlider(QSlider):
    START_COLOR = QColor(0, 190, 110)
    END_COLOR = QColor(255, 140, 0)

    def __init__(self, orientation: Qt.Orientation, parent: QWidget | None = None) -> None:
        super().__init__(orientation, parent)
        self._start_sec: float | None = None
        self._end_sec: float | None = None

    def set_annotation_markers(self, start_sec: float | None, end_sec: float | None) -> None:
        self._start_sec = start_sec
        self._end_sec = end_sec
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().paintEvent(event)
        if self.orientation() != Qt.Orientation.Horizontal:
            return
        if self.maximum() <= self.minimum():
            return

        option = QStyleOptionSlider()
        self.initStyleOption(option)
        groove = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            option,
            QStyle.SubControl.SC_SliderGroove,
            self,
        )
        if groove.width() <= 1:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        span = max(1, self.maximum() - self.minimum())

        def x_for_seconds(seconds: float) -> int:
            ms = int(round(seconds * 1000.0))
            clamped = min(max(ms, self.minimum()), self.maximum())
            ratio = (clamped - self.minimum()) / span
            return groove.left() + int(round(ratio * groove.width()))

        self._draw_marker(painter, x_for_seconds, self._start_sec, self.START_COLOR, "S", groove)
        self._draw_marker(painter, x_for_seconds, self._end_sec, self.END_COLOR, "E", groove)

        painter.end()

    def _draw_marker(
        self,
        painter: QPainter,
        x_for_seconds,
        seconds: float | None,
        color: QColor,
        label: str,
        groove,
    ) -> None:  # type: ignore[no-untyped-def]
        if seconds is None:
            return

        x = x_for_seconds(seconds)
        painter.setPen(QPen(color, 2))
        painter.drawLine(x, groove.top() - 8, x, groove.bottom() + 8)

        badge_size = 14
        badge_x = x - (badge_size // 2)
        badge_y = max(0, groove.top() - 24)
        painter.setPen(QPen(QColor(255, 255, 255), 1))
        painter.setBrush(color)
        painter.drawEllipse(badge_x, badge_y, badge_size, badge_size)

        painter.setPen(QPen(QColor(255, 255, 255), 1))
        painter.drawText(badge_x, badge_y, badge_size, badge_size, Qt.AlignmentFlag.AlignCenter, label)


class MainWindow(QMainWindow):
    SEEK_STEP_MS = 5000

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SVACC - Simple Video Annotator for Classes with Cropping")
        self.resize(1280, 760)

        self.project_root = Path(__file__).resolve().parents[2]
        self.videos_dir = self.project_root / "videos"
        self.data_dir = self.project_root / "data"

        self.store = JsonStore(self.data_dir)

        self.current_video: Path | None = None
        self.current_record: VideoRecord | None = None
        self._is_user_scrubbing = False

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setMuted(True)

        self.video_widget = ClickableVideoWidget(self)
        self.player.setVideoOutput(self.video_widget.video_output())

        self.video_list = QListWidget(self)
        self.video_list.currentItemChanged.connect(self._on_video_selected)

        self.refresh_button = QPushButton("Refresh Videos", self)
        self.refresh_button.clicked.connect(self.load_video_list)

        self.reset_annotations_button = QPushButton("Reset annotation data", self)
        self.reset_annotations_button.clicked.connect(self._reset_annotation_data)

        self.reset_selected_button = QPushButton("Reset selected video data", self)
        self.reset_selected_button.clicked.connect(self._reset_selected_video_data)

        self.play_pause_button = QPushButton("Play", self)
        self.play_pause_button.clicked.connect(self._toggle_play_pause)

        self.mute_button = QPushButton("Unmute", self)
        self.mute_button.clicked.connect(self._toggle_mute)

        self.start_button = QPushButton("Set START", self)
        self.start_button.clicked.connect(self._set_start)

        self.end_button = QPushButton("Set END", self)
        self.end_button.clicked.connect(self._set_end)

        self.roi_mode_button = QPushButton("ROI Mode: Off", self)
        self.roi_mode_button.clicked.connect(self._toggle_roi_mode)

        self.seek_slider = TimelineSlider(Qt.Orientation.Horizontal, self)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.sliderPressed.connect(self._on_slider_pressed)
        self.seek_slider.sliderReleased.connect(self._on_slider_released)
        self.seek_slider.sliderMoved.connect(self._on_slider_moved)

        self.time_label = QLabel("00:00.000 / 00:00.000", self)
        self.start_label = QLabel("START: -", self)
        self.end_label = QLabel("END: -", self)
        self.marker_label = QLabel("Marker: -", self)
        self.roi_label = QLabel("ROI: -", self)

        self.status = QStatusBar(self)
        self.setStatusBar(self.status)
        self._shortcuts: list[QShortcut] = []

        self._build_layout()
        self._wire_player_events()
        self._setup_shortcuts()

        self.video_widget.marker_placed.connect(self._on_marker_placed)
        self.video_widget.negative_marker_placed.connect(self._on_negative_marker_placed)
        self.video_widget.roi_placed.connect(self._on_roi_placed)
        self.video_widget.roi_invalid.connect(self._on_roi_invalid)
        self.load_video_list()

    def _build_layout(self) -> None:
        container = QWidget(self)
        root = QHBoxLayout(container)

        left = QVBoxLayout()
        left.addWidget(QLabel("Videos", self))
        left.addWidget(self.video_list, stretch=1)
        left.addWidget(self.refresh_button)
        left.addWidget(self.reset_selected_button)
        left.addWidget(self.reset_annotations_button)

        right = QVBoxLayout()
        right.addWidget(self.video_widget, stretch=1)

        controls = QHBoxLayout()
        controls.addWidget(self.play_pause_button)
        controls.addWidget(self.mute_button)
        controls.addWidget(self.start_button)
        controls.addWidget(self.end_button)
        controls.addWidget(self.roi_mode_button)
        controls.addStretch(1)

        right.addLayout(controls)
        right.addWidget(self.seek_slider)
        right.addWidget(self.time_label)
        right.addWidget(self.start_label)
        right.addWidget(self.end_label)
        right.addWidget(self.marker_label)
        right.addWidget(self.roi_label)

        root.addLayout(left, stretch=1)
        root.addLayout(right, stretch=4)

        self.setCentralWidget(container)

    def _wire_player_events(self) -> None:
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.player.metaDataChanged.connect(self._on_metadata_changed)
        self.player.errorOccurred.connect(self._on_player_error)

    def _setup_shortcuts(self) -> None:
        self._register_shortcut(QKeySequence(Qt.Key.Key_Space), self._toggle_play_pause)
        self._register_shortcut(QKeySequence(Qt.Key.Key_Right), self._seek_forward)
        self._register_shortcut(QKeySequence(Qt.Key.Key_Left), self._seek_backward)
        self._register_shortcut(QKeySequence(Qt.Key.Key_S), self._set_start)
        self._register_shortcut(QKeySequence(Qt.Key.Key_E), self._set_end)
        self._register_shortcut(QKeySequence(Qt.Key.Key_R), self._toggle_roi_mode)

    def _register_shortcut(self, sequence: QKeySequence, handler) -> None:  # type: ignore[no-untyped-def]
        shortcut = QShortcut(sequence, self)
        shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        shortcut.activated.connect(handler)
        self._shortcuts.append(shortcut)

    def _reset_annotation_data(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Reset annotation data",
            "Delete all annotation JSON files in the data folder?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        deleted_count = 0
        for json_file in self.data_dir.glob("*.json"):
            try:
                json_file.unlink()
                deleted_count += 1
            except OSError:
                continue

        self.current_record = None
        self.video_widget.clear_marker()
        self.video_widget.clear_negative_markers()
        self.video_widget.clear_roi()
        self.load_video_list()
        self.status.showMessage(f"Deleted {deleted_count} annotation file(s).")

    def _reset_selected_video_data(self) -> None:
        if self.current_video is None:
            QMessageBox.information(
                self,
                "No video selected",
                "Select a video first.",
            )
            return

        confirm = QMessageBox.question(
            self,
            "Reset selected video",
            f"Delete annotation JSON for {self.current_video.name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        metadata = self._build_file_metadata(self.current_video)
        deleted = self.store.delete_for_video(metadata.relative_path)

        self.current_record = self.store.load_or_create(metadata)
        self._refresh_annotation_labels()
        self._refresh_video_list_item_status(self.current_video)

        if deleted:
            self.status.showMessage(f"Reset annotations for {self.current_video.name}")
        else:
            self.status.showMessage(f"No saved annotations found for {self.current_video.name}")

    def load_video_list(self) -> None:
        selected_video_path: str | None = None
        current_item = self.video_list.currentItem()
        if current_item is not None:
            selected_video_path = str(current_item.data(Qt.ItemDataRole.UserRole))

        self.video_list.clear()
        videos = list_videos(self.videos_dir)

        for video in videos:
            is_complete = self._video_has_complete_annotations(video)
            item = QListWidgetItem(self._video_list_display_name(video.name, is_complete))
            item.setData(Qt.ItemDataRole.UserRole, str(video))
            self.video_list.addItem(item)

        if not videos:
            self.status.showMessage("No .mp4 videos found in videos folder.")
            return

        if selected_video_path is not None:
            self._select_video_by_path(selected_video_path)
        if self.video_list.currentRow() < 0 and self.video_list.count() > 0:
            self.video_list.setCurrentRow(0)
        self.status.showMessage(f"Loaded {len(videos)} video(s).")

    def _select_video_by_path(self, video_path: str) -> None:
        for index in range(self.video_list.count()):
            item = self.video_list.item(index)
            if str(item.data(Qt.ItemDataRole.UserRole)) == video_path:
                self.video_list.setCurrentRow(index)
                return

    @staticmethod
    def _video_list_display_name(file_name: str, is_complete: bool) -> str:
        if is_complete:
            return f"✓ {file_name}"
        return file_name

    @staticmethod
    def _record_is_complete(record: VideoRecord | None) -> bool:
        if record is None:
            return False
        return (
            record.annotations.start_sec is not None
            and record.annotations.end_sec is not None
            and record.annotations.marker is not None
        )

    def _video_has_complete_annotations(self, video_path: Path) -> bool:
        metadata = self._build_file_metadata(video_path)
        record = self.store.load_or_create(metadata)
        return self._record_is_complete(record)

    def _refresh_video_list_item_status(self, video_path: Path) -> None:
        is_complete = self._record_is_complete(self.current_record)
        for index in range(self.video_list.count()):
            item = self.video_list.item(index)
            item_video_path = Path(str(item.data(Qt.ItemDataRole.UserRole)))
            if item_video_path == video_path:
                item.setText(self._video_list_display_name(video_path.name, is_complete))
                return

    def _on_video_selected(self, current: QListWidgetItem | None, _: QListWidgetItem | None) -> None:
        self._save_current_record()

        if current is None:
            return

        video_path = Path(current.data(Qt.ItemDataRole.UserRole))
        if not video_path.exists():
            QMessageBox.warning(self, "Missing file", f"Video not found: {video_path}")
            return

        self.current_video = video_path
        metadata = self._build_file_metadata(video_path)
        self.current_record = self.store.load_or_create(metadata)

        self.player.setSource(QUrl.fromLocalFile(str(video_path)))
        self.player.pause()
        self.player.setPosition(self.current_record.annotations.last_position_ms)
        self._refresh_annotation_labels()
        self._refresh_video_list_item_status(video_path)
        self.status.showMessage(f"Loaded {video_path.name}")

    def _build_file_metadata(self, video_path: Path) -> VideoMetadata:
        stat = video_path.stat()
        relative_path = str(video_path.relative_to(self.project_root)).replace("\\", "/")

        modified = datetime.fromtimestamp(stat.st_mtime, timezone.utc).replace(microsecond=0)
        return VideoMetadata(
            file_name=video_path.name,
            relative_path=relative_path,
            file_size_bytes=stat.st_size,
            modified_time_utc=modified.isoformat(),
        )

    def _on_player_error(self, error, error_string: str) -> None:  # type: ignore[no-untyped-def]
        if error == QMediaPlayer.Error.NoError:
            return
        self.status.showMessage(f"Player error: {error_string}")

    def _toggle_play_pause(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _seek_forward(self) -> None:
        self._seek_relative(self.SEEK_STEP_MS)

    def _seek_backward(self) -> None:
        self._seek_relative(-self.SEEK_STEP_MS)

    def _seek_relative(self, delta_ms: int) -> None:
        duration = max(self.player.duration(), 0)
        if duration <= 0:
            return

        next_position = self.player.position() + delta_ms
        next_position = max(0, min(duration, next_position))
        self.player.setPosition(next_position)

    def _toggle_mute(self) -> None:
        is_muted = self.audio_output.isMuted()
        self.audio_output.setMuted(not is_muted)
        self._update_mute_button_text()

        if self.audio_output.isMuted():
            self.status.showMessage("Audio muted")
        else:
            self.status.showMessage("Audio unmuted")

    def _toggle_roi_mode(self) -> None:
        enabled = not self.video_widget.is_roi_mode_enabled()
        self.video_widget.set_roi_mode_enabled(enabled)
        if enabled:
            self.roi_mode_button.setText("ROI Mode: On")
            self.status.showMessage("ROI mode enabled. Click and drag to draw rectangle.")
        else:
            self.roi_mode_button.setText("ROI Mode: Off")
            self.status.showMessage("ROI mode disabled")

    def _update_mute_button_text(self) -> None:
        if self.audio_output.isMuted():
            self.mute_button.setText("Unmute")
        else:
            self.mute_button.setText("Mute")

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_pause_button.setText("Pause")
        else:
            self.play_pause_button.setText("Play")

    def _on_duration_changed(self, duration_ms: int) -> None:
        self.seek_slider.setRange(0, max(duration_ms, 0))
        self._update_time_label(self.player.position(), duration_ms)
        self._refresh_timeline_markers()

        if self.current_record is not None:
            self.current_record.metadata.duration_ms = duration_ms
            self._save_current_record()

    def _on_position_changed(self, position_ms: int) -> None:
        if not self._is_user_scrubbing:
            with QSignalBlocker(self.seek_slider):
                self.seek_slider.setValue(position_ms)

        self._update_time_label(position_ms, self.player.duration())

        if self.current_record is not None:
            self.current_record.annotations.last_position_ms = position_ms

    def _on_slider_pressed(self) -> None:
        self._is_user_scrubbing = True

    def _on_slider_released(self) -> None:
        self._is_user_scrubbing = False
        self.player.setPosition(self.seek_slider.value())

    def _on_slider_moved(self, position_ms: int) -> None:
        self._update_time_label(position_ms, self.player.duration())

    def _set_start(self) -> None:
        if self.current_record is None:
            return

        proposed_start_sec = round(self.player.position() / 1000.0, 3)
        end_sec = self.current_record.annotations.end_sec
        if end_sec is not None and proposed_start_sec > end_sec:
            QMessageBox.warning(
                self,
                "Invalid START",
                "START cannot be after END.",
            )
            self.status.showMessage("START not saved: cannot be after END")
            return

        set_start(self.current_record, proposed_start_sec)
        self._refresh_annotation_labels()
        self._save_current_record()
        if self.current_video is not None:
            self._refresh_video_list_item_status(self.current_video)
        self.status.showMessage("Saved START timestamp")

    def _set_end(self) -> None:
        if self.current_record is None:
            return

        start_sec = self.current_record.annotations.start_sec
        if start_sec is None:
            QMessageBox.warning(
                self,
                "Set START first",
                "END cannot be set before START. Please set START first.",
            )
            self.status.showMessage("END not saved: set START first")
            return

        proposed_end_sec = round(self.player.position() / 1000.0, 3)
        if proposed_end_sec < start_sec:
            QMessageBox.warning(
                self,
                "Invalid END",
                "END cannot be before START.",
            )
            self.status.showMessage("END not saved: cannot be before START")
            return

        set_end(self.current_record, proposed_end_sec)
        self._refresh_annotation_labels()
        self._save_current_record()
        if self.current_video is not None:
            self._refresh_video_list_item_status(self.current_video)
        self.status.showMessage("Saved END timestamp")

    def _on_marker_placed(self, x_px: float, y_px: float, x_norm: float, y_norm: float) -> None:
        if self.current_record is None:
            return

        marker = Marker(
            x_px=int(round(x_px)),
            y_px=int(round(y_px)),
            x_norm=round(x_norm, 6),
            y_norm=round(y_norm, 6),
            captured_at_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        )
        set_marker(self.current_record, marker)
        self._refresh_annotation_labels()
        self._save_current_record()
        if self.current_video is not None:
            self._refresh_video_list_item_status(self.current_video)
        self.status.showMessage("Saved marker coordinates")

    def _on_negative_marker_placed(self, x_px: float, y_px: float, x_norm: float, y_norm: float) -> None:
        if self.current_record is None:
            return

        marker = Marker(
            x_px=int(round(x_px)),
            y_px=int(round(y_px)),
            x_norm=round(x_norm, 6),
            y_norm=round(y_norm, 6),
            captured_at_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        )
        add_negative_marker(self.current_record, marker)
        self._refresh_annotation_labels()
        self._save_current_record()
        self.status.showMessage("Added negative marker")

    def _on_roi_placed(
        self,
        x_px: float,
        y_px: float,
        w_px: float,
        h_px: float,
        x_norm: float,
        y_norm: float,
        w_norm: float,
        h_norm: float,
    ) -> None:
        if self.current_record is None:
            return

        meta_w = self.current_record.metadata.width if self.current_record.metadata is not None else None
        meta_h = self.current_record.metadata.height if self.current_record.metadata is not None else None

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

        set_crop_roi(self.current_record, crop_roi)
        self._refresh_annotation_labels()
        self._save_current_record()
        self.status.showMessage("Saved ROI rectangle")

    def _on_roi_invalid(self, message: str) -> None:
        self.status.showMessage(message)

    def _on_metadata_changed(self) -> None:
        if self.current_record is None:
            return

        resolution = self.player.metaData().value(QMediaMetaData.Key.Resolution)
        if resolution is not None:
            self.current_record.metadata.width = int(resolution.width())
            self.current_record.metadata.height = int(resolution.height())

        frame_rate = self.player.metaData().value(QMediaMetaData.Key.VideoFrameRate)
        if frame_rate is not None:
            self.current_record.metadata.fps = float(frame_rate)

        self._save_current_record()

    def _refresh_annotation_labels(self) -> None:
        if self.current_record is None:
            self.start_label.setText("START: -")
            self.end_label.setText("END: -")
            self.marker_label.setText("Marker: -")
            self.roi_label.setText("ROI: -")
            self.seek_slider.set_annotation_markers(None, None)
            self.video_widget.clear_marker()
            self.video_widget.clear_negative_markers()
            self.video_widget.clear_roi()
            return

        start = self.current_record.annotations.start_sec
        end = self.current_record.annotations.end_sec
        marker = self.current_record.annotations.marker
        negative_markers = self.current_record.annotations.negative_markers
        crop_roi = self.current_record.annotations.crop_roi

        self.start_label.setText(f"START: {self._format_seconds(start)}")
        self.end_label.setText(f"END: {self._format_seconds(end)}")
        self._refresh_timeline_markers()

        if marker is None:
            self.marker_label.setText(f"Markers: positive=- negative={len(negative_markers)}")
            self.video_widget.clear_marker()
        else:
            self.marker_label.setText(
                "Markers: "
                f"px=({marker.x_px}, {marker.y_px}) "
                f"norm=({marker.x_norm:.4f}, {marker.y_norm:.4f}) "
                f"negative={len(negative_markers)}"
            )
            self.video_widget.set_marker_norm(marker.x_norm, marker.y_norm)

        self.video_widget.set_negative_marker_norms(
            [(negative.x_norm, negative.y_norm) for negative in negative_markers]
        )

        if crop_roi is None:
            self.roi_label.setText("ROI: -")
            self.video_widget.clear_roi()
        else:
            self.roi_label.setText(
                "ROI: "
                f"px=({crop_roi.x_px}, {crop_roi.y_px}, {crop_roi.w_px}, {crop_roi.h_px}) "
                f"norm=({crop_roi.x_norm:.4f}, {crop_roi.y_norm:.4f}, "
                f"{crop_roi.w_norm:.4f}, {crop_roi.h_norm:.4f})"
            )
            self.video_widget.set_roi_norm_rect(
                crop_roi.x_norm,
                crop_roi.y_norm,
                crop_roi.w_norm,
                crop_roi.h_norm,
            )

    def _refresh_timeline_markers(self) -> None:
        if self.current_record is None:
            self.seek_slider.set_annotation_markers(None, None)
            return

        self.seek_slider.set_annotation_markers(
            self.current_record.annotations.start_sec,
            self.current_record.annotations.end_sec,
        )

    def _update_time_label(self, position_ms: int, duration_ms: int) -> None:
        self.time_label.setText(
            f"{self._format_milliseconds(position_ms)} / {self._format_milliseconds(duration_ms)}"
        )

    def _save_current_record(self) -> None:
        if self.current_record is None:
            return

        self.store.save(self.current_record)

    @staticmethod
    def _format_milliseconds(milliseconds: int) -> str:
        total_seconds = max(milliseconds, 0) / 1000.0
        return MainWindow._format_seconds(total_seconds)

    @staticmethod
    def _format_seconds(value: float | None) -> str:
        if value is None:
            return "-"
        minutes = int(value // 60)
        seconds = value - (minutes * 60)
        return f"{minutes:02d}:{seconds:06.3f}"

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._save_current_record()
        super().closeEvent(event)
