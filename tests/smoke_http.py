"""Run manually from project root: python tests/smoke_http.py"""
import json, os, socket, subprocess, sys, tempfile, time, urllib.request
with socket.socket() as sock:
    sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
with tempfile.TemporaryDirectory() as temp:
    env={**os.environ,'REASON_PREVIEW_TOKEN':'smoke-test-code-24-characters','REASON_DB':temp+'/state.sqlite3'}
    proc=subprocess.Popen([sys.executable,'-m','uvicorn','reason.app:app','--host','127.0.0.1','--port',str(port)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    base=f'http://127.0.0.1:{port}'
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen(base+'/healthz') as response:
                    assert json.load(response)['mode']=='simulation'
                break
            except OSError:time.sleep(.05)
        else:raise RuntimeError('Server did not start')
        for path in ['/','/app.js','/style.css','/sw.js','/manifest.webmanifest']:
            with urllib.request.urlopen(base+path) as response:assert response.status==200
        request=urllib.request.Request(base+'/api/status',headers={'Authorization':'Bearer '+env['REASON_PREVIEW_TOKEN']})
        with urllib.request.urlopen(request) as response:
            status=json.load(response);assert status['paused'] and status['equity']==100000
        print('HTTP smoke passed: dashboard, assets, health and authenticated account')
    finally:
        proc.terminate();proc.wait(timeout=5)
