import json
import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np

from app.models.schemas import ConversionCreateRequest, ConverterOptions
from app.services.lerobot_service import _is_hdf5_info
from app.services.converter_service import (
    ConversionError,
    NormalizedEpisode,
    _create_hdf5_image_dataset,
    _raw_cutoff,
    _write_hdf5,
    preflight,
)


class ConverterServiceTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
