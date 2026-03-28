from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QSignalBlocker, Qt, QUrl
from PySide6.QtGui import QIcon, QIntValidator, QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaMetaData, QMediaPlayer
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from src.data.json_store import JsonStore
from src.ui.annotation_controller import AnnotationController
from src.ui.timeline_slider import TimelineSlider
from src.ui.video_manager import VideoManager
from src.ui.video_player_controller import VideoPlayerController
from src.ui.video_widget import ClickableVideoWidget


class MainWindow(QMainWindow):
    SETTINGS_ORG = "SVACC"
    SETTINGS_APP = "VideoAutoSegmenter"
    DEFAULT_POS_BOX_WIDTH = ClickableVideoWidget.DEFAULT_BOX_WIDTH
    DEFAULT_POS_BOX_HEIGHT = ClickableVideoWidget.DEFAULT_BOX_HEIGHT
    DEFAULT_NEG_BOX_WIDTH = ClickableVideoWidget.DEFAULT_BOX_WIDTH
    DEFAULT_NEG_BOX_HEIGHT = ClickableVideoWidget.DEFAULT_BOX_HEIGHT

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SVACC - Simple Video Annotator for Classes with Cropping")
        self.resize(1280, 760)
        self.app_settings = QSettings(self.SETTINGS_ORG, self.SETTINGS_APP)

        self.project_root = Path(__file__).resolve().parents[2]
        self.data_dir = self.project_root / "data"

        self.store = JsonStore(self.data_dir)
        self.video_manager = VideoManager(self.store, self.project_root)
        self.annotation_controller = AnnotationController(self)

        self.current_video: Path | None = None
        self.current_record = None
        self._marker_undo_stack: list[str] = []

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setMuted(True)
        self.player_controller = VideoPlayerController(self.player)

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

        self.play_pause_button = QPushButton("Play (Space)", self)
        play_icon = QIcon("src/ui/icons/media-play.svg") 
        self.play_pause_button.setIcon(play_icon)
        self.play_pause_button.clicked.connect(self._toggle_play_pause)

        self.mute_button = QPushButton("Unmute", self)
        mute_icon = QIcon("src/ui/icons/volume-off-outline.svg")
        self.mute_button.setIcon(mute_icon)
        self.mute_button.clicked.connect(self._toggle_mute)

        plus_icon = QIcon("src/ui/icons/plus-outline.svg")
        self.start_button = QPushButton("Set START (S)", self)
        self.start_button.setIcon(plus_icon)
        self.start_button.clicked.connect(self._set_start)

        self.mark_button = QPushButton("Set MARK (D)", self)
        self.mark_button.setIcon(plus_icon)
        self.mark_button.clicked.connect(self._add_mark)

        self.end_button = QPushButton("Set END (E)", self)
        self.end_button.setIcon(plus_icon)
        self.end_button.clicked.connect(self._set_end)

        self.roi_mode_button = QPushButton("ROI Mode: Off (R)", self)
        roi_icon = QIcon("src/ui/icons/crop-outline.svg")
        self.roi_mode_button.setIcon(roi_icon)
        self.roi_mode_button.clicked.connect(self._toggle_roi_mode)

        self.help_button = QPushButton("Help", self)
        help_icon = QIcon("src/ui/icons/question-mark-circle-outline.svg")
        self.help_button.setIcon(help_icon)
        self.help_button.clicked.connect(self._show_help)

        self.settings_button = QPushButton("Settings", self)
        self.settings_menu = QMenu(self.settings_button)
        self.settings_button.setMenu(self.settings_menu)
        self._build_settings_menu()
        self.settings_menu.aboutToHide.connect(self._on_settings_controls_changed)
        self._load_settings()

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

        controls.addStretch(0)

        controls.addWidget(self.start_button)
        controls.addWidget(self.mark_button)
        controls.addWidget(self.end_button)
        controls.addWidget(self.roi_mode_button)

        controls.addStretch(0)

        controls.addSpacing(10)
        controls.addWidget(self.settings_button)
        controls.addWidget(self.help_button)
        controls.addSpacing(10)

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

    def _build_settings_menu(self) -> None:
        menu_content = QWidget(self.settings_menu)
        form_layout = QFormLayout(menu_content)
        form_layout.setContentsMargins(10, 8, 10, 8)
        form_layout.setHorizontalSpacing(10)
        form_layout.setVerticalSpacing(6)

        self.settings_enable_checkbox = QCheckBox("Enable bounding boxes", menu_content)
        self.settings_pos_box_width = QLineEdit(menu_content)
        self.settings_pos_box_height = QLineEdit(menu_content)
        self.settings_neg_box_width = QLineEdit(menu_content)
        self.settings_neg_box_height = QLineEdit(menu_content)

        int_validator = QIntValidator(1, 999, menu_content)
        self.settings_pos_box_width.setValidator(int_validator)
        self.settings_pos_box_height.setValidator(int_validator)
        self.settings_neg_box_width.setValidator(int_validator)
        self.settings_neg_box_height.setValidator(int_validator)

        self.settings_enable_checkbox.toggled.connect(self._on_settings_controls_changed)
        self.settings_pos_box_width.editingFinished.connect(self._on_settings_controls_changed)
        self.settings_pos_box_height.editingFinished.connect(self._on_settings_controls_changed)
        self.settings_neg_box_width.editingFinished.connect(self._on_settings_controls_changed)
        self.settings_neg_box_height.editingFinished.connect(self._on_settings_controls_changed)

        form_layout.addRow(self.settings_enable_checkbox)
        form_layout.addRow("Positive class box width", self.settings_pos_box_width)
        form_layout.addRow("Positive class box height", self.settings_pos_box_height)
        form_layout.addRow("Negative class box width", self.settings_neg_box_width)
        form_layout.addRow("Negative class box height", self.settings_neg_box_height)

        menu_action = QWidgetAction(self.settings_menu)
        menu_action.setDefaultWidget(menu_content)
        self.settings_menu.addAction(menu_action)

    def _load_settings(self) -> None:
        enabled = self.app_settings.value("bounding_boxes/enabled", True, type=bool)
        self.settings_enable_checkbox.setChecked(enabled)
        pos_w, pos_h, neg_w, neg_h = self._record_or_default_box_sizes()
        self._set_box_size_controls(pos_w, pos_h, neg_w, neg_h)
        self._apply_bounding_box_settings(enabled, pos_w, pos_h, neg_w, neg_h)

    def _line_edit_int(self, line_edit: QLineEdit, default: int) -> int:
        text = line_edit.text().strip()
        if not text:
            return default
        try:
            return max(int(text), 1)
        except ValueError:
            return default

    def _on_settings_controls_changed(self) -> None:
        enabled = self.settings_enable_checkbox.isChecked()
        pos_w = self._line_edit_int(self.settings_pos_box_width, self.DEFAULT_POS_BOX_WIDTH)
        pos_h = self._line_edit_int(self.settings_pos_box_height, self.DEFAULT_POS_BOX_HEIGHT)
        neg_w = self._line_edit_int(self.settings_neg_box_width, self.DEFAULT_NEG_BOX_WIDTH)
        neg_h = self._line_edit_int(self.settings_neg_box_height, self.DEFAULT_NEG_BOX_HEIGHT)

        self._set_box_size_controls(pos_w, pos_h, neg_w, neg_h)

        self._apply_bounding_box_settings(enabled, pos_w, pos_h, neg_w, neg_h)
        self._persist_box_sizes_to_current_record(pos_w, pos_h, neg_w, neg_h)
        self._save_settings(enabled)

    def _record_or_default_box_sizes(self) -> tuple[int, int, int, int]:
        if self.current_record is None:
            return (
                self.DEFAULT_POS_BOX_WIDTH,
                self.DEFAULT_POS_BOX_HEIGHT,
                self.DEFAULT_NEG_BOX_WIDTH,
                self.DEFAULT_NEG_BOX_HEIGHT,
            )

        annotations = self.current_record.annotations
        pos_w = annotations.positive_box_width_px or self.DEFAULT_POS_BOX_WIDTH
        pos_h = annotations.positive_box_height_px or self.DEFAULT_POS_BOX_HEIGHT
        neg_w = annotations.negative_box_width_px or self.DEFAULT_NEG_BOX_WIDTH
        neg_h = annotations.negative_box_height_px or self.DEFAULT_NEG_BOX_HEIGHT
        return (max(pos_w, 1), max(pos_h, 1), max(neg_w, 1), max(neg_h, 1))

    def _set_box_size_controls(self, pos_w: int, pos_h: int, neg_w: int, neg_h: int) -> None:
        with QSignalBlocker(self.settings_pos_box_width):
            self.settings_pos_box_width.setText(str(pos_w))
        with QSignalBlocker(self.settings_pos_box_height):
            self.settings_pos_box_height.setText(str(pos_h))
        with QSignalBlocker(self.settings_neg_box_width):
            self.settings_neg_box_width.setText(str(neg_w))
        with QSignalBlocker(self.settings_neg_box_height):
            self.settings_neg_box_height.setText(str(neg_h))

    def _sync_box_sizes_from_current_record(self) -> None:
        pos_w, pos_h, neg_w, neg_h = self._record_or_default_box_sizes()
        enabled = self.settings_enable_checkbox.isChecked()
        self._set_box_size_controls(pos_w, pos_h, neg_w, neg_h)
        self._apply_bounding_box_settings(enabled, pos_w, pos_h, neg_w, neg_h)

    def _persist_box_sizes_to_current_record(self, pos_w: int, pos_h: int, neg_w: int, neg_h: int) -> None:
        if self.current_record is None:
            return

        annotations = self.current_record.annotations
        annotations.positive_box_width_px = pos_w
        annotations.positive_box_height_px = pos_h
        annotations.negative_box_width_px = neg_w
        annotations.negative_box_height_px = neg_h
        self._save_current_record()

    def _apply_bounding_box_settings(
        self,
        enabled: bool,
        pos_w: int,
        pos_h: int,
        neg_w: int,
        neg_h: int,
    ) -> None:
        self.video_widget.set_bounding_boxes_enabled(enabled)
        self.video_widget.set_positive_box_size(pos_w, pos_h)
        self.video_widget.set_negative_box_size(neg_w, neg_h)

    def _save_settings(self, enabled: bool) -> None:
        self.app_settings.setValue("bounding_boxes/enabled", enabled)
        self.app_settings.sync()

    def _wire_player_events(self) -> None:
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.player.metaDataChanged.connect(self._on_metadata_changed)
        self.player.errorOccurred.connect(self._on_player_error)

    def _setup_shortcuts(self) -> None:
        self._register_shortcut(QKeySequence(Qt.Key.Key_Space), self._toggle_play_pause)
        self._register_shortcut(QKeySequence(Qt.Key.Key_Right), self.player_controller.seek_forward)
        self._register_shortcut(QKeySequence(Qt.Key.Key_Left), self.player_controller.seek_backward)
        self._register_shortcut(QKeySequence(Qt.Key.Key_S), self._set_start)
        self._register_shortcut(QKeySequence(Qt.Key.Key_D), self._add_mark)
        self._register_shortcut(QKeySequence(Qt.Key.Key_E), self._set_end)
        self._register_shortcut(QKeySequence(Qt.Key.Key_R), self._toggle_roi_mode)
        self._register_shortcut(QKeySequence.StandardKey.Undo, self._undo_marker)

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

        deleted_count = self.video_manager.delete_all_annotations()

        self.current_video = None
        self.current_record = None
        self._marker_undo_stack.clear()
        self._sync_box_sizes_from_current_record()
        self._refresh_annotation_labels()
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

        metadata = self.video_manager.get_video_metadata(self.current_video)
        deleted = self.video_manager.delete_video_annotations(metadata.relative_path)

        self.current_record = self.video_manager.load_or_create_record(self.current_video)
        self._marker_undo_stack.clear()
        self._sync_box_sizes_from_current_record()
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
        videos = self.video_manager.list_videos()

        for video in videos:
            record = self.video_manager.load_or_create_record(video)
            is_complete = self.video_manager.record_is_complete(record)
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

    def _refresh_video_list_item_status(self, video_path: Path) -> None:
        if self.current_record is None:
            return

        is_complete = self.video_manager.record_is_complete(self.current_record)
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
        self.current_record = self.video_manager.load_or_create_record(video_path)
        self._marker_undo_stack.clear()
        self._sync_box_sizes_from_current_record()

        self.player.setSource(QUrl.fromLocalFile(str(video_path)))
        self.player.pause()
        self.player.setPosition(self.current_record.annotations.last_position_ms)
        self._refresh_annotation_labels()
        self._refresh_video_list_item_status(video_path)
        self.status.showMessage(f"Loaded {video_path.name}")

    def _on_player_error(self, error, error_string: str) -> None:  # type: ignore[no-untyped-def]
        if error == QMediaPlayer.Error.NoError:
            return
        self.status.showMessage(f"Player error: {error_string}")

    def _toggle_play_pause(self) -> None:
        self.player_controller.toggle_play_pause()

    def _toggle_mute(self) -> None:
        old_muted = self.audio_output.isMuted()
        self.player_controller.toggle_mute(self.audio_output)
        self._update_mute_button_text()
        self.status.showMessage("Audio muted" if not old_muted else "Audio unmuted")

    def _toggle_roi_mode(self) -> None:
        enabled = not self.video_widget.is_roi_mode_enabled()
        self.video_widget.set_roi_mode_enabled(enabled)
        if enabled:
            self.roi_mode_button.setText("ROI Mode: On (R)")
            self.roi_mode_button.setStyleSheet("background-color: #00ff00; font-weight: bold;")
            self.status.showMessage("ROI mode enabled. Click and drag to draw rectangle.")
        else:
            self.roi_mode_button.setText("ROI Mode: Off (R)")
            self.roi_mode_button.setStyleSheet("")
            self.status.showMessage("ROI mode disabled")

    def _show_help(self) -> None:
        QMessageBox.information(
            self,
            "Help",
            "Keyboard Shortcuts:\n"
            "Space - Play/Pause\n"
            "M - Mute/Unmute\n"
            "D - Add MARK\n"
            "R - Toggle ROI Mode\n"
            "Z - Undo Marker\n"
            "Ctrl + Z - Undo Marker Placement\n\n"
            "Info:\n"
            "Positive markers are represented by a red dot. Negative markers are represented by blue dots.\n"
            "ROI mode (Region Of Interest): When in ROI mode a green outline will be displayed around video preview. Click and drag to create a ROI selection.\n"
            "Videos that have START, END, a negative class data will recieve a checkmark next to their names in the video manager.\n"
            "In the Settings menu bounding boxes can be enabled/disabled and their size can be configured. The bounding box is a rectangle drawn around placed markers.\n"
        )

    def _update_mute_button_text(self) -> None:
        if self.audio_output.isMuted():
            self.mute_button.setText("Unmute")
        else:
            self.mute_button.setText("Mute")

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_pause_button.setText("Pause (Space)")
        else:
            self.play_pause_button.setText("Play (Space)")

    def _on_duration_changed(self, duration_ms: int) -> None:
        self.seek_slider.setRange(0, max(duration_ms, 0))
        self._update_time_label(self.player.position(), duration_ms)
        self._refresh_timeline_markers()

        if self.current_record is not None:
            self.current_record.metadata.duration_ms = duration_ms
            self._save_current_record()

    def _on_position_changed(self, position_ms: int) -> None:
        if not self.player_controller.is_user_scrubbing:
            with QSignalBlocker(self.seek_slider):
                self.seek_slider.setValue(position_ms)

        self._update_time_label(position_ms, self.player.duration())

        if self.current_record is not None:
            self.current_record.annotations.last_position_ms = position_ms

    def _on_slider_pressed(self) -> None:
        self.player_controller.is_user_scrubbing = True

    def _on_slider_released(self) -> None:
        self.player_controller.is_user_scrubbing = False
        self.player.setPosition(self.seek_slider.value())

    def _on_slider_moved(self, position_ms: int) -> None:
        self._update_time_label(position_ms, self.player.duration())

    def _set_start(self) -> None:
        success, message = self.annotation_controller.set_start(self.current_record, self.player.position())
        if not success:
            QMessageBox.warning(self, "Invalid START", message.replace(" not saved:", ""))
        self._refresh_annotation_labels()
        self._save_current_record()
        if self.current_video is not None:
            self._refresh_video_list_item_status(self.current_video)
        self.status.showMessage(message)

    def _set_end(self) -> None:
        success, message = self.annotation_controller.set_end(self.current_record, self.player.position())
        if not success:
            QMessageBox.warning(self, "Invalid END", message.replace(" not saved:", ""))
        self._refresh_annotation_labels()
        self._save_current_record()
        if self.current_video is not None:
            self._refresh_video_list_item_status(self.current_video)
        self.status.showMessage(message)

    def _add_mark(self) -> None:
        success, message = self.annotation_controller.add_mark(self.current_record, self.player.position())
        if not success:
            QMessageBox.warning(self, "Invalid MARK", message)
        self._refresh_annotation_labels()
        self._save_current_record()
        if self.current_video is not None:
            self._refresh_video_list_item_status(self.current_video)
        self.status.showMessage(message)

    def _undo_marker(self) -> None:
        if self.current_record is None:
            self.status.showMessage("No video loaded")
            return

        action: str | None = None
        if self._marker_undo_stack:
            action = self._marker_undo_stack.pop()
        elif self.current_record.annotations.negative_markers:
            action = "negative"
        elif self.current_record.annotations.marker is not None:
            action = "positive"

        if action == "negative":
            success, message = self.annotation_controller.undo_negative_marker(self.current_record)
        else:
            success, message = self.annotation_controller.undo_marker(self.current_record)

        if not success:
            self.status.showMessage(message)
            return

        self._refresh_annotation_labels()
        self._save_current_record()
        if self.current_video is not None:
            self._refresh_video_list_item_status(self.current_video)
        self.status.showMessage(message)

    def _on_marker_placed(self, x_px: float, y_px: float, x_norm: float, y_norm: float) -> None:
        pos_w = self._line_edit_int(self.settings_pos_box_width, self.DEFAULT_POS_BOX_WIDTH)
        pos_h = self._line_edit_int(self.settings_pos_box_height, self.DEFAULT_POS_BOX_HEIGHT)
        self.annotation_controller.add_marker(self.current_record, x_px, y_px, x_norm, y_norm, pos_w, pos_h)
        self._marker_undo_stack.append("positive")
        self._refresh_annotation_labels()
        self._save_current_record()
        if self.current_video is not None:
            self._refresh_video_list_item_status(self.current_video)
        self.status.showMessage("Saved marker coordinates")

    def _on_negative_marker_placed(self, x_px: float, y_px: float, x_norm: float, y_norm: float) -> None:
        neg_w = self._line_edit_int(self.settings_neg_box_width, self.DEFAULT_NEG_BOX_WIDTH)
        neg_h = self._line_edit_int(self.settings_neg_box_height, self.DEFAULT_NEG_BOX_HEIGHT)
        self.annotation_controller.add_negative_marker(self.current_record, x_px, y_px, x_norm, y_norm, neg_w, neg_h)
        self._marker_undo_stack.append("negative")
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
        self.annotation_controller.set_roi(
            self.current_record,
            x_px,
            y_px,
            w_px,
            h_px,
            x_norm,
            y_norm,
            w_norm,
            h_norm,
        )
        self._refresh_annotation_labels()
        self._save_current_record()
        self.status.showMessage("Saved ROI rectangle")

    def _on_roi_invalid(self, message: str) -> None:
        self.annotation_controller.show_roi_error(message)
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
            self.seek_slider.set_annotation_markers(None, None, [])
            self.video_widget.clear_marker()
            self.video_widget.clear_negative_markers()
            self.video_widget.clear_roi()
            return

        start = self.current_record.annotations.start_sec
        end = self.current_record.annotations.end_sec
        marks = self.current_record.annotations.marks_sec
        marker = self.current_record.annotations.marker
        negative_markers = self.current_record.annotations.negative_markers
        crop_roi = self.current_record.annotations.crop_roi

        self.start_label.setText(f"START: {self._format_seconds(start)}")
        self.end_label.setText(f"END: {self._format_seconds(end)}")
        self._refresh_timeline_markers()

        if marker is None:
            self.marker_label.setText(
                f"Markers: positive=- negative={len(negative_markers)} marks={len(marks)}"
            )
            self.video_widget.clear_marker()
        else:
            self.marker_label.setText(
                "Markers: "
                f"px=({marker.x_px}, {marker.y_px}) "
                f"norm=({marker.x_norm:.4f}, {marker.y_norm:.4f}) "
                f"negative={len(negative_markers)} "
                f"marks={len(marks)}"
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
            self.seek_slider.set_annotation_markers(None, None, [])
            return

        self.seek_slider.set_annotation_markers(
            self.current_record.annotations.start_sec,
            self.current_record.annotations.end_sec,
            self.current_record.annotations.marks_sec,
        )

    def _update_time_label(self, position_ms: int, duration_ms: int) -> None:
        self.time_label.setText(
            f"{self._format_milliseconds(position_ms)} / {self._format_milliseconds(duration_ms)}"
        )

    def _save_current_record(self) -> None:
        if self.current_record is None:
            return
        self.video_manager.save_record(self.current_record)

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
        self._on_settings_controls_changed()
        self._save_current_record()
        super().closeEvent(event)
