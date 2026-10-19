import importlib
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('REASON_PREVIEW_TOKEN','test-access-code-at-least-24-chars')
    monkeypatch.setenv('REASON_DB',str(tmp_path/'api.sqlite3'))
    from reason import app
    importlib.reload(app)
    with TestClient(app.app) as c:yield c

AUTH={'Authorization':'Bearer test-access-code-at-least-24-chars'}
def test_auth_and_static(client):
    assert client.get('/').status_code==200
    assert client.get('/api/status').status_code==401
    assert client.get('/api/status',headers=AUTH).status_code==200
    assert client.get('/api/status',headers=AUTH).headers['cache-control']=='no-store'
    assert client.get('/.env').status_code==404

def test_ai_is_not_connected(client):
    assert client.post('/api/ai',headers=AUTH).status_code==409

def test_confirmation_and_origin(client):
    assert client.post('/api/control/close-all',json={},headers=AUTH).status_code==422
    assert client.post('/api/control/pause',json={},headers={**AUTH,'Origin':'https://evil.test'}).status_code==403

def test_card_validation_api(client):
    c=client.post('/api/example',headers=AUTH).json()
    assert client.post('/api/cards',json=c,headers=AUTH).status_code==200
    assert client.post('/api/cards',json=c,headers=AUTH).json()['status']=='duplicate'
    c=client.post('/api/example',headers=AUTH).json();c['decisions'][0]['target_weight']='one'
    assert client.post('/api/cards',json=c,headers=AUTH).status_code==422
