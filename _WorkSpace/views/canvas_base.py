from typing import Optional
from PIL import Image
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QImage,
    QPixmap,
    QPainter,
    QPen,
    QColor,
    QWheelEvent,
    QMouseEvent,
    QKeyEvent,
)
from PySide6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
)


def pil_to_qpixmap(pil_img: Image.Image) -> QPixmap:
    rgba_img = pil_img if pil_img.mode == "RGBA" else pil_img.convert("RGBA")
    data = rgba_img.tobytes("raw", "RGBA")
    qimg = QImage(
        data,
        rgba_img.width,
        rgba_img.height,
        rgba_img.width * 4,
        QImage.Format.Format_RGBA8888,
    )
    return QPixmap.fromImage(qimg.copy())


class PixelCanvasView(QGraphicsView):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self._pixmap_item: Optional[QGraphicsPixmapItem] = None
        self._image_width: int = 0
        self._image_height: int = 0

        self._grid_w: int = 16
        self._grid_h: int = 16
        self._show_grid: bool = True

        self._zoom_factor: float = 1.0
        self._is_panning: bool = False
        self._space_pressed: bool = False
        self._last_pan_pos = QPointF()

        self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

    @property
    def image_width(self) -> int:
        return self._image_width

    @property
    def image_height(self) -> int:
        return self._image_height

    def set_pil_image(self, pil_img: Optional[Image.Image], reset_view: bool = True) -> None:
        self._scene.clear()
        self._pixmap_item = None
        if pil_img is None:
            self._image_width = 0
            self._image_height = 0
            self._scene.setSceneRect(QRectF(0, 0, 1, 1))
            self.viewport().update()
            return

        pixmap = pil_to_qpixmap(pil_img)
        self._image_width = pixmap.width()
        self._image_height = pixmap.height()
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._pixmap_item.setZValue(0)
        self._scene.setSceneRect(QRectF(0, 0, self._image_width, self._image_height))
        if reset_view:
            self.reset_zoom()
        self.viewport().update()

    def set_grid(self, grid_w: int, grid_h: int, visible: bool = True) -> None:
        self._grid_w = max(1, grid_w)
        self._grid_h = max(1, grid_h)
        self._show_grid = visible
        self.viewport().update()

    def zoom_in(self) -> None:
        self._apply_zoom(1.25)

    def zoom_out(self) -> None:
        self._apply_zoom(0.8)

    def reset_zoom(self) -> None:
        self.resetTransform()
        self._zoom_factor = 1.0

    def _apply_zoom(self, factor: float) -> None:
        new_zoom = self._zoom_factor * factor
        if new_zoom < 0.25 or new_zoom > 32.0:
            return
        self._zoom_factor = new_zoom
        self.scale(factor, factor)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.angleDelta().y() > 0:
            self._apply_zoom(1.25)
        elif event.angleDelta().y() < 0:
            self._apply_zoom(0.8)
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_pressed = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_pressed = False
            if not self._is_panning:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if (
            event.button() == Qt.MouseButton.MiddleButton
            or (event.button() == Qt.MouseButton.LeftButton and self._space_pressed)
        ):
            self._is_panning = True
            self._last_pan_pos = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._is_panning:
            delta = event.position() - self._last_pan_pos
            self._last_pan_pos = event.position()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x())
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y())
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._is_panning and (
            event.button() == Qt.MouseButton.MiddleButton
            or event.button() == Qt.MouseButton.LeftButton
        ):
            self._is_panning = False
            self.setCursor(
                Qt.CursorShape.OpenHandCursor
                if self._space_pressed
                else Qt.CursorShape.ArrowCursor
            )
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, QColor(45, 45, 48))
        if self._image_width <= 0 or self._image_height <= 0:
            return

        img_rect = QRectF(0, 0, self._image_width, self._image_height).intersected(rect)
        if img_rect.isEmpty():
            return

        checker_size = 8
        c1 = QColor(200, 200, 200)
        c2 = QColor(150, 150, 150)

        start_x = int(img_rect.left() // checker_size) * checker_size
        start_y = int(img_rect.top() // checker_size) * checker_size
        end_x = int(img_rect.right())
        end_y = int(img_rect.bottom())

        for y in range(start_y, end_y + checker_size, checker_size):
            for x in range(start_x, end_x + checker_size, checker_size):
                cell_rect = QRectF(x, y, checker_size, checker_size).intersected(img_rect)
                if not cell_rect.isEmpty():
                    is_even = ((x // checker_size) + (y // checker_size)) % 2 == 0
                    painter.fillRect(cell_rect, c1 if is_even else c2)

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        if not self._show_grid or self._image_width <= 0 or self._image_height <= 0:
            return

        pen = QPen(QColor(255, 255, 255, 90))
        pen.setWidth(0)
        painter.setPen(pen)

        for x in range(0, self._image_width + 1, self._grid_w):
            painter.drawLine(x, 0, x, self._image_height)
        for y in range(0, self._image_height + 1, self._grid_h):
            painter.drawLine(0, y, self._image_width, y)
