# RoboData Pipeline

RoboData Pipeline is a local data post-processing workspace for Pika/UR5 embodied intelligence datasets.

The first milestone focuses on LeRobot 3.0 dataset visualization and format validation using the existing `drawer_multicam_jointbin30` sample dataset.

## Structure

```text
robodata-pipeline/
  backend/   FastAPI service for dataset discovery, parquet/json reading, media access, validation
  frontend/  Vue 3 + Vite + TypeScript dashboard
```

## Backend

```bash
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

By default the backend scans the parent directory of `robodata-pipeline` for datasets containing `meta/info.json`.

Set a custom data root when needed:

```powershell
$env:ROBODATA_DATA_ROOT="D:\path\to\datasets"
python -m uvicorn app.main:app --reload
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

If PowerShell blocks `npm.ps1`, use `npm.cmd install` and `npm.cmd run dev`.

Open `http://127.0.0.1:5173`.

## First Milestone

- Dataset selection
- Dataset overview
- Episode list
- Episode video playback
- State/action curves
- LeRobot 3.0 format validation

Future modules are reserved for raw viewing, conversion, subtask annotation, and training export.
