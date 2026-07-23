"""Read-only Part 0 background job status API."""

from fastapi import APIRouter, Query, Request

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
