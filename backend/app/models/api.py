from pydantic import BaseModel, HttpUrl, field_validator
from typing import Optional


class ChannelFetchRequest(BaseModel):
    url: str


class ScrapeRequest(BaseModel):
    video_ids: list[int]

    @field_validator("video_ids")
    @classmethod
    def max_ten(cls, v: list[int]) -> list[int]:
        if len(v) > 10:
            raise ValueError("Maximum 10 videos per scrape job")
        if len(v) == 0:
            raise ValueError("At least one video required")
        return v


class QueryRequest(BaseModel):
    intent: str
    video_ids: Optional[list[int]] = None
    min_score: int = 1
    model: str = "claude-haiku-4-5-20251001"


class VideoOut(BaseModel):
    id: int
    youtube_id: str
    title: str
    duration_sec: Optional[int]
    upload_date: Optional[str]
    scraped: bool


class JobStatusOut(BaseModel):
    job_id: str
    type: str
    status: str
    completed: int
    total: int
    ref_id: Optional[int] = None
    error_json: Optional[str] = None


class ResultOut(BaseModel):
    score: int
    reasoning: str
    chunk_text: str
    start_sec: float
    end_sec: float
    youtube_id: str
    video_title: str
    youtube_url: str


class QueryOut(BaseModel):
    id: int
    intent: str
    model: str
    created_at: str
    result_count: int
