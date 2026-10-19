from reason.engine import Engine

def test_pause_pending_buy_then_resume(tmp_path):
    e=Engine(tmp_path/'state.sqlite3');e.activate(e.example());e.tick()
    e.control('pause');e.tick()
    assert not e.status()['positions']
    e.control('resume');e.tick();e.tick()
    s=e.status()
    assert s['positions']['TQQQ']['qty']==142
    assert [o['status'] for o in s['orders']]==['canceled','filled']

def test_close_all_cancels_pending_exit(tmp_path):
    e=Engine(tmp_path/'state.sqlite3');e.activate(e.example());e.tick();e.tick()
    e.quote('TQQQ',59);e.tick()
    e.control('close-all');e.tick();e.tick()
    assert not e.status()['positions']
    assert len([o for o in e.status()['orders'] if o['side']=='sell' and o['status']=='filled'])==1
