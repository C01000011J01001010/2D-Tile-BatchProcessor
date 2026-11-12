from typing import List, Optional
from models.tile_order_model import TileOrderModel, TileOrderEntry
from .base_command import ICommand


class AssignTileOrderCommand(ICommand):
    def __init__(self, model: TileOrderModel, col: int, row: int) -> None:
        self._model = model
        self._col = col
        self._row = row
        self._assigned_id: Optional[int] = None

    def execute(self) -> None:
        if self._model.has_coord(self._col, self._row):
            return
        entry = self._model.assign_next(self._col, self._row)
        if entry is not None:
            self._assigned_id = entry.tile_id

    def undo(self) -> None:
        self._model.remove_at(self._col, self._row)

    @property
    def description(self) -> str:
        return f"Assign Tile ({self._col}, {self._row}) -> ID {self._assigned_id}"


class ResetTileOrderCommand(ICommand):
    def __init__(self, model: TileOrderModel) -> None:
        self._model = model
        self._backup_mappings: List[TileOrderEntry] = []

    def execute(self) -> None:
        self._backup_mappings = self._model.clone_mappings()
        self._model.clear()

    def undo(self) -> None:
        self._model.mappings = [
            TileOrderEntry(e.tile_id, e.col, e.row) for e in self._backup_mappings
        ]

    @property
    def description(self) -> str:
        return "Reset Tile Order"


class ReplaceTileOrderMappingsCommand(ICommand):
    def __init__(
        self,
        model: TileOrderModel,
        new_mappings: List[TileOrderEntry],
    ) -> None:
        self._model = model
        self._new_mappings = [
            TileOrderEntry(e.tile_id, e.col, e.row) for e in new_mappings
        ]
        self._backup_mappings: List[TileOrderEntry] = []

    def execute(self) -> None:
        self._backup_mappings = self._model.clone_mappings()
        self._model.mappings = [
            TileOrderEntry(e.tile_id, e.col, e.row) for e in self._new_mappings
        ]

    def undo(self) -> None:
        self._model.mappings = [
            TileOrderEntry(e.tile_id, e.col, e.row) for e in self._backup_mappings
        ]

    @property
    def description(self) -> str:
        return f"Apply Tile Order ({len(self._new_mappings)} tiles)"


class ShiftRemoveTileOrderCommand(ICommand):
    def __init__(self, model: TileOrderModel, target_id: int) -> None:
        self._model = model
        self._target_id = target_id
        self._backup_mappings: List[TileOrderEntry] = []

    def execute(self) -> None:
        self._backup_mappings = self._model.clone_mappings()
        new_mappings = []
        for m in self._model.mappings:
            if m.tile_id < self._target_id:
                new_mappings.append(TileOrderEntry(m.tile_id, m.col, m.row))
            elif m.tile_id > self._target_id:
                new_mappings.append(TileOrderEntry(m.tile_id - 1, m.col, m.row))
        self._model.mappings = new_mappings

    def undo(self) -> None:
        self._model.mappings = [
            TileOrderEntry(e.tile_id, e.col, e.row) for e in self._backup_mappings
        ]

    @property
    def description(self) -> str:
        return f"Remove Tile ID {self._target_id} and Shift"
