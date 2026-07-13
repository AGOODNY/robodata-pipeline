import json
import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
from PIL import Image

from app.core.config import settings
from app.models.schemas import ConversionCreateRequest, ConversionJob, ConverterOptions
from app.services import lerobot_service
from app.services.lerobot_service import _is_hdf5_info, get_summary, hdf5_cameras, hdf5_frames
from app.services.converter_service import (
    ConversionError,
    ConversionManager,
    EpisodeImageSource,
    NormalizedEpisode,
    _create_hdf5_image_dataset,
    _hdf5_image_source,
    _iter_hdf5_episodes,
    _load_raw_episode,
    _raw_cutoff,
    _write_hdf5,
    _write_lerobot,
    preflight,
)


class ConverterServiceTests(unittest.TestCase):
    def set_data_root(self, root: Path) -> None:
        settings.data_root = root
        for cached in (
            lerobot_service.load_info,
            lerobot_service.load_stats,
            lerobot_service.load_tasks,
            lerobot_service.load_episodes_df,
            lerobot_service.load_data_df,
            lerobot_service.load_episode_stats,
        ):
            cached.cache_clear()

    def create_raw_episode(self, root: Path, *, include_tcp: bool = True) -> Path:
        episode = root / "raw/demo/episode_001"
        folders = {
            "camera": episode / "camera/color/pikaGripperDepthCamera",
            "joint": episode / "arm/jointState/armJointState",
            "gripper": episode / "gripper/encoder/pikaGripper",
            "tcp": episode / "arm/endPose/armEndPose",
            "target": episode / "arm/endPose/armTargetPose",
        }
        for folder in folders.values():
            folder.mkdir(parents=True, exist_ok=True)
        for index, stamp in enumerate((1.0, 2.0, 3.0), start=1):
            Image.fromarray(np.full((2, 3, 3), index, dtype=np.uint8)).save(folders["camera"] / f"{stamp}.jpg")
            (folders["joint"] / f"{stamp}.json").write_text(json.dumps({"position": [stamp] * 6}), encoding="utf-8")
            (folders["gripper"] / f"{stamp}.json").write_text(json.dumps({"angle": stamp * 10}), encoding="utf-8")
            actual = dict(zip(("x", "y", "z", "roll", "pitch", "yaw"), [100 + stamp] * 6))
            target = dict(zip(("x", "y", "z", "roll", "pitch", "yaw"), [1000 + stamp] * 6))
            if include_tcp:
                (folders["tcp"] / f"{stamp}.json").write_text(json.dumps(actual), encoding="utf-8")
            (folders["target"] / f"{stamp}.json").write_text(json.dumps(target), encoding="utf-8")
        return episode

    def create_hdf5_dataset(self, root: Path, name: str = "hdf5_demo") -> Path:
        dataset = root / name
        (dataset / "meta").mkdir(parents=True)
        (dataset / "episodes").mkdir()
        info = {"codebase_version": "hdf5_v1", "format": "HDF5 v1", "total_episodes": 1, "total_frames": 20, "fps": 30, "features": {}}
        (dataset / "meta/info.json").write_text(json.dumps(info), encoding="utf-8")
        (dataset / "meta/tasks.jsonl").write_text(json.dumps({"task_index": 0, "task": "task a"}) + "\n", encoding="utf-8")
        row = {"episode_index": 0, "episode_name": "episode_001", "file": "episodes/episode_000000.hdf5", "task": "task a", "length": 20, "state_names": ["joint"], "action_names": ["joint"]}
        (dataset / "meta/episodes.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
        with h5py.File(dataset / row["file"], "w") as file:
            file.create_dataset("timestamp", data=np.arange(20, dtype=np.float64) / 30)
            file.create_dataset("observation/state", data=np.arange(20, dtype=np.float32).reshape(20, 1))
            file.create_dataset("action", data=np.arange(20, dtype=np.float32).reshape(20, 1))
            images = file.create_group("images")
            for key in ("gripper_depth_camera", "orbbecCamera", "third_party_cam"):
                images.create_dataset(key, data=np.zeros((20, 4, 4, 3), dtype=np.uint8), chunks=(16, 4, 4, 3))
            file.create_group("extras")
        return dataset

    def test_cancel_is_immediate_idempotent_and_prevents_queued_job_start(self) -> None:
        manager = ConversionManager()
        request = ConversionCreateRequest(
            source_name="does_not_need_to_exist",
            source_format="raw",
            target_format="hdf5",
        )
        manager.jobs["job"] = ConversionJob(
            id="job",
            source_name=request.source_name,
            source_format=request.source_format,
            target_format=request.target_format,
            status="queued",
            stage="Queued",
        )
        try:
            first = manager.cancel("job")
            second = manager.cancel("job")
            self.assertEqual(first.status, "cancelling")
            self.assertEqual(second.status, "cancelling")
            self.assertEqual(first.stage, "Cancelling")

            manager._run("job", request)
            stopped = manager.get("job")
            self.assertEqual(stopped.status, "cancelled")
            self.assertEqual(stopped.stage, "Cancelled")
        finally:
            manager.worker.shutdown(wait=True)

    def test_hdf5_writer_checks_cancellation_between_image_batches(self) -> None:
        yielded: list[int] = []

        def batches():
            for size in (16, 16, 8):
                yielded.append(size)
                yield np.zeros((size, 2, 3, 3), dtype=np.uint8)

        episode = NormalizedEpisode(
            name="episode_001",
            task="demo",
            timestamps=np.arange(40, dtype=np.float64) / 30,
            state=np.zeros((40, 1), dtype=np.float32),
            action=np.zeros((40, 1), dtype=np.float32),
            state_names=["state"],
            action_names=["action"],
            image_sources={"camera": EpisodeImageSource(40, 2, 3, batches)},
        )
        checks = 0

        def check_cancel() -> None:
            nonlocal checks
            checks += 1
            if checks == 3:
                raise ConversionError("Cancelled by user")

        with tempfile.TemporaryDirectory() as directory:
            request = ConversionCreateRequest(source_name="raw", source_format="raw", target_format="hdf5")
            with self.assertRaisesRegex(ConversionError, "Cancelled by user"):
                _write_hdf5(Path(directory) / "output", [episode], request, lambda *_: None, check_cancel)
        self.assertEqual(yielded, [16, 16])

    def test_preflight_rejects_same_source_and_target_format(self) -> None:
        request = ConversionCreateRequest(
            source_name="dataset",
            source_format="lerobot_v30",
            target_format="lerobot_v30",
        )
        with self.assertRaisesRegex(ConversionError, "must be different"):
            preflight(request)

    def test_tail_cut_only_applies_when_double_click_marker_exists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            episode = Path(directory) / "episode_001"
            episode.mkdir()
            options = ConverterOptions(trim_trigger_tail=True, trim_tail_seconds=0.5)
            self.assertIsNone(_raw_cutoff(episode, options))
            (episode / "gripper_trigger_stop.json").write_text(json.dumps({"stop_timestamp": 10.0}), encoding="utf-8")
            self.assertEqual(_raw_cutoff(episode, options), 9.5)

    def test_tcp_target_uses_current_target_and_gripper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            episode = self.create_raw_episode(Path(directory))
            target = _load_raw_episode(episode, ConverterOptions(action_type="tcp", tcp_action_source="target"), load_images=False)
            endpose = _load_raw_episode(episode, ConverterOptions(action_type="tcp", tcp_action_source="endpose"), load_images=False)
            np.testing.assert_array_equal(target.action[:, :6], np.array([[1001] * 6, [1002] * 6], dtype=np.float32))
            np.testing.assert_array_equal(target.action[:, 6], np.array([10, 20], dtype=np.float32))
            np.testing.assert_array_equal(endpose.action[:, :6], np.array([[102] * 6, [103] * 6], dtype=np.float32))
            np.testing.assert_array_equal(endpose.action[:, 6], np.array([20, 30], dtype=np.float32))

    def test_raw_preflight_counts_one_action_per_synchronized_pair(self) -> None:
        old_root = settings.data_root
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.create_raw_episode(root)
                self.set_data_root(root)
                result = preflight(ConversionCreateRequest(source_name="demo", source_format="raw", target_format="hdf5"))
                self.assertEqual(result.valid_episodes, 1)
                self.assertEqual(result.total_output_frames, 2)
                self.assertEqual(result.episodes[0].output_frames, 2)
        finally:
            self.set_data_root(old_root)

    def test_all_preflight_requires_actual_tcp(self) -> None:
        old_root = settings.data_root
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.create_raw_episode(root, include_tcp=False)
                self.set_data_root(root)
                request = ConversionCreateRequest(source_name="demo", source_format="raw", target_format="hdf5", options=ConverterOptions(action_type="all"))
                result = preflight(request)
                self.assertEqual(result.valid_episodes, 0)
                self.assertEqual(result.total_output_frames, 0)
        finally:
            self.set_data_root(old_root)

    def test_hdf5_writer_preserves_rgb_pixels_and_vectors(self) -> None:
        episode = NormalizedEpisode(
            name="episode_001", task="place box", timestamps=np.array([0.0]),
            state=np.arange(7, dtype=np.float32).reshape(1, 7),
            action=np.arange(7, dtype=np.float32).reshape(1, 7),
            state_names=["joint"] * 7, action_names=["joint"] * 7,
            images={"pikaGripperDepthCamera": np.full((1, 2, 3, 3), 17, dtype=np.uint8)},
        )
        request = ConversionCreateRequest(source_name="raw", source_format="raw", target_format="hdf5")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "output"
            _write_hdf5(root, [episode], request, lambda *_: None)
            info = json.loads((root / "meta/info.json").read_text(encoding="utf-8"))
            self.assertEqual(info["codebase_version"], "hdf5_v1")
            self.assertEqual(info["format"], "HDF5 v1")
            self.assertEqual(info["total_tasks"], 1)
            with h5py.File(root / "episodes/episode_000000.hdf5") as file:
                np.testing.assert_array_equal(file["observation/state"][:], episode.state)
                np.testing.assert_array_equal(file["images/pikaGripperDepthCamera"][:], episode.images["pikaGripperDepthCamera"])
                self.assertEqual(file["images/pikaGripperDepthCamera"].compression, "lzf")
                self.assertEqual(file["images/pikaGripperDepthCamera"].chunks, (1, 2, 3, 3))

    def test_hdf5_image_dataset_uses_lossless_batched_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "output.hdf5"
            source = np.arange(20 * 2 * 3 * 3, dtype=np.uint8).reshape(20, 2, 3, 3)
            with h5py.File(path, "w") as file:
                dataset = _create_hdf5_image_dataset(file.create_group("images"), "camera", 20, 2, 3)
                dataset[:16] = source[:16]
                dataset[16:] = source[16:]
            with h5py.File(path, "r") as file:
                dataset = file["images/camera"]
                self.assertEqual(dataset.compression, "lzf")
                self.assertEqual(dataset.chunks, (16, 2, 3, 3))
                np.testing.assert_array_equal(dataset[:], source)

    def test_hdf5_detection_accepts_legacy_version_identifier(self) -> None:
        self.assertTrue(_is_hdf5_info({"codebase_version": "robodata_" + "hdf5_v1"}))
        self.assertTrue(_is_hdf5_info({"codebase_version": "hdf5_v1"}))

    def test_hdf5_preflight_and_image_source_are_batched(self) -> None:
        old_root = settings.data_root
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                dataset = self.create_hdf5_dataset(root)
                self.set_data_root(root)
                result = preflight(ConversionCreateRequest(source_name=dataset.name, source_format="hdf5", target_format="lerobot_v21"))
                self.assertEqual(result.total_output_frames, 20)
                source = _hdf5_image_source(dataset / "episodes/episode_000000.hdf5", "gripper_depth_camera", (20, 4, 4, 3))
                self.assertEqual([len(batch) for batch in source.batches()], [16, 4])
        finally:
            self.set_data_root(old_root)

    def test_hdf5_camera_discovery_and_legacy_task_count(self) -> None:
        old_root = settings.data_root
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                dataset = self.create_hdf5_dataset(root)
                self.set_data_root(root)
                cameras = hdf5_cameras(dataset.name, 0)["cameras"]
                self.assertEqual({camera["key"] for camera in cameras}, {"gripper_depth_camera", "orbbecCamera", "third_party_cam"})
                self.assertEqual(hdf5_frames(dataset.name, 0, "third_party_cam")["frames"][-1]["index"], 19)
                self.assertEqual(get_summary(dataset.name).total_tasks, 1)
        finally:
            self.set_data_root(old_root)

    def test_lerobot_writer_consumes_image_batches_incrementally(self) -> None:
        seen: list[int] = []

        def batches():
            for count in (16, 4):
                seen.append(count)
                yield np.zeros((count, 4, 4, 3), dtype=np.uint8)

        episode = NormalizedEpisode(
            name="episode_001", task="task a", timestamps=np.arange(20, dtype=np.float64) / 30,
            state=np.zeros((20, 1), dtype=np.float32), action=np.zeros((20, 1), dtype=np.float32),
            state_names=["joint"], action_names=["joint"],
            image_sources={"third_party_cam": EpisodeImageSource(20, 4, 4, batches)},
        )
        request = ConversionCreateRequest(source_name="source", source_format="hdf5", target_format="lerobot_v21")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "output"
            result = _write_lerobot(root, iter([episode]), request, lambda *_: None)
            self.assertEqual(result.frames, 20)
            self.assertEqual(max(seen), 16)
            self.assertEqual(len(pd.read_parquet(root / "data/chunk-000/episode_000000.parquet")), 20)
            self.assertTrue((root / "videos/chunk-000/observation.images.third_party_cam/episode_000000.mp4").is_file())

    def test_hdf5_to_lerobot_streams_all_cameras(self) -> None:
        old_root = settings.data_root
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                dataset = self.create_hdf5_dataset(root)
                self.set_data_root(root)
                output = root / "output"
                request = ConversionCreateRequest(source_name=dataset.name, source_format="hdf5", target_format="lerobot_v21")
                result = _write_lerobot(output, _iter_hdf5_episodes(dataset.name), request, lambda *_: None)
                self.assertEqual((result.episodes, result.frames), (1, 20))
                for camera in ("gripper_depth_camera", "orbbecCamera", "third_party_cam"):
                    self.assertTrue((output / f"videos/chunk-000/observation.images.{camera}/episode_000000.mp4").is_file())
        finally:
            self.set_data_root(old_root)

    def test_lerobot_v30_parquet_is_appended_per_episode(self) -> None:
        def episode(index: int) -> NormalizedEpisode:
            return NormalizedEpisode(
                name=f"episode_{index:03d}", task="task a",
                timestamps=np.arange(3, dtype=np.float64) / 30,
                state=np.full((3, 1), index, dtype=np.float32),
                action=np.full((3, 1), index + 1, dtype=np.float32),
                state_names=["joint"], action_names=["joint"],
            )

        request = ConversionCreateRequest(source_name="source", source_format="hdf5", target_format="lerobot_v30")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "output"
            result = _write_lerobot(root, iter([episode(0), episode(1)]), request, lambda *_: None)
            data = pd.read_parquet(root / "data/chunk-000/file-000.parquet")
            self.assertEqual((result.episodes, result.frames), (2, 6))
            self.assertEqual(data["episode_index"].tolist(), [0, 0, 0, 1, 1, 1])


if __name__ == "__main__":
    unittest.main()
