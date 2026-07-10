from fastapi import APIRouter, HTTPException

from app.models.schemas import ConversionCreateRequest, ConversionJob, ConversionPreflight
from app.services.converter_service import ConversionError, manager, preflight

router = APIRouter()


def _bad_request(error: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(error))


@router.post("/converter/preflight", response_model=ConversionPreflight)
def converter_preflight(request: ConversionCreateRequest) -> ConversionPreflight:
    try:
        return preflight(request)
    except (ConversionError, FileNotFoundError) as error:
        raise _bad_request(error) from error


@router.post("/converter/jobs", response_model=ConversionJob, status_code=202)
def create_conversion_job(request: ConversionCreateRequest) -> ConversionJob:
    try:
        return manager.create(request)
    except (ConversionError, FileNotFoundError) as error:
        raise _bad_request(error) from error


@router.get("/converter/jobs/{job_id}", response_model=ConversionJob)
def conversion_job(job_id: str) -> ConversionJob:
    try:
        return manager.get(job_id)
    except ConversionError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.delete("/converter/jobs/{job_id}", response_model=ConversionJob)
def cancel_conversion_job(job_id: str) -> ConversionJob:
    try:
        return manager.cancel(job_id)
    except ConversionError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
