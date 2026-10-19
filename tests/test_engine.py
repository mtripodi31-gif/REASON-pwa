from datetime import timedelta
import pytest
from pydantic import ValidationError
from reason.engine import Engine, now, stamp

@pytest.fixture
def e(tmp_path): return Engine(tmp_path/'state.sqlite3')
def activate(e):
    card=e.example(); e.activate(card); return card
def fill(e): e.tick(); e.tick()

def test_paused_initial_and_no_hidden_positions(e):
    s=e.status(); assert s['paused'] and not s['positions'] and s['cash']==100000

def test_valid_card_fills_and_no_duplicates(e):
    c=activate(e); fill(e)
    s=e.status(); assert s['positions']['TQQQ']['qty']==142
    assert e.activate(c)['status']=='duplicate'
    for _ in range(5): e.tick()
    assert len(e.status()['orders'])==1

def test_changed_duplicate_rejected(e):
    c=activate(e); c['assessment']='changed'
    with pytest.raises(ValueError,match='different content'): e.activate(c)

def test_stale_packet_rejected(e):
    c=e.example(); e.control('pause')
    with pytest.raises(ValueError,match='Stale'):e.activate(c)

def test_stop_works_while_entries_paused(e):
    activate(e);fill(e);e.control('pause');e.quote('TQQQ',59);fill(e)
    assert not e.status()['positions']
    assert e.status()['paused']

def test_expired_entry_canceled_before_fill(e):
    activate(e);e.tick()
    def expire(s):s['plans']['TQQQ']['expires_at']=stamp(now()-timedelta(seconds=1))
    e.transaction(expire); e.tick()
    s=e.status(); assert not s['positions'];assert s['orders'][0]['status']=='canceled'

def test_existing_exits_survive_expiration(e):
    activate(e);fill(e)
    e.transaction(lambda s:s['plans']['TQQQ'].update(expires_at=stamp(now()-timedelta(seconds=1))))
    e.tick();assert e.status()['positions'];e.quote('TQQQ',86);fill(e)
    assert not e.status()['positions']

def test_unknown_evidence_and_duplicate_symbol_rejected(e):
    c=e.example(); c['decisions'][0]['evidence_ids']=['fake']
    with pytest.raises(ValueError,match='evidence'):e.activate(c)
    c=e.example();c['decisions']*=2
    with pytest.raises(ValueError,match='one decision'):e.activate(c)

def test_cash_only_and_no_negative_targets(e):
    c=e.example();d=c['decisions'][0];d['target_weight']=-.2
    with pytest.raises(ValidationError):e.activate(c)
    c=e.example();d=c['decisions'][0];d['target_weight']=.8
    second=dict(d,symbol='UPRO',exits={'stop':80,'take':100},evidence_ids=['sim:UPRO'])
    c['decisions'].append(second)
    with pytest.raises(ValueError,match='exceed'):e.activate(c)

def test_restart_persisted_intent_fills_once(e):
    activate(e);e.tick()
    recovered=Engine(e.db);fill(recovered)
    assert len(recovered.status()['orders'])==1
    assert recovered.status()['positions']['TQQQ']['qty']==142

def test_cash_reserved_across_pending_orders(e):
    c=e.example();c['decisions'][0]['target_weight']=.5
    d=dict(c['decisions'][0],symbol='UPRO',target_weight=.5,exits={'stop':80,'take':100},evidence_ids=['sim:UPRO'])
    c['decisions'].append(d);e.activate(c);e.tick()
    s=e.status();assert s['reserved_cash']<=s['cash']
    fill(e);assert e.status()['cash']>=0

def test_close_all_waits_for_fill(e):
    activate(e);fill(e);e.control('close-all');e.tick()
    assert e.status()['liquidation']
    e.tick();assert not e.status()['positions'] and not e.status()['liquidation']

def test_replacement_retains_unmentioned_exit(e):
    activate(e);fill(e);c=e.example();c['decisions']=[];e.activate(c)
    assert e.status()['plans']['TQQQ']['exits']['stop']==60
    e.quote('TQQQ',59);fill(e);assert not e.status()['positions']

def test_stale_quotes_block(e):
    c=e.example()
    e.transaction(lambda s:s['quotes']['TQQQ'].update(at=stamp(now()-timedelta(seconds=20))))
    with pytest.raises(ValueError,match='stale quote'):e.activate(c)

def test_conditional_trigger_and_price_gaps(e):
    c=e.example();c['decisions'][0]['entry']={'kind':'above','price':72}
    e.activate(c);e.tick();assert not e.status()['orders']
    e.quote('TQQQ',86);e.tick();assert not e.status()['orders']
    assert e.status()['plans']['TQQQ']['blocked']
    e.quote('TQQQ',73);fill(e);assert e.status()['positions']

def test_simulation_only(e):
    c=e.example();c['mode']='live'
    with pytest.raises(ValidationError):e.activate(c)
    c=e.example();c['unexpected']='do stuff'
    with pytest.raises(ValidationError):e.activate(c)

def test_bad_exit_rejected_atomically(e):
    c=e.example();c['decisions'][0]['exits']={'stop':80,'take':60}
    with pytest.raises(ValueError):e.activate(c)
    assert not e.status()['plans'] and e.status()['paused']

def test_nonfinite_and_boolean_prices_rejected(e):
    for price in [True,float('nan'),float('inf'),-1]:
        with pytest.raises(ValueError):e.quote('TQQQ',price)
