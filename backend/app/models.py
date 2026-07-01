from typing import Any

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    preset: str
    options: dict[str, Any] = Field(default_factory=dict)


class PresetField(BaseModel):
    name: str
    label: str
    type: str
    required: bool = False
    default: Any = None
    min: int | None = None
    max: int | None = None


class Preset(BaseModel):
    id: str
    label: str
    description: str
    fields: list[PresetField]


class RunResponse(BaseModel):
    ok: bool
    command: list[str]
    data: Any
