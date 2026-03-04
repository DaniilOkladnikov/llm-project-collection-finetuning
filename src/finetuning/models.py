"""Pydantic models for fine-tuning dataset generation."""

from enum import Enum
from typing import Dict, List, Optional, Any, Literal, Union
from pydantic import BaseModel, ConfigDict, Field


class VariableType(str, Enum):
    """Types of variables that can be used in scenario drafts."""
    OBJECT_TYPE = "OBJECT_TYPE"
    LOCATION = "LOCATION"


class LocationMode(str, Enum):
    """Mode for resolving LOCATION variables."""
    OBJECT_LOCATION = "OBJECT_LOCATION"  # Only object locations (e.g., "box1_11")
    LOCATION_NAME = "LOCATION_NAME"       # Only location names (e.g., "table")
    ANY = "ANY"                           # Either object location or location name


class VariableDefinition(BaseModel):
    """Definition of a variable used in a scenario draft."""
    name: str                                     # e.g., "$X", "$Y"
    type: VariableType
    mode: LocationMode = LocationMode.ANY         # Only used for LOCATION type
    constraints: Optional[Dict[str, Any]] = None  # e.g., {"must_exist_in": "$Y"}


class ObjectPlacementRule(BaseModel):
    """Rule for placing objects in specific locations during initial state setup."""
    min_objects: int = 0
    max_objects: int = 1
    location_pattern: str = "*"       # Glob pattern or variable reference like "$Y"
    type_pattern: str = "*"           # Glob pattern or variable reference like "$X"
    type_exclude: Optional[Union[str, List[str]]] = None  # Type(s) to exclude, e.g. "$X" or ["$X", "$W"]
    location_exclude: Optional[str] = None  # Location to exclude


class InitialStateConfig(BaseModel):
    """Configuration for initial scene state."""
    robot: Dict[str, Any]  # {"position": ["reset"], "gripper_open": [true]}
    objects: Any           # "reset" | "prev" | List[ObjectPlacementRule]


class ScenarioDraft(BaseModel):
    """A scenario draft template for generating conversations."""
    id: str                                       # e.g., "1.1", "2.3"
    name: str
    description: str
    category: str                                 # "pick" or "place"

    initial_state: InitialStateConfig
    variables: List[VariableDefinition]
    prompt_templates: List[str]                    # e.g., ["Pick up the $X from $Y.", ...]
    tool_routine: str                             # e.g., "observe_and_pick"
    final_messages: Dict[str, str]                # outcome -> message template
    min_object_types: int = 1                     # Minimum distinct object types required in scene


class ConversationMessage(BaseModel):
    """A single message in a conversation."""
    model_config = ConfigDict(exclude_none=True)

    role: Literal["system", "user", "assistant", "tool"]
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


class Conversation(BaseModel):
    """Complete fine-tuning conversation."""
    messages: List[ConversationMessage]
    metadata: Optional[Dict[str, Any]] = None  # draft_id, scene info, outcome, etc.


class ScenarioDraftsFile(BaseModel):
    """Root model for scenario_drafts.json file."""
    scenarios: List[ScenarioDraft]
