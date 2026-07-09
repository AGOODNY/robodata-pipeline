from __future__ import annotations

from app.models.schemas import CatalogDataset
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
        if dataset_format is None:
            continue
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
