from typing import List, Optional
from models.project_model import ProjectModel
from models.region_data import RegionData
from .base_command import ICommand


class AddRegionCommand(ICommand):
    def __init__(self, project: ProjectModel, region: RegionData) -> None:
        self._project = project
        self._region = region.clone()

    def execute(self) -> None:
        self._project.add_region(self._region.clone())

    def undo(self) -> None:
        self._project.remove_region(self._region.region_id)

    @property
    def description(self) -> str:
        return f"Add Region '{self._region.base_name}'"


class DeleteRegionCommand(ICommand):
    def __init__(self, project: ProjectModel, region_id: str) -> None:
        self._project = project
        self._region_id = region_id
        self._backup_region: Optional[RegionData] = None
        self._backup_index: int = -1

    def execute(self) -> None:
        for idx, reg in enumerate(self._project.regions):
            if reg.region_id == self._region_id:
                self._backup_index = idx
                self._backup_region = reg.clone()
                self._project.regions.pop(idx)
                break

    def undo(self) -> None:
        if self._backup_region is not None:
            insert_idx = max(0, min(self._backup_index, len(self._project.regions)))
            self._project.regions.insert(insert_idx, self._backup_region.clone())

    @property
    def description(self) -> str:
        name = self._backup_region.base_name if self._backup_region else self._region_id
        return f"Delete Region '{name}'"


class ModifyRegionCommand(ICommand):
    def __init__(
        self,
        project: ProjectModel,
        before_state: RegionData,
        after_state: RegionData,
    ) -> None:
        self._project = project
        self._before = before_state.clone()
        self._after = after_state.clone()

    def _apply_state(self, state: RegionData) -> None:
        target = self._project.get_region_by_id(state.region_id)
        if target is not None:
            target.base_name = state.base_name
            target.x = state.x
            target.y = state.y
            target.width = state.width
            target.height = state.height
            target.tile_width = state.tile_width
            target.tile_height = state.tile_height
            target.tile_order_path = state.tile_order_path
            target.custom_mappings = [e for e in state.custom_mappings]

    def execute(self) -> None:
        self._apply_state(self._after)

    def undo(self) -> None:
        self._apply_state(self._before)

    @property
    def description(self) -> str:
        return f"Modify Region '{self._after.base_name}'"


class AutoSliceRegionsCommand(ICommand):
    def __init__(
        self,
        project: ProjectModel,
        new_regions: List[RegionData],
        replace_existing: bool = True,
    ) -> None:
        self._project = project
        self._new_regions = [r.clone() for r in new_regions]
        self._replace_existing = replace_existing
        self._previous_regions: List[RegionData] = []

    def execute(self) -> None:
        self._previous_regions = [r.clone() for r in self._project.regions]
        if self._replace_existing:
            self._project.regions = [r.clone() for r in self._new_regions]
        else:
            self._project.regions.extend(r.clone() for r in self._new_regions)

    def undo(self) -> None:
        self._project.regions = [r.clone() for r in self._previous_regions]

    @property
    def description(self) -> str:
        return f"Auto Slice ({len(self._new_regions)} regions)"
