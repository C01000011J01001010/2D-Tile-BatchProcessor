import math
from typing import Optional, Dict
from PIL import Image
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QEvent
from PySide6.QtGui import (
    QPainter,
    QPen,
    QColor,
    QFont,
    QPolygonF,
    QMouseEvent,
    QKeyEvent,
    QShortcut,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QGroupBox,
    QFormLayout,
    QSpinBox,
    QLineEdit,
    QCheckBox,
    QPushButton,
    QButtonGroup,
    QListWidget,
    QListWidgetItem,
    QFileDialog,
    QLabel,
    QMessageBox,
)

from models.project_model import ProjectModel
from models.region_data import RegionData
from commands.base_command import CommandManager
from commands.region_commands import (
    AddRegionCommand,
    DeleteRegionCommand,
    ModifyRegionCommand,
    AutoSliceRegionsCommand,
)
from services.image_service import ImageService
from .canvas_base import PixelCanvasView


class RegionSlicerCanvas(PixelCanvasView):
    MODE_SELECT = 1
    MODE_MOVE = 2
    MODE_RESIZE = 3

    region_selected = Signal(str)
    region_drawn = Signal(int, int, int, int)
    region_modified = Signal(str, int, int, int, int)
    edit_mode_changed = Signal(int)
    wasd_move_requested = Signal(int, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._project: Optional[ProjectModel] = None
        self._selected_region_id: str = ""
        self._edit_mode: int = self.MODE_SELECT

        self._snap_enabled: bool = True
        self._snap_size: int = 16

        self._is_drawing: bool = False
        self._drag_start_scene = QPointF()
        self._current_drag_rect = QRectF()

        # Mode 2 / Mode 3 gizmo interaction state
        self._active_handle: str = ""  # "", "MOVE_XY", "MOVE_X", "MOVE_Y", "RESIZE_T", "RESIZE_B", "RESIZE_L", "RESIZE_R"
        self._orig_region_rect = QRectF()
        self._preview_rect = QRectF()

    @property
    def edit_mode(self) -> int:
        return self._edit_mode

    def set_edit_mode(self, mode: int) -> None:
        if mode in (self.MODE_MOVE, self.MODE_RESIZE) and not self._selected_region_id:
            mode = self.MODE_SELECT
        if mode not in (self.MODE_SELECT, self.MODE_MOVE, self.MODE_RESIZE):
            mode = self.MODE_SELECT

        self._active_handle = ""
        self._preview_rect = QRectF()
        if self._edit_mode != mode:
            self._edit_mode = mode
            self.edit_mode_changed.emit(self._edit_mode)
        self._update_hover_cursor(QPointF(-9999, -9999))
        self.viewport().update()

    def cycle_edit_mode(self) -> None:
        if not self._selected_region_id:
            self.set_edit_mode(self.MODE_SELECT)
            return
        next_mode = (self._edit_mode % 3) + 1
        self.set_edit_mode(next_mode)

    def set_project(self, project: ProjectModel) -> None:
        self._project = project
        self._selected_region_id = ""
        self.set_edit_mode(self.MODE_SELECT)
        self.viewport().update()

    def set_selected_region(self, region_id: str) -> None:
        if region_id != self._selected_region_id:
            self._selected_region_id = region_id
            # 새로운 Region 선택(또는 선택 해제) 시 반드시 사용모드 1로 초기화
            self.set_edit_mode(self.MODE_SELECT)
        elif not region_id:
            self.set_edit_mode(self.MODE_SELECT)
        self.viewport().update()

    def set_snap(self, enabled: bool, snap_size: int) -> None:
        self._snap_enabled = enabled
        self._snap_size = max(1, snap_size)
        self.set_grid(self._snap_size, self._snap_size, True)

    def _snap_floor(self, val: float) -> int:
        if not self._snap_enabled:
            return int(round(val))
        return int(math.floor(val / self._snap_size) * self._snap_size)

    def _snap_ceil(self, val: float) -> int:
        if not self._snap_enabled:
            return int(round(val))
        return int(math.ceil(val / self._snap_size) * self._snap_size)

    def _snap_delta(self, delta: float) -> int:
        if not self._snap_enabled:
            return int(round(delta))
        return int(round(delta / self._snap_size) * self._snap_size)

    def _clamp_scene_point(self, pt: QPointF) -> QPointF:
        x = max(0.0, min(float(self.image_width), pt.x()))
        y = max(0.0, min(float(self.image_height), pt.y()))
        return QPointF(x, y)

    def _inv_zoom(self) -> float:
        m11 = self.transform().m11()
        return 1.0 / m11 if m11 > 0 else 1.0

    def _get_selected_region_obj(self) -> Optional[RegionData]:
        if self._project is None or not self._selected_region_id:
            return None
        return self._project.get_region_by_id(self._selected_region_id)

    def _get_active_region_rect(self, region: RegionData) -> QRectF:
        if (
            self._active_handle
            and not self._preview_rect.isEmpty()
            and region.region_id == self._selected_region_id
        ):
            return QRectF(self._preview_rect)
        return QRectF(region.x, region.y, region.width, region.height)

    def _get_move_gizmo_hitboxes(self, rect: QRectF) -> Dict[str, QRectF]:
        iz = self._inv_zoom()
        cx = rect.center().x()
        cy = rect.center().y()

        box_half = 7.0 * iz
        arrow_len = 36.0 * iz
        hit_half = 6.0 * iz

        center_rect = QRectF(cx - box_half, cy - box_half, box_half * 2.0, box_half * 2.0)
        x_rect = QRectF(cx + box_half, cy - hit_half, arrow_len - box_half + 4.0 * iz, hit_half * 2.0)
        y_rect = QRectF(cx - hit_half, cy + box_half, hit_half * 2.0, arrow_len - box_half + 4.0 * iz)
        return {
            "MOVE_XY": center_rect,
            "MOVE_X": x_rect,
            "MOVE_Y": y_rect,
        }

    def _get_resize_edge_handles(self, rect: QRectF) -> Dict[str, QRectF]:
        iz = self._inv_zoom()
        cx = rect.center().x()
        cy = rect.center().y()

        bar_w = min(28.0 * iz, max(8.0 * iz, rect.width() * 0.45))
        bar_h = min(28.0 * iz, max(8.0 * iz, rect.height() * 0.45))
        thick = 7.0 * iz

        return {
            "RESIZE_T": QRectF(cx - bar_w / 2.0, rect.top() - thick / 2.0, bar_w, thick),
            "RESIZE_B": QRectF(cx - bar_w / 2.0, rect.bottom() - thick / 2.0, bar_w, thick),
            "RESIZE_L": QRectF(rect.left() - thick / 2.0, cy - bar_h / 2.0, thick, bar_h),
            "RESIZE_R": QRectF(rect.right() - thick / 2.0, cy - bar_h / 2.0, thick, bar_h),
        }

    def _hit_test_handle(self, scene_pos: QPointF) -> str:
        reg = self._get_selected_region_obj()
        if reg is None:
            return ""
        r_rect = self._get_active_region_rect(reg)

        if self._edit_mode == self.MODE_MOVE:
            boxes = self._get_move_gizmo_hitboxes(r_rect)
            for name in ("MOVE_XY", "MOVE_X", "MOVE_Y"):
                if boxes[name].contains(scene_pos):
                    return name
        elif self._edit_mode == self.MODE_RESIZE:
            iz = self._inv_zoom()
            pad = 4.0 * iz
            handles = self._get_resize_edge_handles(r_rect)
            for name, h_rect in handles.items():
                if h_rect.adjusted(-pad, -pad, pad, pad).contains(scene_pos):
                    return name
            # Also allow grabbing along the 4 edges directly
            edge_band = 4.5 * iz
            if r_rect.left() <= scene_pos.x() <= r_rect.right():
                if abs(scene_pos.y() - r_rect.top()) <= edge_band:
                    return "RESIZE_T"
                if abs(scene_pos.y() - r_rect.bottom()) <= edge_band:
                    return "RESIZE_B"
            if r_rect.top() <= scene_pos.y() <= r_rect.bottom():
                if abs(scene_pos.x() - r_rect.left()) <= edge_band:
                    return "RESIZE_L"
                if abs(scene_pos.x() - r_rect.right()) <= edge_band:
                    return "RESIZE_R"
        return ""

    def _update_hover_cursor(self, scene_pos: QPointF) -> None:
        if self._is_panning:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if self._space_pressed:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            return

        handle = self._active_handle or self._hit_test_handle(scene_pos)
        if handle == "MOVE_XY":
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        elif handle == "MOVE_X":
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif handle == "MOVE_Y":
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif handle in ("RESIZE_T", "RESIZE_B"):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif handle in ("RESIZE_L", "RESIZE_R"):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if (
            self._edit_mode == self.MODE_MOVE
            and self._selected_region_id
            and not (event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier))
        ):
            step = self._snap_size if self._snap_enabled else 1
            k = event.key()
            if k == Qt.Key.Key_W:
                self.wasd_move_requested.emit(0, -step)
                event.accept()
                return
            if k == Qt.Key.Key_S:
                self.wasd_move_requested.emit(0, step)
                event.accept()
                return
            if k == Qt.Key.Key_A:
                self.wasd_move_requested.emit(-step, 0)
                event.accept()
                return
            if k == Qt.Key.Key_D:
                self.wasd_move_requested.emit(step, 0)
                event.accept()
                return

        super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.setFocus()
        if (
            event.button() == Qt.MouseButton.LeftButton
            and not self._space_pressed
            and self.image_width > 0
            and self._project is not None
        ):
            scene_pos = self.mapToScene(event.position().toPoint())

            # 1. Mode 2 / Mode 3: Check gizmo / handle hit first
            if self._edit_mode in (self.MODE_MOVE, self.MODE_RESIZE) and self._selected_region_id:
                hit_handle = self._hit_test_handle(scene_pos)
                if hit_handle:
                    reg = self._get_selected_region_obj()
                    if reg is not None:
                        self._active_handle = hit_handle
                        self._drag_start_scene = scene_pos
                        self._orig_region_rect = QRectF(reg.x, reg.y, reg.width, reg.height)
                        self._preview_rect = QRectF(self._orig_region_rect)
                        self._update_hover_cursor(scene_pos)
                        self.viewport().update()
                        event.accept()
                        return

            # 2. Check region selection (unless Shift is held in Mode 1 to draw overlapping region)
            if not (
                self._edit_mode == self.MODE_SELECT
                and (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            ):
                for region in reversed(self._project.regions):
                    r_rect = QRectF(region.x, region.y, region.width, region.height)
                    if r_rect.contains(scene_pos):
                        if region.region_id != self._selected_region_id:
                            self._selected_region_id = region.region_id
                            self.set_edit_mode(self.MODE_SELECT)
                            self.region_selected.emit(region.region_id)
                        self.viewport().update()
                        event.accept()
                        return

                # Clicked empty space: clear selection & reset to Mode 1
                if self._selected_region_id or self._edit_mode != self.MODE_SELECT:
                    self._selected_region_id = ""
                    self.set_edit_mode(self.MODE_SELECT)
                    self.region_selected.emit("")
                    self.viewport().update()

            # 3. In Mode 1, dragging on empty space (or Shift+drag) draws a new region
            if self._edit_mode == self.MODE_SELECT:
                self._is_drawing = True
                self._drag_start_scene = self._clamp_scene_point(scene_pos)
                self._current_drag_rect = QRectF()
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._is_panning:
            super().mouseMoveEvent(event)
            return

        scene_pos = self.mapToScene(event.position().toPoint())

        if self._active_handle and (event.buttons() & Qt.MouseButton.LeftButton):
            reg = self._get_selected_region_obj()
            if reg is not None:
                dx = scene_pos.x() - self._drag_start_scene.x()
                dy = scene_pos.y() - self._drag_start_scene.y()

                ox = int(self._orig_region_rect.x())
                oy = int(self._orig_region_rect.y())
                ow = int(self._orig_region_rect.width())
                oh = int(self._orig_region_rect.height())

                if self._active_handle in ("MOVE_XY", "MOVE_X", "MOVE_Y"):
                    sdx = self._snap_delta(dx) if self._active_handle in ("MOVE_XY", "MOVE_X") else 0
                    sdy = self._snap_delta(dy) if self._active_handle in ("MOVE_XY", "MOVE_Y") else 0
                    nx = max(0, min(self.image_width - ow, ox + sdx))
                    ny = max(0, min(self.image_height - oh, oy + sdy))
                    self._preview_rect = QRectF(nx, ny, ow, oh)

                elif self._active_handle.startswith("RESIZE_"):
                    min_w = max(reg.tile_width, self._snap_size if self._snap_enabled else 1)
                    min_h = max(reg.tile_height, self._snap_size if self._snap_enabled else 1)
                    left = ox
                    top = oy
                    right = ox + ow
                    bottom = oy + oh

                    if self._active_handle == "RESIZE_L":
                        new_left = ox + self._snap_delta(dx)
                        left = max(0, min(right - min_w, new_left))
                    elif self._active_handle == "RESIZE_R":
                        new_right = right + self._snap_delta(dx)
                        right = max(left + min_w, min(self.image_width, new_right))
                    elif self._active_handle == "RESIZE_T":
                        new_top = oy + self._snap_delta(dy)
                        top = max(0, min(bottom - min_h, new_top))
                    elif self._active_handle == "RESIZE_B":
                        new_bottom = bottom + self._snap_delta(dy)
                        bottom = max(top + min_h, min(self.image_height, new_bottom))

                    self._preview_rect = QRectF(left, top, right - left, bottom - top)

                self.viewport().update()
            event.accept()
            return

        if self._is_drawing:
            curr = self._clamp_scene_point(scene_pos)
            x1 = min(self._drag_start_scene.x(), curr.x())
            y1 = min(self._drag_start_scene.y(), curr.y())
            x2 = max(self._drag_start_scene.x(), curr.x())
            y2 = max(self._drag_start_scene.y(), curr.y())

            sx1 = max(0, self._snap_floor(x1))
            sy1 = max(0, self._snap_floor(y1))
            sx2 = min(self.image_width, self._snap_ceil(x2))
            sy2 = min(self.image_height, self._snap_ceil(y2))

            self._current_drag_rect = QRectF(sx1, sy1, max(0, sx2 - sx1), max(0, sy2 - sy1))
            self.viewport().update()
            event.accept()
            return

        self._update_hover_cursor(scene_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._active_handle and event.button() == Qt.MouseButton.LeftButton:
            rect = QRectF(self._preview_rect)
            orig = QRectF(self._orig_region_rect)
            reg_id = self._selected_region_id
            self._active_handle = ""
            self._preview_rect = QRectF()

            if reg_id and not rect.isEmpty() and rect != orig:
                self.region_modified.emit(
                    reg_id,
                    int(rect.x()),
                    int(rect.y()),
                    int(rect.width()),
                    int(rect.height()),
                )
            self._update_hover_cursor(self.mapToScene(event.position().toPoint()))
            self.viewport().update()
            event.accept()
            return

        if self._is_drawing and event.button() == Qt.MouseButton.LeftButton:
            self._is_drawing = False
            rect = self._current_drag_rect
            self._current_drag_rect = QRectF()
            if rect.width() >= 4 and rect.height() >= 4:
                self.region_drawn.emit(
                    int(rect.x()),
                    int(rect.y()),
                    int(rect.width()),
                    int(rect.height()),
                )
            self.viewport().update()
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def _draw_move_gizmo(self, painter: QPainter, rect: QRectF) -> None:
        painter.save()
        iz = self._inv_zoom()
        cx = rect.center().x()
        cy = rect.center().y()

        box_half = 7.0 * iz
        arrow_len = 36.0 * iz
        head_len = 9.0 * iz
        head_half = 5.0 * iz

        # X-axis shaft & arrowhead (Red)
        x_color = QColor(255, 85, 85, 245)
        x_pen = QPen(x_color, max(1.5 * iz, 0.0))
        painter.setPen(x_pen)
        painter.drawLine(QPointF(cx + box_half, cy), QPointF(cx + arrow_len, cy))
        x_head = QPolygonF([
            QPointF(cx + arrow_len + 3.0 * iz, cy),
            QPointF(cx + arrow_len - head_len, cy - head_half),
            QPointF(cx + arrow_len - head_len, cy + head_half),
        ])
        painter.setBrush(x_color)
        painter.drawPolygon(x_head)

        # Y-axis shaft & arrowhead (Green)
        y_color = QColor(80, 240, 110, 245)
        y_pen = QPen(y_color, max(1.5 * iz, 0.0))
        painter.setPen(y_pen)
        painter.drawLine(QPointF(cx, cy + box_half), QPointF(cx, cy + arrow_len))
        y_head = QPolygonF([
            QPointF(cx, cy + arrow_len + 3.0 * iz),
            QPointF(cx - head_half, cy + arrow_len - head_len),
            QPointF(cx + head_half, cy + arrow_len - head_len),
        ])
        painter.setBrush(y_color)
        painter.drawPolygon(y_head)

        # Center XY box (Yellow)
        center_rect = QRectF(cx - box_half, cy - box_half, box_half * 2.0, box_half * 2.0)
        painter.setBrush(QColor(255, 235, 80, 245))
        painter.setPen(QPen(QColor(20, 20, 20, 255), 0))
        painter.drawRect(center_rect)
        painter.restore()

    def _draw_resize_handles(self, painter: QPainter, rect: QRectF) -> None:
        painter.save()
        handles = self._get_resize_edge_handles(rect)
        painter.setBrush(QColor(255, 220, 60, 245))
        painter.setPen(QPen(QColor(20, 20, 20, 255), 0))
        for h_rect in handles.values():
            painter.drawRect(h_rect)
        painter.restore()

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawForeground(painter, rect)
        if self._project is None:
            return

        painter.setBrush(Qt.BrushStyle.NoBrush)
        font = QFont("Consolas", 8, QFont.Weight.Bold)
        painter.setFont(font)

        selected_rect_to_decorate: Optional[QRectF] = None

        for region in self._project.regions:
            r_rect = self._get_active_region_rect(region)
            is_selected = region.region_id == self._selected_region_id

            if is_selected:
                selected_rect_to_decorate = r_rect
                if self._edit_mode == self.MODE_MOVE:
                    fill_color = QColor(40, 220, 140, 65)
                    border_pen = QPen(QColor(80, 255, 160, 255))
                elif self._edit_mode == self.MODE_RESIZE:
                    fill_color = QColor(255, 140, 40, 65)
                    border_pen = QPen(QColor(255, 200, 60, 255))
                else:
                    fill_color = QColor(0, 180, 255, 60)
                    border_pen = QPen(QColor(0, 220, 255, 255))
            else:
                fill_color = QColor(255, 180, 0, 45)
                border_pen = QPen(QColor(255, 200, 0, 220))

            border_pen.setWidth(0)
            painter.fillRect(r_rect, fill_color)
            painter.setPen(border_pen)
            painter.drawRect(r_rect)

            painter.setPen(QColor(255, 255, 255))
            painter.drawText(
                r_rect.adjusted(2, 2, -2, -2),
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                region.base_name,
            )

        if selected_rect_to_decorate is not None:
            if self._edit_mode == self.MODE_MOVE:
                self._draw_move_gizmo(painter, selected_rect_to_decorate)
            elif self._edit_mode == self.MODE_RESIZE:
                self._draw_resize_handles(painter, selected_rect_to_decorate)

        if self._is_drawing and not self._current_drag_rect.isEmpty():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            drag_pen = QPen(QColor(80, 255, 120, 255), 0, Qt.PenStyle.DashLine)
            painter.setPen(drag_pen)
            painter.fillRect(self._current_drag_rect, QColor(80, 255, 120, 50))
            painter.drawRect(self._current_drag_rect)


class RegionSlicerTab(QWidget):
    open_in_tile_mapper_requested = Signal(str)

    def __init__(self, project: ProjectModel, parent=None) -> None:
        super().__init__(parent)
        self._project = project
        self._source_image: Optional[Image.Image] = None
        self.command_manager = CommandManager()
        self.command_manager.add_change_listener(self.refresh_ui)

        self._updating_ui = False
        self._build_ui()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        main_layout.addWidget(splitter)

        left_widget = QWidget(self)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Row 1: Zoom & Snap & Mode Toolbar
        toolbar_layout = QHBoxLayout()
        btn_zoom_in = QPushButton("확대 (+)")
        btn_zoom_out = QPushButton("축소 (-)")
        btn_zoom_reset = QPushButton("100%")
        self.chk_snap = QCheckBox("그리드 스냅")
        self.chk_snap.setChecked(True)
        self.spin_snap = QSpinBox()
        self.spin_snap.setRange(1, 256)
        self.spin_snap.setValue(16)

        toolbar_layout.addWidget(btn_zoom_in)
        toolbar_layout.addWidget(btn_zoom_out)
        toolbar_layout.addWidget(btn_zoom_reset)
        toolbar_layout.addSpacing(8)
        toolbar_layout.addWidget(self.chk_snap)
        toolbar_layout.addWidget(QLabel("스냅 픽셀:"))
        toolbar_layout.addWidget(self.spin_snap)
        toolbar_layout.addSpacing(12)

        # Mode Selector Buttons (Tab to cycle)
        toolbar_layout.addWidget(QLabel("사용 모드 (Tab 전환):"))
        self.mode_btn_group = QButtonGroup(self)
        self.mode_btn_group.setExclusive(True)

        self.btn_mode_select = QPushButton("1. 선택 / 생성")
        self.btn_mode_select.setCheckable(True)
        self.btn_mode_select.setChecked(True)

        self.btn_mode_move = QPushButton("2. 스냅 이동 (기즈모/WASD)")
        self.btn_mode_move.setCheckable(True)

        self.btn_mode_resize = QPushButton("3. 영역 신축 (테두리)")
        self.btn_mode_resize.setCheckable(True)

        self.mode_btn_group.addButton(self.btn_mode_select, RegionSlicerCanvas.MODE_SELECT)
        self.mode_btn_group.addButton(self.btn_mode_move, RegionSlicerCanvas.MODE_MOVE)
        self.mode_btn_group.addButton(self.btn_mode_resize, RegionSlicerCanvas.MODE_RESIZE)

        toolbar_layout.addWidget(self.btn_mode_select)
        toolbar_layout.addWidget(self.btn_mode_move)
        toolbar_layout.addWidget(self.btn_mode_resize)
        toolbar_layout.addStretch()

        # Row 2: Contextual Mode Guide Label
        self.lbl_mode_hint = QLabel()
        self.lbl_mode_hint.setStyleSheet("color: #66d9ef; font-weight: bold; padding: 2px 4px;")

        self.canvas = RegionSlicerCanvas(self)
        self.canvas.set_project(self._project)

        left_layout.addLayout(toolbar_layout)
        left_layout.addWidget(self.lbl_mode_hint)
        left_layout.addWidget(self.canvas, stretch=1)

        btn_zoom_in.clicked.connect(self.canvas.zoom_in)
        btn_zoom_out.clicked.connect(self.canvas.zoom_out)
        btn_zoom_reset.clicked.connect(self.canvas.reset_zoom)
        self.chk_snap.toggled.connect(self._on_snap_changed)
        self.spin_snap.valueChanged.connect(self._on_snap_changed)

        self.mode_btn_group.idClicked.connect(self._on_mode_button_clicked)
        self.canvas.edit_mode_changed.connect(self._on_canvas_edit_mode_changed)
        self.canvas.region_selected.connect(self._on_canvas_region_selected)
        self.canvas.region_drawn.connect(self._on_canvas_region_drawn)
        self.canvas.region_modified.connect(self._on_canvas_region_modified)
        self.canvas.wasd_move_requested.connect(self._on_wasd_move_requested)

        del_shortcut = QShortcut(QKeySequence.StandardKey.Delete, self, self._on_delete_selected_region)
        del_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)

        right_widget = QWidget(self)
        right_layout = QVBoxLayout(right_widget)

        auto_group = QGroupBox("1. 오토 슬라이스 (Grid by Cell)")
        auto_form = QFormLayout(auto_group)

        self.spin_cell_w = QSpinBox()
        self.spin_cell_w.setRange(1, 4096)
        self.spin_cell_w.setValue(192)

        self.spin_cell_h = QSpinBox()
        self.spin_cell_h.setRange(1, 4096)
        self.spin_cell_h.setValue(64)

        self.spin_offset_x = QSpinBox()
        self.spin_offset_x.setRange(0, 4096)
        self.spin_offset_y = QSpinBox()
        self.spin_offset_y.setRange(0, 4096)

        self.spin_pad_x = QSpinBox()
        self.spin_pad_x.setRange(0, 4096)
        self.spin_pad_y = QSpinBox()
        self.spin_pad_y.setRange(0, 4096)

        self.edit_prefix = QLineEdit("Region")
        self.chk_skip_empty_reg = QCheckBox("완전 투명 블록 제외")
        self.chk_skip_empty_reg.setChecked(True)
        self.chk_replace_existing = QCheckBox("기존 영역 덮어쓰기")
        self.chk_replace_existing.setChecked(True)
        btn_auto_slice = QPushButton("오토 슬라이스 실행")
        btn_auto_slice.clicked.connect(self._on_run_auto_slice)

        cell_size_row = QHBoxLayout()
        cell_size_row.addWidget(self.spin_cell_w)
        cell_size_row.addWidget(QLabel("x"))
        cell_size_row.addWidget(self.spin_cell_h)

        offset_row = QHBoxLayout()
        offset_row.addWidget(self.spin_offset_x)
        offset_row.addWidget(QLabel(","))
        offset_row.addWidget(self.spin_offset_y)

        pad_row = QHBoxLayout()
        pad_row.addWidget(self.spin_pad_x)
        pad_row.addWidget(QLabel(","))
        pad_row.addWidget(self.spin_pad_y)

        auto_form.addRow("Cell 크기 (W x H):", cell_size_row)
        auto_form.addRow("Offset (X, Y):", offset_row)
        auto_form.addRow("Padding (X, Y):", pad_row)
        auto_form.addRow("이름 접두사:", self.edit_prefix)
        auto_form.addRow(self.chk_skip_empty_reg)
        auto_form.addRow(self.chk_replace_existing)
        auto_form.addRow(btn_auto_slice)

        list_group = QGroupBox("2. 분할 영역 (Region) 목록")
        list_layout = QVBoxLayout(list_group)
        self.list_regions = QListWidget()
        self.list_regions.currentItemChanged.connect(self._on_list_selection_changed)
        self.list_regions.itemDoubleClicked.connect(lambda _: self._on_request_open_mapper())
        self.list_regions.installEventFilter(self)

        list_btn_row = QHBoxLayout()
        btn_delete_reg = QPushButton("선택 영역 삭제")
        btn_open_mapper = QPushButton("Tile Mapper에서 열기 ->")
        btn_delete_reg.clicked.connect(self._on_delete_selected_region)
        btn_open_mapper.clicked.connect(self._on_request_open_mapper)
        list_btn_row.addWidget(btn_delete_reg)
        list_btn_row.addWidget(btn_open_mapper)

        list_layout.addWidget(self.list_regions)
        list_layout.addLayout(list_btn_row)

        insp_group = QGroupBox("3. 선택된 영역 속성 편집")
        insp_form = QFormLayout(insp_group)

        self.edit_reg_name = QLineEdit()
        self.edit_reg_name.returnPressed.connect(self._on_apply_region_changes)
        self.spin_reg_x = QSpinBox()
        self.spin_reg_x.setRange(0, 16384)
        self.spin_reg_y = QSpinBox()
        self.spin_reg_y.setRange(0, 16384)
        self.spin_reg_w = QSpinBox()
        self.spin_reg_w.setRange(1, 16384)
        self.spin_reg_h = QSpinBox()
        self.spin_reg_h.setRange(1, 16384)
        self.spin_tile_w = QSpinBox()
        self.spin_tile_w.setRange(1, 1024)
        self.spin_tile_w.setValue(16)
        self.spin_tile_h = QSpinBox()
        self.spin_tile_h.setRange(1, 1024)
        self.spin_tile_h.setValue(16)

        self.edit_tile_order = QLineEdit()
        btn_browse_order = QPushButton("찾기...")
        btn_browse_order.clicked.connect(self._on_browse_tile_order)
        order_row = QHBoxLayout()
        order_row.addWidget(self.edit_tile_order)
        order_row.addWidget(btn_browse_order)

        btn_apply_reg = QPushButton("영역 속성 변경 적용 (Enter)")
        btn_apply_reg.clicked.connect(self._on_apply_region_changes)

        pos_row = QHBoxLayout()
        pos_row.addWidget(self.spin_reg_x)
        pos_row.addWidget(QLabel(","))
        pos_row.addWidget(self.spin_reg_y)

        size_row = QHBoxLayout()
        size_row.addWidget(self.spin_reg_w)
        size_row.addWidget(QLabel("x"))
        size_row.addWidget(self.spin_reg_h)

        tile_row = QHBoxLayout()
        tile_row.addWidget(self.spin_tile_w)
        tile_row.addWidget(QLabel("x"))
        tile_row.addWidget(self.spin_tile_h)

        insp_form.addRow("이름 (BaseName):", self.edit_reg_name)
        insp_form.addRow("위치 (X, Y):", pos_row)
        insp_form.addRow("크기 (W x H):", size_row)
        insp_form.addRow("타일 크기 (W x H):", tile_row)
        insp_form.addRow(".tileorder 경로:", order_row)
        insp_form.addRow(btn_apply_reg)

        right_layout.addWidget(auto_group)
        right_layout.addWidget(list_group, stretch=1)
        right_layout.addWidget(insp_group)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        self._update_mode_ui(RegionSlicerCanvas.MODE_SELECT)

    def focusNextPrevChild(self, _next: bool) -> bool:
        focus_widget = self.focusWidget()
        if isinstance(focus_widget, (QLineEdit, QSpinBox)):
            return super().focusNextPrevChild(_next)
        self.canvas.cycle_edit_mode()
        self.canvas.setFocus()
        return True

    def eventFilter(self, watched, event: QEvent) -> bool:
        if (
            watched is self.list_regions
            and event.type() == QEvent.Type.KeyPress
            and self.canvas.edit_mode == RegionSlicerCanvas.MODE_MOVE
        ):
            key_event = event  # type: ignore[assignment]
            if key_event.key() in (Qt.Key.Key_W, Qt.Key.Key_A, Qt.Key.Key_S, Qt.Key.Key_D):
                self.canvas.keyPressEvent(key_event)
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        focus_widget = self.focusWidget()
        if (
            not isinstance(focus_widget, (QLineEdit, QSpinBox))
            and self.canvas.edit_mode == RegionSlicerCanvas.MODE_MOVE
            and event.key() in (Qt.Key.Key_W, Qt.Key.Key_A, Qt.Key.Key_S, Qt.Key.Key_D)
        ):
            self.canvas.keyPressEvent(event)
            return
        super().keyPressEvent(event)

    def _on_mode_button_clicked(self, mode_id: int) -> None:
        if mode_id in (RegionSlicerCanvas.MODE_MOVE, RegionSlicerCanvas.MODE_RESIZE) and self.current_region() is None:
            self.canvas.set_edit_mode(RegionSlicerCanvas.MODE_SELECT)
            self._update_mode_ui(RegionSlicerCanvas.MODE_SELECT)
            QMessageBox.information(self, "알림", "이동 또는 영역 신축 모드를 사용하려면 먼저 영역(Region)을 선택해주세요.")
            return
        self.canvas.set_edit_mode(mode_id)
        self.canvas.setFocus()

    def _on_canvas_edit_mode_changed(self, mode_id: int) -> None:
        self._update_mode_ui(mode_id)

    def _update_mode_ui(self, mode_id: int) -> None:
        btn = self.mode_btn_group.button(mode_id)
        if btn is not None:
            btn.setChecked(True)

        active_style_1 = "background-color: #007acc; color: white; font-weight: bold; padding: 4px 10px;"
        active_style_2 = "background-color: #1e824c; color: white; font-weight: bold; padding: 4px 10px;"
        active_style_3 = "background-color: #d35400; color: white; font-weight: bold; padding: 4px 10px;"
        inactive_style = "padding: 4px 10px;"

        self.btn_mode_select.setStyleSheet(active_style_1 if mode_id == RegionSlicerCanvas.MODE_SELECT else inactive_style)
        self.btn_mode_move.setStyleSheet(active_style_2 if mode_id == RegionSlicerCanvas.MODE_MOVE else inactive_style)
        self.btn_mode_resize.setStyleSheet(active_style_3 if mode_id == RegionSlicerCanvas.MODE_RESIZE else inactive_style)

        if mode_id == RegionSlicerCanvas.MODE_SELECT:
            self.lbl_mode_hint.setText(
                "[모드 1: 선택/생성] 클릭: 영역 선택 | 빈 공간 드래그: 새 영역 생성 (겹친 영역 위는 Shift+드래그) | Tab: 모드 전환"
            )
            self.lbl_mode_hint.setStyleSheet("color: #66d9ef; font-weight: bold; padding: 2px 4px;")
        elif mode_id == RegionSlicerCanvas.MODE_MOVE:
            self.lbl_mode_hint.setText(
                "[모드 2: 스냅 이동] 중앙 사각형(XY 자유) / 빨간 화살표(X축) / 초록 화살표(Y축) 드래그 또는 W·A·S·D 키로 이동 | 다른 영역 선택 시 모드 1 복귀"
            )
            self.lbl_mode_hint.setStyleSheet("color: #50fa7b; font-weight: bold; padding: 2px 4px;")
        elif mode_id == RegionSlicerCanvas.MODE_RESIZE:
            self.lbl_mode_hint.setText(
                "[모드 3: 영역 신축] 상·하·좌·우 테두리의 노란 핸들을 드래그하여 크기 확장/축소 | 다른 영역 선택 시 모드 1 복귀"
            )
            self.lbl_mode_hint.setStyleSheet("color: #ffb86c; font-weight: bold; padding: 2px 4px;")

    def set_project_and_image(
        self, project: ProjectModel, source_img: Optional[Image.Image]
    ) -> None:
        self._project = project
        self._source_image = source_img
        self.command_manager.clear()
        self.canvas.set_project(project)
        self.canvas.set_pil_image(source_img, reset_view=True)
        self.refresh_ui()

    def current_region(self) -> Optional[RegionData]:
        item = self.list_regions.currentItem()
        if item is None:
            return None
        reg_id = item.data(Qt.ItemDataRole.UserRole)
        return self._project.get_region_by_id(reg_id)

    def _on_snap_changed(self) -> None:
        self.canvas.set_snap(self.chk_snap.isChecked(), self.spin_snap.value())

    def _on_run_auto_slice(self) -> None:
        if self._source_image is None:
            QMessageBox.warning(self, "알림", "먼저 원본 이미지를 열어주세요.")
            return

        new_regions = ImageService.compute_auto_slice_regions(
            source_img=self._source_image,
            cell_w=self.spin_cell_w.value(),
            cell_h=self.spin_cell_h.value(),
            offset_x=self.spin_offset_x.value(),
            offset_y=self.spin_offset_y.value(),
            padding_x=self.spin_pad_x.value(),
            padding_y=self.spin_pad_y.value(),
            tile_w=self.spin_tile_w.value(),
            tile_h=self.spin_tile_h.value(),
            name_prefix=self.edit_prefix.text().strip() or "Region",
            skip_transparent=self.chk_skip_empty_reg.isChecked(),
        )
        cmd = AutoSliceRegionsCommand(
            project=self._project,
            new_regions=new_regions,
            replace_existing=self.chk_replace_existing.isChecked(),
        )
        self.command_manager.execute_command(cmd)
        self.canvas.set_edit_mode(RegionSlicerCanvas.MODE_SELECT)

    def _on_canvas_region_drawn(self, x: int, y: int, w: int, h: int) -> None:
        if self._source_image is not None:
            temp_reg = RegionData(base_name="temp", x=x, y=y, width=w, height=h)
            cropped = ImageService.crop_region(self._source_image, temp_reg)
            if ImageService.is_fully_transparent(cropped):
                return

        prefix = self.edit_prefix.text().strip() or "Region"
        name = self._project.generate_unique_name(prefix)
        new_reg = RegionData(
            base_name=name,
            x=x,
            y=y,
            width=w,
            height=h,
            tile_width=self.spin_tile_w.value(),
            tile_height=self.spin_tile_h.value(),
        )
        cmd = AddRegionCommand(self._project, new_reg)
        self.command_manager.execute_command(cmd)
        self._select_region_by_id(new_reg.region_id)
        self.canvas.set_edit_mode(RegionSlicerCanvas.MODE_SELECT)

    def _on_canvas_region_modified(self, region_id: str, x: int, y: int, w: int, h: int) -> None:
        reg = self._project.get_region_by_id(region_id)
        if reg is None:
            return
        if reg.x == x and reg.y == y and reg.width == w and reg.height == h:
            return
        before = reg.clone()
        after = reg.clone()
        after.x = x
        after.y = y
        after.width = w
        after.height = h
        cmd = ModifyRegionCommand(self._project, before, after)
        self.command_manager.execute_command(cmd)
        self._populate_inspector(after)

    def _on_wasd_move_requested(self, dx: int, dy: int) -> None:
        reg = self.current_region()
        if reg is None or self.canvas.image_width <= 0:
            return
        nx = max(0, min(self.canvas.image_width - reg.width, reg.x + dx))
        ny = max(0, min(self.canvas.image_height - reg.height, reg.y + dy))
        if nx == reg.x and ny == reg.y:
            return
        before = reg.clone()
        after = reg.clone()
        after.x = nx
        after.y = ny
        cmd = ModifyRegionCommand(self._project, before, after)
        self.command_manager.execute_command(cmd)
        self._populate_inspector(after)

    def _on_canvas_region_selected(self, region_id: str) -> None:
        if not region_id:
            self.list_regions.clearSelection()
            return
        self._select_region_by_id(region_id)

    def _select_region_by_id(self, region_id: str) -> None:
        for i in range(self.list_regions.count()):
            item = self.list_regions.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == region_id:
                self.list_regions.setCurrentItem(item)
                break

    def _on_list_selection_changed(
        self, current: Optional[QListWidgetItem], _previous: Optional[QListWidgetItem]
    ) -> None:
        if self._updating_ui:
            return
        if current is None:
            self.canvas.set_selected_region("")
            return
        reg_id = current.data(Qt.ItemDataRole.UserRole)
        self.canvas.set_selected_region(reg_id)
        region = self._project.get_region_by_id(reg_id)
        if region is not None:
            self._populate_inspector(region)

    def _populate_inspector(self, region: RegionData) -> None:
        self.edit_reg_name.setText(region.base_name)
        self.spin_reg_x.setValue(region.x)
        self.spin_reg_y.setValue(region.y)
        self.spin_reg_w.setValue(region.width)
        self.spin_reg_h.setValue(region.height)
        self.spin_tile_w.setValue(region.tile_width)
        self.spin_tile_h.setValue(region.tile_height)
        self.edit_tile_order.setText(region.tile_order_path)

    def _on_browse_tile_order(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            ".tileorder 파일 선택",
            "",
            "Tile Order Files (*.tileorder *.json);;All Files (*)",
        )
        if path:
            self.edit_tile_order.setText(path)

    def _on_apply_region_changes(self) -> None:
        reg = self.current_region()
        if reg is None:
            return
        before = reg.clone()
        after = reg.clone()
        after.base_name = self.edit_reg_name.text().strip() or reg.base_name
        after.x = self.spin_reg_x.value()
        after.y = self.spin_reg_y.value()
        after.width = self.spin_reg_w.value()
        after.height = self.spin_reg_h.value()
        after.tile_width = self.spin_tile_w.value()
        after.tile_height = self.spin_tile_h.value()
        after.tile_order_path = self.edit_tile_order.text().strip()

        cmd = ModifyRegionCommand(self._project, before, after)
        self.command_manager.execute_command(cmd)

    def _on_delete_selected_region(self) -> None:
        focus_widget = self.focusWidget()
        if isinstance(focus_widget, (QLineEdit, QSpinBox)):
            return

        reg = self.current_region()
        if reg is None:
            return
        cmd = DeleteRegionCommand(self._project, reg.region_id)
        self.command_manager.execute_command(cmd)
        self.canvas.set_edit_mode(RegionSlicerCanvas.MODE_SELECT)

    def _on_request_open_mapper(self) -> None:
        reg = self.current_region()
        if reg is None:
            QMessageBox.information(self, "알림", "먼저 목록에서 영역을 선택해주세요.")
            return
        self.open_in_tile_mapper_requested.emit(reg.region_id)

    def refresh_ui(self) -> None:
        self._updating_ui = True
        prev_selected_id = ""
        curr_item = self.list_regions.currentItem()
        if curr_item is not None:
            prev_selected_id = curr_item.data(Qt.ItemDataRole.UserRole)
        elif self.canvas._selected_region_id:
            prev_selected_id = self.canvas._selected_region_id

        self.list_regions.clear()
        restored_item = None
        for reg in self._project.regions:
            label = f"{reg.base_name}  ({reg.x}, {reg.y} | {reg.width}x{reg.height})"
            if reg.tile_order_path:
                label += " [Order]"
            elif reg.custom_mappings:
                label += f" [{len(reg.custom_mappings)} tiles]"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, reg.region_id)
            self.list_regions.addItem(item)
            if reg.region_id == prev_selected_id:
                restored_item = item

        if restored_item is not None:
            self.list_regions.setCurrentItem(restored_item)
            self._updating_ui = False
            reg = self._project.get_region_by_id(prev_selected_id)
            if reg is not None:
                self.canvas.set_selected_region(reg.region_id)
                self._populate_inspector(reg)
        elif self.list_regions.count() > 0:
            self._updating_ui = False
            self.list_regions.setCurrentRow(0)
        else:
            self._updating_ui = False
            self.canvas.set_selected_region("")

        self.canvas.viewport().update()
