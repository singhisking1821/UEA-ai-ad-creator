import uuid
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class AdRequest(BaseModel):
    raw_prompt: str
    ad_type: str
    state: str
    count: int
    chat_id: int


class AdScript(BaseModel):
    script_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ad_type: str
    state: str
    hook: str
    body: str
    cta: str
    full_script: str
    estimated_seconds: float
    avatar_key: str
    avatar_reasoning: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BrollClip(BaseModel):
    search_query: str
    clip_url: str
    duration_seconds: float
    description: str
    placement_hint: str


class ShotstackTrack(BaseModel):
    type: str
    asset_url: str
    start: float
    length: float
    position: str = 'center'
    opacity: float = 1.0
    fit: str = 'cover'


class ShotstackPayload(BaseModel):
    timeline_json: dict
    total_duration: float
    track_summary: str


class AdOutput(BaseModel):
    script_id: str
    ad_type: str
    state: str
    avatar_key: str
    heygen_video_url: str
    shotstack_render_url: str
    drive_url: Optional[str] = None
    render_duration_seconds: float
    created_at: datetime = Field(default_factory=datetime.utcnow)
