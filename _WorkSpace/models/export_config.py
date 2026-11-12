from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class ExportConfig:
    output_dir: str = "output"
    separator: str = "_"
    padding_digits: int = 2
    skip_transparent_tiles: bool = True

    def format_filename(self, base_name: str, tile_id: int) -> str:
        digits = max(1, int(self.padding_digits))
        return f"{base_name}{self.separator}{tile_id:0{digits}d}.png"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "output_dir": self.output_dir,
            "separator": self.separator,
            "padding_digits": self.padding_digits,
            "skip_transparent_tiles": self.skip_transparent_tiles,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExportConfig":
        return cls(
            output_dir=str(data.get("output_dir", "output")),
            separator=str(data.get("separator", "_")),
            padding_digits=int(data.get("padding_digits", 2)),
            skip_transparent_tiles=bool(data.get("skip_transparent_tiles", True)),
        )
