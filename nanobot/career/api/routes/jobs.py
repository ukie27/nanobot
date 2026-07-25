"""Read-only Part 0 background job status API."""

from fastapi import APIRouter, HTTPException, Query, Request

from nanobot.career.api.schemas import BackgroundJobListResponse, BackgroundJobResponse

router = APIRouter(prefix="/api/v1/jobs", tags=["background-jobs"])


@router.get("", response_model=BackgroundJobListResponse)
def list_jobs(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
) -> BackgroundJobListResponse:
    items = request.app.state.jobs.list_jobs(limit=limit)
    responses = [BackgroundJobResponse.model_validate(item) for item in items]
    return BackgroundJobListResponse(items=responses, total=len(responses))


@router.post("/{job_id}/retry", response_model=BackgroundJobResponse)
def retry_job(job_id: str, request: Request) -> BackgroundJobResponse:
    try:
        return BackgroundJobResponse.model_validate(request.app.state.jobs.retry(job_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{job_id}/cancel", response_model=BackgroundJobResponse)
def cancel_job(job_id: str, request: Request) -> BackgroundJobResponse:
    try:
        return BackgroundJobResponse.model_validate(request.app.state.jobs.cancel(job_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
