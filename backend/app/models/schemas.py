from typing import Any, Literal

from pydantic import BaseModel


class DatasetListItem(BaseModel):
    name: str
    path: str
    codebase_version: str | None = None
    robot_type: str | None = None
    total_episodes: int | None = None
    total_frames: int | None = None
    fps: float | None = None


DatasetFormat = Literal["lerobot_v21", "lerobot_v30", "raw"]


class CatalogDataset(BaseModel):
    name: str
    path: str
    format: DatasetFormat
    format_label: str
    robot_type: str | None = None
    total_episodes: int | None = None
    total_frames: int | None = None
    fps: float | None = None


class HealthResponse(BaseModel):
    status: str
    app: str


class DatasetSummary(BaseModel):
    name: str
    path: str
    codebase_version: str | None = None
    robot_type: str | None = None
    total_episodes: int | None = None
    total_frames: int | None = None
    total_tasks: int | None = None
    fps: float | None = None
    features: dict[str, Any]
    tasks: list[dict[str, Any]]
    stats: dict[str, Any]


class VideoAsset(BaseModel):
    key: str
    relative_path: str
    url: str
    exists: bool
    from_timestamp: float | None = None
    to_timestamp: float | None = None


class EpisodeListItem(BaseModel):
    episode_index: int
    tasks: list[str]
    length: int
    dataset_from_index: int | None = None
    dataset_to_index: int | None = None
    videos: list[VideoAsset]


class EpisodeDetail(EpisodeListItem):
    stats: dict[str, Any]


class EpisodeSeries(BaseModel):
    episode_index: int
    timestamp: list[float]
    observation_state: list[list[float]]
    action: list[list[float]]
    state_names: list[str]
    action_names: list[str]


class RawDatasetListItem(BaseModel):
    name: str
    path: str
    total_episodes: int
    format: str = "Pika raw"


class RawCameraStream(BaseModel):
    key: str
    relative_path: str
    frame_count: int
    fps: float | None = None
    from_timestamp: float | None = None
    to_timestamp: float | None = None


class RawEpisodeListItem(BaseModel):
    name: str
    path: str
    frame_count: int
    duration_seconds: float | None = None
    has_gripper_trigger_stop: bool
    cameras: list[RawCameraStream]


class RawEpisodeDetail(RawEpisodeListItem):
    format: str = "Pika raw"
    statistic: dict[str, Any]
    trigger_stop: dict[str, Any] | None = None


class RawDatasetSummary(BaseModel):
    name: str
    path: str
    format: str = "Pika raw"
    total_episodes: int
    total_frames: int
    total_seconds: float | None = None
    trigger_stop_episodes: int
    cameras: list[RawCameraStream]


class RawFrame(BaseModel):
    index: int
    timestamp: float
    relative_path: str
    url: str


class RawFrameList(BaseModel):
    camera: str
    frames: list[RawFrame]


class RawSeriesLine(BaseModel):
    key: str
    label: str
    timestamps: list[float]
    values: list[float | None]


class RawSeriesGroup(BaseModel):
    key: str
    label: str
    lines: list[RawSeriesLine]


class RawEpisodeSeries(BaseModel):
    episode_name: str
    groups: list[RawSeriesGroup]
