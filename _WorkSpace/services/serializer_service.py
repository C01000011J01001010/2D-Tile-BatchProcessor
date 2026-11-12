import json
import os
from models.project_model import ProjectModel
from models.tile_order_model import TileOrderModel


class ProjectSerializer:
    PROJECT_EXTENSIONS = (".imgreg", ".imgregions")
    TILE_ORDER_EXTENSION = ".tileorder"

    @staticmethod
    def save_project(project: ProjectModel, file_path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        base_dir = os.path.dirname(os.path.abspath(file_path))
        data = project.to_dict()

        if project.image_path and os.path.isabs(project.image_path):
            try:
                data["image_path"] = os.path.relpath(project.image_path, base_dir)
            except ValueError:
                pass

        for r_data, r_obj in zip(data.get("regions", []), project.regions):
            if r_obj.tile_order_path and os.path.isabs(r_obj.tile_order_path):
                try:
                    r_data["tile_order_path"] = os.path.relpath(r_obj.tile_order_path, base_dir)
                except ValueError:
                    pass

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @staticmethod
    def load_project(file_path: str) -> ProjectModel:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        base_dir = os.path.dirname(os.path.abspath(file_path))
        
        img_path = data.get("image_path", "")
        if img_path and not os.path.isabs(img_path):
            data["image_path"] = os.path.normpath(os.path.join(base_dir, img_path))

        for r_data in data.get("regions", []):
            top = r_data.get("tile_order_path", "")
            if top and not os.path.isabs(top):
                r_data["tile_order_path"] = os.path.normpath(os.path.join(base_dir, top))

        return ProjectModel.from_dict(data)

    @staticmethod
    def save_tile_order(tile_order: TileOrderModel, file_path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        data = tile_order.to_dict()
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @staticmethod
    def load_tile_order(file_path: str) -> TileOrderModel:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return TileOrderModel.from_dict(data)
