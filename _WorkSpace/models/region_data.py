import uuid
from dataclasses import dataclass, field
from typing import Dict, Any, List
from .tile_order_model import TileOrderEntry


@dataclass
class RegionData:
    base_name: str
    x: int
    y: int
    width: int
    height: int
    tile_width: int = 16
    tile_height: int = 16
    tile_order_path: str = ""
    custom_mappings: List[TileOrderEntry] = field(default_factory=list)
    region_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    @property
    def cols(self) -> int:
        return self.width // self.tile_width if self.tile_width > 0 else 0

    @property
    def rows(self) -> int:
        return self.height // self.tile_height if self.tile_height > 0 else 0

    def clone(self) -> "RegionData":
        return RegionData(
            base_name=self.base_name,
            x=self.x,
            y=self.y,
            width=self.width,
            height=self.height,
            tile_width=self.tile_width,
            tile_height=self.tile_height,
            tile_order_path=self.tile_order_path,
            custom_mappings=[TileOrderEntry(e.tile_id, e.col, e.row) for e in self.custom_mappings],
            region_id=self.region_id,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "region_id": self.region_id,
            "base_name": self.base_name,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "tile_width": self.tile_width,
            "tile_height": self.tile_height,
            "tile_order_path": self.tile_order_path,
            "custom_mappings": [e.to_dict() for e in self.custom_mappings],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RegionData":
        raw_mappings = data.get("custom_mappings", [])
        mappings = [TileOrderEntry.from_dict(m) for m in raw_mappings]
        return cls(
            region_id=str(data.get("region_id", uuid.uuid4().hex[:8])),
            base_name=str(data.get("base_name", "Region")),
            x=int(data.get("x", 0)),
            y=int(data.get("y", 0)),
            width=int(data.get("width", 16)),
            height=int(data.get("height", 16)),
            tile_width=int(data.get("tile_width", 16)),
            tile_height=int(data.get("tile_height", 16)),
            tile_order_path=str(data.get("tile_order_path", "")),
            custom_mappings=mappings,
        )
