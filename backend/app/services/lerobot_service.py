from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
import h5py

from app.core.config import settings
from app.models.schemas import (
    DatasetListItem,
    DatasetSummary,
    EpisodeDetail,
    EpisodeListItem,
    EpisodeSeries,
    VideoAsset,
)


class DatasetNotFoundError(FileNotFoundError):
    pass


def _jsonable(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return _jsonable(value.tolist())
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if not isinstance(value, (list, dict, tuple)) and pd.isna(value):
        return None
    return value


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def _read_parquet(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


def _chunk_file_path(root: Path, pattern: str) -> list[Path]:
    return sorted(root.glob(pattern))


def discover_dataset_paths() -> list[Path]:
    if not settings.data_root.exists():
        return []
    roots = [settings.data_root]
    outputs = settings.data_root / "outputs"
    if outputs.exists():
        roots.append(outputs)
    return sorted(
        path
        for root in roots
        for path in root.iterdir()
        if path.is_dir() and (path / "meta" / "info.json").exists()
    )


def get_dataset_path(dataset_name: str) -> Path:
    data_root = settings.data_root.resolve()
    for candidate in ((data_root / dataset_name).resolve(), (data_root / "outputs" / dataset_name).resolve()):
        if data_root in candidate.parents and (candidate / "meta" / "info.json").exists():
            return candidate
    raise DatasetNotFoundError(dataset_name)


def _is_v21_info(info: dict[str, Any]) -> bool:
    return "2.1" in str(info.get("codebase_version", "")).lower()


def _is_hdf5_info(info: dict[str, Any]) -> bool:
    return str(info.get("codebase_version", "")).lower() == "robodata_hdf5_v1"


@lru_cache(maxsize=16)
def load_info(dataset_name: str) -> dict[str, Any]:
    return _read_json(get_dataset_path(dataset_name) / "meta" / "info.json")


@lru_cache(maxsize=16)
def load_stats(dataset_name: str) -> dict[str, Any]:
    path = get_dataset_path(dataset_name) / "meta" / "stats.json"
    return _read_json(path) if path.exists() else {}


@lru_cache(maxsize=16)
def load_tasks(dataset_name: str) -> list[dict[str, Any]]:
    dataset = get_dataset_path(dataset_name)
    info = load_info(dataset_name)
    if _is_v21_info(info) or _is_hdf5_info(info):
        path = dataset / "meta" / "tasks.jsonl"
        return [_jsonable(row) for row in _read_jsonl(path)] if path.exists() else []
    path = dataset / "meta" / "tasks.parquet"
    if not path.exists():
        return []
    df = _read_parquet(path).reset_index()
    return [_jsonable(row.dropna().to_dict()) for _, row in df.iterrows()]


@lru_cache(maxsize=16)
def load_episodes_df(dataset_name: str) -> pd.DataFrame:
    dataset = get_dataset_path(dataset_name)
    info = load_info(dataset_name)
    if _is_hdf5_info(info):
        path = dataset / "meta" / "episodes.jsonl"
        rows = _read_jsonl(path) if path.exists() else []
        for row in rows:
            row["tasks"] = [row.get("task", "UR teleop")]
        return pd.DataFrame(rows)
    if _is_v21_info(info):
        path = dataset / "meta" / "episodes.jsonl"
        return pd.DataFrame(_read_jsonl(path)) if path.exists() else pd.DataFrame()
    files = _chunk_file_path(dataset, "meta/episodes/chunk-*/file-*.parquet")
    if not files:
        return pd.DataFrame()
    return pd.concat([_read_parquet(path) for path in files], ignore_index=True)


@lru_cache(maxsize=8)
def load_data_df(dataset_name: str) -> pd.DataFrame:
    dataset = get_dataset_path(dataset_name)
    info = load_info(dataset_name)
    if _is_hdf5_info(info):
        manifest = dataset / "meta" / "episodes.jsonl"
        rows: list[dict[str, Any]] = []
        for episode in _read_jsonl(manifest) if manifest.exists() else []:
            path = dataset / str(episode.get("file", ""))
            if not path.exists():
                continue
            with h5py.File(path, "r") as file:
                timestamps, states, actions = file["timestamp"][:], file["observation/state"][:], file["action"][:]
                extras = {key: file["extras"][key][:] for key in file.get("extras", {})}
                for index in range(min(len(timestamps), len(states), len(actions))):
                    row: dict[str, Any] = {"episode_index": int(episode["episode_index"]), "frame_index": index, "timestamp": float(timestamps[index]), "observation.state": states[index], "action": actions[index]}
                    row.update({key: value[index] for key, value in extras.items() if index < len(value)})
                    rows.append(row)
        return pd.DataFrame(rows)
    pattern = "data/chunk-*/episode_*.parquet" if _is_v21_info(info) else "data/chunk-*/file-*.parquet"
    files = _chunk_file_path(dataset, pattern)
    if not files:
        return pd.DataFrame()
    return pd.concat([_read_parquet(path) for path in files], ignore_index=True)


@lru_cache(maxsize=16)
def load_episode_stats(dataset_name: str) -> dict[int, dict[str, Any]]:
    dataset = get_dataset_path(dataset_name)
    info = load_info(dataset_name)
    if not _is_v21_info(info):
        return {}
    path = dataset / "meta" / "episodes_stats.jsonl"
    if not path.exists():
        return {}
    return {int(row["episode_index"]): _jsonable(row.get("stats", {})) for row in _read_jsonl(path)}


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
    info = load_info(dataset_name)
    assets: list[VideoAsset] = []
    if _is_hdf5_info(info):
        return assets
    if _is_v21_info(info):
        episode_index = int(row["episode_index"])
        chunk_size = int(info.get("chunks_size") or 1000)
        episode_chunk = episode_index // chunk_size
        video_features = [
            key for key, feature in info.get("features", {}).items() if feature.get("dtype") == "video"
        ]
        for key in sorted(video_features):
            relative = f"videos/chunk-{episode_chunk:03d}/{key}/episode_{episode_index:06d}.mp4"
            path = dataset / relative
            assets.append(
                VideoAsset(
                    key=key,
                    relative_path=relative,
                    url=f"/media/{dataset_name}/{relative}",
                    exists=path.exists(),
                )
            )
        return assets

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
    stats = load_episode_stats(dataset_name).get(episode_index)
    if stats is None:
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


def media_file(dataset_name: str, relative_path: str) -> Path:
    dataset = get_dataset_path(dataset_name)
    path = (dataset / relative_path).resolve()
    if dataset.resolve() not in path.parents:
        raise DatasetNotFoundError(relative_path)
    if not path.exists() or not path.is_file():
        raise DatasetNotFoundError(relative_path)
    return path


def _hdf5_episode_row(dataset_name: str, episode_index: int) -> dict[str, Any]:
    info = load_info(dataset_name)
    if not _is_hdf5_info(info):
        raise DatasetNotFoundError(f"{dataset_name} is not a RoboData HDF5 dataset")
    rows = _read_jsonl(get_dataset_path(dataset_name) / "meta" / "episodes.jsonl")
    for row in rows:
        if int(row.get("episode_index", -1)) == episode_index:
            return row
    raise DatasetNotFoundError(f"{dataset_name}/episode/{episode_index}")


def hdf5_frames(dataset_name: str, episode_index: int, camera: str) -> dict[str, Any]:
    row = _hdf5_episode_row(dataset_name, episode_index)
    path = get_dataset_path(dataset_name) / str(row["file"])
    with h5py.File(path, "r") as file:
        if "images" not in file or camera not in file["images"]:
            raise DatasetNotFoundError(camera)
        count = len(file["images"][camera])
        timestamps = file["timestamp"][:count]
    return {"camera": camera, "frames": [{"index": index, "timestamp": float(timestamps[index]), "relative_path": f"images/{camera}/{index}", "url": f"/hdf5-media/{dataset_name}/{episode_index}/{camera}/{index}"} for index in range(count)]}


def hdf5_frame(dataset_name: str, episode_index: int, camera: str, frame_index: int) -> Any:
    row = _hdf5_episode_row(dataset_name, episode_index)
    path = get_dataset_path(dataset_name) / str(row["file"])
    with h5py.File(path, "r") as file:
        if "images" not in file or camera not in file["images"] or frame_index < 0 or frame_index >= len(file["images"][camera]):
            raise DatasetNotFoundError(camera)
        return file["images"][camera][frame_index]
