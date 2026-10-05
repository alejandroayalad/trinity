"""Expose authorized SQL only through the supervised query service."""
import asyncio
import threading
from fastapi import APIRouter, Depends, Request
from trinity.auth.dependencies import bearer_token
from trinity.queries.schemas import QueryRequest, QueryResponse
from trinity.queries.preview_schemas import PreviewResponse
from trinity.queries.choice_schemas import FacilityOptions, GeneratorOptions

router=APIRouter(prefix='/api/v1',tags=['queries'])


@router.post('/queries',response_model=QueryResponse)
async def run_query(body: QueryRequest,request: Request,token: str=Depends(bearer_token)):
    """Cancel analytical work on disconnect without releasing unknown execution."""
    service=request.app.state.query_service
    if service is None:
        from trinity.queries.config import execution_factory
        from trinity.queries.service import QueryService
        database=request.app.state.auth.database
        service=QueryService(database,lambda:execution_factory(database))
    return await supervised_call(request, service.execute, token, body.sql)


async def supervised_call(request, execute, *args, **kwargs):
    """Propagate disconnect/cancellation while the execution owner retains cleanup."""
    cancelled=threading.Event()
    task=asyncio.create_task(asyncio.to_thread(execute,*args,**kwargs,cancelled=cancelled))
    try:
        while not task.done():
            await asyncio.wait({task},timeout=.1)
            if not task.done() and await request.is_disconnected():cancelled.set()
        return await task
    finally:
        if not task.done():
            cancelled.set()
            try:await asyncio.shield(task)
            except Exception:pass


@router.get('/datasets/{dataset_key}/preview', response_model=PreviewResponse)
async def preview_dataset(dataset_key: str, request: Request, token: str = Depends(bearer_token)):
    """Preserve duplicate query parameters for identity-first strict validation."""
    service = request.app.state.preview_service
    if service is None:
        from trinity.queries.config import preview_execution_factory
        from trinity.queries.service import PreviewService
        database = request.app.state.auth.database
        service = PreviewService(database, lambda: preview_execution_factory(
            database, enabled=request.app.state.preview_enabled))
    return await supervised_call(request, service.execute, token, dataset_key,
                                 request.query_params.multi_items(), body=await request.body())


async def choice_call(dataset_key, choice, request, token):
    """Keep duplicate parameters and disconnect handling identical to preview."""
    service = request.app.state.choice_service
    if service is None:
        from trinity.queries.config import preview_execution_factory
        from trinity.queries.choice_service import ChoiceService
        database = request.app.state.auth.database
        service = ChoiceService(database, lambda: preview_execution_factory(
            database, enabled=request.app.state.preview_enabled))
    return await supervised_call(request, service.execute, token, dataset_key, choice,
                                 request.query_params.multi_items(), body=await request.body())


@router.get('/datasets/{dataset_key}/facilities', response_model=FacilityOptions)
async def facility_choices(dataset_key: str, request: Request, token: str = Depends(bearer_token)):
    """List published Plants observed in the requested detailed dataset range."""
    return await choice_call(dataset_key, 'facilities', request, token)


@router.get('/datasets/{dataset_key}/generators', response_model=GeneratorOptions)
async def generator_choices(dataset_key: str, request: Request, token: str = Depends(bearer_token)):
    """List distinct generator IDs for one exact published Plant ID."""
    return await choice_call(dataset_key, 'generators', request, token)
