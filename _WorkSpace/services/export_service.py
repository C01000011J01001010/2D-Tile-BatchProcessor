import os
from dataclasses import dataclass, field
from typing import List, Optional
from PIL import Image
from models.export_config import ExportConfig
from models.project_model import ProjectModel
from models.region_data import RegionData
from models.tile_order_model import TileOrderModel
from .image_service import ImageService
from .serializer_service import ProjectSerializer


@dataclass
class ExportResult:
    total_regions: int = 0
    total_tiles_exported: int = 0
    output_root: str = ""
    errors: List[str] = field(default_factory=list)


class TileExportService:
    @staticmethod
    def resolve_output_root(output_dir: str, base_dir: str = "") -> str:
        if os.path.isabs(output_dir) or not base_dir:
            return os.path.abspath(output_dir)
        return os.path.abspath(os.path.join(base_dir, output_dir))

    @classmethod
    def export_single_region(
        cls,
        source_img: Image.Image,
        region: RegionData,
        export_config: ExportConfig,
        tile_order: Optional[TileOrderModel] = None,
        base_dir: str = "",
    ) -> int:
        output_root = cls.resolve_output_root(export_config.output_dir, base_dir)
        region_dir = os.path.join(output_root, region.base_name)
        os.makedirs(region_dir, exist_ok=True)

        region_img = ImageService.crop_region(source_img, region)
        cols = region.cols
        rows = region.rows
        tile_w = region.tile_width
        tile_h = region.tile_height

        active_order = tile_order
        # 1. Memory priority (from custom_mappings)
        if active_order is None and region.custom_mappings:
            active_order = TileOrderModel(
                cols=cols,
                rows=rows,
                tile_width=tile_w,
                tile_height=tile_h,
                mappings=list(region.custom_mappings),
            )
        
        # 2. Disk priority (from tile_order_path) if memory is empty
        if active_order is None and region.tile_order_path:
            order_path = region.tile_order_path
            if not os.path.isabs(order_path) and base_dir:
                candidate = os.path.join(base_dir, order_path)
                if os.path.exists(candidate):
                    order_path = candidate
            if os.path.exists(order_path):
                active_order = ProjectSerializer.load_tile_order(order_path)

        exported_count = 0

        if active_order is not None:
            for entry in active_order.mappings:
                if not (0 <= entry.col < cols and 0 <= entry.row < rows):
                    continue
                tile_img = ImageService.crop_tile(
                    region_img, entry.col, entry.row, tile_w, tile_h
                )
                if export_config.skip_transparent_tiles and ImageService.is_fully_transparent(tile_img):
                    continue
                filename = export_config.format_filename(region.base_name, entry.tile_id)
                tile_img.save(os.path.join(region_dir, filename), format="PNG")
                exported_count += 1
        else:
            current_id = 0
            for r in range(rows):
                for c in range(cols):
                    tile_img = ImageService.crop_tile(region_img, c, r, tile_w, tile_h)
                    if export_config.skip_transparent_tiles and ImageService.is_fully_transparent(tile_img):
                        continue
                    filename = export_config.format_filename(region.base_name, current_id)
                    tile_img.save(os.path.join(region_dir, filename), format="PNG")
                    current_id += 1
                    exported_count += 1

        return exported_count

    @classmethod
    def export_project(
        cls,
        project: ProjectModel,
        base_dir: str = "",
    ) -> ExportResult:
        output_root = cls.resolve_output_root(project.export_config.output_dir, base_dir)
        result = ExportResult(output_root=output_root)

        # Check for duplicate BaseNames
        base_names = [r.base_name for r in project.regions]
        duplicates = set([x for x in base_names if base_names.count(x) > 1])
        if duplicates:
            result.errors.append(f"경고: 중복된 영역 이름이 존재합니다 {list(duplicates)}. 동일한 폴더에 덮어써질 수 있습니다.")

        if not project.image_path or not os.path.exists(project.image_path):
            result.errors.append(f"원본 이미지를 찾을 수 없습니다: {project.image_path}")
            return result

        try:
            source_img = ImageService.load_rgba_image(project.image_path)
        except Exception as exc:
            result.errors.append(f"이미지 로드 실패: {exc}")
            return result

        for region in project.regions:
            try:
                count = cls.export_single_region(
                    source_img=source_img,
                    region=region,
                    export_config=project.export_config,
                    tile_order=None,
                    base_dir=base_dir,
                )
                result.total_regions += 1
                result.total_tiles_exported += count
            except Exception as exc:
                result.errors.append(f"[{region.base_name}] 내보내기 오류: {exc}")

        return result
