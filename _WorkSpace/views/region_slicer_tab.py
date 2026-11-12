import math
from typing import Optional
from PIL import Image
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QMouseEvent, QShortcut, QKeySequence
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
    region_selected = Signal(str)
    region_drawn = Signal(int, int, int, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._project: Optional[ProjectModel] = None
        self._selected_region_id: str = ""
        self._snap_enabled: bool = True
        self._snap_size: int = 16

        self._is_drawing: bool = False
        self._drag_start_scene = QPointF()
        self._current_drag_rect = QRectF()

    def set_project(self, project: ProjectModel) -> None:
        self._project = project
        self.viewport().update()

    def set_selected_region(self, region_id: str) -> None:
        self._selected_region_id = region_id
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

    def _clamp_scene_point(self, pt: QPointF) -> QPointF:
        x = max(0.0, min(float(self.image_width), pt.x()))
        y = max(0.0, min(float(self.image_height), pt.y()))
        return QPointF(x, y)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and not self._space_pressed
            and self.image_width > 0
            and self._project is not None
        ):
            scene_pos = self.mapToScene(event.position().toPoint())
            if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                for region in reversed(self._project.regions):
                    r_rect = QRectF(region.x, region.y, region.width, region.height)
                    if r_rect.contains(scene_pos):
                        self._selected_region_id = region.region_id
                        self.region_selected.emit(region.region_id)
                        self.viewport().update()
                        event.accept()
                        return

                self._selected_region_id = ""
                self.region_selected.emit("")
                self.viewport().update()

            self._is_drawing = True
            self._drag_start_scene = self._clamp_scene_point(scene_pos)
            self._current_drag_rect = QRectF()
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._is_drawing:
            curr = self._clamp_scene_point(self.mapToScene(event.position().toPoint()))
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
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
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

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawForeground(painter, rect)
        if self._project is None:
            return

        painter.setBrush(Qt.BrushStyle.NoBrush)
        font = QFont("Consolas", 8, QFont.Weight.Bold)
        painter.setFont(font)

        for region in self._project.regions:
            r_rect = QRectF(region.x, region.y, region.width, region.height)
            is_selected = region.region_id == self._selected_region_id

            if is_selected:
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

        if self._is_drawing and not self._current_drag_rect.isEmpty():
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

        toolbar_layout = QHBoxLayout()
        btn_zoom_in = QPushButton("확대 (+)")
        btn_zoom_out = QPushButton("축소 (-)")
        btn_zoom_reset = QPushButton("100%")
        self.chk_snap = QCheckBox("그리드 스냅")
        self.chk_snap.setChecked(True)
        self.spin_snap = QSpinBox()
        self.spin_snap.setRange(1, 256)
        self.spin_snap.setValue(16)
        lbl_hint = QLabel("드래그: 영역 생성 (겹친 영역 위는 Shift+드래그) | Space+드래그: 화면 이동 | Delete: 선택 삭제")

        toolbar_layout.addWidget(btn_zoom_in)
        toolbar_layout.addWidget(btn_zoom_out)
        toolbar_layout.addWidget(btn_zoom_reset)
        toolbar_layout.addWidget(self.chk_snap)
        toolbar_layout.addWidget(QLabel("스냅 픽셀:"))
        toolbar_layout.addWidget(self.spin_snap)
        toolbar_layout.addWidget(lbl_hint)
        toolbar_layout.addStretch()

        self.canvas = RegionSlicerCanvas(self)
        self.canvas.set_project(self._project)

        left_layout.addLayout(toolbar_layout)
        left_layout.addWidget(self.canvas, stretch=1)

        btn_zoom_in.clicked.connect(self.canvas.zoom_in)
        btn_zoom_out.clicked.connect(self.canvas.zoom_out)
        btn_zoom_reset.clicked.connect(self.canvas.reset_zoom)
        self.chk_snap.toggled.connect(self._on_snap_changed)
        self.spin_snap.valueChanged.connect(self._on_snap_changed)
        self.canvas.region_selected.connect(self._on_canvas_region_selected)
        self.canvas.region_drawn.connect(self._on_canvas_region_drawn)

        QShortcut(QKeySequence.StandardKey.Delete, self, self._on_delete_selected_region)

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
        reg = self.current_region()
        if reg is None:
            return
        cmd = DeleteRegionCommand(self._project, reg.region_id)
        self.command_manager.execute_command(cmd)

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

        self._updating_ui = False

        if restored_item is not None:
            self.list_regions.setCurrentItem(restored_item)
        elif self.list_regions.count() > 0:
            self.list_regions.setCurrentRow(0)
        else:
            self.canvas.set_selected_region("")

        self.canvas.viewport().update()
