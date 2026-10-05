"""Accept durable Admin refresh intent and expose its tracking URL.

The HTTP adapter passes raw bounded input to the service. The service checks
current authority before parsing protected commands or reading run state.
It commits only application state and a database outbox intent. It does not
fetch EIA, access S3, or enqueue Redis work during this request.
"""
from fastapi import APIRouter, Request, Response
from starlette.concurrency import run_in_threadpool

from trinity.auth.dependencies import bearer_token
from trinity.auth.schemas import EmptyRequest
from trinity.refresh.schemas import ActionReceipt, Run, RunList
from trinity.refresh.service import RefreshService

router = APIRouter(prefix='/api/v1/refresh-runs',tags=['refresh'])


def service(request):
    """Use an injected service or the API-owned lazy database pool."""
    supplied = request.app.state.refresh_service
    return supplied if supplied is not None else RefreshService(request.app.state.auth.database)


@router.post('',response_model=ActionReceipt,status_code=202,openapi_extra={
    'requestBody':{'required':True,'content':{'application/json':{'schema':EmptyRequest.model_json_schema()}}},
    'parameters':[{'name':'Idempotency-Key','in':'header','required':True,'schema':{'type':'string','format':'uuid'}}],
    'responses':{'200':{'description':'Original acceptance receipt replayed.'}},
})
async def start(request: Request, response: Response):
    """Return 202 only after all four acceptance effects commit; replay returns 200."""
    token = bearer_token(request)
    raw = await request.body()
    result = await run_in_threadpool(service(request).start,token,raw,
        request.headers.getlist('idempotency-key'),request.query_params.multi_items())
    response.status_code = 200 if result.replayed else 202
    response.headers['Location'] = result.status_url
    if not result.replayed:
        response.headers['Retry-After'] = '2'
    return result


@router.get('',response_model=RunList)
async def history(request: Request):
    """Read one bounded history page and the current admission context."""
    token = bearer_token(request)
    return await run_in_threadpool(service(request).history,token,request.query_params.multi_items(),
                                  body=await request.body())


@router.get('/{run_id}',response_model=Run)
async def detail(run_id: str, request: Request, response: Response):
    """Keep the returned URL useful before any worker starts."""
    token = bearer_token(request)
    result = await run_in_threadpool(service(request).detail,token,run_id,request.query_params.multi_items(),
                                    body=await request.body())
    response.headers['ETag'] = f'"run-{result.revision}"'
    return result


RECOVERY_PARAMETERS = [
    {'name':'run_id','in':'path','required':True,'schema':{'type':'string','format':'uuid'}},
    {'name':'Idempotency-Key','in':'header','required':True,'schema':{'type':'string','format':'uuid'}},
    {'name':'If-Match','in':'header','required':True,'schema':{'type':'string'}},
]


async def _recover(run_id, action, request, response):
    """Pass raw bounded input to the service and return its committed receipt."""
    result = await run_in_threadpool(service(request).recover, bearer_token(request),
        run_id, action, await request.body(), request.headers.getlist('idempotency-key'),
        request.headers.getlist('if-match'), request.query_params.multi_items())
    response.status_code = 202 if action == 'rerun' and not result.replayed else 200
    response.headers['Location'] = result.status_url
    if response.status_code == 202:
        response.headers['Retry-After'] = '2'
    return result


@router.post('/{run_id}/rerun', response_model=ActionReceipt, status_code=202, openapi_extra={
    'parameters': RECOVERY_PARAMETERS,
    'requestBody': {'required':True,'content':{'application/json':{'schema':EmptyRequest.model_json_schema()}}},
    'responses': {'200': {'description':'Original acceptance receipt replayed.',
                          'content':{'application/json':{'schema':{'$ref':'#/components/schemas/ActionReceipt'}}}}},
})
async def rerun(run_id: str, request: Request, response: Response):
    """Resolve a stopped failure and accept one linked complete new refresh."""
    return await _recover(run_id, 'rerun', request, response)


@router.delete('/{run_id}/warning', response_model=ActionReceipt,
               openapi_extra={'parameters': RECOVERY_PARAMETERS})
async def delete_warning(run_id: str, request: Request, response: Response):
    """Resolve a stopped failure without starting work or deleting history."""
    return await _recover(run_id, 'delete_warning', request, response)
