import copy
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
import pytest
from reason.cloud import Settings, create_app, PaperReader, BrokerUnavailable

class Store:
    def __init__(self):self.data={}
    def get(self,c,k):return copy.deepcopy(self.data.get((c,k)))
    def put(self,c,k,v):self.data[(c,k)]=copy.deepcopy(v)
    def create(self,c,k,v):
        if (c,k) in self.data:return False
        self.put(c,k,v);return True
    def recent(self,c,limit=20):return sorted([copy.deepcopy(v) for (col,k),v in self.data.items() if col==c],key=lambda v:v['at'],reverse=True)[:limit]
class Broker:
    configured=True
    def snapshot(self):return dict(at=datetime.now(timezone.utc).isoformat(),account={'id':'paper-account','cash':'100000','equity':'100000'},positions=[],orders=[],revision='a'*64,changing_during_read=False)

@pytest.fixture
def setup():
    cfg=Settings('reason-512120','owner@example.com','public-web-key','public-app-id',alpaca_account='paper-account')
    store=Store();broker=Broker()
    def verify(token):
        if token=='invalid':raise ValueError('Invalid token')
        return dict(uid='owner-id',email='owner@example.com' if token!='other' else 'other@example.com',email_verified=token!='unverified',firebase={'sign_in_provider':'google.com' if token!='password' else 'password'})
    app=create_app(cfg,store,verify,broker)
    with TestClient(app) as client:yield client,store,broker

AUTH={'Authorization':'Bearer owner'}
def make_card(client):
    p=client.post('/api/packet',json={},headers=AUTH).json();t=datetime.now(timezone.utc)
    return dict(schema_version='reason.trade-card.v1',card_id='test',mode='paper',account_id='paper-account',packet_id=p['packet_id'],revision=p['revision'],generated_at=t.isoformat(),activate_before=(t+timedelta(minutes=5)).isoformat(),expires_at=(t+timedelta(hours=1)).isoformat(),sessions=['regular'],assessment='No change; no market evidence.',concentration_reason='No changes.',decisions=[])

def test_public_shell_and_only_public_config(setup):
    c,_,_=setup
    assert c.get('/').status_code==200
    cfg=c.get('/api/config').json()
    assert cfg['firebase']['projectId']=='reason-512120'
    assert 'secret' not in str(cfg).lower()
    assert c.get('/healthz').json()['execution_enabled'] is False

def test_owner_google_only(setup):
    c,_,_=setup
    assert c.get('/api/status').status_code==401
    for token,status in [('other',403),('unverified',403),('password',403),('invalid',401),('owner',200)]:
        assert c.get('/api/status',headers={'Authorization':'Bearer '+token}).status_code==status

def test_refresh_persists_only_real_broker_snapshot(setup):
    c,s,_=setup
    before=c.get('/api/status',headers=AUTH).json()
    assert before['snapshot'] is None and before['worker_running'] is False
    assert c.post('/api/refresh',json={},headers=AUTH).status_code==200
    assert s.get('system','paper_snapshot')['account']['id']=='paper-account'
    assert c.get('/api/status',headers=AUTH).headers['cache-control']=='no-store'

def test_no_credentials_no_request(setup):
    c,_,b=setup;b.configured=False
    assert c.post('/api/refresh',json={},headers=AUTH).status_code==409

def test_broker_failure_sanitized_and_recorded(setup):
    c,s,b=setup
    def broken():raise BrokerUnavailable('Connection unavailable')
    b.snapshot=broken
    assert c.post('/api/refresh',json={},headers=AUTH).status_code==502
    assert len(s.recent('errors'))==1

def test_packet_lists_missing_evidence(setup):
    c,_,_=setup;p=c.post('/api/packet',json={},headers=AUTH).json()
    assert not p['evidence'] and p['missing'] and p['schema']['properties']

def test_draft_never_executes_and_duplicate_safe(setup):
    c,_,_=setup;card=make_card(c)
    assert c.post('/api/cards',json=card,headers=AUTH).json()['status']=='draft_not_active'
    assert c.post('/api/cards',json=card,headers=AUTH).json()['status']=='duplicate'
    card['assessment']='changed'
    assert c.post('/api/cards',json=card,headers=AUTH).status_code==409

def test_no_ai_or_execution_endpoints(setup):
    c,_,_=setup
    assert c.post('/api/ai',json={},headers=AUTH).status_code==409
    assert c.post('/api/control/resume',json={},headers=AUTH).status_code==409

def test_reject_unknown_packet_live_and_malformed_time(setup):
    c,_,_=setup
    card=make_card(c);card['mode']='live'
    assert c.post('/api/cards',json=card,headers=AUTH).status_code==422
    card=make_card(c);card['packet_id']='b'*32
    assert c.post('/api/cards',json=card,headers=AUTH).status_code==409
    card=make_card(c);card['expires_at']='tomorrow'
    assert c.post('/api/cards',json=card,headers=AUTH).status_code==422

def test_body_size_bound_and_untrusted_html_not_rendered_by_server(setup):
    c,_,_=setup
    assert c.post('/api/cards',content='x'*131073,headers=AUTH).status_code==413
    assert c.get('/.env').status_code==404

def test_mid_read_account_change_blocks_packet(setup):
    c,_,b=setup;original=b.snapshot
    def changed():return dict(original(),changing_during_read=True)
    b.snapshot=changed
    assert c.post('/api/packet',json={},headers=AUTH).status_code==409

def test_paper_reader_host_and_allowlist():
    cfg=Settings('project','owner','key','app',alpaca_account='paper')
    b=PaperReader(cfg)
    assert b.HOST=='https://paper-api.alpaca.markets'
    with pytest.raises(ValueError):b.get('/v2/orders/anything')
    with pytest.raises(BrokerUnavailable):b.get('/v2/account')
    assert not hasattr(b,'submit_order')

def test_uid_pin():
    cfg=Settings('project','owner@example.com','key','app',owner_uid='one')
    app=create_app(cfg,Store(),lambda token:dict(uid='two',email='owner@example.com',email_verified=True,firebase={'sign_in_provider':'google.com'}),Broker())
    with TestClient(app) as c:assert c.get('/api/me',headers=AUTH).status_code==403

def test_missing_cloud_configuration_fails_closed(monkeypatch):
    for env in ('GOOGLE_CLOUD_PROJECT','REASON_OWNER_EMAIL','FIREBASE_WEB_API_KEY','FIREBASE_WEB_APP_ID'):monkeypatch.delenv(env,raising=False)
    with pytest.raises(RuntimeError):Settings.env()
