import asyncio
import hmac
import json
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError
from .engine import Engine

ROOT=Path(__file__).resolve().parent.parent
TOKEN=os.environ.get('REASON_PREVIEW_TOKEN','')
if not TOKEN or len(TOKEN)<24:
    raise RuntimeError('Set REASON_PREVIEW_TOKEN to a random token of at least 24 characters')
# This build cannot accidentally become an authenticated production broker server.
if os.environ.get('K_SERVICE') or os.environ.get('REASON_BROKER','simulation')!='simulation':
    raise RuntimeError('Simulation preview only. Cloud production API/broker integration is not enabled.')
engine=Engine(os.environ.get('REASON_DB',str(ROOT/'data'/'preview.sqlite3')))
async def work():
    while True:
        try: await asyncio.to_thread(engine.tick,True)
        except Exception as e:
            # Never hide a failed worker behind a fresh heartbeat.
            def record(s):
                s['heartbeat']=None; s['paused']=True
                s['errors'].append(dict(at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),component='simulation-worker',message=type(e).__name__))
                s['errors']=s['errors'][-100:]
            await asyncio.to_thread(engine.transaction,record)
        await asyncio.sleep(2)
@asynccontextmanager
async def lifespan(app):
    task=asyncio.create_task(work())
    yield
    task.cancel()
    try: await task
    except asyncio.CancelledError: pass
app=FastAPI(title='REASON simulation preview',lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)

async def owner(request:Request):
    supplied=request.headers.get('authorization','')
    if not hmac.compare_digest(supplied,'Bearer '+TOKEN): raise HTTPException(401,'Preview access code required')
    # Browser mutations must originate from the same host. No cookie auth or CORS.
    origin=request.headers.get('origin')
    if origin and origin.rstrip('/')!=str(request.base_url).rstrip('/'):
        raise HTTPException(403,'Cross-origin access denied')

@app.middleware('http')
async def secure(request,call_next):
    if request.method=='POST':
        if int(request.headers.get('content-length','0'))>131072: return JSONResponse({'detail':'Card exceeds 128 KiB'},413)
        body=await request.body()
        if len(body)>131072:return JSONResponse({'detail':'Card exceeds 128 KiB'},413)
    response=await call_next(request)
    response.headers['Cache-Control']='no-store' if request.url.path.startswith('/api') else 'no-cache'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    return response

@app.exception_handler(ValueError)
async def bad(request,exc): return JSONResponse({'detail':str(exc)},422)
@app.exception_handler(ValidationError)
async def invalid(request,exc):
    return JSONResponse({'detail':[dict(field='.'.join(map(str,e['loc'])),message=e['msg']) for e in exc.errors()]},422)
@app.get('/healthz')
def health(): return {'status':'ok','mode':'simulation'}
@app.get('/api/status',dependencies=[Depends(owner)])
def status(): return engine.status()
@app.get('/api/packet',dependencies=[Depends(owner)])
def packet(): return engine.packet()
@app.get('/api/schema',dependencies=[Depends(owner)])
def schema():
    from .engine import Card
    return Card.model_json_schema()
@app.post('/api/example',dependencies=[Depends(owner)])
def example(): return engine.example()
@app.post('/api/cards',dependencies=[Depends(owner)])
async def cards(request:Request):
    try: raw=await request.json()
    except Exception: raise HTTPException(422,'Paste a JSON object')
    return engine.activate(raw)
@app.post('/api/control/{action}',dependencies=[Depends(owner)])
async def control(action:str,request:Request):
    body=await request.json()
    if action=='close-all' and body.get('confirmation')!='CLOSE SIMULATED POSITIONS':
        raise HTTPException(422,'Explicit close-all confirmation required')
    return engine.control(action)
@app.post('/api/quote',dependencies=[Depends(owner)])
async def quote(request:Request):
    b=await request.json(); return engine.quote(b.get('symbol'),b.get('price'))
@app.post('/api/ai',dependencies=[Depends(owner)])
def ai(): raise HTTPException(409,'Paid AI is not connected in this preview. No call or charge occurred.')
@app.get('/')
def index(): return FileResponse(ROOT/'web'/'index.html')
@app.get('/{asset}')
def static(asset:str):
    if asset not in ('app.js','style.css','sw.js','manifest.webmanifest','icon.svg'): raise HTTPException(404)
    return FileResponse(ROOT/'web'/asset)
