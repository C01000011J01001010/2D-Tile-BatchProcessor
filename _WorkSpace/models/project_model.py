from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from .export_config import ExportConfig
from .region_data import RegionData


@dataclass
class ProjectModel:
    image_path: str = ""
    image_width: int = 0
    image_height: int = 0
    export_config: ExportConfig = field(default_factory=ExportConfig)
    regions: List[RegionData] = field(default_factory=list)

    def get_region_by_id(self, region_id: str) -> Optional[RegionData]:
        for region in self.regions:
            if region.region_id == region_id:
                return region
        return None

    def add_region(self, region: RegionData) -> None:
        self.regions.append(region)

    def remove_region(self, region_id: str) -> Optional[RegionData]:
        for idx, region in enumerate(self.regions):
            if region.region_id == region_id:
                return self.regions.pop(idx)
        return None

    def generate_unique_name(self, prefix: str = "Region") -> str:
        existing = {r.base_name for r in self.regions}
        index = 0
        while True:
            candidate = f"{prefix}_{index:02d}"
            if candidate not in existing:
                return candidate
            index += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "image_path": self.image_path,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "export_config": self.export_config.to_dict(),
            "regions": [r.to_dict() for r in self.regions],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectModel":
        export_cfg = ExportConfig.from_dict(data.get("export_config", {}))
        regions = [
            RegionData.from_dict(item)
            for item in data.get("regions", [])
        ]
        return cls(
            image_path=str(data.get("image_path", "")),
            image_width=int(data.get("image_width", 0)),
            image_height=int(data.get("image_height", 0)),
            export_config=export_cfg,
            regions=regions,
        )
