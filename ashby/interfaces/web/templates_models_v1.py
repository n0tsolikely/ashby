from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class TemplateDescriptorV1(BaseModel):
    template_id: str
    template_title: str
    template_version: str
    mode: Literal["meeting", "journal"]
    source: Literal["system", "user"]


class TemplateRecordV1(BaseModel):
    descriptor: TemplateDescriptorV1
    defaults: Dict[str, bool] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    template_text: str = ""


class TemplateDraftV1(BaseModel):
    persisted: bool = False
    mode: Literal["meeting", "journal"]
    template_title: str
    template_text: str
    defaults: Dict[str, bool] = Field(default_factory=dict)


class TemplateListResponseV1(BaseModel):
    items: List[TemplateDescriptorV1] = Field(default_factory=list)
    limit: int = 50
    offset: int = 0
    returned: int = 0
    total: int = 0
