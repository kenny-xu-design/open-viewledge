from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


SECTIONS = (
    "metadata", "summary", "highlights", "prerequisites", "steps", "glossary",
    "thoughts", "action_items", "warnings", "chapters", "keyframes", "chat",
    "user_notes", "source_materials",
)

PRESETS = {
    "light": ["metadata", "summary", "highlights", "chapters"],
    "summary-chat": ["metadata", "summary", "highlights", "chat", "user_notes"],
    "full": list(SECTIONS),
}


class ExportSelection(BaseModel):
    knowledge_id: str
    sections: list[str] = Field(default_factory=lambda: list(PRESETS["full"]))
    order: list[str] = Field(default_factory=list)
    destination: Literal["preview", "download", "vault", "obsidian-open"] = "preview"
    filename: str = ""
    overwrite: bool = False
    open_after_export: bool = False

    def normalized_sections(self) -> list[str]:
        chosen = [value for value in self.sections if value in SECTIONS]
        order = [value for value in self.order if value in chosen]
        return order + [value for value in chosen if value not in order]


def selection_from_preset(knowledge_id: str, preset: str = "full", **updates: object) -> ExportSelection:
    return ExportSelection(knowledge_id=knowledge_id, sections=list(PRESETS.get(preset, PRESETS["full"])), **updates)
