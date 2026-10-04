"""Expose authorized SQL only through the supervised query service."""
import asyncio
import threading
from fastapi import APIRouter, Depends, Request
from trinity.auth.dependencies import bearer_token
from trinity.queries.schemas import QueryRequest, QueryResponse

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
    cancelled=threading.Event()
    task=asyncio.create_task(asyncio.to_thread(service.execute,token,body.sql,cancelled=cancelled))
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
