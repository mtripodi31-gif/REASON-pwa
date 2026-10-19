import copy
from datetime import datetime, timedelta, timezone

from reason.paper import ExecutionWorker, WorkerSettings, client_order_id, market_evidence


class Store:
    def __init__(self): self.data={}
    def get(self,c,k): return copy.deepcopy(self.data.get((c,k)))
    def put(self,c,k,v): self.data[(c,k)]=copy.deepcopy(v)
    def create(self,c,k,v):
        if (c,k) in self.data: return False
        self.put(c,k,v); return True


class Broker:
    def __init__(self):
        self.settings=WorkerSettings('project','paper','key','secret','iex',True)
        self.submitted=[];self.canceled=[]
        self.positions=[];self.orders=[]
    def snapshot(self):
        return ({'id':'paper','equity':'100000','cash':'100000'},copy.deepcopy(self.positions),copy.deepcopy(self.orders))
    def snapshots(self,symbols):
        return {s:{'latestTrade':{'p':100,'t':'2026-10-19T20:00:00Z'},'latestQuote':{'bp':99.9,'ap':100.1,'t':'2026-10-19T20:00:00Z'},'minuteBar':{'c':100,'t':'2026-10-19T20:00:00Z'},'dailyBar':{'c':100},'prevDailyBar':{'c':98}} for s in symbols}
    def by_client_id(self,cid): return next((o for o in self.submitted if o['client_order_id']==cid),None)
    def submit(self,payload):
        order=dict(payload,id='order-'+str(len(self.submitted)+1),status='accepted')
        self.submitted.append(order);return order
    def cancel(self,oid): self.canceled.append(oid)


def card(decisions,expires=None):
    now=datetime.now(timezone.utc)
    return {'card_id':'card-1','expires_at':(expires or now+timedelta(hours=1)).isoformat(),'decisions':decisions}


def decision(symbol='TQQQ',weight=.1):
    return {'symbol':symbol,'target_weight':weight,'entry':{'kind':'immediate','price':None},
            'exits':{'stop':90,'take':115},'evidence_ids':['evidence'],
            'advantage':'test','contrary':'test','invalidation':'test','horizon':'test'}


def activate(store,value):
    store.put('system','active_card',{'card':value,'status':'active','revision':'a'*64})
    store.put('system','control',{'entries_paused':False,'close_all':False,'generation':1})


def test_market_evidence_has_stable_ids_and_feed_label():
    evidence=market_evidence(Broker(),['TQQQ'])
    assert evidence[0]['id'].startswith('alpaca:iex:TQQQ:')
    assert evidence[0]['feed']=='iex' and evidence[0]['latest_quote']['ap']==100.1


def test_worker_submits_cash_only_bracket_with_deterministic_id():
    store,broker=Store(),Broker();activate(store,card([decision()]))
    result=ExecutionWorker(store,broker,'worker').tick()
    assert result['status']=='evaluated' and len(broker.submitted)==1
    order=broker.submitted[0]
    assert order['order_class']=='bracket' and order['side']=='buy' and order['qty']=='100'
    assert order['client_order_id']==client_order_id('card-1','TQQQ','buy','entry')
    ExecutionWorker(store,broker,'worker').tick()
    assert len(broker.submitted)==1


def test_pause_blocks_new_entry_but_allows_short_close():
    store,broker=Store(),Broker();broker.positions=[{'symbol':'QQQ','qty':'-5'}]
    activate(store,card([decision('QQQ',0)]));store.put('system','control',{'entries_paused':True,'close_all':False,'generation':1})
    ExecutionWorker(store,broker,'worker').tick()
    assert broker.submitted[0]['side']=='buy' and broker.submitted[0]['position_intent']=='buy_to_close'


def test_expiry_cancels_only_reason_orders():
    store,broker=Store(),Broker();broker.orders=[
        {'id':'one','symbol':'TQQQ','client_order_id':'reason-owned','status':'accepted'},
        {'id':'two','symbol':'SPY','client_order_id':'manual','status':'accepted'}]
    activate(store,card([decision()],datetime.now(timezone.utc)-timedelta(seconds=1)))
    result=ExecutionWorker(store,broker,'worker').tick()
    assert result['status']=='expired' and broker.canceled==['one']


def test_close_all_never_cancels_external_order_and_closes_both_sides():
    store,broker=Store(),Broker();broker.positions=[{'symbol':'SPY','qty':'3'},{'symbol':'QQQ','qty':'-2'}]
    broker.orders=[{'id':'one','symbol':'SPY','client_order_id':'reason-owned','status':'accepted'},
                   {'id':'two','symbol':'QQQ','client_order_id':'manual','status':'accepted'}]
    store.put('system','control',{'entries_paused':True,'close_all':True,'generation':7})
    ExecutionWorker(store,broker,'worker').tick()
    assert broker.canceled==['one']
    assert {(o['symbol'],o['side']) for o in broker.submitted}=={('SPY','sell'),('QQQ','buy')}
