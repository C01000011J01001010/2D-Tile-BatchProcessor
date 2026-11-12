from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class TileOrderEntry:
    tile_id: int
    col: int
    row: int

    def to_dict(self) -> Dict[str, int]:
        return {
            "id": self.tile_id,
            "col": self.col,
            "row": self.row,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TileOrderEntry":
        return cls(
            tile_id=int(data["id"]),
            col=int(data["col"]),
            row=int(data["row"]),
        )


@dataclass
class TileOrderModel:
    cols: int = 12
    rows: int = 4
    tile_width: int = 16
    tile_height: int = 16
    mappings: List[TileOrderEntry] = field(default_factory=list)

    def has_coord(self, col: int, row: int) -> bool:
        return any(entry.col == col and entry.row == row for entry in self.mappings)

    def get_id_at(self, col: int, row: int) -> Optional[int]:
        for entry in self.mappings:
            if entry.col == col and entry.row == row:
                return entry.tile_id
        return None

    def next_id(self) -> int:
        return len(self.mappings)

    def assign_next(self, col: int, row: int) -> Optional[TileOrderEntry]:
        if self.has_coord(col, row):
            return None
        entry = TileOrderEntry(tile_id=self.next_id(), col=col, row=row)
        self.mappings.append(entry)
        return entry

    def remove_at(self, col: int, row: int) -> bool:
        for i, entry in enumerate(self.mappings):
            if entry.col == col and entry.row == row:
                self.mappings.pop(i)
                return True
        return False

    def clear(self) -> None:
        self.mappings.clear()

    def clone_mappings(self) -> List[TileOrderEntry]:
        return [TileOrderEntry(e.tile_id, e.col, e.row) for e in self.mappings]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cols": self.cols,
            "rows": self.rows,
            "tile_width": self.tile_width,
            "tile_height": self.tile_height,
            "mappings": [entry.to_dict() for entry in self.mappings],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TileOrderModel":
        mappings = [
            TileOrderEntry.from_dict(item)
            for item in data.get("mappings", [])
        ]
        return cls(
            cols=int(data.get("cols", 12)),
            rows=int(data.get("rows", 4)),
            tile_width=int(data.get("tile_width", 16)),
            tile_height=int(data.get("tile_height", 16)),
            mappings=mappings,
        )
