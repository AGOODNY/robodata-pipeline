from __future__ import annotations

import shutil
from pathlib import Path

from app.models.schemas import CatalogDataset
from app.core.config import settings
from app.services import lerobot_service
from app.services.lerobot_service import list_datasets
from app.services.raw_service import list_raw_datasets


def _lerobot_format(codebase_version: str | None) -> tuple[str, str] | None:
    normalized = (codebase_version or "").lower()
    if "2.1" in normalized:
        return "lerobot_v21", "LeRobot 2.1"
    if "3.0" in normalized:
        return "lerobot_v30", "LeRobot 3.0"
    return None


def list_catalog_datasets() -> list[CatalogDataset]:
    items: list[CatalogDataset] = []
    for dataset in list_datasets():
        dataset_format = _lerobot_format(dataset.codebase_version)
        if dataset_format is not None:
            format_key, format_label = dataset_format
            items.append(
                CatalogDataset(
                    name=dataset.name,
                    path=dataset.path,
                    format=format_key,
                    format_label=format_label,
                    robot_type=dataset.robot_type,
                    total_episodes=dataset.total_episodes,
                    total_frames=dataset.total_frames,
                    fps=dataset.fps,
                )
            )
        elif (dataset.codebase_version or "").lower() == "robodata_hdf5_v1":
            items.append(
                CatalogDataset(
                    name=dataset.name,
                    path=dataset.path,
                    format="hdf5",
                    format_label="RoboData HDF5",
                    robot_type=dataset.robot_type,
                    total_episodes=dataset.total_episodes,
                    total_frames=dataset.total_frames,
                    fps=dataset.fps,
                )
            )

    for dataset in list_raw_datasets():
        items.append(
            CatalogDataset(
                name=dataset.name,
                path=dataset.path,
                format="raw",
                format_label="Raw",
                total_episodes=dataset.total_episodes,
            )
        )

    return sorted(items, key=lambda item: (item.format, item.name))


class DatasetDeletionNotAllowedError(ValueError):
    pass


def delete_generated_dataset(dataset_name: str) -> None:
    """Delete only Converter output, never a Raw capture or bundled sample."""
    path = lerobot_service.get_dataset_path(dataset_name)
    outputs_root = (settings.data_root / "outputs").resolve()
    resolved = path.resolve()
    if outputs_root not in resolved.parents:
        raise DatasetDeletionNotAllowedError("Only datasets created under outputs/ can be deleted from the platform")
    shutil.rmtree(resolved)
    lerobot_service.load_info.cache_clear()
    lerobot_service.load_stats.cache_clear()
    lerobot_service.load_tasks.cache_clear()
    lerobot_service.load_episodes_df.cache_clear()
    lerobot_service.load_data_df.cache_clear()
    lerobot_service.load_episode_stats.cache_clear()
