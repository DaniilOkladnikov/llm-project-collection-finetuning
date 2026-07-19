from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional, Any, Set, List
from enum import Enum, auto
import pydantic
from pydantic import BaseModel, model_validator, Field


@dataclass
class NamedSpot:
    name: str


@dataclass
class Object:
    id: int
    type: str
    location: "ObjectLocation"


class PositionType(Enum):
    GENERAL = auto()
    PICK = auto()
    PLACE = auto()
    OBSERVE = auto()


# ============================================================================
# Pydantic Configuration Models
# ============================================================================

class PositionConfig(BaseModel):
    type: str  # "GENERAL", "PICK", "PLACE", "OBSERVE"
    bound_type: Optional[str] = None
    bound_location: Optional[str] = None
    observable_locations: Optional[List[str]] = None

    class Config:
        frozen = True


class ObjectConfig(BaseModel):
    id: int
    type: str

    class Config:
        frozen = True


class SceneConfig(BaseModel):
    """Immutable scene topology: locations, positions, object types."""
    object_locations: List[str]
    object_types: List[str]
    positions: Dict[str, PositionConfig]
    objects: Dict[str, ObjectConfig]
    location_names: Optional[Dict[str, List[str]]] = None

    class Config:
        frozen = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneConfig":
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


# ============================================================================
# Scene State Model
# ============================================================================

class SceneState(BaseModel):
    """Current mutable state of the scene."""
    robot_position: str
    robot_gripper_open: bool
    object_locations: Dict[int, str]  # object_id -> location_name
    observed_positions: Set[str] = Field(default_factory=set)

    class Config:
        arbitrary_types_allowed = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "robot_position": self.robot_position,
            "robot_gripper_open": self.robot_gripper_open,
            "object_locations": {str(k): v for k, v in self.object_locations.items()},
            "observed_positions": list(self.observed_positions),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneState":
        obj_locs = data.get("object_locations", {})
        return cls(
            robot_position=data["robot_position"],
            robot_gripper_open=data["robot_gripper_open"],
            object_locations={int(k): v for k, v in obj_locs.items()},
            observed_positions=set(data.get("observed_positions", [])),
        )

    def copy(self) -> "SceneState":
        return SceneState(
            robot_position=self.robot_position,
            robot_gripper_open=self.robot_gripper_open,
            object_locations=dict(self.object_locations),
            observed_positions=set(self.observed_positions),
        )


# ============================================================================
# Dataclass Models (for runtime usage)
# ============================================================================

@dataclass
class Position(NamedSpot):
    type: PositionType
    bound_type: Optional[str] = None
    bound_location: Optional["ObjectLocation"] = None
    observable_locations: Optional[List["ObjectLocation"]] = None

    def is_general(self) -> bool:
        return self.type == PositionType.GENERAL

    def is_pick(self) -> bool:
        return self.type == PositionType.PICK

    def is_place(self) -> bool:
        return self.type == PositionType.PLACE

    def is_observe(self) -> bool:
        return self.type == PositionType.OBSERVE


@dataclass
class ObjectLocation(NamedSpot):
    pass


class Robot:
    def __init__(self, start_position: Position, start_gripper: bool):
        self.position: Position = start_position
        self.gripper_open: bool = start_gripper


# ============================================================================
# Main Scene Class
# ============================================================================

class Scene(pydantic.BaseModel):
    """Complete scene with config and state."""
    config: SceneConfig
    state: SceneState
    initial_state: SceneState

    # Derived/cached fields (computed from config)
    undefined_location: Optional[ObjectLocation] = Field(default=None, exclude=True)
    attached_location: Optional[ObjectLocation] = Field(default=None, exclude=True)
    object_locations: Optional[Dict[str, ObjectLocation]] = Field(default=None, exclude=True)
    positions: Optional[Dict[str, Position]] = Field(default=None, exclude=True)
    objects: Optional[Dict[int, Object]] = Field(default=None, exclude=True)
    robot: Optional[Robot] = Field(default=None, exclude=True)

    class Config:
        arbitrary_types_allowed = True

    @model_validator(mode='after')
    def build_derived_fields(self) -> "Scene":
        self.undefined_location = ObjectLocation(name="UNDEFINED")
        self.attached_location = ObjectLocation(name="ATTACHED")

        self.object_locations = {
            name: ObjectLocation(name)
            for name in self.config.object_locations
        }
        self.object_locations["ATTACHED"] = self.attached_location
        self.object_locations["UNDEFINED"] = self.undefined_location

        def location_by_name(name: Optional[str]) -> Optional[ObjectLocation]:
            if name is None:
                return None
            return self.object_locations.get(name)

        self.positions = {
            name: Position(
                name=name,
                type=PositionType[pos_cfg.type],
                bound_type=pos_cfg.bound_type,
                bound_location=location_by_name(pos_cfg.bound_location),
                observable_locations=(
                    [location_by_name(loc_name) for loc_name in pos_cfg.observable_locations]
                    if pos_cfg.observable_locations else None
                ),
            )
            for name, pos_cfg in self.config.positions.items()
        }

        self.objects = {
            int(obj_id): Object(
                id=int(obj_id),
                type=obj_cfg.type,
                location=location_by_name(self.state.object_locations[int(obj_id)]),
            )
            for obj_id, obj_cfg in self.config.objects.items()
        }

        self.robot = Robot(
            start_position=self.positions.get(self.state.robot_position),
            start_gripper=self.state.robot_gripper_open
        )

        return self

    # --- Helper methods ---

    def is_known_position_name(self, name: str) -> bool:
        return name in self.positions

    def robot_held(self) -> Optional[Object]:
        return next(
            (obj for obj in self.objects.values()
             if obj.location == self.attached_location),
            None,
        )

    def position_by_name(self, name: str) -> Optional[Position]:
        return self.positions.get(name)

    def location_by_name(self, name: Optional[str]) -> Optional[ObjectLocation]:
        if name is None:
            return None
        return self.object_locations.get(name)

    def object_by_location(self, location: ObjectLocation) -> Optional[Object]:
        return next(
            (obj for obj in self.objects.values()
             if obj.location == location),
            None,
        )

    def pick_position_by_loc_and_type(
        self, location: ObjectLocation, type: str
    ) -> Optional[Position]:
        return next(
            (
                position
                for position in self.positions.values()
                if position.bound_location == location
                and position.bound_type == type
            ),
            None,
        )

    def is_position_observed(self, position_name: str) -> bool:
        return position_name in self.state.observed_positions

    def mark_position_observed(self, position_name: str) -> None:
        position = self.position_by_name(position_name)
        if position and position.is_pick():
            self.state.observed_positions.add(position_name)

    # --- State Management ---

    def get_state(self) -> SceneState:
        return SceneState(
            robot_position=self.robot.position.name,
            robot_gripper_open=self.robot.gripper_open,
            object_locations={obj.id: obj.location.name for obj in self.objects.values()},
            observed_positions=self.state.observed_positions.copy()
        )

    def set_state(self, state: SceneState) -> None:
        self.state = state
        self._sync_dataclasses_from_state()

    def reset_state(self) -> None:
        self.state = self.initial_state.copy()
        self._sync_dataclasses_from_state()

    def _sync_dataclasses_from_state(self) -> None:
        self.robot.position = self.position_by_name(self.state.robot_position)
        self.robot.gripper_open = self.state.robot_gripper_open
        for obj in self.objects.values():
            location_name = self.state.object_locations[obj.id]
            obj.location = self.location_by_name(location_name)
