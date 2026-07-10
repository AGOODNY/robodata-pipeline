import json
import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np

from app.models.schemas import ConversionCreateRequest, ConverterOptions
from app.services.converter_service import NormalizedEpisode, _raw_cutoff, _write_hdf5


class ConverterServiceTests(unittest.TestCase):
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
            with h5py.File(root / "episodes/episode_000000.hdf5") as file:
                np.testing.assert_array_equal(file["observation/state"][:], episode.state)
                np.testing.assert_array_equal(file["images/pikaGripperDepthCamera"][:], episode.images["pikaGripperDepthCamera"])


if __name__ == "__main__":
    unittest.main()
