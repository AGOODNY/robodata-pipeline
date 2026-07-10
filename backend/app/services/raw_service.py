from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import h5py

from app.core.config import settings
from app.models.schemas import (
    RawCameraStream,
    RawDatasetListItem,
    RawDatasetSummary,
    RawEpisodeDetail,
    RawEpisodeListItem,
    RawEpisodeSeries,
    RawFrame,
    RawFrameList,
    RawSeriesGroup,
    RawSeriesLine,
)


class RawDatasetNotFoundError(FileNotFoundError):
    pass


RGB_CAMERAS = {
    "pikaGripperDepthCamera": Path("camera/color/pikaGripperDepthCamera"),
    "orbbecCamera": Path("camera/color/orbbecCamera"),
}

SERIES_TOPICS = {
    "joint_position": {
        "label": "Joint Position",
        "path": Path("arm/jointState/armJointState"),
        "fields": ["joint_1", "joint_2", "joint_3", "joint_4", "joint_5", "joint_6"],
        "array_key": "position",
    },
    "actual_tcp": {
        "label": "Actual TCP Pose",
        "path": Path("arm/endPose/armEndPose"),
        "fields": ["x", "y", "z", "roll", "pitch", "yaw"],
    },
    "target_tcp": {
        "label": "Target TCP Pose",
        "path": Path("arm/endPose/armTargetPose"),
        "fields": ["x", "y", "z", "roll", "pitch", "yaw"],
    },
    "gripper": {
        "label": "Gripper",
        "path": Path("gripper/encoder/pikaGripper"),
        "fields": ["angle", "distance"],
    },
}

HDF5_SERIES_PATHS = {
    "joint_position": "arm/jointStatePosition/armJointState",
    "actual_tcp": "arm/endPose/armEndPose",
    "target_tcp": "arm/endPose/armTargetPose",
}


def _raw_root() -> Path:
    return (settings.data_root / "raw").resolve()


def _ensure_inside(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        raise RawDatasetNotFoundError(str(path))
    return resolved


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        value = json.load(file)
    return _jsonable(value) if isinstance(value, dict) else {}


def _optional_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _timestamp(path: Path) -> float | None:
    try:
        return float(path.stem)
    except ValueError:
        return None


def _timestamp_files(path: Path, pattern: str) -> list[Path]:
    if not path.exists():
        return []
    files = [file for file in path.glob(pattern) if _timestamp(file) is not None]
    return sorted(files, key=lambda file: _timestamp(file) or 0.0)


def _readable_timestamp_files(path: Path, pattern: str) -> list[Path]:
    files: list[Path] = []
    for file in _timestamp_files(path, pattern):
        try:
            if file.stat().st_size > 0:
                files.append(file)
        except OSError:
            continue
    return files


def _duration_from_timestamps(files: list[Path]) -> float | None:
    if len(files) < 2:
        return None
    first = _timestamp(files[0])
    last = _timestamp(files[-1])
    if first is None or last is None:
        return None
    return max(0.0, last - first)


def _parse_statistic(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]
    result: dict[str, Any] = {"topics": {}, "configs": {}}
    section = ""
    for index, line in enumerate(lines):
        if index == 0:
            try:
                result["duration_seconds"] = float(line)
            except ValueError:
                pass
            continue
        if line.endswith(":"):
            section = line[:-1]
            continue
        parts = line.split()
        if section == "topic" and len(parts) >= 3:
            try:
                result["topics"][parts[0]] = {"count": int(parts[1]), "fps": float(parts[2])}
            except ValueError:
                continue
        elif section == "config" and len(parts) >= 2:
            try:
                result["configs"][parts[0]] = int(parts[1])
            except ValueError:
                continue
    return result


def _camera_stream(episode: Path, key: str, relative: Path, statistic: dict[str, Any]) -> RawCameraStream:
    topic = relative.as_posix()
    topic_stats = statistic.get("topics", {}).get(topic, {})
    recorded_count = topic_stats.get("count")
    if isinstance(recorded_count, int):
        return RawCameraStream(
            key=key,
            relative_path=topic,
            frame_count=recorded_count,
            fps=topic_stats.get("fps"),
        )

    files = _readable_timestamp_files(episode / relative, "*.jpg")
    return RawCameraStream(
        key=key,
        relative_path=topic,
        frame_count=len(files),
        fps=topic_stats.get("fps"),
        from_timestamp=_timestamp(files[0]) if files else None,
        to_timestamp=_timestamp(files[-1]) if files else None,
    )


def _episode_item(dataset_name: str, episode: Path) -> RawEpisodeListItem:
    statistic = _parse_statistic(episode / "statistic.txt")
    cameras = [_camera_stream(episode, key, relative, statistic) for key, relative in RGB_CAMERAS.items()]
    frame_count = max((camera.frame_count for camera in cameras), default=0)
    duration = statistic.get("duration_seconds")
    if duration is None:
        durations = [
            _duration_from_timestamps(_timestamp_files(episode / relative, "*.jpg"))
            for relative in RGB_CAMERAS.values()
        ]
        duration = max((value for value in durations if value is not None), default=None)
    return RawEpisodeListItem(
        name=episode.name,
        path=str(episode),
        frame_count=frame_count,
        duration_seconds=duration,
        has_gripper_trigger_stop=(episode / "gripper_trigger_stop.json").exists(),
        cameras=cameras,
    )


def discover_raw_dataset_paths() -> list[Path]:
    root = _raw_root()
    if not root.exists():
        return []
    return sorted(path for path in root.iterdir() if path.is_dir())


def get_raw_dataset_path(raw_name: str) -> Path:
    root = _raw_root()
    candidate = _ensure_inside(root / raw_name, root)
    if not candidate.exists() or not candidate.is_dir():
        raise RawDatasetNotFoundError(raw_name)
    return candidate


def get_raw_episode_path(raw_name: str, episode_name: str) -> Path:
    dataset = get_raw_dataset_path(raw_name)
    candidate = _ensure_inside(dataset / episode_name, dataset)
    if not candidate.exists() or not candidate.is_dir() or not candidate.name.startswith("episode_"):
        raise RawDatasetNotFoundError(f"{raw_name}/{episode_name}")
    return candidate


def list_raw_datasets() -> list[RawDatasetListItem]:
    items: list[RawDatasetListItem] = []
    for path in discover_raw_dataset_paths():
        episode_count = len([episode for episode in path.iterdir() if episode.is_dir() and episode.name.startswith("episode_")])
        items.append(RawDatasetListItem(name=path.name, path=str(path), total_episodes=episode_count))
    return items


def list_raw_episodes(raw_name: str) -> list[RawEpisodeListItem]:
    dataset = get_raw_dataset_path(raw_name)
    episodes = sorted(path for path in dataset.iterdir() if path.is_dir() and path.name.startswith("episode_"))
    return [_episode_item(raw_name, episode) for episode in episodes]


def get_raw_summary(raw_name: str) -> RawDatasetSummary:
    dataset = get_raw_dataset_path(raw_name)
    episodes = list_raw_episodes(raw_name)
    total_seconds_values = [episode.duration_seconds for episode in episodes if episode.duration_seconds is not None]
    camera_totals: dict[str, RawCameraStream] = {}
    for episode in episodes:
        for camera in episode.cameras:
            current = camera_totals.get(camera.key)
            if current is None:
                camera_totals[camera.key] = RawCameraStream(
                    key=camera.key,
                    relative_path=camera.relative_path,
                    frame_count=camera.frame_count,
                    fps=camera.fps,
                    from_timestamp=camera.from_timestamp,
                    to_timestamp=camera.to_timestamp,
                )
                continue
            current.frame_count += camera.frame_count
            timestamps = [value for value in [current.from_timestamp, camera.from_timestamp] if value is not None]
            current.from_timestamp = min(timestamps) if timestamps else None
            timestamps = [value for value in [current.to_timestamp, camera.to_timestamp] if value is not None]
            current.to_timestamp = max(timestamps) if timestamps else None
    return RawDatasetSummary(
        name=dataset.name,
        path=str(dataset),
        total_episodes=len(episodes),
        total_frames=sum(episode.frame_count for episode in episodes),
        total_seconds=sum(total_seconds_values) if total_seconds_values else None,
        trigger_stop_episodes=sum(1 for episode in episodes if episode.has_gripper_trigger_stop),
        cameras=sorted(camera_totals.values(), key=lambda camera: camera.key),
    )


def get_raw_episode(raw_name: str, episode_name: str) -> RawEpisodeDetail:
    episode = get_raw_episode_path(raw_name, episode_name)
    item = _episode_item(raw_name, episode)
    trigger_path = episode / "gripper_trigger_stop.json"
    return RawEpisodeDetail(
        **item.model_dump(),
        statistic=_parse_statistic(episode / "statistic.txt"),
        trigger_stop=_read_json(trigger_path) if trigger_path.exists() else None,
    )


def get_raw_frames(raw_name: str, episode_name: str, camera: str) -> RawFrameList:
    episode = get_raw_episode_path(raw_name, episode_name)
    relative = RGB_CAMERAS.get(camera)
    if relative is None:
        raise RawDatasetNotFoundError(camera)
    frames: list[RawFrame] = []
    for index, file in enumerate(_readable_timestamp_files(episode / relative, "*.jpg")):
        relative_path = file.relative_to(episode).as_posix()
        frames.append(
            RawFrame(
                index=index,
                timestamp=float(file.stem),
                relative_path=relative_path,
                url=f"/raw-media/{raw_name}/{episode_name}/{relative_path}",
            )
        )
    return RawFrameList(camera=camera, frames=frames)


def _series_group(episode: Path, key: str, config: dict[str, Any]) -> RawSeriesGroup:
    files = _timestamp_files(episode / config["path"], "*.json")
    timestamps: list[float] = []
    values_by_field: dict[str, list[float | None]] = {field: [] for field in config["fields"]}
    for file in files:
        timestamp = _timestamp(file)
        if timestamp is None:
            continue
        try:
            data = _read_json(file)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not data:
            continue
        timestamps.append(timestamp)
        array_key = config.get("array_key")
        if array_key:
            values = data.get(array_key) or []
            for index, field in enumerate(config["fields"]):
                values_by_field[field].append(_optional_float(values[index]) if index < len(values) else None)
        else:
            for field in config["fields"]:
                values_by_field[field].append(_optional_float(data.get(field)))
    lines = [
        RawSeriesLine(key=f"{key}.{field}", label=field, timestamps=timestamps, values=values)
        for field, values in values_by_field.items()
    ]
    if not timestamps:
        return _hdf5_series_group(episode, key, config)
    return RawSeriesGroup(key=key, label=config["label"], lines=lines)


def _hdf5_timestamps(file: h5py.File, count: int) -> list[float]:
    if count <= 0 or "timestamp" not in file:
        return []
    source = file["timestamp"]
    if len(source) == 0:
        return []
    start = _optional_float(source[0])
    end = _optional_float(source[-1])
    if start is None or end is None:
        return []
    if count == 1:
        return [start]
    step = (end - start) / (count - 1)
    return [start + step * index for index in range(count)]


def _hdf5_series_group(episode: Path, key: str, config: dict[str, Any]) -> RawSeriesGroup:
    empty = RawSeriesGroup(
        key=key,
        label=config["label"],
        lines=[RawSeriesLine(key=f"{key}.{field}", label=field, timestamps=[], values=[]) for field in config["fields"]],
    )
    path = episode / "data.hdf5"
    if not path.exists():
        return empty
    try:
        with h5py.File(path, "r") as file:
            if key == "gripper":
                angle_path = "gripper/encoderAngle/pikaGripper"
                distance_path = "gripper/encoderDistance/pikaGripper"
                if angle_path not in file or distance_path not in file:
                    return empty
                count = min(len(file[angle_path]), len(file[distance_path]))
                rows = [(file[angle_path][index], file[distance_path][index]) for index in range(count)]
            else:
                dataset_path = HDF5_SERIES_PATHS.get(key)
                if dataset_path is None or dataset_path not in file:
                    return empty
                source = file[dataset_path]
                count = len(source)
                rows = [source[index] for index in range(count)]
            timestamps = _hdf5_timestamps(file, count)
    except (OSError, ValueError):
        return empty

    if not timestamps:
        return empty
    values_by_field = {field: [] for field in config["fields"]}
    for row in rows:
        for index, field in enumerate(config["fields"]):
            values_by_field[field].append(_optional_float(row[index]) if index < len(row) else None)
    return RawSeriesGroup(
        key=key,
        label=config["label"],
        lines=[
            RawSeriesLine(key=f"{key}.{field}", label=field, timestamps=timestamps, values=values)
            for field, values in values_by_field.items()
        ],
    )


def get_raw_series(raw_name: str, episode_name: str) -> RawEpisodeSeries:
    episode = get_raw_episode_path(raw_name, episode_name)
    groups = [_series_group(episode, key, config) for key, config in SERIES_TOPICS.items()]
    return RawEpisodeSeries(episode_name=episode_name, groups=groups)


def raw_media_file(raw_name: str, episode_name: str, relative_path: str) -> Path:
    episode = get_raw_episode_path(raw_name, episode_name)
    path = _ensure_inside(episode / relative_path, episode)
    if not path.exists() or not path.is_file():
        raise RawDatasetNotFoundError(relative_path)
    return path
