from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path

import anyio

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from services.core.domain import (
    Artifact, CameraMeta, DomainError, ImageProvider, JobProgressEvent, Project, Reference,
    ReferenceRole, RenderJob, RenderRequest, Scene, StylePack, ensure_can_finalize,
)
from services.core.orchestration import JobManager, OrchestrationError, provider_health
from services.core.storage import DataRoot, Database
from services.providers.mock import MockProvider
from .schemas import FinalizeRequest, HealthResponse, ProjectCreate, ProviderInfo, StylePackCreate


def create_app(data_root: Path | str | None = None, *, providers: list[ImageProvider] | None = None, timeout: float = 120, poll_interval: float = .1) -> FastAPI:
    root = DataRoot(Path(data_root or os.environ.get('AI_STUDIO_DATA_ROOT', Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'AIInteriorStudio')))
    adapters = providers if providers is not None else [MockProvider()]

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database(root.db_path)
        manager = JobManager(db, root, adapters, timeout=timeout, poll_interval=poll_interval)
        app.state.manager = manager
        await manager.start()
        try:
            yield
        finally:
            await manager.stop()
            db.close()

    app = FastAPI(title='AI Interior Studio API', version='0.1.0', lifespan=lifespan)

    def manager() -> JobManager:
        return app.state.manager

    @app.exception_handler(DomainError)
    async def domain_error(_request, exc: DomainError):
        status = 404 if exc.code in ('NOT_FOUND', 'ARTIFACT_NOT_FOUND') else 409
        return JSONResponse(status_code=status, content=exc.to_dict())

    @app.exception_handler(OrchestrationError)
    async def orchestration_error(_request, exc: OrchestrationError):
        return JSONResponse(status_code=422, content={'code': exc.code, 'message': exc.message})

    @app.get('/providers', response_model=list[ProviderInfo])
    async def get_providers():
        health = await asyncio.gather(*(provider_health(p) for p in adapters))
        return [ProviderInfo(id=p.id, capabilities=p.capabilities, health=h) for p, h in zip(adapters, health)]

    @app.get('/health', response_model=HealthResponse)
    async def health():
        return HealthResponse(providers=await get_providers())

    @app.post('/projects', response_model=Project, status_code=201)
    async def create_project(body: ProjectCreate):
        project = manager().db.projects.add(Project(**body.model_dump()))
        root.project(project.id).ensure()
        return project

    @app.get('/projects', response_model=list[Project])
    async def list_projects():
        return manager().db.projects.list()

    @app.get('/projects/{identifier}', response_model=Project)
    async def get_project(identifier: str):
        return manager().db.projects.get(identifier)

    async def store_upload(project_id: str, file: UploadFile, kind: str) -> Artifact:
        manager().db.projects.get(project_id)
        if file.content_type not in ('image/png', 'image/jpeg', 'image/webp'):
            raise HTTPException(422, 'Expected PNG, JPEG or WebP')
        data = await file.read(20 * 1024 * 1024 + 1)
        await file.close()
        if not data or len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, 'Image must contain 1 byte to 20 MiB')
        # Do not use an untrusted filename as a filesystem suffix.
        artifact = manager().artifacts.put_bytes(project_id, data, kind=kind, media_type=file.content_type)
        return manager().db.artifacts.add(artifact)

    @app.post('/projects/{identifier}/scenes/import', response_model=Scene, status_code=201)
    async def import_scene(identifier: str, file: UploadFile = File(...), name: str = Form('Scene'), camera: str | None = Form(None), model_checksum: str | None = Form(None)):
        try:
            metadata = CameraMeta.model_validate_json(camera) if camera else None
        except ValidationError:
            raise HTTPException(422, 'Invalid CameraMeta JSON') from None
        artifact = await store_upload(identifier, file, 'source_scene')
        return manager().db.scenes.add(Scene(project_id=identifier, name=name, rgb_artifact_id=artifact.id, camera=metadata, model_checksum=model_checksum))

    @app.post('/style-packs', response_model=StylePack, status_code=201)
    async def create_pack(body: StylePackCreate):
        if body.project_id:
            manager().db.projects.get(body.project_id)
        return manager().db.style_packs.add_version(StylePack(**body.model_dump()))

    @app.get('/style-packs', response_model=list[StylePack])
    async def list_packs(project_id: str | None = None):
        return manager().db.style_packs.list_latest(project_id)

    @app.get('/style-packs/{identifier}', response_model=StylePack)
    async def get_pack(identifier: str, version: int | None = None):
        return manager().db.style_packs.get(identifier, version)

    @app.post('/style-packs/{identifier}/references', response_model=StylePack, status_code=201)
    async def add_reference(identifier: str, file: UploadFile = File(...), role: ReferenceRole = Form(...), source_note: str | None = Form(None), usage_rights_note: str | None = Form(None)):
        pack = manager().db.style_packs.get(identifier)
        if not pack.project_id:
            raise HTTPException(422, 'Uploads require a project-owned Style Pack')
        artifact = await store_upload(pack.project_id, file, 'reference')
        # Upload awaits may overlap; append to the latest version after reading bytes.
        pack = manager().db.style_packs.get(identifier)
        reference = Reference(artifact_id=artifact.id, role=role, source_note=source_note, usage_rights_note=usage_rights_note)
        return manager().db.style_packs.add_version(pack.next_version(references=[*pack.references, reference]))

    @app.post('/render/jobs', response_model=RenderJob, status_code=201)
    async def create_job(body: RenderRequest):
        return await manager().submit(body)

    @app.get('/render/jobs', response_model=list[RenderJob])
    async def list_jobs(project_id: str | None = None):
        return manager().db.jobs.list(project_id)

    @app.get('/render/jobs/{identifier}', response_model=RenderJob)
    async def get_job(identifier: str):
        return manager().db.jobs.get(identifier)

    @app.post('/render/jobs/{identifier}/cancel', response_model=RenderJob)
    async def cancel(identifier: str):
        return await manager().cancel(identifier)

    @app.post('/render/jobs/{identifier}/approve', response_model=RenderJob)
    async def approve(identifier: str):
        return await manager().approve(identifier)

    @app.post('/render/jobs/{identifier}/retry', response_model=RenderJob, status_code=201)
    async def retry(identifier: str):
        return await manager().retry(identifier)

    @app.post('/render/jobs/{identifier}/finalize', response_model=RenderJob, status_code=201)
    async def finalize(identifier: str, body: FinalizeRequest = FinalizeRequest()):
        parent = manager().db.jobs.get(identifier)
        ensure_can_finalize(parent)
        request = RenderRequest(project_id=parent.project_id, mode='upscale', parent_job_id=parent.id, quality='final', ratio=parent.request.ratio, provider_policy=parent.request.provider_policy, **body.model_dump())
        return await manager().submit(request)

    @app.get('/artifacts/{identifier}', response_model=Artifact)
    async def artifact_metadata(identifier: str):
        return manager().db.artifacts.get(identifier)

    @app.get('/artifacts/{identifier}/file', responses={200: {'content': {'image/png': {}}}})
    async def artifact_file(identifier: str):
        artifact = manager().db.artifacts.get(identifier)
        manager().artifacts.verify(artifact)
        return Response(manager().artifacts.read_bytes(artifact), media_type=artifact.media_type)

    @app.websocket('/ws/jobs')
    async def job_events(websocket: WebSocket):
        queue = manager().subscribe()
        await websocket.accept()

        async def send():
            while True:
                event = await queue.get()
                await websocket.send_json(event.model_dump(mode='json'))

        async def receive():
            while True:
                await websocket.receive_text()

        try:
            async with anyio.create_task_group() as group:
                group.start_soon(send)
                try:
                    await receive()
                except WebSocketDisconnect:
                    pass
                finally:
                    group.cancel_scope.cancel()
        finally:
            manager().subscribers.discard(queue)

    original_openapi = app.openapi

    def openapi():
        schema = original_openapi()
        # OpenAPI has no native WebSocket operations; expose the shared event schema.
        schema['components']['schemas']['JobProgressEvent'] = JobProgressEvent.model_json_schema(ref_template='#/components/schemas/{model}')
        return schema

    app.openapi = openapi
    return app
