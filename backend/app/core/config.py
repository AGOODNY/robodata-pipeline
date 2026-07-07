from pathlib import Path
import os

from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = "RoboData Pipeline"
    api_prefix: str = "/api"
    platform_root: Path = Path(__file__).resolve().parents[3]
    data_root: Path = Path(
        os.getenv("ROBODATA_DATA_ROOT", Path(__file__).resolve().parents[3].parent)
    )


settings = Settings()
