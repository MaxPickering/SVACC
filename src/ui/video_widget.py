from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QResizeEvent
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsView,
    QVBoxLayout,
    QWidget,
)


@dataclass
class MarkerPlacement:
    x_px: int
    y_px: int
    x_norm: float
    y_norm: float


@dataclass
class RoiPlacement:
    x_px: int
    y_px: int
    w_px: int
    h_px: int
    x_norm: float
    y_norm: float
    w_norm: float
    h_norm: float


class VideoView(QGraphicsView):
    mouse_pressed = Signal(float, float, int)
    mouse_moved = Signal(float, float)
    mouse_released = Signal(float, float, int)
    OUTER_RADIUS = 9.0
    INNER_RADIUS = 5.5
    CROSSHAIR_HALF = 13.0

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._marker_scene_pos: QPointF | None = None
        self._negative_marker_scene_positions: list[QPointF] = []
        self._roi_scene_rect: QRectF | None = None
        self._roi_preview_scene_rect: QRectF | None = None
        self._roi_mode_enabled = False
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setRenderHints(self.renderHints())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            scene_pos = self.mapToScene(event.position().toPoint())
            self.mouse_pressed.emit(
                float(scene_pos.x()),
                float(scene_pos.y()),
                int(event.button().value),
            )
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        scene_pos = self.mapToScene(event.position().toPoint())
        self.mouse_moved.emit(float(scene_pos.x()), float(scene_pos.y()))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        scene_pos = self.mapToScene(event.position().toPoint())
        self.mouse_released.emit(
            float(scene_pos.x()),
            float(scene_pos.y()),
            int(event.button().value),
        )
        super().mouseReleaseEvent(event)

    def set_marker_scene_pos(self, pos: QPointF | None) -> None:
        self._marker_scene_pos = pos
        self.viewport().update()

    def set_negative_marker_scene_positions(self, positions: list[QPointF]) -> None:
        self._negative_marker_scene_positions = positions
        self.viewport().update()

    def set_roi_scene_rect(self, rect: QRectF | None) -> None:
        self._roi_scene_rect = rect
        self.viewport().update()

    def set_roi_preview_scene_rect(self, rect: QRectF | None) -> None:
        self._roi_preview_scene_rect = rect
        self.viewport().update()

    def set_roi_mode_enabled(self, enabled: bool) -> None:
        self._roi_mode_enabled = enabled
        self.viewport().update()

    def drawForeground(self, painter: QPainter, rect) -> None:  # type: ignore[no-untyped-def]
        super().drawForeground(painter, rect)
        painter.save()
        painter.resetTransform()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Draw green border when ROI mode is active
        if self._roi_mode_enabled:
            viewport_rect = self.viewport().rect()
            painter.setPen(QPen(QColor(0, 255, 0), 4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(viewport_rect.adjusted(0, 0, -1, -1))

        if self._marker_scene_pos is not None:
            self._draw_marker(painter, self._marker_scene_pos, QColor(220, 20, 60))

        for negative_marker_pos in self._negative_marker_scene_positions:
            self._draw_marker(painter, negative_marker_pos, QColor(50, 120, 255))

        if self._roi_scene_rect is not None:
            self._draw_roi_rect(painter, self._roi_scene_rect, QColor(0, 220, 120, 230), 2)

        if self._roi_preview_scene_rect is not None:
            self._draw_roi_rect(painter, self._roi_preview_scene_rect, QColor(255, 200, 0, 220), 2)

        painter.restore()

    def _draw_roi_rect(self, painter: QPainter, scene_rect: QRectF, color: QColor, pen_width: int) -> None:
        top_left = self.mapFromScene(scene_rect.topLeft())
        bottom_right = self.mapFromScene(scene_rect.bottomRight())
        view_rect = QRectF(QPointF(top_left), QPointF(bottom_right)).normalized()

        painter.setPen(QPen(color, pen_width))
        painter.setBrush(QColor(color.red(), color.green(), color.blue(), 40))
        painter.drawRect(view_rect)

    def _draw_marker(self, painter: QPainter, scene_pos: QPointF, fill_color: QColor) -> None:
        # Convert marker from scene space to viewport space and draw in pixel units,
        # so marker size stays constant regardless of fitInView scaling.
        view_point = self.mapFromScene(scene_pos)
        x = float(view_point.x())
        y = float(view_point.y())

        painter.setPen(QPen(QColor(0, 0, 0, 220), 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(x - self.CROSSHAIR_HALF, y), QPointF(x + self.CROSSHAIR_HALF, y))
        painter.drawLine(QPointF(x, y - self.CROSSHAIR_HALF), QPointF(x, y + self.CROSSHAIR_HALF))

        painter.setPen(QPen(QColor(255, 255, 255), 3))
        painter.setBrush(QColor(255, 255, 255, 35))
        painter.drawEllipse(QPointF(x, y), self.OUTER_RADIUS, self.OUTER_RADIUS)

        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.setBrush(fill_color)
        painter.drawEllipse(QPointF(x, y), self.INNER_RADIUS, self.INNER_RADIUS)


class ClickableVideoWidget(QWidget):
    marker_placed = Signal(float, float, float, float)
    negative_marker_placed = Signal(float, float, float, float)
    roi_placed = Signal(float, float, float, float, float, float, float, float)
    roi_invalid = Signal(str)
    MIN_ROI_WIDTH_PX = 8
    MIN_ROI_HEIGHT_PX = 8

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._video_width = 0
        self._video_height = 0
        self._marker_norm: tuple[float, float] | None = None
        self._negative_marker_norms: list[tuple[float, float]] = []
        self._roi_norm_rect: tuple[float, float, float, float] | None = None
        self._roi_mode_enabled = False
        self._roi_drag_start_scene: QPointF | None = None
        self._video_rect = QRectF(0.0, 0.0, 1.0, 1.0)

        self._scene = QGraphicsScene(self)
        self._view = VideoView(self)
        self._view.setScene(self._scene)
        self._view.mouse_pressed.connect(self._on_view_mouse_pressed)
        self._view.mouse_moved.connect(self._on_view_mouse_moved)
        self._view.mouse_released.connect(self._on_view_mouse_released)

        self._video_item = QGraphicsVideoItem()
        self._video_item.nativeSizeChanged.connect(self._on_native_size_changed)
        self._scene.addItem(self._video_item)

        container_layout = QVBoxLayout(self)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(self._view)

        self._update_fallback_video_rect()
        self._fit_video_in_view()

    def video_output(self) -> QGraphicsVideoItem:
        return self._video_item

    def _on_native_size_changed(self, size: QSizeF) -> None:
        if size.width() <= 0 or size.height() <= 0:
            return

        self._video_width = int(round(size.width()))
        self._video_height = int(round(size.height()))
        self._video_rect = QRectF(0.0, 0.0, size.width(), size.height())
        self._video_item.setSize(size)
        self._scene.setSceneRect(self._video_rect)
        self._fit_video_in_view()
        self._update_marker_graphics()
        self._update_negative_marker_graphics()
        self._update_roi_graphics()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_fallback_video_rect()
        self._fit_video_in_view()
        self._update_marker_graphics()
        self._update_negative_marker_graphics()
        self._update_roi_graphics()

    def _on_view_mouse_pressed(self, x: float, y: float, button: int) -> None:
        pos = QPointF(x, y)

        if button == int(Qt.MouseButton.RightButton.value):
            placement = self._calculate_marker_placement(pos)
            if placement is None:
                return

            self.add_negative_marker_norm(placement.x_norm, placement.y_norm)
            self.negative_marker_placed.emit(
                float(placement.x_px),
                float(placement.y_px),
                placement.x_norm,
                placement.y_norm,
            )
            return

        if button != int(Qt.MouseButton.LeftButton.value):
            return

        if self._roi_mode_enabled:
            display_rect = self._display_rect()
            if display_rect is None:
                return
            clamped = self._clamp_point_to_rect(pos, display_rect)
            self._roi_drag_start_scene = clamped
            self._view.set_roi_preview_scene_rect(QRectF(clamped, clamped))
            return

        placement = self._calculate_marker_placement(pos)
        if placement is None:
            return

        self.set_marker_norm(placement.x_norm, placement.y_norm)
        self.marker_placed.emit(
            float(placement.x_px),
            float(placement.y_px),
            placement.x_norm,
            placement.y_norm,
        )

    def _on_view_mouse_moved(self, x: float, y: float) -> None:
        if not self._roi_mode_enabled or self._roi_drag_start_scene is None:
            return

        display_rect = self._display_rect()
        if display_rect is None:
            return

        current = self._clamp_point_to_rect(QPointF(x, y), display_rect)
        preview = QRectF(self._roi_drag_start_scene, current).normalized()
        self._view.set_roi_preview_scene_rect(preview)

    def _on_view_mouse_released(self, x: float, y: float, button: int) -> None:
        if button != int(Qt.MouseButton.LeftButton.value):
            return
        if not self._roi_mode_enabled or self._roi_drag_start_scene is None:
            return

        display_rect = self._display_rect()
        if display_rect is None:
            self._roi_drag_start_scene = None
            self._view.set_roi_preview_scene_rect(None)
            return

        end = self._clamp_point_to_rect(QPointF(x, y), display_rect)
        roi_rect = QRectF(self._roi_drag_start_scene, end).normalized()
        self._roi_drag_start_scene = None
        self._view.set_roi_preview_scene_rect(None)

        placement = self._calculate_roi_placement(roi_rect)
        if placement is None:
            self.roi_invalid.emit(
                f"ROI too small. Minimum is {self.MIN_ROI_WIDTH_PX}x{self.MIN_ROI_HEIGHT_PX} pixels."
            )
            return

        self.set_roi_norm_rect(
            placement.x_norm,
            placement.y_norm,
            placement.w_norm,
            placement.h_norm,
        )
        self.roi_placed.emit(
            float(placement.x_px),
            float(placement.y_px),
            float(placement.w_px),
            float(placement.h_px),
            placement.x_norm,
            placement.y_norm,
            placement.w_norm,
            placement.h_norm,
        )

    def set_marker_norm(self, x_norm: float, y_norm: float) -> None:
        self._marker_norm = (
            min(max(x_norm, 0.0), 1.0),
            min(max(y_norm, 0.0), 1.0),
        )
        self._update_marker_graphics()

    def clear_marker(self) -> None:
        self._marker_norm = None
        self._view.set_marker_scene_pos(None)

    def set_negative_marker_norms(self, marker_norms: list[tuple[float, float]]) -> None:
        normalized: list[tuple[float, float]] = []
        for x_norm, y_norm in marker_norms:
            normalized.append((min(max(x_norm, 0.0), 1.0), min(max(y_norm, 0.0), 1.0)))
        self._negative_marker_norms = normalized
        self._update_negative_marker_graphics()

    def add_negative_marker_norm(self, x_norm: float, y_norm: float) -> None:
        self._negative_marker_norms.append(
            (min(max(x_norm, 0.0), 1.0), min(max(y_norm, 0.0), 1.0))
        )
        self._update_negative_marker_graphics()

    def clear_negative_markers(self) -> None:
        self._negative_marker_norms = []
        self._view.set_negative_marker_scene_positions([])

    def set_roi_mode_enabled(self, enabled: bool) -> None:
        self._roi_mode_enabled = enabled
        self._roi_drag_start_scene = None
        self._view.set_roi_preview_scene_rect(None)
        self._view.set_roi_mode_enabled(enabled)

    def is_roi_mode_enabled(self) -> bool:
        return self._roi_mode_enabled

    def set_roi_norm_rect(self, x_norm: float, y_norm: float, w_norm: float, h_norm: float) -> None:
        x = min(max(x_norm, 0.0), 1.0)
        y = min(max(y_norm, 0.0), 1.0)
        w = min(max(w_norm, 0.0), 1.0 - x)
        h = min(max(h_norm, 0.0), 1.0 - y)
        self._roi_norm_rect = (x, y, w, h)
        self._update_roi_graphics()

    def clear_roi(self) -> None:
        self._roi_norm_rect = None
        self._view.set_roi_scene_rect(None)

    def _display_rect(self) -> QRectF | None:
        if self._video_rect.width() <= 0 or self._video_rect.height() <= 0:
            return None
        return self._video_rect

    def _calculate_marker_placement(self, pos: QPointF) -> MarkerPlacement | None:
        display_rect = self._display_rect()
        if display_rect is None:
            return None

        if not display_rect.contains(pos):
            return None

        x_in_display = pos.x() - display_rect.left()
        y_in_display = pos.y() - display_rect.top()

        x_norm = min(max(x_in_display / display_rect.width(), 0.0), 1.0)
        y_norm = min(max(y_in_display / display_rect.height(), 0.0), 1.0)

        video_w = self._video_width or int(round(display_rect.width()))
        video_h = self._video_height or int(round(display_rect.height()))

        x_px = int(round(x_norm * video_w))
        y_px = int(round(y_norm * video_h))

        return MarkerPlacement(
            x_px=x_px,
            y_px=y_px,
            x_norm=round(x_norm, 6),
            y_norm=round(y_norm, 6),
        )

    def _fit_video_in_view(self) -> None:
        display_rect = self._display_rect()
        if display_rect is None:
            return
        self._view.fitInView(display_rect, Qt.AspectRatioMode.KeepAspectRatio)

    def _update_fallback_video_rect(self) -> None:
        if self._video_width > 0 and self._video_height > 0:
            return

        view_size = self._view.viewport().size()
        width = max(1, view_size.width())
        height = max(1, view_size.height())
        self._video_rect = QRectF(0.0, 0.0, float(width), float(height))
        self._video_item.setSize(QSizeF(float(width), float(height)))
        self._scene.setSceneRect(self._video_rect)

    def _clamp_point_to_rect(self, pos: QPointF, rect: QRectF) -> QPointF:
        clamped_x = min(max(pos.x(), rect.left()), rect.right())
        clamped_y = min(max(pos.y(), rect.top()), rect.bottom())
        return QPointF(clamped_x, clamped_y)

    def _calculate_roi_placement(self, roi_rect: QRectF) -> RoiPlacement | None:
        display_rect = self._display_rect()
        if display_rect is None:
            return None

        left = min(roi_rect.left(), roi_rect.right())
        top = min(roi_rect.top(), roi_rect.bottom())
        right = max(roi_rect.left(), roi_rect.right())
        bottom = max(roi_rect.top(), roi_rect.bottom())

        width = right - left
        height = bottom - top

        video_w = self._video_width or int(round(display_rect.width()))
        video_h = self._video_height or int(round(display_rect.height()))
        x_norm = min(max((left - display_rect.left()) / display_rect.width(), 0.0), 1.0)
        y_norm = min(max((top - display_rect.top()) / display_rect.height(), 0.0), 1.0)
        w_norm = min(max(width / display_rect.width(), 0.0), 1.0 - x_norm)
        h_norm = min(max(height / display_rect.height(), 0.0), 1.0 - y_norm)

        display_w_px = int(round(width))
        display_h_px = int(round(height))
        if display_w_px < self.MIN_ROI_WIDTH_PX or display_h_px < self.MIN_ROI_HEIGHT_PX:
            return None

        w_px = int(round(w_norm * video_w))
        h_px = int(round(h_norm * video_h))

        x_px = int(round(x_norm * video_w))
        y_px = int(round(y_norm * video_h))
        return RoiPlacement(
            x_px=x_px,
            y_px=y_px,
            w_px=w_px,
            h_px=h_px,
            x_norm=round(x_norm, 6),
            y_norm=round(y_norm, 6),
            w_norm=round(w_norm, 6),
            h_norm=round(h_norm, 6),
        )

    def _update_marker_graphics(self) -> None:
        display_rect = self._display_rect()
        if display_rect is None:
            self._view.set_marker_scene_pos(None)
            return

        if self._marker_norm is None:
            self._view.set_marker_scene_pos(None)
            return

        x = display_rect.left() + (self._marker_norm[0] * display_rect.width())
        y = display_rect.top() + (self._marker_norm[1] * display_rect.height())
        self._view.set_marker_scene_pos(QPointF(x, y))

    def _update_negative_marker_graphics(self) -> None:
        display_rect = self._display_rect()
        if display_rect is None:
            self._view.set_negative_marker_scene_positions([])
            return

        scene_positions: list[QPointF] = []
        for x_norm, y_norm in self._negative_marker_norms:
            x = display_rect.left() + (x_norm * display_rect.width())
            y = display_rect.top() + (y_norm * display_rect.height())
            scene_positions.append(QPointF(x, y))

        self._view.set_negative_marker_scene_positions(scene_positions)

    def _update_roi_graphics(self) -> None:
        display_rect = self._display_rect()
        if display_rect is None:
            self._view.set_roi_scene_rect(None)
            return

        if self._roi_norm_rect is None:
            self._view.set_roi_scene_rect(None)
            return

        x = display_rect.left() + (self._roi_norm_rect[0] * display_rect.width())
        y = display_rect.top() + (self._roi_norm_rect[1] * display_rect.height())
        w = self._roi_norm_rect[2] * display_rect.width()
        h = self._roi_norm_rect[3] * display_rect.height()
        self._view.set_roi_scene_rect(QRectF(x, y, w, h))
