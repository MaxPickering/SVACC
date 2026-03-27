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


class VideoView(QGraphicsView):
    clicked = Signal(float, float)
    OUTER_RADIUS = 9.0
    INNER_RADIUS = 5.5
    CROSSHAIR_HALF = 13.0

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._marker_scene_pos: QPointF | None = None
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setRenderHints(self.renderHints())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.position().toPoint())
            self.clicked.emit(float(scene_pos.x()), float(scene_pos.y()))
        super().mousePressEvent(event)

    def set_marker_scene_pos(self, pos: QPointF | None) -> None:
        self._marker_scene_pos = pos
        self.viewport().update()

    def drawForeground(self, painter: QPainter, rect) -> None:  # type: ignore[no-untyped-def]
        super().drawForeground(painter, rect)
        if self._marker_scene_pos is None:
            return

        # Convert marker from scene space to viewport space and draw in pixel units,
        # so marker size stays constant regardless of fitInView scaling.
        view_point = self.mapFromScene(self._marker_scene_pos)
        x = float(view_point.x())
        y = float(view_point.y())

        painter.save()
        painter.resetTransform()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(0, 0, 0, 220), 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(x - self.CROSSHAIR_HALF, y), QPointF(x + self.CROSSHAIR_HALF, y))
        painter.drawLine(QPointF(x, y - self.CROSSHAIR_HALF), QPointF(x, y + self.CROSSHAIR_HALF))

        painter.setPen(QPen(QColor(255, 255, 255), 3))
        painter.setBrush(QColor(255, 255, 255, 35))
        painter.drawEllipse(QPointF(x, y), self.OUTER_RADIUS, self.OUTER_RADIUS)

        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.setBrush(QColor(220, 20, 60))
        painter.drawEllipse(QPointF(x, y), self.INNER_RADIUS, self.INNER_RADIUS)
        painter.restore()


class ClickableVideoWidget(QWidget):
    marker_placed = Signal(float, float, float, float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._video_width = 0
        self._video_height = 0
        self._marker_norm: tuple[float, float] | None = None
        self._video_rect = QRectF(0.0, 0.0, 1.0, 1.0)

        self._scene = QGraphicsScene(self)
        self._view = VideoView(self)
        self._view.setScene(self._scene)
        self._view.clicked.connect(self._on_view_clicked)

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

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_fallback_video_rect()
        self._fit_video_in_view()
        self._update_marker_graphics()

    def _on_view_clicked(self, x: float, y: float) -> None:
        placement = self._calculate_marker_placement(QPointF(x, y))
        if placement is None:
            return

        self.set_marker_norm(placement.x_norm, placement.y_norm)
        self.marker_placed.emit(
            float(placement.x_px),
            float(placement.y_px),
            placement.x_norm,
            placement.y_norm,
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
