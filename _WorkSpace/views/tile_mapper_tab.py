import os
from typing import Optional
from PIL import Image
from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QMouseEvent, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QGroupBox,
    QFormLayout,
    QComboBox,
    QSpinBox,
    QPushButton,
    QCheckBox,
    QLabel,
    QFileDialog,
    QMessageBox,
)

from models.project_model import ProjectModel
from models.region_data import RegionData
from models.tile_order_model import TileOrderModel
from commands.base_command import CommandManager
from commands.tile_order_commands import (
    AssignTileOrderCommand,
    ResetTileOrderCommand,
    ReplaceTileOrderMappingsCommand,
    ShiftRemoveTileOrderCommand,
)
from services.image_service import ImageService
from services.serializer_service import ProjectSerializer
from services.export_service import TileExportService
from .canvas_base import PixelCanvasView

TILE_RULES = {
    0: "[00] 고립", 1: "[01] 북 연결", 2: "[02] 동 연결", 3: "[03] 남 연결", 4: "[04] 서 연결",
    5: "[05] 남북 직선", 6: "[06] 동서 직선", 7: "[07] 북동 코너 (대각 x)", 8: "[08] 북동 코너 (대각 o)",
    9: "[09] 동남 코너 (대각 x)", 10: "[10] 동남 코너 (대각 o)", 11: "[11] 남서 코너 (대각 x)", 12: "[12] 남서 코너 (대각 o)",
    13: "[13] 서북 코너 (대각 x)", 14: "[14] 서북 코너 (대각 o)", 15: "[15] 서쪽 끊긴 T자 (대각 둘다 x)",
    16: "[16] 서쪽 끊긴 T자 (북동만 o)", 17: "[17] 서쪽 끊긴 T자 (동남만 o)", 18: "[18] 서쪽 끊긴 T자 (대각 둘다 o)",
    19: "[19] 북쪽 끊긴 T자 (대각 둘다 x)", 20: "[20] 북쪽 끊긴 T자 (동남만 o)", 21: "[21] 북쪽 끊긴 T자 (남서만 o)",
    22: "[22] 북쪽 끊긴 T자 (대각 둘다 o)", 23: "[23] 동쪽 끊긴 T자 (대각 둘다 x)", 24: "[24] 동쪽 끊긴 T자 (남서만 o)",
    25: "[25] 동쪽 끊긴 T자 (서북만 o)", 26: "[26] 동쪽 끊긴 T자 (대각 둘다 o)", 27: "[27] 남쪽 끊긴 T자 (대각 둘다 x)",
    28: "[28] 남쪽 끊긴 T자 (서북만 o)", 29: "[29] 남쪽 끊긴 T자 (북동만 o)", 30: "[30] 남쪽 끊긴 T자 (대각 둘다 o)",
    31: "[31] 십자 교차로 (대각 0개)", 32: "[32] 십자 교차로 (북동만 o)", 33: "[33] 십자 교차로 (동남만 o)",
    34: "[34] 십자 교차로 (남서만 o)", 35: "[35] 십자 교차로 (서북만 o)", 36: "[36] 십자 교차로 (북동, 동남 o)",
    37: "[37] 십자 교차로 (동남, 남서 o)", 38: "[38] 십자 교차로 (남서, 서북 o)", 39: "[39] 십자 교차로 (서북, 북동 o)",
    40: "[40] 십자 교차로 (북동, 남서 o)", 41: "[41] 십자 교차로 (서북, 동남 o)", 42: "[42] 십자 교차로 (서북만 x)",
    43: "[43] 십자 교차로 (북동만 x)", 44: "[44] 십자 교차로 (동남만 x)", 45: "[45] 십자 교차로 (남서만 x)",
    46: "[46] 십자 교차로 (대각 4개 o)"
}

class TileMapperCanvas(PixelCanvasView):
    tile_cell_clicked = Signal(int, int)
    tile_cell_dragged = Signal(int, int)
    tile_cell_right_clicked = Signal(int, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self._tile_order: Optional[TileOrderModel] = None
        self._padding_digits: int = 2
        self._last_drag_cell = (-1, -1)

    def set_tile_order_model(self, model: Optional[TileOrderModel]) -> None:
        self._tile_order = model
        if model is not None:
            self.set_grid(model.tile_width, model.tile_height, True)
        self.viewport().update()

    def set_padding_digits(self, digits: int) -> None:
        self._padding_digits = max(1, digits)
        self.viewport().update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self._space_pressed and self._tile_order is not None and self.image_width > 0:
            scene_pos = self.mapToScene(event.position().toPoint())
            if 0 <= scene_pos.x() < self.image_width and 0 <= scene_pos.y() < self.image_height:
                col = int(scene_pos.x() // self._tile_order.tile_width)
                row = int(scene_pos.y() // self._tile_order.tile_height)
                if 0 <= col < self._tile_order.cols and 0 <= row < self._tile_order.rows:
                    if event.button() == Qt.MouseButton.LeftButton:
                        self._last_drag_cell = (col, row)
                        self.tile_cell_clicked.emit(col, row)
                        event.accept()
                        return
                    elif event.button() == Qt.MouseButton.RightButton:
                        self.tile_cell_right_clicked.emit(col, row)
                        event.accept()
                        return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._is_panning:
            super().mouseMoveEvent(event)
            return

        scene_pos = self.mapToScene(event.position().toPoint())
        if (event.buttons() & Qt.MouseButton.LeftButton) and not self._space_pressed and self._tile_order and self.image_width > 0:
            if 0 <= scene_pos.x() < self.image_width and 0 <= scene_pos.y() < self.image_height:
                col = int(scene_pos.x() // self._tile_order.tile_width)
                row = int(scene_pos.y() // self._tile_order.tile_height)
                if 0 <= col < self._tile_order.cols and 0 <= row < self._tile_order.rows:
                    if (col, row) != self._last_drag_cell:
                        self._last_drag_cell = (col, row)
                        self.tile_cell_dragged.emit(col, row)
                        event.accept()
                        return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._last_drag_cell = (-1, -1)
        super().mouseReleaseEvent(event)

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawForeground(painter, rect)
        if self._tile_order is None: return
        tw = self._tile_order.tile_width
        th = self._tile_order.tile_height
        font = QFont("Consolas", max(6, min(10, tw // 2)), QFont.Weight.Bold)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setFont(font)
        for entry in self._tile_order.mappings:
            cell_rect = QRectF(entry.col * tw, entry.row * th, tw, th)
            painter.fillRect(cell_rect, QColor(0, 140, 255, 95))
            border_pen = QPen(QColor(80, 220, 255, 230))
            border_pen.setWidth(0)
            painter.setPen(border_pen)
            painter.drawRect(cell_rect)
            text = f"{entry.tile_id:0{self._padding_digits}d}"
            painter.setPen(QColor(0, 0, 0, 220))
            painter.drawText(cell_rect.translated(0.6, 0.6), Qt.AlignmentFlag.AlignCenter, text)
            painter.setPen(QColor(255, 255, 100, 255))
            painter.drawText(cell_rect, Qt.AlignmentFlag.AlignCenter, text)


class TileMapperTab(QWidget):
    region_order_linked = Signal()

    def __init__(self, project: ProjectModel, parent=None) -> None:
        super().__init__(parent)
        self._project = project
        self._source_image: Optional[Image.Image] = None
        self._current_region_img: Optional[Image.Image] = None
        self._tile_order = TileOrderModel()

        self.command_manager = CommandManager()
        self.command_manager.add_change_listener(self._on_command_history_changed)
        self._updating_combo = False
        self._build_ui()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        main_layout.addWidget(splitter)
        left_widget = QWidget(self)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        toolbar = QHBoxLayout()
        btn_zoom_in = QPushButton("확대 (+)")
        btn_zoom_out = QPushButton("축소 (-)")
        btn_zoom_reset = QPushButton("100%")
        self.lbl_next_id = QLabel("다음 할당 ID: 00 | 할당된 타일: 0개")
        self.lbl_next_id.setStyleSheet("font-weight: bold; color: #00b4ff;")
        toolbar.addWidget(btn_zoom_in)
        toolbar.addWidget(btn_zoom_out)
        toolbar.addWidget(btn_zoom_reset)
        toolbar.addSpacing(12)
        toolbar.addWidget(self.lbl_next_id)
        toolbar.addStretch()

        self.canvas = TileMapperCanvas(self)
        self.canvas.set_tile_order_model(self._tile_order)
        left_layout.addLayout(toolbar)
        left_layout.addWidget(self.canvas, stretch=1)

        btn_zoom_in.clicked.connect(self.canvas.zoom_in)
        btn_zoom_out.clicked.connect(self.canvas.zoom_out)
        btn_zoom_reset.clicked.connect(self.canvas.reset_zoom)
        self.canvas.tile_cell_clicked.connect(self._on_tile_cell_clicked)
        self.canvas.tile_cell_right_clicked.connect(self._on_tile_cell_right_clicked)

        right_widget = QWidget(self)
        right_layout = QVBoxLayout(right_widget)
        reg_group = QGroupBox("1. 작업 대상 영역 (Region) 및 타일 규격")
        reg_form = QFormLayout(reg_group)
        self.combo_regions = QComboBox()
        self.combo_regions.currentIndexChanged.connect(self._on_region_combo_changed)
        self.spin_tile_w = QSpinBox()
        self.spin_tile_w.setRange(1, 1024)
        self.spin_tile_w.setValue(16)
        self.spin_tile_h = QSpinBox()
        self.spin_tile_h.setRange(1, 1024)
        self.spin_tile_h.setValue(16)
        btn_apply_tile_size = QPushButton("타일 그리드 크기 적용")
        btn_apply_tile_size.clicked.connect(self._on_apply_tile_grid_size)
        tile_size_row = QHBoxLayout()
        tile_size_row.addWidget(self.spin_tile_w)
        tile_size_row.addWidget(QLabel("x"))
        tile_size_row.addWidget(self.spin_tile_h)
        reg_form.addRow("대상 영역:", self.combo_regions)
        reg_form.addRow("타일 픽셀 (W x H):", tile_size_row)
        reg_form.addRow(btn_apply_tile_size)

        order_group = QGroupBox("2. 타일 순서 지정 (클릭 매핑 & 자동 번호)")
        order_layout = QVBoxLayout(order_group)
        lbl_guide = QLabel(
            "• 좌클릭: 0번부터 순차적 ID 부여 (중복/빈 공간 무시)\n"
            "• 우클릭: 해당 타일 삭제 및 이후 번호 하나씩 당기기 (Shift)\n"
            "• 실행 취소 (Ctrl+Z) / 다시 실행 (Ctrl+Y)"
        )
        lbl_guide.setWordWrap(True)
        self.chk_skip_transparent_seq = QCheckBox("자동 순차 부여 시 완전 투명 타일 건너뛰기")
        self.chk_skip_transparent_seq.setChecked(True)
        btn_auto_seq = QPushButton("좌상단 -> 우하단 자동 순차 번호 부여")
        btn_reset_order = QPushButton("현재 타일 순서 모두 초기화 (Reset)")
        btn_auto_seq.clicked.connect(self._on_auto_sequential)
        btn_reset_order.clicked.connect(self._on_reset_order)
        order_layout.addWidget(lbl_guide)
        order_layout.addWidget(self.chk_skip_transparent_seq)
        order_layout.addWidget(btn_auto_seq)
        order_layout.addWidget(btn_reset_order)

        file_group = QGroupBox("3. .tileorder 파일 관리 및 적용")
        file_layout = QVBoxLayout(file_group)
        self.lbl_linked_order = QLabel("연결된 파일: (없음)")
        self.lbl_linked_order.setWordWrap(True)
        self.chk_apply_same_size = QCheckBox("동일한 그리드 크기의 모든 Region에 함께 연결")
        self.chk_apply_same_size.setChecked(True)
        btn_load_order = QPushButton(".tileorder 파일 불러오기...")
        btn_save_order = QPushButton("현재 순서를 .tileorder 파일로 저장...")
        btn_unlink_order = QPushButton("연결 해제 (Unlink)")
        btn_export_single = QPushButton("현재 영역만 즉시 테스트 내보내기")
        
        btn_load_order.clicked.connect(self._on_load_tile_order_file)
        btn_save_order.clicked.connect(self._on_save_tile_order_file)
        btn_unlink_order.clicked.connect(self._on_unlink_tile_order)
        btn_export_single.clicked.connect(self._on_export_current_region)
        
        file_layout.addWidget(self.lbl_linked_order)
        file_layout.addWidget(self.chk_apply_same_size)
        
        btn_row = QHBoxLayout()
        btn_row.addWidget(btn_load_order)
        btn_row.addWidget(btn_unlink_order)
        file_layout.addLayout(btn_row)
        
        file_layout.addWidget(btn_save_order)
        file_layout.addSpacing(8)
        file_layout.addWidget(btn_export_single)
        right_layout.addWidget(reg_group)
        right_layout.addWidget(order_group)
        right_layout.addWidget(file_group)
        right_layout.addStretch()

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

    def set_project_and_image(
        self, project: ProjectModel, source_img: Optional[Image.Image]
    ) -> None:
        self._project = project
        self._source_image = source_img
        self.refresh_region_list()

    def refresh_region_list(self, select_region_id: str = "") -> None:
        self._updating_combo = True
        prev_id = select_region_id or self.current_region_id()
        self.combo_regions.clear()
        selected_idx = 0
        for idx, reg in enumerate(self._project.regions):
            self.combo_regions.addItem(f"{reg.base_name} ({reg.width}x{reg.height})", reg.region_id)
            if reg.region_id == prev_id: selected_idx = idx
        self._updating_combo = False
        if self.combo_regions.count() > 0:
            self.combo_regions.setCurrentIndex(selected_idx)
            self._load_selected_region()
        else:
            self._current_region_img = None
            self.canvas.set_pil_image(None)
            self._tile_order.clear()
            self.command_manager.clear()
            self._update_status_labels()

    def current_region_id(self) -> str:
        idx = self.combo_regions.currentIndex()
        if idx < 0: return ""
        return str(self.combo_regions.itemData(idx))

    def current_region(self) -> Optional[RegionData]:
        return self._project.get_region_by_id(self.current_region_id())

    def _on_region_combo_changed(self, _index: int) -> None:
        if self._updating_combo: return
        self._load_selected_region()

    def _load_selected_region(self) -> None:
        reg = self.current_region()
        if reg is None or self._source_image is None:
            self._current_region_img = None
            self.canvas.set_pil_image(None)
            return

        self.spin_tile_w.setValue(reg.tile_width)
        self.spin_tile_h.setValue(reg.tile_height)
        self._current_region_img = ImageService.crop_region(self._source_image, reg)
        self._tile_order = TileOrderModel(
            cols=reg.cols, rows=reg.rows, tile_width=reg.tile_width, tile_height=reg.tile_height
        )
        if reg.custom_mappings:
            self._tile_order.mappings = [
                e for e in reg.clone().custom_mappings
            ]
        elif reg.tile_order_path and os.path.exists(reg.tile_order_path):
            try:
                loaded_order = ProjectSerializer.load_tile_order(reg.tile_order_path)
                self._tile_order.mappings = loaded_order.clone_mappings()
            except Exception:
                pass
        self.command_manager.clear()
        self.canvas.set_padding_digits(self._project.export_config.padding_digits)
        self.canvas.set_tile_order_model(self._tile_order)
        self.canvas.set_pil_image(self._current_region_img, reset_view=True)
        for _ in range(4): self.canvas.zoom_in()
        self._update_status_labels()

    def _on_apply_tile_grid_size(self) -> None:
        reg = self.current_region()
        if reg is None: return
        reg.tile_width = self.spin_tile_w.value()
        reg.tile_height = self.spin_tile_h.value()
        self._load_selected_region()

    def _on_tile_cell_clicked(self, col: int, row: int) -> None:
        if self._tile_order.has_coord(col, row): return
        if self._current_region_img is not None:
            tile_img = ImageService.crop_tile(
                self._current_region_img, col, row, self._tile_order.tile_width, self._tile_order.tile_height
            )
            if ImageService.is_fully_transparent(tile_img): return
        cmd = AssignTileOrderCommand(self._tile_order, col, row)
        self.command_manager.execute_command(cmd)
        
    def _on_tile_cell_right_clicked(self, col: int, row: int) -> None:
        target_id = self._tile_order.get_id_at(col, row)
        if target_id is not None:
            cmd = ShiftRemoveTileOrderCommand(self._tile_order, target_id)
            self.command_manager.execute_command(cmd)

    def _on_auto_sequential(self) -> None:
        if self._current_region_img is None: return
        seq_model = ImageService.generate_sequential_tile_order(
            region_img=self._current_region_img,
            tile_w=self._tile_order.tile_width,
            tile_h=self._tile_order.tile_height,
            skip_transparent=self.chk_skip_transparent_seq.isChecked(),
        )
        cmd = ReplaceTileOrderMappingsCommand(self._tile_order, seq_model.mappings)
        self.command_manager.execute_command(cmd)

    def _on_reset_order(self) -> None:
        if len(self._tile_order.mappings) == 0: return
        cmd = ResetTileOrderCommand(self._tile_order)
        self.command_manager.execute_command(cmd)

    def _on_load_tile_order_file(self) -> None:
        reg = self.current_region()
        if reg is None: return
        path, _ = QFileDialog.getOpenFileName(
            self, ".tileorder 파일 열기", "", "Tile Order Files (*.tileorder *.json);;All Files (*)"
        )
        if not path: return
        try:
            loaded = ProjectSerializer.load_tile_order(path)
            cmd = ReplaceTileOrderMappingsCommand(self._tile_order, loaded.mappings)
            self.command_manager.execute_command(cmd)
            self._link_order_path_to_regions(reg, path)
        except Exception as exc: QMessageBox.critical(self, "오류", f".tileorder 로드 실패:\n{exc}")

    def _on_save_tile_order_file(self) -> None:
        reg = self.current_region()
        if reg is None: return
        default_name = f"{reg.base_name}.tileorder"
        path, _ = QFileDialog.getSaveFileName(
            self, ".tileorder 파일 저장", default_name, "Tile Order Files (*.tileorder);;JSON Files (*.json)"
        )
        if not path: return
        if not (path.endswith(".tileorder") or path.endswith(".json")): path += ".tileorder"
        try:
            ProjectSerializer.save_tile_order(self._tile_order, path)
            self._link_order_path_to_regions(reg, path)
            QMessageBox.information(self, "저장 완료", f".tileorder 파일이 저장되었습니다:\n{path}")
        except Exception as exc: QMessageBox.critical(self, "오류", f".tileorder 저장 실패:\n{exc}")

    def _on_unlink_tile_order(self) -> None:
        reg = self.current_region()
        if reg is None or not reg.tile_order_path: return
        self._link_order_path_to_regions(reg, "")
        QMessageBox.information(self, "연결 해제", "현재 영역의 .tileorder 연결이 해제되었습니다.\n(저장 전까지 파일에 반영되지 않습니다.)")

    def _link_order_path_to_regions(self, active_reg: RegionData, order_path: str) -> None:
        active_reg.tile_order_path = order_path
        if self.chk_apply_same_size.isChecked():
            for r in self._project.regions:
                if r.cols == active_reg.cols and r.rows == active_reg.rows:
                    r.tile_order_path = order_path
                    if order_path:
                        r.custom_mappings = self._tile_order.clone_mappings()
        self._update_status_labels()
        self.region_order_linked.emit()

    def _on_export_current_region(self) -> None:
        reg = self.current_region()
        if reg is None or self._source_image is None:
            QMessageBox.warning(self, "알림", "내보낼 영역이나 원본 이미지가 없습니다.")
            return
        try:
            active_order = self._tile_order if len(self._tile_order.mappings) > 0 else None
            base_dir = (
                os.path.dirname(self.window()._current_project_path)
                if hasattr(self.window(), "_current_project_path") and self.window()._current_project_path
                else ""
            )
            count = TileExportService.export_single_region(
                source_img=self._source_image,
                region=reg,
                export_config=self._project.export_config,
                tile_order=active_order,
                base_dir=base_dir,
            )
            out_dir = os.path.join(
                TileExportService.resolve_output_root(self._project.export_config.output_dir, base_dir),
                reg.base_name,
            )
            QMessageBox.information(
                self, "내보내기 완료", f"[{reg.base_name}] 영역에서 총 {count}개의 타일을 추출했습니다.\n경로: {out_dir}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "오류", f"내보내기 실패:\n{exc}")

    def _on_command_history_changed(self) -> None:
        reg = self.current_region()
        if reg is not None:
            reg.custom_mappings = self._tile_order.clone_mappings()
        self.canvas.viewport().update()
        self._update_status_labels()

    def _update_status_labels(self) -> None:
        digits = max(1, self._project.export_config.padding_digits)
        next_id = self._tile_order.next_id()
        total_cells = self._tile_order.cols * self._tile_order.rows
        rule_text = TILE_RULES.get(next_id, f"[{next_id:02d}] (사용자 정의 / 47타일 외)")
        
        self.lbl_next_id.setText(
            f"다음 할당 ID: {next_id:0{digits}d} ▶ {rule_text} | 할당된 타일: {len(self._tile_order.mappings)} / {total_cells}칸"
        )
        reg = self.current_region()
        if reg and reg.tile_order_path:
            self.lbl_linked_order.setText(f"연결된 파일: {reg.tile_order_path}")
        else:
            self.lbl_linked_order.setText("연결된 파일: (없음 - 단발성 인메모리 매핑으로 프로젝트 내 저장됨)")
