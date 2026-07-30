"""Connector configuration and controlled OpenCLI actions."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from career_console.infrastructure.connectors import OpenCliError
from career_console.interfaces.http.schemas import (
    ConnectorConfigUpdate,
    ConnectorLoginRequest,
    NowcoderConnectorConfigUpdate,
    NowcoderScanRequest,
    OpenCliRuntimeUpdate,
)

router = APIRouter(prefix="/api/v1/connectors", tags=["connectors"])


@router.get("/opencli")
def get_opencli(request: Request) -> dict:
    return request.app.state.integration_configuration.get_opencli()


@router.put("/opencli")
def configure_opencli(body: OpenCliRuntimeUpdate, request: Request) -> dict:
    return request.app.state.integration_configuration.configure_opencli(
        body.executable
    )


@router.get("/boss")
def get_boss(request: Request) -> dict:
    return request.app.state.connector_service.get_boss()


@router.put("/boss")
def configure_boss(body: ConnectorConfigUpdate, request: Request) -> dict:
    try:
        return request.app.state.integration_configuration.configure_boss(
            **body.model_dump()
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/boss/health")
def boss_health(request: Request) -> dict:
    return request.app.state.connector_service.health()


@router.post("/boss/login")
def boss_login(body: ConnectorLoginRequest, request: Request) -> dict:
    try:
        return request.app.state.connector_service.login(timeout=body.timeout)
    except OpenCliError as exc:
        raise HTTPException(
            status_code=409, detail={"code": exc.code, "message": str(exc)}
        ) from exc


@router.post("/boss/scan")
def boss_scan(request: Request) -> dict:
    try:
        return request.app.state.connector_service.scan()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OpenCliError as exc:
        raise HTTPException(
            status_code=409, detail={"code": exc.code, "message": str(exc)}
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/run-due")
def run_due(request: Request) -> dict:
    try:
        run = request.app.state.connector_service.run_due()
        return {"processed": int(run is not None), "run": run}
    except (OpenCliError, RuntimeError, ValueError) as exc:
        code = exc.code if isinstance(exc, OpenCliError) else "connector_failed"
        raise HTTPException(status_code=409, detail={"code": code, "message": str(exc)}) from exc


@router.get("/nowcoder")
def get_nowcoder(request: Request) -> dict:
    return request.app.state.nowcoder_connector_service.get()


@router.put("/nowcoder")
def configure_nowcoder(body: NowcoderConnectorConfigUpdate, request: Request) -> dict:
    try:
        return request.app.state.integration_configuration.configure_nowcoder(
            **body.model_dump()
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/nowcoder/health")
def nowcoder_health(request: Request) -> dict:
    return request.app.state.nowcoder_connector_service.health()


@router.post("/nowcoder/login")
def nowcoder_login(body: ConnectorLoginRequest, request: Request) -> dict:
    try:
        return request.app.state.nowcoder_connector_service.login(timeout=body.timeout)
    except OpenCliError as exc:
        raise HTTPException(
            status_code=409, detail={"code": exc.code, "message": str(exc)}
        ) from exc


@router.post("/nowcoder/scan")
def nowcoder_scan(body: NowcoderScanRequest, request: Request) -> dict:
    try:
        return request.app.state.nowcoder_connector_service.scan(
            lookback_days=body.lookback_days
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OpenCliError as exc:
        raise HTTPException(
            status_code=409, detail={"code": exc.code, "message": str(exc)}
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
