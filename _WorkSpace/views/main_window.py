import os
from typing import Optional
from PIL import Image
from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtGui import QAction, QKeySequence, QCloseEvent
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QGroupBox,
    QLineEdit,
    QSpinBox,
    QCheckBox,
    QPushButton,
    QLabel,
    QFileDialog,
    QMessageBox,
)

from models.project_model import ProjectModel
from commands.region_commands import AutoSliceRegionsCommand
from services.image_service import ImageService
from services.serializer_service import ProjectSerializer
from services.export_service import TileExportService
from .region_slicer_tab import RegionSlicerTab
from .tile_mapper_tab import TileMapperTab


class MainWindow(QMainWindow):
    BASE_TITLE = "2D Tilemap Region Slicer & Tile Mapper"

    def __init__(self, initial_path: str = "") -> None:
        super().__init__()
        self.setWindowTitle(self.BASE_TITLE)
        self.resize(1360, 860)

        self._project: ProjectModel = ProjectModel()
        self._source_image: Optional[Image.Image] = None
        self._current_project_path: str = ""
        self._initial_dir: str = ""
        self._updating_export_ui: bool = False
        self._is_dirty: bool = False

        self._build_menus()
        self._build_ui()
        self._update_preview_label()

        if initial_path and os.path.exists(initial_path):
            abs_init = os.path.abspath(initial_path)
            if os.path.isdir(abs_init):
                self._initial_dir = abs_init
                self._project.export_config.output_dir = os.path.join(abs_init, "output")
                self._sync_export_config_ui()
            elif abs_init.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
                self._initial_dir = os.path.dirname(abs_init)
                self._open_image_with_sidecar(abs_init)
            elif abs_init.lower().endswith((".imgmeta", ".imgreg", ".imgregions", ".json")):
                self._initial_dir = os.path.dirname(abs_init)
                self._load_project_file(abs_init)

    def _build_menus(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("파일(&F)")

        act_open_img = QAction("원본 타일셋 이미지 열기(&O)...", self)
        act_open_img.setShortcut(QKeySequence("Ctrl+O"))
        act_open_img.triggered.connect(self.action_open_image)

        act_save_proj = QAction("현재 영역 메타(.imgmeta) 즉시 저장(&S)", self)
        act_save_proj.setShortcut(QKeySequence("Ctrl+S"))
        act_save_proj.triggered.connect(self.action_save_project)

        act_import_layout = QAction("다른 .imgmeta에서 영역 레이아웃 가져오기(&I)...", self)
        act_import_layout.setShortcut(QKeySequence("Ctrl+I"))
        act_import_layout.triggered.connect(self.action_import_layout)

        act_load_proj = QAction("영역 메타(.imgmeta) 파일 직접 열기(&L)...", self)
        act_load_proj.triggered.connect(self.action_load_project)

        act_export_all = QAction("전체 영역 일괄 내보내기(&E)", self)
        act_export_all.setShortcut(QKeySequence("Ctrl+E"))
        act_export_all.triggered.connect(self.action_export_all)

        act_exit = QAction("종료(&X)", self)
        act_exit.triggered.connect(self.close)

        file_menu.addAction(act_open_img)
        file_menu.addAction(act_save_proj)
        file_menu.addSeparator()
        file_menu.addAction(act_import_layout)
        file_menu.addAction(act_load_proj)
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

        self.tabs = QTabWidget(self)
        self.region_slicer_tab = RegionSlicerTab(self._project, self)
        self.tile_mapper_tab = TileMapperTab(self._project, self)

        self.tabs.addTab(self.region_slicer_tab, "1. Region Slicer (1차 영역 분할)")
        self.tabs.addTab(self.tile_mapper_tab, "2. Tile Mapper (2차 타일 순서 지정)")

        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.region_slicer_tab.command_manager.add_change_listener(self._mark_dirty)
        self.tile_mapper_tab.command_manager.add_change_listener(self._mark_dirty)
        self.region_slicer_tab.open_in_tile_mapper_requested.connect(
            self._on_open_in_tile_mapper
        )
        self.tile_mapper_tab.region_order_linked.connect(
            self._on_region_order_linked
        )

        root_layout.addWidget(export_group)
        root_layout.addWidget(self.tabs, stretch=1)

    def _on_region_order_linked(self) -> None:
        self.region_slicer_tab.refresh_ui()
        self._mark_dirty()

    def _mark_dirty(self) -> None:
        self._is_dirty = True
        title = self.BASE_TITLE
        if self._current_project_path:
            title += f" - {os.path.basename(self._current_project_path)} *"
        else:
            title += " *"
        self.setWindowTitle(title)

    def _clear_dirty(self) -> None:
        self._is_dirty = False
        title = self.BASE_TITLE
        if self._current_project_path:
            title += f" - {os.path.basename(self._current_project_path)}"
        self.setWindowTitle(title)

    def _check_unsaved_changes(self) -> bool:
        if not self._is_dirty:
            return True
        reply = QMessageBox.question(
            self,
            "저장하지 않은 변경사항",
            "저장하지 않은 작업 내역이 있습니다.\n현재 메타 파일(.imgmeta)에 저장하시겠습니까?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.action_save_project()
            return not self._is_dirty
        if reply == QMessageBox.StandardButton.No:
            return True
        return False

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._check_unsaved_changes():
            event.accept()
        else:
            event.ignore()

    def _sync_export_config_ui(self) -> None:
        self._updating_export_ui = True
        try:
            cfg = self._project.export_config
            with (
                QSignalBlocker(self.edit_output_dir),
                QSignalBlocker(self.edit_separator),
                QSignalBlocker(self.spin_digits),
                QSignalBlocker(self.chk_skip_transparent),
            ):
                self.edit_output_dir.setText(cfg.output_dir)
                self.edit_separator.setText(cfg.separator)
                self.spin_digits.setValue(cfg.padding_digits)
                self.chk_skip_transparent.setChecked(cfg.skip_transparent_tiles)
            self.tile_mapper_tab.canvas.set_padding_digits(cfg.padding_digits)
            self._update_preview_label()
        finally:
            self._updating_export_ui = False

    def _on_export_config_changed(self) -> None:
        if self._updating_export_ui:
            return
        cfg = self._project.export_config
        cfg.output_dir = self.edit_output_dir.text().strip() or "output"
        cfg.separator = self.edit_separator.text()
        cfg.padding_digits = self.spin_digits.value()
        cfg.skip_transparent_tiles = self.chk_skip_transparent.isChecked()
        self.tile_mapper_tab.canvas.set_padding_digits(cfg.padding_digits)
        self._update_preview_label()
        if self._source_image is not None or self._current_project_path:
            self._mark_dirty()

    def _update_preview_label(self) -> None:
        cfg = self._project.export_config
        sample_file = cfg.format_filename("Temple", 0)
        self.lbl_format_preview.setText(
            f"예시: {cfg.output_dir}/Temple/{sample_file}"
        )

    def _on_browse_output_dir(self) -> None:
        start_dir = self._initial_dir or (
            os.path.dirname(self._current_project_path) if self._current_project_path else ""
        )
        folder = QFileDialog.getExistingDirectory(self, "출력 루트 폴더 선택", start_dir)
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
        if not self._check_unsaved_changes():
            return
        start_dir = self._initial_dir or (
            os.path.dirname(self._current_project_path) if self._current_project_path else ""
        )
        path, _ = QFileDialog.getOpenFileName(
            self,
            "원본 타일셋 이미지 선택",
            start_dir,
            "PNG Images (*.png);;All Images (*.png *.bmp *.jpg *.jpeg);;All Files (*)",
        )
        if not path:
            return
        self._open_image_with_sidecar(path)

    def _open_image_with_sidecar(self, img_path: str) -> None:
        try:
            abs_img_path = os.path.abspath(img_path)
            img = ImageService.load_rgba_image(abs_img_path)
            self._source_image = img
            self._initial_dir = os.path.dirname(abs_img_path)

            img_dir = os.path.dirname(abs_img_path)
            base_name = os.path.splitext(os.path.basename(abs_img_path))[0]
            sidecar_path = os.path.join(img_dir, f"{base_name}.imgmeta")

            if os.path.exists(sidecar_path):
                try:
                    loaded_proj = ProjectSerializer.load_project(sidecar_path)
                    self._project = loaded_proj
                    self._current_project_path = sidecar_path
                    self._project.image_path = abs_img_path
                    self._project.image_width = img.width
                    self._project.image_height = img.height
                except Exception:
                    self._project = ProjectModel(
                        image_path=abs_img_path,
                        image_width=img.width,
                        image_height=img.height,
                    )
                    self._current_project_path = sidecar_path
                    ProjectSerializer.save_project(self._project, sidecar_path)
            else:
                self._project = ProjectModel(
                    image_path=abs_img_path,
                    image_width=img.width,
                    image_height=img.height,
                )
                self._current_project_path = sidecar_path
                ProjectSerializer.save_project(self._project, sidecar_path)

            self._sync_export_config_ui()
            self.region_slicer_tab.set_project_and_image(self._project, img)
            self.tile_mapper_tab.set_project_and_image(self._project, img)
            self._clear_dirty()
            self.statusBar().showMessage(
                f"로드 완료: {abs_img_path} ({img.width}x{img.height}) | 사이드카: {os.path.basename(sidecar_path)}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "이미지 로드 오류", f"이미지를 열 수 없습니다:\n{exc}")

    def _load_source_image(self, path: str, reset_regions: bool = False) -> None:
        try:
            abs_img_path = os.path.abspath(path)
            img = ImageService.load_rgba_image(abs_img_path)
            self._source_image = img
            self._initial_dir = os.path.dirname(abs_img_path)
            self._project.image_path = abs_img_path
            self._project.image_width = img.width
            self._project.image_height = img.height
            if reset_regions:
                self._project.regions.clear()
            self.region_slicer_tab.set_project_and_image(self._project, img)
            self.tile_mapper_tab.set_project_and_image(self._project, img)
            self.statusBar().showMessage(
                f"로드 완료: {abs_img_path} ({img.width}x{img.height})"
            )
        except Exception as exc:
            QMessageBox.critical(self, "이미지 로드 오류", f"이미지를 열 수 없습니다:\n{exc}")

    def action_save_project(self) -> None:
        if not self._current_project_path and self._project.image_path:
            img_dir = os.path.dirname(os.path.abspath(self._project.image_path))
            base_name = os.path.splitext(os.path.basename(self._project.image_path))[0]
            self._current_project_path = os.path.join(img_dir, f"{base_name}.imgmeta")

        if self._current_project_path:
            try:
                ProjectSerializer.save_project(self._project, self._current_project_path)
                self._clear_dirty()
                self.statusBar().showMessage(f"즉시 저장 완료: {self._current_project_path}")
                return
            except Exception as exc:
                QMessageBox.critical(self, "저장 오류", f"메타 파일 저장 실패:\n{exc}")
                return

        start_dir = self._initial_dir or "project.imgmeta"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "영역 메타(.imgmeta) 파일 저장",
            start_dir,
            "Image Meta Project (*.imgmeta);;JSON Files (*.json)",
        )
        if not path:
            return
        if not path.endswith((".imgmeta", ".json")):
            path += ".imgmeta"
        try:
            abs_path = os.path.abspath(path)
            ProjectSerializer.save_project(self._project, abs_path)
            self._current_project_path = abs_path
            self._clear_dirty()
            self.statusBar().showMessage(f"프로젝트 저장 완료: {self._current_project_path}")
        except Exception as exc:
            QMessageBox.critical(self, "저장 오류", f"프로젝트 저장 실패:\n{exc}")

    def _load_project_file(self, path: str) -> None:
        try:
            abs_meta_path = os.path.abspath(path)
            loaded_proj = ProjectSerializer.load_project(abs_meta_path)
            self._project = loaded_proj
            self._current_project_path = abs_meta_path
            self._initial_dir = os.path.dirname(abs_meta_path)

            self._sync_export_config_ui()

            img_path = self._project.image_path
            if img_path and not os.path.exists(img_path):
                candidate = os.path.join(os.path.dirname(abs_meta_path), os.path.basename(img_path))
                if os.path.exists(candidate):
                    img_path = candidate
                    self._project.image_path = candidate

            if img_path and os.path.exists(img_path):
                self._load_source_image(img_path, reset_regions=False)
                self._clear_dirty()
            else:
                self._source_image = None
                self.region_slicer_tab.set_project_and_image(self._project, None)
                self.tile_mapper_tab.set_project_and_image(self._project, None)
                self._clear_dirty()
                QMessageBox.warning(
                    self,
                    "원본 이미지 확인 필요",
                    "메타 파일은 로드되었으나 원본 이미지 경로를 찾을 수 없습니다. '파일 -> 원본 타일셋 이미지 열기'로 이미지를 지정해주세요.",
                )
        except Exception as exc:
            QMessageBox.critical(self, "로드 오류", f"메타 파일 불러오기 실패:\n{exc}")

    def action_load_project(self) -> None:
        if not self._check_unsaved_changes():
            return
        start_dir = self._initial_dir or (
            os.path.dirname(self._current_project_path) if self._current_project_path else ""
        )
        path, _ = QFileDialog.getOpenFileName(
            self,
            "영역 메타(.imgmeta) 파일 열기",
            start_dir,
            "Image Meta Project (*.imgmeta *.imgreg *.imgregions *.json);;All Files (*)",
        )
        if not path:
            return
        self._load_project_file(path)

    def action_import_layout(self) -> None:
        if self._source_image is None:
            QMessageBox.warning(self, "알림", "먼저 원본 타일셋 이미지를 열어주세요.")
            return
        start_dir = self._initial_dir or (
            os.path.dirname(self._current_project_path) if self._current_project_path else ""
        )
        path, _ = QFileDialog.getOpenFileName(
            self,
            "레이아웃을 가져올 .imgmeta 파일 선택",
            start_dir,
            "Image Meta Project (*.imgmeta *.imgreg *.imgregions *.json);;All Files (*)",
        )
        if not path:
            return
        try:
            other_proj = ProjectSerializer.load_project(path)
            if not other_proj.regions:
                QMessageBox.information(self, "알림", "선택한 파일에 가져올 영역이 없습니다.")
                return

            new_regs = [r.clone() for r in other_proj.regions]
            cmd = AutoSliceRegionsCommand(
                project=self._project,
                new_regions=new_regs,
                replace_existing=True,
            )
            self.region_slicer_tab.command_manager.execute_command(cmd)
            if self.tabs.currentIndex() == 1:
                curr_reg = self.region_slicer_tab.current_region()
                reg_id = curr_reg.region_id if curr_reg else ""
                self.tile_mapper_tab.refresh_region_list(select_region_id=reg_id)

            self.statusBar().showMessage(
                f"레이아웃 복사 완료 ({len(new_regs)}개 영역) - Ctrl+S를 눌러야 현재 이미지의 .imgmeta에 저장됩니다."
            )
            QMessageBox.information(
                self,
                "가져오기 완료",
                f"총 {len(new_regs)}개의 영역 레이아웃을 현재 이미지로 복사했습니다.\n"
                f"(Ctrl+Z로 취소 가능하며, Ctrl+S로 저장하기 전까지 파일에 덮어써지지 않습니다.)",
            )
        except Exception as exc:
            QMessageBox.critical(self, "오류", f"레이아웃 가져오기 실패:\n{exc}")

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
                f"내보내기 중 확인이 필요한 항목이 있습니다:\n{err_msg}\n\n추출된 타일 수: {result.total_tiles_exported}개",
            )
        else:
            QMessageBox.information(
                self,
                "전체 내보내기 완료",
                f"총 {result.total_regions}개 영역에서 {result.total_tiles_exported}개의 타일 이미지를 추출했습니다.\n\n저장 위치:\n{result.output_root}",
            )
