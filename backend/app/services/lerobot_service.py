from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.config import settings
from app.models.schemas import (
    DatasetListItem,
    DatasetSummary,
    EpisodeDetail,
    EpisodeListItem,
    EpisodeSeries,
    ValidationIssue,
    VideoAsset,
)


class DatasetNotFoundError(FileNotFoundError):
    pass


def _jsonable(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if not isinstance(value, (list, dict, tuple)) and pd.isna(value):
        return None
    return value


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _read_parquet(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


def _chunk_file_path(root: Path, pattern: str) -> list[Path]:
    return sorted(root.glob(pattern))


def discover_dataset_paths() -> list[Path]:
    if not settings.data_root.exists():
        return []
    return sorted(
        path
        for path in settings.data_root.iterdir()
        if path.is_dir() and (path / "meta" / "info.json").exists()
    )


def get_dataset_path(dataset_name: str) -> Path:
    candidate = (settings.data_root / dataset_name).resolve()
    data_root = settings.data_root.resolve()
    if data_root not in candidate.parents and candidate != data_root:
        raise DatasetNotFoundError(dataset_name)
    if not (candidate / "meta" / "info.json").exists():
        raise DatasetNotFoundError(dataset_name)
    return candidate


@lru_cache(maxsize=16)
def load_info(dataset_name: str) -> dict[str, Any]:
    return _read_json(get_dataset_path(dataset_name) / "meta" / "info.json")


@lru_cache(maxsize=16)
def load_stats(dataset_name: str) -> dict[str, Any]:
    path = get_dataset_path(dataset_name) / "meta" / "stats.json"
    return _read_json(path) if path.exists() else {}


@lru_cache(maxsize=16)
def load_tasks(dataset_name: str) -> list[dict[str, Any]]:
    path = get_dataset_path(dataset_name) / "meta" / "tasks.parquet"
    if not path.exists():
        return []
    df = _read_parquet(path).reset_index()
    return [_jsonable(row.dropna().to_dict()) for _, row in df.iterrows()]


@lru_cache(maxsize=16)
def load_episodes_df(dataset_name: str) -> pd.DataFrame:
    dataset = get_dataset_path(dataset_name)
    files = _chunk_file_path(dataset, "meta/episodes/chunk-*/file-*.parquet")
    if not files:
        return pd.DataFrame()
    return pd.concat([_read_parquet(path) for path in files], ignore_index=True)


@lru_cache(maxsize=8)
def load_data_df(dataset_name: str) -> pd.DataFrame:
    dataset = get_dataset_path(dataset_name)
    files = _chunk_file_path(dataset, "data/chunk-*/file-*.parquet")
    if not files:
        return pd.DataFrame()
    return pd.concat([_read_parquet(path) for path in files], ignore_index=True)


def list_datasets() -> list[DatasetListItem]:
    items: list[DatasetListItem] = []
    for path in discover_dataset_paths():
        info = _read_json(path / "meta" / "info.json")
        items.append(
            DatasetListItem(
                name=path.name,
                path=str(path),
                codebase_version=info.get("codebase_version"),
                robot_type=info.get("robot_type"),
                total_episodes=info.get("total_episodes"),
                total_frames=info.get("total_frames"),
                fps=info.get("fps"),
            )
        )
    return items


def get_summary(dataset_name: str) -> DatasetSummary:
    dataset = get_dataset_path(dataset_name)
    info = load_info(dataset_name)
    return DatasetSummary(
        name=dataset.name,
        path=str(dataset),
        codebase_version=info.get("codebase_version"),
        robot_type=info.get("robot_type"),
        total_episodes=info.get("total_episodes"),
        total_frames=info.get("total_frames"),
        total_tasks=info.get("total_tasks"),
        fps=info.get("fps"),
        features=_jsonable(info.get("features", {})),
        tasks=load_tasks(dataset_name),
        stats=_jsonable(load_stats(dataset_name)),
    )


def _optional_int(value: Any) -> int | None:
    return None if value is None or pd.isna(value) else int(value)


def _optional_float(value: Any) -> float | None:
    return None if value is None or pd.isna(value) else float(value)


def _video_assets(dataset_name: str, row: pd.Series) -> list[VideoAsset]:
    dataset = get_dataset_path(dataset_name)
    assets: list[VideoAsset] = []
    prefix = "videos/"
    keys = sorted(
        {
            column[len(prefix) :].split("/")[0]
            for column in row.index
            if column.startswith(prefix) and column.endswith("/file_index")
        }
    )
    for key in keys:
        chunk = row.get(f"videos/{key}/chunk_index")
        file_index = row.get(f"videos/{key}/file_index")
        if pd.isna(chunk) or pd.isna(file_index):
            continue
        relative = f"videos/{key}/chunk-{int(chunk):03d}/file-{int(file_index):03d}.mp4"
        relative_url = relative.replace("\\", "/")
        path = dataset / relative
        assets.append(
            VideoAsset(
                key=key,
                relative_path=relative_url,
                url=f"/media/{dataset_name}/{relative_url}",
                exists=path.exists(),
                from_timestamp=_optional_float(row.get(f"videos/{key}/from_timestamp")),
                to_timestamp=_optional_float(row.get(f"videos/{key}/to_timestamp")),
            )
        )
    return assets


def _episode_item(dataset_name: str, row: pd.Series) -> EpisodeListItem:
    return EpisodeListItem(
        episode_index=int(row["episode_index"]),
        tasks=_jsonable(row.get("tasks", [])) or [],
        length=int(row.get("length", 0)),
        dataset_from_index=_optional_int(row.get("dataset_from_index")),
        dataset_to_index=_optional_int(row.get("dataset_to_index")),
        videos=_video_assets(dataset_name, row),
    )


def list_episodes(dataset_name: str) -> list[EpisodeListItem]:
    df = load_episodes_df(dataset_name)
    if df.empty:
        return []
    return [_episode_item(dataset_name, row) for _, row in df.iterrows()]


def get_episode(dataset_name: str, episode_index: int) -> EpisodeDetail:
    df = load_episodes_df(dataset_name)
    match = df[df["episode_index"] == episode_index]
    if match.empty:
        raise DatasetNotFoundError(f"{dataset_name}/episode/{episode_index}")
    row = match.iloc[0]
    item = _episode_item(dataset_name, row)
    stats = {
        column.removeprefix("stats/"): _jsonable(row[column])
        for column in row.index
        if column.startswith("stats/")
    }
    return EpisodeDetail(**item.model_dump(), stats=stats)


def _float_list(value: Any) -> list[float]:
    value = _jsonable(value)
    return [float(item) for item in value]


def get_episode_series(dataset_name: str, episode_index: int) -> EpisodeSeries:
    info = load_info(dataset_name)
    df = load_data_df(dataset_name)
    if df.empty or "episode_index" not in df.columns:
        raise DatasetNotFoundError(f"{dataset_name}/episode/{episode_index}/series")
    episode = df[df["episode_index"] == episode_index].sort_values("frame_index")
    if episode.empty:
        raise DatasetNotFoundError(f"{dataset_name}/episode/{episode_index}/series")

    state_feature = info.get("features", {}).get("observation.state", {})
    action_feature = info.get("features", {}).get("action", {})
    return EpisodeSeries(
        episode_index=episode_index,
        timestamp=[float(value) for value in episode["timestamp"].tolist()],
        observation_state=[_float_list(value) for value in episode["observation.state"].tolist()],
        action=[_float_list(value) for value in episode["action"].tolist()],
        state_names=state_feature.get("names") or [],
        action_names=action_feature.get("names") or [],
    )


def validate_dataset(dataset_name: str) -> list[ValidationIssue]:
    dataset = get_dataset_path(dataset_name)
    issues: list[ValidationIssue] = []
    info_path = dataset / "meta" / "info.json"
    stats_path = dataset / "meta" / "stats.json"
    tasks_path = dataset / "meta" / "tasks.parquet"
    data_files = _chunk_file_path(dataset, "data/chunk-*/file-*.parquet")
    episode_files = _chunk_file_path(dataset, "meta/episodes/chunk-*/file-*.parquet")

    for path, code in [
        (info_path, "missing_info"),
        (stats_path, "missing_stats"),
        (tasks_path, "missing_tasks"),
    ]:
        if not path.exists():
            issues.append(ValidationIssue(level="error", code=code, message=f"Missing {path.name}", path=str(path)))

    if not data_files:
        issues.append(ValidationIssue(level="error", code="missing_data_parquet", message="No data parquet files found", path="data/"))
    if not episode_files:
        issues.append(ValidationIssue(level="error", code="missing_episode_parquet", message="No episode parquet files found", path="meta/episodes/"))

    if any(issue.level == "error" and issue.code == "missing_info" for issue in issues):
        return issues

    info = load_info(dataset_name)
    episodes = load_episodes_df(dataset_name)
    data = load_data_df(dataset_name)

    if not episodes.empty and "episode_index" in episodes.columns:
        indexes = sorted(int(value) for value in episodes["episode_index"].tolist())
        expected = list(range(len(indexes)))
        if indexes != expected:
            issues.append(ValidationIssue(level="warning", code="episode_index_gap", message="Episode indexes are not contiguous from 0", path="meta/episodes/"))

    expected_episodes = info.get("total_episodes")
    if expected_episodes is not None and not episodes.empty and int(expected_episodes) != len(episodes):
        issues.append(ValidationIssue(level="error", code="episode_count_mismatch", message=f"info.json reports {expected_episodes} episodes, parquet has {len(episodes)}", path="meta/info.json"))

    expected_frames = info.get("total_frames")
    if expected_frames is not None and not data.empty and int(expected_frames) != len(data):
        issues.append(ValidationIssue(level="error", code="frame_count_mismatch", message=f"info.json reports {expected_frames} frames, data parquet has {len(data)}", path="meta/info.json"))

    required_columns = {"observation.state", "action", "timestamp", "frame_index", "episode_index", "index", "task_index"}
    missing_columns = required_columns - set(data.columns)
    for column in sorted(missing_columns):
        issues.append(ValidationIssue(level="error", code="missing_data_column", message=f"Missing data column: {column}", path="data/"))

    video_features = [
        key for key, feature in info.get("features", {}).items() if feature.get("dtype") == "video"
    ]
    for feature in video_features:
        feature_dir = dataset / "videos" / feature
        files = list(feature_dir.glob("chunk-*/file-*.mp4")) if feature_dir.exists() else []
        if not files:
            issues.append(ValidationIssue(level="warning", code="missing_video_files", message=f"No mp4 files found for {feature}", path=str(feature_dir)))

    for episode in list_episodes(dataset_name):
        for video in episode.videos:
            if not video.exists:
                issues.append(ValidationIssue(level="warning", code="missing_episode_video", message=f"Episode {episode.episode_index} references missing video {video.relative_path}", path=video.relative_path))

    if not issues:
        issues.append(ValidationIssue(level="info", code="dataset_ok", message="Dataset passed first-stage validation.", path=str(dataset)))
    else:
        issues.insert(0, ValidationIssue(level="info", code="validation_complete", message=f"Validation completed with {len(issues)} finding(s).", path=str(dataset)))
    return issues


def media_file(dataset_name: str, relative_path: str) -> Path:
    dataset = get_dataset_path(dataset_name)
    path = (dataset / relative_path).resolve()
    if dataset.resolve() not in path.parents:
        raise DatasetNotFoundError(relative_path)
    if not path.exists() or not path.is_file():
        raise DatasetNotFoundError(relative_path)
    return path
