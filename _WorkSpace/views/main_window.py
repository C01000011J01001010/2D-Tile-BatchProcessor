import os
from typing import Optional
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QGroupBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QCheckBox,
    QPushButton,
    QLabel,
    QFileDialog,
    QMessageBox,
)

from models.project_model import ProjectModel
from services.image_service import ImageService
from services.serializer_service import ProjectSerializer
from services.export_service import TileExportService
from .region_slicer_tab import RegionSlicerTab
from .tile_mapper_tab import TileMapperTab


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("2D Tilemap Region Slicer & Tile Mapper")
        self.resize(1360, 860)

        self._project = ProjectModel()
        self._source_image: Optional[Image.Image] = None
        self._current_project_path: str = ""

        self._build_menus()
        self._build_ui()
        self._update_preview_label()

    def _build_menus(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("파일(&F)")

        act_open_img = QAction("원본 타일셋 이미지 열기(&I)...", self)
        act_open_img.setShortcut(QKeySequence("Ctrl+O"))
        act_open_img.triggered.connect(self.action_open_image)

        act_load_proj = QAction("영역 설정(.imgreg) 불러오기(&L)...", self)
        act_load_proj.triggered.connect(self.action_load_project)

        act_save_proj = QAction("영역 설정(.imgreg) 저장(&S)...", self)
        act_save_proj.setShortcut(QKeySequence("Ctrl+S"))
        act_save_proj.triggered.connect(self.action_save_project)

        act_export_all = QAction("전체 영역 일괄 내보내기(&E)", self)
        act_export_all.setShortcut(QKeySequence("Ctrl+E"))
        act_export_all.triggered.connect(self.action_export_all)

        act_exit = QAction("종료(&X)", self)
        act_exit.triggered.connect(self.close)

        file_menu.addAction(act_open_img)
        file_menu.addSeparator()
        file_menu.addAction(act_load_proj)
        file_menu.addAction(act_save_proj)
        file_menu.addSeparator()
        file_menu.addAction(act_export_all)
        file_menu.addSeparator()
        file_menu.addAction(act_exit)

        edit_menu = menubar.addMenu("편집(&E)")

        act_undo = QAction("실행 취소 (Undo)", self)
        act_undo.setShortcut(QKeySequence("Ctrl+Z"))
        act_undo.triggered.connect(self.action_undo)

        act_redo = QAction("다시 실행 (Redo)", self)
        act_redo.setShortcuts([QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")])
        act_redo.triggered.connect(self.action_redo)

        edit_menu.addAction(act_undo)
        edit_menu.addAction(act_redo)

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)

        # Top Export Config Bar
        export_group = QGroupBox("출력(Export) 및 파일명 포맷 규칙 설정")
        export_layout = QHBoxLayout(export_group)

        self.edit_output_dir = QLineEdit(self._project.export_config.output_dir)
        btn_browse_out = QPushButton("폴더 선택...")
        btn_browse_out.clicked.connect(self._on_browse_output_dir)

        self.edit_separator = QLineEdit(self._project.export_config.separator)
        self.edit_separator.setFixedWidth(50)

        self.spin_digits = QSpinBox()
        self.spin_digits.setRange(1, 6)
        self.spin_digits.setValue(self._project.export_config.padding_digits)

        self.chk_skip_transparent = QCheckBox("완전 투명 타일 제외")
        self.chk_skip_transparent.setChecked(
            self._project.export_config.skip_transparent_tiles
        )

        self.lbl_format_preview = QLabel()
        self.lbl_format_preview.setStyleSheet("font-weight: bold; color: #50fa7b;")

        btn_export_all = QPushButton("전체 Region 일괄 내보내기 (Export All)")
        btn_export_all.setStyleSheet("font-weight: bold; padding: 4px 12px;")
        btn_export_all.clicked.connect(self.action_export_all)

        export_layout.addWidget(QLabel("출력 루트 폴더:"))
        export_layout.addWidget(self.edit_output_dir, stretch=1)
        export_layout.addWidget(btn_browse_out)
        export_layout.addSpacing(10)
        export_layout.addWidget(QLabel("구분자:"))
        export_layout.addWidget(self.edit_separator)
        export_layout.addSpacing(10)
        export_layout.addWidget(QLabel("자릿수(Zero-pad):"))
        export_layout.addWidget(self.spin_digits)
        export_layout.addSpacing(10)
        export_layout.addWidget(self.chk_skip_transparent)
        export_layout.addSpacing(10)
        export_layout.addWidget(self.lbl_format_preview)
        export_layout.addSpacing(10)
        export_layout.addWidget(btn_export_all)

        self.edit_output_dir.textChanged.connect(self._on_export_config_changed)
        self.edit_separator.textChanged.connect(self._on_export_config_changed)
        self.spin_digits.valueChanged.connect(self._on_export_config_changed)
        self.chk_skip_transparent.toggled.connect(self._on_export_config_changed)

        # Workspace Tabs
        self.tabs = QTabWidget(self)
        self.region_slicer_tab = RegionSlicerTab(self._project, self)
        self.tile_mapper_tab = TileMapperTab(self._project, self)

        self.tabs.addTab(self.region_slicer_tab, "1. Region Slicer (1차 영역 분할)")
        self.tabs.addTab(self.tile_mapper_tab, "2. Tile Mapper (2차 타일 순서 지정)")

        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.region_slicer_tab.open_in_tile_mapper_requested.connect(
            self._on_open_in_tile_mapper
        )
        self.tile_mapper_tab.region_order_linked.connect(
            self.region_slicer_tab.refresh_ui
        )

        root_layout.addWidget(export_group)
        root_layout.addWidget(self.tabs, stretch=1)

    def _on_export_config_changed(self) -> None:
        cfg = self._project.export_config
        cfg.output_dir = self.edit_output_dir.text().strip() or "output"
        cfg.separator = self.edit_separator.text()
        cfg.padding_digits = self.spin_digits.value()
        cfg.skip_transparent_tiles = self.chk_skip_transparent.isChecked()
        self.tile_mapper_tab.canvas.set_padding_digits(cfg.padding_digits)
        self._update_preview_label()

    def _update_preview_label(self) -> None:
        cfg = self._project.export_config
        sample_file = cfg.format_filename("Temple", 0)
        self.lbl_format_preview.setText(
            f"예시: {cfg.output_dir}/Temple/{sample_file}"
        )

    def _on_browse_output_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "출력 루트 폴더 선택", "")
        if folder:
            self.edit_output_dir.setText(folder)

    def _on_tab_changed(self, index: int) -> None:
        if index == 1:
            curr_reg = self.region_slicer_tab.current_region()
            reg_id = curr_reg.region_id if curr_reg else ""
            self.tile_mapper_tab.refresh_region_list(select_region_id=reg_id)

    def _on_open_in_tile_mapper(self, region_id: str) -> None:
        self.tabs.setCurrentIndex(1)
        self.tile_mapper_tab.refresh_region_list(select_region_id=region_id)

    def action_undo(self) -> None:
        if self.tabs.currentIndex() == 0:
            self.region_slicer_tab.command_manager.undo()
        else:
            self.tile_mapper_tab.command_manager.undo()

    def action_redo(self) -> None:
        if self.tabs.currentIndex() == 0:
            self.region_slicer_tab.command_manager.redo()
        else:
            self.tile_mapper_tab.command_manager.redo()

    def action_open_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "원본 타일셋 이미지 선택",
            "",
            "PNG Images (*.png);;All Images (*.png *.bmp *.jpg);;All Files (*)",
        )
        if not path:
            return
        self._load_source_image(path, reset_regions=True)

    def _load_source_image(self, path: str, reset_regions: bool = False) -> None:
        try:
            img = ImageService.load_rgba_image(path)
            self._source_image = img
            self._project.image_path = path
            self._project.image_width = img.width
            self._project.image_height = img.height
            if reset_regions:
                self._project.regions.clear()
            self.region_slicer_tab.set_project_and_image(self._project, img)
            self.tile_mapper_tab.set_project_and_image(self._project, img)
            self.statusBar().showMessage(
                f"로드 완료: {path} ({img.width}x{img.height})"
            )
        except Exception as exc:
            QMessageBox.critical(self, "이미지 로드 오류", f"이미지를 열 수 없습니다:\n{exc}")

    def action_save_project(self) -> None:
        default_path = self._current_project_path or "project.imgreg"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "영역 설정 파일 저장",
            default_path,
            "Image Region Project (*.imgreg *.imgregions);;JSON Files (*.json)",
        )
        if not path:
            return
        if not path.endswith((".imgreg", ".imgregions", ".json")):
            path += ".imgreg"
        try:
            ProjectSerializer.save_project(self._project, path)
            self._current_project_path = path
            self.statusBar().showMessage(f"프로젝트 저장 완료: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "저장 오류", f"프로젝트 저장 실패:\n{exc}")

    def action_load_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "영역 설정 파일 열기",
            "",
            "Image Region Project (*.imgreg *.imgregions *.json);;All Files (*)",
        )
        if not path:
            return
        try:
            loaded_proj = ProjectSerializer.load_project(path)
            self._project = loaded_proj
            self._current_project_path = path

            cfg = self._project.export_config
            self.edit_output_dir.setText(cfg.output_dir)
            self.edit_separator.setText(cfg.separator)
            self.spin_digits.setValue(cfg.padding_digits)
            self.chk_skip_transparent.setChecked(cfg.skip_transparent_tiles)

            img_path = self._project.image_path
            if img_path and not os.path.exists(img_path):
                candidate = os.path.join(os.path.dirname(path), os.path.basename(img_path))
                if os.path.exists(candidate):
                    img_path = candidate
                    self._project.image_path = candidate

            if img_path and os.path.exists(img_path):
                self._load_source_image(img_path, reset_regions=False)
            else:
                self._source_image = None
                self.region_slicer_tab.set_project_and_image(self._project, None)
                self.tile_mapper_tab.set_project_and_image(self._project, None)
                QMessageBox.warning(
                    self,
                    "원본 이미지 확인 필요",
                    "설정 파일은 로드되었으나 원본 이미지 경로를 찾을 수 없습니다. '파일 -> 원본 타일셋 이미지 열기'로 이미지를 지정해주세요.",
                )
        except Exception as exc:
            QMessageBox.critical(self, "로드 오류", f"프로젝트 불러오기 실패:\n{exc}")

    def action_export_all(self) -> None:
        if self._source_image is None:
            QMessageBox.warning(self, "알림", "먼저 원본 이미지를 열어주세요.")
            return
        if len(self._project.regions) == 0:
            QMessageBox.warning(self, "알림", "내보낼 분할 영역(Region)이 없습니다.")
            return

        base_dir = (
            os.path.dirname(self._current_project_path)
            if self._current_project_path
            else ""
        )
        result = TileExportService.export_project(self._project, base_dir=base_dir)
        if result.errors:
            err_msg = "\n".join(result.errors)
            QMessageBox.warning(
                self,
                "일부 오류 발생",
                f"내보내기 중 오류가 발생했습니다:\n{err_msg}\n\n추출된 타일 수: {result.total_tiles_exported}개",
            )
        else:
            QMessageBox.information(
                self,
                "전체 내보내기 완료",
                f"총 {result.total_regions}개 영역에서 {result.total_tiles_exported}개의 타일 이미지를 추출했습니다.\n\n저장 위치:\n{result.output_root}",
            )
