from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSlider, QStyle, QStyleOptionSlider, QWidget


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
