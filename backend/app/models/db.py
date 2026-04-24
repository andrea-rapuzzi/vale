from typing import Optional, TypedDict


class Channel(TypedDict):
    id: int
    url: str
    name: Optional[str]
    fetched_at: str


class Video(TypedDict):
    id: int
    channel_id: int
    youtube_id: str
    title: str
    duration_sec: Optional[int]
    upload_date: Optional[str]
    scraped_at: Optional[str]


class Chunk(TypedDict):
    id: int
    video_id: int
    chunk_index: int
    start_sec: float
    end_sec: float
    text: str


class Query(TypedDict):
    id: int
    intent: str
    model: str
    created_at: str


class Result(TypedDict):
    id: int
    query_id: int
    chunk_id: int
    score: int
    reasoning: str
    evaluated_at: str
