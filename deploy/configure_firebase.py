"""Configure only reason-512120 using the current Cloud Shell user's credentials.
Never prints access tokens, provider secrets or private keys. Runtime config is local.
"""
import json, subprocess, sys, time, urllib.request, urllib.error, urllib.parse
from pathlib import Path
PROJECT='reason-512120'
BASE='https://firebase.googleapis.com/v1beta1/'

def call(url,method='GET',body=None):
    token=subprocess.check_output(['gcloud','auth','print-access-token'],text=True).strip()
    req=urllib.request.Request(url,data=json.dumps(body).encode() if body is not None else None,method=method,
        headers={'Authorization':'Bearer '+token,'X-Goog-User-Project':PROJECT,'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)

def finish(op):
    for _ in range(60):
        if op.get('done'):
            if op.get('error'):raise RuntimeError('Firebase operation failed: '+json.dumps(op['error']))
            return op.get('response',{})
        time.sleep(2)
        op=call(BASE+op['name'])
    raise RuntimeError('Firebase operation is still running. Rerun this script later.')

def domains(extra=()):
    url=f'https://identitytoolkit.googleapis.com/admin/v2/projects/{PROJECT}/config'
    config=call(url); values=config.get('authorizedDomains',[])
    for domain in ['reason.directlinemedical.app',PROJECT+'.firebaseapp.com',*extra]:
        if domain not in values:values.append(domain)
    call(url+'?updateMask=authorizedDomains','PATCH',{'authorizedDomains':values})

def rules():
    base=f'https://firebaserules.googleapis.com/v1/projects/{PROJECT}'
    source=Path(__file__).resolve().parent.parent/'firestore.rules'
    result=call(base+'/rulesets','POST',{'source':{'files':[{'name':'firestore.rules','content':source.read_text()}]}})
    name=f'projects/{PROJECT}/releases/cloud.firestore'
    release={'name':name,'rulesetName':result['name']}
    try:call(base+'/releases/cloud.firestore','PATCH',{'release':release,'updateMask':'rulesetName'})
    except urllib.error.HTTPError as e:
        if e.code!=404:raise
        call(base+'/releases','POST',release)

def main():
    if len(sys.argv)>1:
        domain=urllib.parse.urlparse(sys.argv[1]).hostname
        if not domain or not domain.endswith('.run.app'):raise ValueError('Expected the deployed Cloud Run HTTPS URL')
        domains([domain]);print('Cloud Run sign-in domain authorized.');return
    try:call(BASE+'projects/'+PROJECT)
    except urllib.error.HTTPError as e:
        if e.code!=404:raise
        finish(call(BASE+'projects/'+PROJECT+':addFirebase','POST',{}))
    apps=call(BASE+'projects/'+PROJECT+'/webApps').get('apps',[])
    matches=[a for a in apps if a.get('displayName')=='REASON Web']
    if len(matches)>1:raise RuntimeError('Multiple REASON Web apps found; choose one explicitly before proceeding.')
    app=matches[0] if matches else finish(call(BASE+'projects/'+PROJECT+'/webApps','POST',{'displayName':'REASON Web'}))
    config=call(BASE+app['name']+'/config')
    if config.get('projectId')!=PROJECT:raise RuntimeError('Firebase project mismatch')
    env={'GOOGLE_CLOUD_PROJECT':PROJECT,'REASON_OWNER_EMAIL':'tripodi@directlinemedical.app',
         'FIREBASE_WEB_API_KEY':config['apiKey'],'FIREBASE_WEB_APP_ID':config['appId']}
    target=Path(__file__).resolve().parent/'runtime.env.yaml'
    if target.exists():
        previous={k:json.loads(v.strip()) for line in target.read_text().splitlines() if ':' in line for k,v in [line.split(':',1)]}
        for key in ('REASON_OWNER_UID','REASON_ACCOUNT_ID'):
            if previous.get(key):env[key]=previous[key]
    target.write_text(''.join(k+': '+json.dumps(v)+'\n' for k,v in env.items()));target.chmod(0o600)
    domains();rules()
    print('Firebase Web app configured. Browser database access denied. Runtime config written locally.')

if __name__=='__main__':
    try:main()
    except urllib.error.HTTPError as e:
        # Google admin errors are useful; request headers and provider config aren't printed.
        print('Google configuration failed:',e.code,e.read().decode(),file=sys.stderr);sys.exit(1)
