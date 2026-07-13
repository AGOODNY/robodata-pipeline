"""Safe, local dataset conversion primitives used by the Converter UI.

The converter never edits source data.  It first materialises a small, explicit
intermediate representation and writes to a sibling temporary directory.  This
keeps Raw, LeRobot and HDF5 conversion semantics in one place.
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator

import h5py
import numpy as np
import pandas as pd

from app.core.config import settings
from app.models.schemas import (
    ConversionCreateRequest, ConversionJob, ConversionPreflight,
    ConversionPreflightEpisode, ConverterOptions,
)
from app.services import lerobot_service, raw_service


class ConversionError(ValueError):
    pass


@dataclass
class NormalizedEpisode:
    name: str
    task: str
    timestamps: np.ndarray
    state: np.ndarray
    action: np.ndarray
    state_names: list[str]
    action_names: list[str]
    images: dict[str, np.ndarray] = field(default_factory=dict)
    extras: dict[str, np.ndarray] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)


def _json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    return value if isinstance(value, dict) else {}


def _timestamp_files(path: Path, suffix: str) -> list[tuple[float, Path]]:
    if not path.exists():
        return []
    result: list[tuple[float, Path]] = []
    # scandir avoids creating thousands of Path objects while the preflight
    # checks a large Raw capture directory.
    with os.scandir(path) as entries:
        for item in entries:
            if not item.is_file() or not item.name.endswith(suffix):
                continue
            try:
                if item.stat().st_size:
                    result.append((float(Path(item.name).stem), Path(item.path)))
            except (OSError, ValueError):
                continue
    return sorted(result)


def _raw_reference_files(episode: Path) -> list[tuple[float, Path]]:
    color_root = episode / "camera" / "color"
    preferred = _timestamp_files(color_root / "pikaGripperDepthCamera", ".jpg")
    if preferred or not color_root.exists():
        return preferred
    for camera in sorted(path for path in color_root.iterdir() if path.is_dir()):
        files = _timestamp_files(camera, ".jpg")
        if files:
            return files
    return []


def _raw_synchronized_frame_count(
    episode: Path,
    reference: list[tuple[float, Path]],
    cutoff: float | None,
    options: ConverterOptions,
) -> int:
    """Count usable Raw rows without decoding images or JSON payloads.

    This deliberately mirrors _load_raw_episode's timestamp requirements, so
    preflight totals cannot promise frames that the converter later skips.
    """
    joint = _timestamp_files(episode / "arm/jointState/armJointState", ".json")
    gripper = _timestamp_files(episode / "gripper/encoder/pikaGripper", ".json")
    tcp = _timestamp_files(episode / "arm/endPose/armEndPose", ".json") if options.action_type == "tcp" else []
    target = _timestamp_files(episode / "arm/endPose/armTargetPose", ".json") if options.action_type == "tcp" and options.tcp_action_source == "target" else []
    count = 0
    for timestamp, _ in reference:
        if cutoff is not None and timestamp > cutoff:
            continue
        if not _nearest(joint, timestamp) or not _nearest(gripper, timestamp):
            continue
        if options.action_type == "tcp" and not _nearest(tcp, timestamp):
            continue
        if options.action_type == "tcp" and options.tcp_action_source == "target" and not _nearest(target, timestamp):
            continue
        count += 1
    return count


def _nearest(items: list[tuple[float, Path]], target: float, limit: float = 0.03) -> Path | None:
    if not items:
        return None
    stamps = [item[0] for item in items]
    index = int(np.searchsorted(stamps, target))
    candidates = [item for item in (items[max(0, index - 1): index + 1]) if item]
    if not candidates:
        return None
    _, path = min(candidates, key=lambda item: abs(item[0] - target))
    return path if abs(float(path.stem) - target) <= limit else None


def _read_rgb(path: Path) -> np.ndarray:
    try:
        from PIL import Image
    except ImportError as error:  # pragma: no cover - dependency preflight reports this
        raise ConversionError("Pillow is required for image conversion. Install backend requirements.") from error
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"), dtype=np.uint8)


def _task_from_raw(episode: Path, override: str) -> str:
    if override:
        return override
    for candidate in (episode / "instructions.json", episode.parent / "instructions.json"):
        if candidate.exists():
            data = _json(candidate)
            value = data.get(episode.name, data.get(episode.parent.name, data.get("instruction", data.get("task", ""))))
            if isinstance(value, str) and value:
                return value
    name = episode.parent.name.replace("_", " ")
    for word in ("place", "pick", "put", "into", "drawer", "box", "cube", "blue", "red", "green"):
        name = name.replace(word, f" {word} ")
    return " ".join(name.split()) or "UR teleop"


def _raw_episode_paths(name: str) -> list[Path]:
    root = raw_service.get_raw_dataset_path(name)
    return sorted(path for path in root.iterdir() if path.is_dir() and path.name.startswith("episode_"))


def _raw_cutoff(episode: Path, options: ConverterOptions) -> float | None:
    marker = episode / "gripper_trigger_stop.json"
    if not options.trim_trigger_tail or not marker.exists():
        return None
    value = raw_service._optional_float(_json(marker).get("stop_timestamp"))
    return value - options.trim_tail_seconds if value is not None else None


def _raw_camera_files(episode: Path) -> dict[str, list[tuple[float, Path]]]:
    root = episode / "camera" / "color"
    if not root.exists():
        return {}
    result: dict[str, list[tuple[float, Path]]] = {}
    for camera in root.iterdir():
        if not camera.is_dir():
            continue
        files = _timestamp_files(camera, ".jpg")
        if files:
            result[camera.name] = files
    return result


def preflight(request: ConversionCreateRequest) -> ConversionPreflight:
    if request.source_format == request.target_format:
        raise ConversionError("Source and target formats must be different")
    options = request.options
    if request.source_format == "raw":
        rows: list[ConversionPreflightEpisode] = []
        trigger_count = 0
        for episode in _raw_episode_paths(request.source_name):
            reference = _raw_reference_files(episode)
            cutoff = _raw_cutoff(episode, options)
            source_count = len(reference)
            post_trim_count = len([item for item in reference if cutoff is None or item[0] <= cutoff])
            synchronized_count = _raw_synchronized_frame_count(episode, reference, cutoff, options) if reference else 0
            output_count = max(0, synchronized_count - 1)
            trimmed = source_count - post_trim_count
            warnings: list[str] = []
            valid = bool(reference)
            if not reference:
                warnings.append("No readable RGB camera frames")
            if synchronized_count < 2:
                valid = False
                warnings.append("Fewer than two synchronized RGB/robot frames remain after cleaning")
            if cutoff is not None:
                trigger_count += 1
            rows.append(ConversionPreflightEpisode(name=episode.name, source_frames=source_count, output_frames=max(0, output_count - 1), trimmed_frames=trimmed, warnings=warnings, valid=valid))
        return ConversionPreflight(
            source_name=request.source_name, source_format="raw", target_format=request.target_format,
            total_episodes=len(rows), valid_episodes=sum(row.valid for row in rows),
            total_output_frames=sum(row.output_frames for row in rows if row.valid),
            trim_trigger_episodes=trigger_count, encoder_available=_encoder_available() if request.target_format != "hdf5" else True,
            episodes=rows,
        )
    episodes = _load_dataset_episodes(request.source_name, request.source_format, load_images=False)
    rows = [ConversionPreflightEpisode(name=episode.name, source_frames=len(episode.timestamps), output_frames=len(episode.timestamps), valid=len(episode.timestamps) > 0) for episode in episodes]
    return ConversionPreflight(
        source_name=request.source_name, source_format=request.source_format, target_format=request.target_format,
        total_episodes=len(rows), valid_episodes=sum(row.valid for row in rows),
        total_output_frames=sum(row.output_frames for row in rows),
        encoder_available=_encoder_available() if request.target_format != "hdf5" else True, episodes=rows,
    )


def _load_raw_episode(path: Path, options: ConverterOptions) -> NormalizedEpisode:
    cameras = _raw_camera_files(path)
    reference_name = "pikaGripperDepthCamera" if "pikaGripperDepthCamera" in cameras else next(iter(cameras), "")
    reference = cameras.get(reference_name, [])
    cutoff = _raw_cutoff(path, options)
    joint = _timestamp_files(path / "arm/jointState/armJointState", ".json")
    actual_tcp = _timestamp_files(path / "arm/endPose/armEndPose", ".json")
    target_tcp = _timestamp_files(path / "arm/endPose/armTargetPose", ".json")
    gripper = _timestamp_files(path / "gripper/encoder/pikaGripper", ".json")
    rows: list[dict[str, Any]] = []
    for stamp, image_path in reference:
        if cutoff is not None and stamp > cutoff:
            continue
        joint_path, gripper_path = _nearest(joint, stamp), _nearest(gripper, stamp)
        tcp_path = _nearest(actual_tcp, stamp)
        target_path = _nearest(target_tcp, stamp)
        required = [joint_path, gripper_path]
        if options.action_type in ("tcp", "all"):
            required.append(tcp_path)
        if options.action_type == "tcp" and options.tcp_action_source == "target":
            required.append(target_path)
        if not all(required):
            continue
        joint_value = np.asarray(_json(joint_path).get("position", []), dtype=np.float32)
        grip_value = raw_service._optional_float(_json(gripper_path).get("angle"))
        if joint_value.shape != (6,) or grip_value is None:
            continue
        row: dict[str, Any] = {"timestamp": stamp, "joint": joint_value, "gripper": float(grip_value), "images": {reference_name: _read_rgb(image_path)}}
        for name, files in cameras.items():
            if name == reference_name:
                continue
            camera_path = _nearest(files, stamp)
            if camera_path:
                row["images"][name] = _read_rgb(camera_path)
        for key, source in (("tcp", tcp_path), ("target", target_path)):
            if source:
                item = _json(source)
                vector = np.asarray([item.get(field) for field in ("x", "y", "z", "roll", "pitch", "yaw")], dtype=np.float32)
                if vector.shape == (6,) and np.isfinite(vector).all():
                    row[key] = vector
        rows.append(row)
    if len(rows) < 2:
        raise ConversionError(f"{path.name}: no synchronized frame pairs")
    images = {name: np.stack([row["images"].get(name, np.zeros_like(rows[0]["images"][reference_name])) for row in rows[:-1]]) for name in cameras}
    if options.action_type == "tcp":
        state = np.stack([np.r_[row["tcp"], row["gripper"]] for row in rows[:-1]])
        action_key = "target" if options.tcp_action_source == "target" else "tcp"
        action = np.stack([np.r_[row[action_key], row["gripper"]] for row in rows[1:]])
        names = ["x", "y", "z", "roll", "pitch", "yaw", "gripper"]
        extras: dict[str, np.ndarray] = {}
    else:
        state = np.stack([np.r_[row["joint"], row["gripper"]] for row in rows[:-1]])
        action = np.stack([np.r_[row["joint"], row["gripper"]] for row in rows[1:]])
        names = ["shoulder_pan", "shoulder_lift", "elbow", "wrist_1", "wrist_2", "wrist_3", "gripper"]
        extras = {"observation.state.tcp": np.stack([row["tcp"] for row in rows[:-1]])} if options.action_type == "all" else {}
    return NormalizedEpisode(
        name=path.name, task=_task_from_raw(path, options.instruction), timestamps=np.asarray([row["timestamp"] for row in rows[:-1]], dtype=np.float64),
        state=state.astype(np.float32), action=action.astype(np.float32), state_names=names, action_names=names,
        images=images, extras=extras,
        provenance={"source_episode": str(path), "trimmed_trigger_tail": cutoff is not None, "trim_cutoff": cutoff, "action_type": options.action_type},
    )


def _load_hdf5_episodes(name: str, on_episode: Callable[[int, int], None] | None = None) -> list[NormalizedEpisode]:
    root = lerobot_service.get_dataset_path(name)
    rows = [json.loads(line) for line in (root / "meta/episodes.jsonl").read_text(encoding="utf-8").splitlines() if line]
    result: list[NormalizedEpisode] = []
    completed = 0
    for row in rows:
        path = root / row["file"]
        with h5py.File(path, "r") as file:
            images = {key: file["images"][key][:] for key in file.get("images", {})}
            extras = {key: file["extras"][key][:] for key in file.get("extras", {})}
            result.append(NormalizedEpisode(name=row["episode_name"], task=row["task"], timestamps=file["timestamp"][:], state=file["observation/state"][:], action=file["action"][:], state_names=row["state_names"], action_names=row["action_names"], images=images, extras=extras, provenance=row.get("provenance", {})))
        completed += len(result[-1].timestamps)
        if on_episode:
            on_episode(len(result), completed)
    return result


def _load_dataset_episodes(name: str, source_format: str, load_images: bool, on_episode: Callable[[int, int], None] | None = None) -> list[NormalizedEpisode]:
    if source_format == "hdf5":
        return _load_hdf5_episodes(name, on_episode)
    info = lerobot_service.load_info(name)
    data = lerobot_service.load_data_df(name)
    if data.empty:
        raise ConversionError("No LeRobot data frames found")
    state_names = info.get("features", {}).get("observation.state", {}).get("names") or []
    action_names = info.get("features", {}).get("action", {}).get("names") or []
    episodes: list[NormalizedEpisode] = []
    completed = 0
    for episode_index, frame_data in data.groupby("episode_index", sort=True):
        frame_data = frame_data.sort_values("frame_index")
        detail = lerobot_service.get_episode(name, int(episode_index))
        task = detail.tasks[0] if detail.tasks else "UR teleop"
        images: dict[str, np.ndarray] = {}
        if load_images:
            for video in detail.videos:
                frames = _decode_video(lerobot_service.get_dataset_path(name) / video.relative_path, len(frame_data), video.from_timestamp)
                if frames:
                    images[video.key.removeprefix("observation.images.")] = np.stack(frames)
        extras = {column: np.stack(frame_data[column].map(np.asarray).to_list()).astype(np.float32) for column in frame_data.columns if column not in {"observation.state", "action", "timestamp", "frame_index", "episode_index", "index", "task_index"} and not column.startswith("videos/")}
        episodes.append(NormalizedEpisode(name=f"episode_{int(episode_index):06d}", task=task, timestamps=frame_data["timestamp"].to_numpy(dtype=np.float64), state=np.stack(frame_data["observation.state"].map(np.asarray).to_list()).astype(np.float32), action=np.stack(frame_data["action"].map(np.asarray).to_list()).astype(np.float32), state_names=state_names, action_names=action_names, images=images, extras=extras, provenance={"source_dataset": name, "source_episode_index": int(episode_index)}))
        completed += len(frame_data)
        if on_episode:
            on_episode(len(episodes), completed)
    return episodes


def _encoder_available() -> bool:
    try:
        import av  # noqa: F401
        return True
    except ImportError:
        return False


def _decode_video(path: Path, expected: int, start: float | None, on_frame: Callable[[int], None] | None = None) -> list[np.ndarray]:
    if not _encoder_available() or not path.exists():
        return []
    import av
    result: list[np.ndarray] = []
    with av.open(path) as container:
        if start is not None:
            try:
                container.seek(int(start * av.time_base), any_frame=False, backward=True)
            except (ValueError, OSError):
                pass
        for frame in container.decode(video=0):
            result.append(frame.to_ndarray(format="rgb24"))
            if on_frame and (len(result) % 30 == 0 or len(result) == expected):
                on_frame(len(result))
            if len(result) >= expected:
                break
    if on_frame:
        on_frame(len(result))
    return result


def _decode_video_segment(path: Path, expected: int, start: float) -> list[np.ndarray]:
    """Decode exactly one v3 episode from a shared video file."""
    if not _encoder_available() or not path.exists():
        return []
    import av
    result: list[np.ndarray] = []
    with av.open(path) as container:
        try:
            container.seek(int(start * av.time_base), any_frame=False, backward=True)
        except (ValueError, OSError):
            pass
        for frame in container.decode(video=0):
            if frame.time is not None and float(frame.time) < start - 1 / 60:
                continue
            result.append(frame.to_ndarray(format="rgb24"))
            if len(result) >= expected:
                break
    return result


_HDF5_IMAGE_BATCH_SIZE = 16
_HDF5_IMAGE_COMPRESSION = "lzf"
_HDF5_VIDEO_DECODE_THREADS = min(4, max(1, (os.cpu_count() or 2) // 2))


def _video_frame_size(path: Path) -> tuple[int, int]:
    """Return a video's dimensions without decoding its frames."""
    if not _encoder_available() or not path.exists():
        raise ConversionError(f"Video is unavailable: {path}")
    import av

    with av.open(path) as container:
        stream = container.streams.video[0]
        if not stream.width or not stream.height:
            raise ConversionError(f"Video has no usable dimensions: {path}")
        return int(stream.height), int(stream.width)


def _decode_video_batches(
    path: Path,
    expected: int,
    start: float | None = None,
    on_frame: Callable[[int], None] | None = None,
) -> Iterator[np.ndarray]:
    """Yield small RGB batches so HDF5 exports do not retain an episode in RAM."""
    if not _encoder_available() or not path.exists():
        return
    import av

    batch: list[np.ndarray] = []
    decoded = 0
    with av.open(path) as container:
        # PyAV/FFmpeg otherwise auto-selects enough workers to saturate a
        # laptop CPU.  Conversion is a background job, so leave cores free for
        # the UI and the rest of the system.
        container.streams.video[0].thread_count = _HDF5_VIDEO_DECODE_THREADS
        if start is not None and start > 0:
            try:
                container.seek(int(start * av.time_base), any_frame=False, backward=True)
            except (ValueError, OSError):
                pass
        for frame in container.decode(video=0):
            if start is not None and frame.time is not None and float(frame.time) < start - 1 / 60:
                continue
            batch.append(frame.to_ndarray(format="rgb24"))
            decoded += 1
            if len(batch) == _HDF5_IMAGE_BATCH_SIZE:
                yield np.stack(batch)
                batch.clear()
            if on_frame and (decoded % 30 == 0 or decoded == expected):
                on_frame(decoded)
            if decoded >= expected:
                break
    if batch:
        yield np.stack(batch)
    if on_frame and decoded % 30:
        on_frame(decoded)


def _create_hdf5_image_dataset(
    group: h5py.Group,
    camera: str,
    count: int,
    height: int,
    width: int,
) -> h5py.Dataset:
    """Create a lossless, fast-to-write RGB dataset with batch-aligned chunks."""
    return group.create_dataset(
        camera,
        shape=(count, height, width, 3),
        dtype=np.uint8,
        compression=_HDF5_IMAGE_COMPRESSION,
        chunks=(min(_HDF5_IMAGE_BATCH_SIZE, count), height, width, 3),
    )


def _write_hdf5(root: Path, episodes: list[NormalizedEpisode], request: ConversionCreateRequest, progress: Callable[[int, int], None]) -> None:
    (root / "meta").mkdir(parents=True)
    (root / "episodes").mkdir()
    image_features = {f"observation.images.{key}": {"dtype": "image", "shape": [3, int(value.shape[1]), int(value.shape[2])], "names": ["channels", "height", "width"]} for key, value in episodes[0].images.items()}
    info = {"codebase_version": "hdf5_v1", "format": "HDF5 v1", "robot_type": "ur5_pika", "fps": request.options.fps, "total_episodes": len(episodes), "total_frames": int(sum(len(item.timestamps) for item in episodes)), "features": {"observation.state": {"dtype": "float32", "names": episodes[0].state_names}, "action": {"dtype": "float32", "names": episodes[0].action_names}, **image_features}, "source_format": request.source_format}
    (root / "meta/info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    episode_rows: list[dict[str, Any]] = []
    tasks: dict[str, int] = {}
    done = 0
    for index, episode in enumerate(episodes):
        relative = f"episodes/episode_{index:06d}.hdf5"
        with h5py.File(root / relative, "w") as file:
            file.create_dataset("timestamp", data=episode.timestamps)
            file.create_dataset("frame_index", data=np.arange(len(episode.timestamps), dtype=np.int64))
            file.create_dataset("observation/state", data=episode.state, compression="gzip")
            file.create_dataset("action", data=episode.action, compression="gzip")
            images = file.create_group("images")
            for key, values in episode.images.items():
                images.create_dataset(
                    key,
                    data=values,
                    compression=_HDF5_IMAGE_COMPRESSION,
                    chunks=(min(_HDF5_IMAGE_BATCH_SIZE, len(values)), *values.shape[1:]),
                )
            extras = file.create_group("extras")
            for key, values in episode.extras.items():
                extras.create_dataset(key, data=values, compression="gzip")
        tasks.setdefault(episode.task, len(tasks))
        episode_rows.append({"episode_index": index, "episode_name": episode.name, "file": relative, "task": episode.task, "length": len(episode.timestamps), "state_names": episode.state_names, "action_names": episode.action_names, "provenance": episode.provenance})
        done += len(episode.timestamps); progress(index + 1, done)
    (root / "meta/episodes.jsonl").write_text("".join(json.dumps(row) + "\n" for row in episode_rows), encoding="utf-8")
    (root / "meta/tasks.jsonl").write_text("".join(json.dumps({"task_index": index, "task": task}) + "\n" for task, index in tasks.items()), encoding="utf-8")


def _stream_lerobot_to_hdf5(
    root: Path,
    source_name: str,
    request: ConversionCreateRequest,
    progress: Callable[[int, int], None],
    media_progress: Callable[[int, int], None],
) -> None:
    """Convert LeRobot to HDF5 one episode and one small RGB batch at a time."""
    source = lerobot_service.get_dataset_path(source_name)
    source_info = lerobot_service.load_info(source_name)
    episodes_df = lerobot_service.load_episodes_df(source_name).sort_values("episode_index")
    data_df = lerobot_service.load_data_df(source_name)
    if episodes_df.empty or data_df.empty:
        raise ConversionError("The LeRobot source has no episodes or data frames")
    (root / "meta").mkdir(parents=True)
    (root / "episodes").mkdir()
    state_feature = source_info.get("features", {}).get("observation.state", {})
    action_feature = source_info.get("features", {}).get("action", {})
    episode_rows: list[dict[str, Any]] = []
    tasks: dict[str, int] = {}
    image_features: dict[str, Any] = {}
    completed_frames = 0
    for output_index, (_, row) in enumerate(episodes_df.iterrows()):
        source_index = int(row["episode_index"])
        frames_df = data_df[data_df["episode_index"] == source_index].copy().sort_values("frame_index")
        count = len(frames_df)
        if not count:
            raise ConversionError(f"Episode {source_index} has no data rows")
        detail = lerobot_service.get_episode(source_name, source_index)
        task = detail.tasks[0] if detail.tasks else "UR teleop"
        relative = f"episodes/episode_{output_index:06d}.hdf5"
        with h5py.File(root / relative, "w") as file:
            file.create_dataset("timestamp", data=frames_df["timestamp"].to_numpy(dtype=np.float64))
            file.create_dataset("frame_index", data=np.arange(count, dtype=np.int64))
            file.create_dataset("observation/state", data=np.stack(frames_df["observation.state"].map(np.asarray).to_list()).astype(np.float32), compression="gzip")
            file.create_dataset("action", data=np.stack(frames_df["action"].map(np.asarray).to_list()).astype(np.float32), compression="gzip")
            image_group = file.create_group("images")
            video_count = len(detail.videos)
            for video_number, video in enumerate(detail.videos):
                path = source / video.relative_path
                height, width = _video_frame_size(path)
                camera = video.key.removeprefix("observation.images.")
                dataset = _create_hdf5_image_dataset(image_group, camera, count, height, width)
                image_features[f"observation.images.{camera}"] = {"dtype": "image", "shape": [3, height, width], "names": ["channels", "height", "width"]}
                callback = lambda loaded, base=completed_frames, index=output_index, camera_index=video_number: media_progress(
                    index + 1,
                    base + int((camera_index * count + loaded) / video_count),
                )
                written = 0
                for batch in _decode_video_batches(path, count, video.from_timestamp, callback):
                    next_written = written + len(batch)
                    dataset[written:next_written] = batch
                    written = next_written
                if written != count:
                    raise ConversionError(f"Could not decode all frames for episode {source_index}, camera {video.key}")
            extras = file.create_group("extras")
            excluded = {"observation.state", "action", "timestamp", "frame_index", "episode_index", "index", "task_index"}
            for column in frames_df.columns:
                if column in excluded or column.startswith("videos/"):
                    continue
                values = np.stack(frames_df[column].map(np.asarray).to_list()).astype(np.float32)
                extras.create_dataset(column, data=values, compression="gzip")
        tasks.setdefault(task, len(tasks))
        episode_rows.append({"episode_index": output_index, "episode_name": f"episode_{source_index:06d}", "file": relative, "task": task, "length": count, "state_names": state_feature.get("names") or [], "action_names": action_feature.get("names") or [], "provenance": {"source_dataset": source_name, "source_episode_index": source_index}})
        completed_frames += count
        progress(output_index + 1, completed_frames)
    info = {"codebase_version": "hdf5_v1", "format": "HDF5 v1", "robot_type": source_info.get("robot_type"), "fps": source_info.get("fps"), "total_episodes": len(episode_rows), "total_frames": completed_frames, "features": {"observation.state": state_feature, "action": action_feature, **image_features}, "source_format": request.source_format}
    (root / "meta/info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    (root / "meta/episodes.jsonl").write_text("".join(json.dumps(row) + "\n" for row in episode_rows), encoding="utf-8")
    (root / "meta/tasks.jsonl").write_text("".join(json.dumps({"task_index": index, "task": task}) + "\n" for task, index in tasks.items()), encoding="utf-8")


def _encode_video(path: Path, frames: np.ndarray, fps: int) -> None:
    if not _encoder_available():
        raise ConversionError("PyAV video encoder unavailable. Install backend requirements before exporting LeRobot.")
    import av
    path.parent.mkdir(parents=True, exist_ok=True)
    with av.open(path, "w") as container:
        stream = container.add_stream("h264", rate=fps)
        stream.pix_fmt = "yuv420p"
        stream.width, stream.height = int(frames.shape[2]), int(frames.shape[1])
        for image in frames:
            for packet in stream.encode(av.VideoFrame.from_ndarray(image, format="rgb24")):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)


def _write_lerobot(root: Path, episodes: list[NormalizedEpisode], request: ConversionCreateRequest, progress: Callable[[int, int], None]) -> None:
    if not _encoder_available():
        raise ConversionError("LeRobot export needs PyAV. Install backend requirements and restart the backend.")
    version = "v2.1" if request.target_format == "lerobot_v21" else "v3.0"
    meta = root / "meta"; meta.mkdir(parents=True)
    tasks: dict[str, int] = {}
    episode_rows: list[dict[str, Any]] = []; data_rows: list[dict[str, Any]] = []
    total = 0; global_index = 0
    feature_images: dict[str, Any] = {}
    for episode_index, episode in enumerate(episodes):
        task_index = tasks.setdefault(episode.task, len(tasks))
        video_meta: dict[str, Any] = {}
        for camera, frames in episode.images.items():
            feature_images.setdefault(f"observation.images.{camera}", {"dtype": "video", "shape": [3, int(frames.shape[1]), int(frames.shape[2])], "names": ["channels", "height", "width"], "info": {"video.height": int(frames.shape[1]), "video.width": int(frames.shape[2]), "video.codec": "h264", "video.pix_fmt": "yuv420p", "video.fps": request.options.fps}})
            if request.target_format == "lerobot_v21":
                relative = f"videos/chunk-000/observation.images.{camera}/episode_{episode_index:06d}.mp4"
            else:
                relative = f"videos/observation.images.{camera}/chunk-000/file-{episode_index:03d}.mp4"
            _encode_video(root / relative, frames, request.options.fps)
            if request.target_format == "lerobot_v30":
                key = f"videos/observation.images.{camera}"
                video_meta[f"{key}/chunk_index"] = 0
                video_meta[f"{key}/file_index"] = episode_index
                video_meta[f"{key}/from_timestamp"] = 0.0
                video_meta[f"{key}/to_timestamp"] = max(0.0, (len(frames) - 1) / request.options.fps)
        start = global_index
        for frame_index in range(len(episode.timestamps)):
            row: dict[str, Any] = {"observation.state": episode.state[frame_index], "action": episode.action[frame_index], "timestamp": float(episode.timestamps[frame_index] - episode.timestamps[0]), "frame_index": frame_index, "episode_index": episode_index, "index": global_index, "task_index": task_index}
            row.update({key: value[frame_index] for key, value in episode.extras.items()})
            data_rows.append(row); global_index += 1
        episode_rows.append({"episode_index": episode_index, "tasks": [episode.task], "length": len(episode.timestamps), "dataset_from_index": start, "dataset_to_index": global_index, **video_meta})
        total += len(episode.timestamps); progress(episode_index + 1, total)
    info = {"codebase_version": version, "robot_type": "ur5_pika", "total_episodes": len(episodes), "total_frames": total, "total_tasks": len(tasks), "chunks_size": 1000, "fps": request.options.fps, "splits": {"train": f"0:{len(episodes)}"}, "data_path": "data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet" if request.target_format == "lerobot_v21" else "data/chunk-{chunk_index:03d}/file-{file_index:03d}.parquet", "video_path": "videos/chunk-{episode_chunk:03d}/{video_key}/episode_{episode_index:06d}.mp4" if request.target_format == "lerobot_v21" else "videos/{video_key}/chunk-{chunk_index:03d}/file-{file_index:03d}.mp4", "features": {"observation.state": {"dtype": "float32", "shape": [len(episodes[0].state_names)], "names": episodes[0].state_names}, "action": {"dtype": "float32", "shape": [len(episodes[0].action_names)], "names": episodes[0].action_names}, **feature_images}}
    (meta / "info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    if request.target_format == "lerobot_v21":
        data_dir = root / "data/chunk-000"; data_dir.mkdir(parents=True)
        for episode_index, group in pd.DataFrame(data_rows).groupby("episode_index"):
            group.to_parquet(data_dir / f"episode_{int(episode_index):06d}.parquet", index=False)
        (meta / "tasks.jsonl").write_text("".join(json.dumps({"task_index": index, "task": task}) + "\n" for task, index in tasks.items()), encoding="utf-8")
        (meta / "episodes.jsonl").write_text("".join(json.dumps(row) + "\n" for row in episode_rows), encoding="utf-8")
    else:
        data_dir = root / "data/chunk-000"; data_dir.mkdir(parents=True)
        pd.DataFrame(data_rows).to_parquet(data_dir / "file-000.parquet", index=False)
        episodes_dir = meta / "episodes/chunk-000"; episodes_dir.mkdir(parents=True)
        pd.DataFrame(episode_rows).to_parquet(episodes_dir / "file-000.parquet", index=False)
        pd.DataFrame([{"task_index": index, "task": task} for task, index in tasks.items()]).to_parquet(meta / "tasks.parquet", index=False)


def _copy_v21_to_v30(root: Path, source_name: str, progress: Callable[[int, int], None]) -> None:
    """Upgrade LeRobot 2.1 without decoding and re-encoding its videos.

    A v2.1 episode already owns one video per camera.  Re-encoding all of
    those frames before the first progress update is expensive, uses a large
    amount of memory, and makes cancellation appear broken.  v3.0 supports a
    file per episode as well, so copy the encoded assets and only rewrite the
    metadata/layout.
    """
    source = lerobot_service.get_dataset_path(source_name)
    info = dict(lerobot_service.load_info(source_name))
    episodes_df = lerobot_service.load_episodes_df(source_name).copy()
    data_df = lerobot_service.load_data_df(source_name)
    if episodes_df.empty or data_df.empty:
        raise ConversionError("The LeRobot 2.1 source has no episodes or data frames")

    meta = root / "meta"
    data_dir = root / "data/chunk-000"
    episodes_dir = meta / "episodes/chunk-000"
    meta.mkdir(parents=True)
    data_dir.mkdir(parents=True)
    episodes_dir.mkdir(parents=True)

    info.update({
        "codebase_version": "v3.0",
        "data_path": "data/chunk-{chunk_index:03d}/file-{file_index:03d}.parquet",
        "video_path": "videos/{video_key}/chunk-{chunk_index:03d}/file-{file_index:03d}.mp4",
        "data_files_size_in_mb": info.get("data_files_size_in_mb", 100),
        "video_files_size_in_mb": info.get("video_files_size_in_mb", 200),
    })
    video_keys = [key for key, feature in info.get("features", {}).items() if feature.get("dtype") == "video"]
    data_df.to_parquet(data_dir / "file-000.parquet", index=False)

    copied_rows: list[dict[str, Any]] = []
    completed_frames = 0
    for output_index, (_, row) in enumerate(episodes_df.sort_values("episode_index").iterrows()):
        source_index = int(row["episode_index"])
        copied = row.to_dict()
        copied["episode_index"] = output_index
        for video_key in video_keys:
            source_relative = f"videos/chunk-{source_index // int(info.get('chunks_size') or 1000):03d}/{video_key}/episode_{source_index:06d}.mp4"
            target_relative = f"videos/{video_key}/chunk-000/file-{output_index:03d}.mp4"
            source_video = source / source_relative
            if not source_video.exists():
                raise ConversionError(f"Missing source video: {source_relative}")
            target_video = root / target_relative
            target_video.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_video, target_video)
            prefix = f"videos/{video_key}"
            copied[f"{prefix}/chunk_index"] = 0
            copied[f"{prefix}/file_index"] = output_index
            copied[f"{prefix}/from_timestamp"] = 0.0
            copied[f"{prefix}/to_timestamp"] = max(0.0, (int(row.get("length", 0)) - 1) / float(info.get("fps") or 30))
        copied_rows.append(copied)
        completed_frames += int(row.get("length", 0))
        progress(output_index + 1, completed_frames)

    pd.DataFrame(copied_rows).to_parquet(episodes_dir / "file-000.parquet", index=False)
    tasks_path = source / "meta/tasks.jsonl"
    tasks = [json.loads(line) for line in tasks_path.read_text(encoding="utf-8").splitlines() if line] if tasks_path.exists() else []
    pd.DataFrame(tasks).to_parquet(meta / "tasks.parquet", index=False)
    (meta / "info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")


def _jsonable_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value.tolist() if hasattr(value, "tolist") else value for key, value in row.items()}


def _copy_v30_to_v21(root: Path, source_name: str, progress: Callable[[int, int], None]) -> None:
    """Downgrade v3.0 one episode at a time instead of loading all videos."""
    source = lerobot_service.get_dataset_path(source_name)
    info = dict(lerobot_service.load_info(source_name))
    episodes_df = lerobot_service.load_episodes_df(source_name).sort_values("episode_index")
    data_df = lerobot_service.load_data_df(source_name)
    if episodes_df.empty or data_df.empty:
        raise ConversionError("The LeRobot 3.0 source has no episodes or data frames")
    meta, data_dir = root / "meta", root / "data/chunk-000"
    meta.mkdir(parents=True); data_dir.mkdir(parents=True)
    info.update({"codebase_version": "v2.1", "data_path": "data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet", "video_path": "videos/chunk-{episode_chunk:03d}/{video_key}/episode_{episode_index:06d}.mp4"})
    info.pop("data_files_size_in_mb", None); info.pop("video_files_size_in_mb", None)
    video_keys = [key for key, feature in info.get("features", {}).items() if feature.get("dtype") == "video"]
    output_rows: list[dict[str, Any]] = []; completed_frames = 0
    for output_index, (_, row) in enumerate(episodes_df.iterrows()):
        source_index = int(row["episode_index"])
        episode_data = data_df[data_df["episode_index"] == source_index].copy().sort_values("frame_index")
        if episode_data.empty:
            raise ConversionError(f"Episode {source_index} has no data rows")
        episode_data["episode_index"] = output_index
        episode_data.to_parquet(data_dir / f"episode_{output_index:06d}.parquet", index=False)
        for video_key in video_keys:
            prefix = f"videos/{video_key}"
            source_video = source / f"videos/{video_key}/chunk-{int(row[f'{prefix}/chunk_index']):03d}/file-{int(row[f'{prefix}/file_index']):03d}.mp4"
            frames = _decode_video_segment(source_video, len(episode_data), float(row.get(f"{prefix}/from_timestamp", 0.0)))
            if len(frames) != len(episode_data):
                raise ConversionError(f"Could not extract all frames for episode {source_index}, camera {video_key}")
            target = root / f"videos/chunk-{output_index // int(info.get('chunks_size') or 1000):03d}/{video_key}/episode_{output_index:06d}.mp4"
            _encode_video(target, np.stack(frames), int(info.get("fps") or 30))
        output = {key: value for key, value in row.to_dict().items() if not key.startswith("videos/")}
        output["episode_index"] = output_index; output_rows.append(output)
        completed_frames += len(episode_data); progress(output_index + 1, completed_frames)
    (meta / "episodes.jsonl").write_text("".join(json.dumps(_jsonable_row(row)) + "\n" for row in output_rows), encoding="utf-8")
    tasks_path = source / "meta/tasks.parquet"
    tasks = pd.read_parquet(tasks_path).to_dict(orient="records") if tasks_path.exists() else []
    (meta / "tasks.jsonl").write_text("".join(json.dumps(_jsonable_row(row)) + "\n" for row in tasks), encoding="utf-8")
    (meta / "info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")


class ConversionManager:
    def __init__(self) -> None:
        self.jobs: dict[str, ConversionJob] = {}
        self.cancelled: set[str] = set()
        self.lock = threading.Lock()
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="robodata-converter")

    def create(self, request: ConversionCreateRequest) -> ConversionJob:
        check = preflight(request)
        if not check.valid_episodes:
            raise ConversionError("No valid episodes passed preflight")
        if request.target_format != "hdf5" and not check.encoder_available:
            raise ConversionError("Video encoder unavailable; install backend requirements before LeRobot export")
        job = ConversionJob(id=uuid.uuid4().hex, source_name=request.source_name, source_format=request.source_format, target_format=request.target_format, status="queued", stage="Queued", total_episodes=check.valid_episodes, total_frames=check.total_output_frames)
        with self.lock: self.jobs[job.id] = job
        self.worker.submit(self._run, job.id, request)
        return job

    def get(self, job_id: str) -> ConversionJob:
        with self.lock:
            if job_id not in self.jobs: raise ConversionError("Conversion job not found")
            return self.jobs[job_id].model_copy(deep=True)

    def cancel(self, job_id: str) -> ConversionJob:
        self.cancelled.add(job_id)
        return self.get(job_id)

    def _run(self, job_id: str, request: ConversionCreateRequest) -> None:
        two_phase = request.source_format != "raw" and (
            (request.source_format, request.target_format)
            not in {
                ("lerobot_v21", "hdf5"),
                ("lerobot_v30", "hdf5"),
                ("lerobot_v21", "lerobot_v30"),
                ("lerobot_v30", "lerobot_v21"),
            }
        )

        def ratio(job: ConversionJob, episodes: int, frames: int) -> float:
            completed = frames if job.total_frames else episodes
            total = job.total_frames or job.total_episodes
            return min(1.0, completed / total) if total else 0.0

        def update(episodes: int, frames: int) -> None:
            with self.lock:
                job = self.jobs[job_id]; job.completed_episodes = episodes; job.completed_frames = frames
                job.stage = f"Writing episode {episodes}/{job.total_episodes}"
                write_progress = ratio(job, episodes, frames)
                job.progress_percent = (50.0 + 50.0 * write_progress) if two_phase else 100.0 * write_progress
            if job_id in self.cancelled: raise ConversionError("Cancelled by user")
        def loading_update(episodes: int, frames: int) -> None:
            with self.lock:
                job = self.jobs[job_id]
                job.completed_episodes = episodes
                job.stage = f"Loading episode media {episodes}/{job.total_episodes}"
                job.progress_percent = 50.0 * ratio(job, episodes, frames)
            if job_id in self.cancelled:
                raise ConversionError("Cancelled by user")
        def media_update(episodes: int, frames: int) -> None:
            with self.lock:
                job = self.jobs[job_id]
                job.completed_episodes = max(0, episodes - 1)
                job.completed_frames = frames
                job.stage = f"Decoding episode video {episodes}/{job.total_episodes}"
                job.progress_percent = 100.0 * ratio(job, episodes, frames)
            if job_id in self.cancelled:
                raise ConversionError("Cancelled by user")
        output_root: Path | None = None
        try:
            with self.lock:
                self.jobs[job_id].status = "running"; self.jobs[job_id].stage = "Loading source"
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_name = f"{request.source_name}__{request.target_format}__{stamp}"
            output_root = settings.data_root / "outputs" / output_name
            temporary = output_root.with_name(f".{output_name}.{job_id}.partial")
            temporary.parent.mkdir(parents=True, exist_ok=True)
            if temporary.exists(): shutil.rmtree(temporary)
            if request.source_format in {"lerobot_v21", "lerobot_v30"} and request.target_format == "hdf5":
                with self.lock:
                    self.jobs[job_id].stage = "Streaming LeRobot videos to HDF5"
                _stream_lerobot_to_hdf5(temporary, request.source_name, request, update, media_update)
                if job_id in self.cancelled:
                    raise ConversionError("Cancelled by user")
                temporary.replace(output_root)
                with self.lock:
                    job = self.jobs[job_id]
                    job.status = "completed"; job.stage = "Completed"; job.completed_episodes = job.total_episodes; job.completed_frames = job.total_frames; job.progress_percent = 100; job.output_name = output_name; job.output_path = str(output_root)
                return
            if request.source_format == "lerobot_v21" and request.target_format == "lerobot_v30":
                with self.lock:
                    self.jobs[job_id].stage = "Copying LeRobot 2.1 videos"
                _copy_v21_to_v30(temporary, request.source_name, update)
                if job_id in self.cancelled:
                    raise ConversionError("Cancelled by user")
                temporary.replace(output_root)
                with self.lock:
                    job = self.jobs[job_id]
                    job.status = "completed"; job.stage = "Completed"; job.completed_episodes = job.total_episodes; job.completed_frames = job.total_frames; job.progress_percent = 100; job.output_name = output_name; job.output_path = str(output_root)
                return
            if request.source_format == "lerobot_v30" and request.target_format == "lerobot_v21":
                with self.lock:
                    self.jobs[job_id].stage = "Extracting LeRobot 3.0 episodes"
                _copy_v30_to_v21(temporary, request.source_name, update)
                if job_id in self.cancelled:
                    raise ConversionError("Cancelled by user")
                temporary.replace(output_root)
                with self.lock:
                    job = self.jobs[job_id]
                    job.status = "completed"; job.stage = "Completed"; job.completed_episodes = job.total_episodes; job.completed_frames = job.total_frames; job.progress_percent = 100; job.output_name = output_name; job.output_path = str(output_root)
                return
            if request.source_format == "raw":
                episodes = []
                skipped: list[str] = []
                for path in _raw_episode_paths(request.source_name):
                    try:
                        episodes.append(_load_raw_episode(path, request.options))
                    except ConversionError as error:
                        skipped.append(str(error))
                if not episodes:
                    raise ConversionError("No raw episodes could be synchronized")
                if skipped:
                    with self.lock:
                        self.jobs[job_id].warnings = skipped
            else:
                episodes = _load_dataset_episodes(request.source_name, request.source_format, load_images=True, on_episode=loading_update)
            episodes = [episode for episode in episodes if len(episode.timestamps)]
            if not episodes:
                raise ConversionError("No episodes remained after source validation")
            actual_total_frames = sum(len(episode.timestamps) for episode in episodes)
            with self.lock:
                job = self.jobs[job_id]
                job.total_episodes = len(episodes)
                job.total_frames = actual_total_frames
            if request.target_format == "hdf5": _write_hdf5(temporary, episodes, request, update)
            else: _write_lerobot(temporary, episodes, request, update)
            if job_id in self.cancelled: raise ConversionError("Cancelled by user")
            temporary.replace(output_root)
            with self.lock:
                job = self.jobs[job_id]; job.status = "completed"; job.stage = "Completed"; job.completed_episodes = job.total_episodes; job.completed_frames = job.total_frames; job.progress_percent = 100; job.output_name = output_name; job.output_path = str(output_root)
        except Exception as error:
            if output_root:
                partial = output_root.with_name(f".{output_root.name}.{job_id}.partial")
                if partial.exists(): shutil.rmtree(partial, ignore_errors=True)
            with self.lock:
                job = self.jobs[job_id]; job.status = "cancelled" if job_id in self.cancelled else "failed"; job.stage = "Cancelled" if job_id in self.cancelled else "Failed"; job.message = str(error)


manager = ConversionManager()
