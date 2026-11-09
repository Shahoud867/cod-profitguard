import json,sqlite3,uuid
import pytest
from app.db import connect,row,rows,js
from app.domain import assess,realized,TRANSITIONS
from app.seed import seed,checksum

def payload(**kw): return {'external_id':'TEST-'+str(uuid.uuid4())[:10],'customer':'Fictional tester','city':'Islamabad','address':'Fictional House 12, Demo Road','cod':450000,'cogs':210000,'weight_g':500,'address_quality':95,**kw}
def new(api,**kw):
    r=api.post('/orders',payload(**kw));assert r.status_code==200,r.text;return r.json()
def ready(api):
    o=new(api);r=api.post('/orders/'+o['id']+'/verification',{'response':'confirm','approved':True});assert r.status_code==200,r.text;return r.json()
def book(api):
    o=ready(api);d=api.get('/orders/'+o['id']).json();q=next(q for q in d['quotes'] if q['eligible'])
    r=api.post('/orders/'+o['id']+'/override-courier',{'courier_id':q['id'],'reason':'Manager approved synthetic route','approved':True});assert r.status_code==200,r.text;return r.json()['order']
def tracking(api,o,target,event_id=None): return api.post('/orders/'+o['id']+'/tracking',{'target':target,'approved':True,'event_id':event_id or str(uuid.uuid4())})

def test_login_session_and_csrf(api):
    assert api.get('/auth/me').json()['role']=='owner'
    assert 'HttpOnly' in api.c.cookies.jar._cookies['testserver.local']['/']['pg_session']._rest
    r=api.c.post('/api/v1/orders',json=payload());assert r.status_code==403
    assert api.post('/orders',payload(),headers={'Origin':'https://evil.example'}).status_code==403

def test_missing_idempotency_key(api):
    token=api.get('/auth/me').json()['csrf']
    assert api.c.post('/api/v1/orders',json=payload(),headers={'X-CSRF-Token':token}).status_code==400

def test_import_validation_duplicates_dryrun(api):
    text='external_id,city,address,cod_pkr,weight_g\nCSV-1,Islamabad,Fictional block street,4500,500\nCSV-1,Islamabad,Fictional street,4500,500\nBAD,Lahore,x,-1,0\nLIMIT,Karachi,Fictional lane block,200001,500'
    first=api.post('/orders/import',{'csv_text':text,'dry_run':True}).json();assert len(first['accepted'])==2;assert len(first['duplicates'])==1;assert len(first['rejected'])==1
    count=api.get('/orders').json()['total']
    second=api.post('/orders/import',{'csv_text':text}).json();assert len(second['accepted'])==2;assert api.get('/orders').json()['total']==count+2
    third=api.post('/orders/import',{'csv_text':text}).json();assert len(third['accepted'])==0
    limit=next(x for x in second['accepted'] if x['external_id']=='LIMIT');assert limit['warning']

def test_exact_csv_decimal(api):
    p={'csv_text':'external_id,city,address,cod_pkr,weight_g\nPAISA,Islamabad,Fictional block street,700.01,500\nSUBPAISA,Lahore,Fictional block,700.001,500'}
    r=api.post('/orders/import',p).json();assert len(r['accepted'])==1;assert len(r['rejected'])==1
    o=api.get('/orders/'+r['accepted'][0]['id']).json()['order'];assert o['cod']==70001

def test_idempotent_atomic_command_and_key_conflict(api):
    p=payload();a=api.post('/orders',p,key='one');b=api.post('/orders',p,key='one');assert a.json()==b.json()
    assert api.get('/orders?q='+p['external_id']).json()['total']==1
    assert api.post('/orders',payload(),key='one').status_code==409
    assert api.post('/orders',p).status_code==409

@pytest.mark.parametrize('response,target',[('confirm','ready_to_ship'),('cancel','cancelled_before_ship'),('no_response','hold_review'),('address_change','ready_to_ship')])
def test_verification_workflows(api,response,target):
    o=new(api);r=api.post('/orders/'+o['id']+'/verification',{'response':response,'address':'Fictional corrected House 18 Demo Street','approved':True})
    assert r.status_code==200,r.text;assert r.json()['status']==target
    assert r.json()['service_cost']==1500
    if response=='no_response': assert r.json()['risk_score']==0

def test_risk_explanations_false_hold_and_release(api):
    o=new(api,address_quality=40);r=api.post('/orders/'+o['id']+'/verification',{'response':'confirm','approved':True});assert r.json()['status']=='hold_review'
    d=api.get('/orders/'+o['id']).json();assert d['risk']['score']==35;assert d['risk']['factors'][0]['points']==35
    result=api.post('/orders/'+o['id']+'/release',{'reason':'Manager checked legitimate address','approved':True});assert result.json()['status']=='ready_to_ship'

def test_policy_limit_blocks_dispatch_after_override(api):
    o=new(api,cod=20000001)
    api.post('/orders/'+o['id']+'/verification',{'response':'confirm','approved':True})
    r=api.post('/orders/'+o['id']+'/release',{'reason':'Attempt policy override blocked','approved':True});assert r.status_code==409
    assert api.get('/orders/'+o['id']).json()['order']['status']=='hold_review'

def test_unknown_zone_no_courier(api):
    o=new(api,city='Unknown City');quotes=api.get('/orders/'+o['id']).json()['quotes'];assert not any(q['eligible'] for q in quotes)

def test_no_approval_no_state_change(api):
    o=new(api);assert api.post('/orders/'+o['id']+'/verification',{'response':'confirm','approved':False}).status_code==422
    assert api.get('/orders/'+o['id']).json()['order']['status']=='verification_pending'

def test_held_order_cannot_book(api):
    o=new(api);api.post('/orders/'+o['id']+'/verification',{'response':'no_response','approved':True});q=api.get('/orders/'+o['id']).json()['quotes'][0]
    assert api.post('/orders/'+o['id']+'/override-courier',{'courier_id':q['id'],'reason':'Unsafe held booking attempt','approved':True}).status_code==409

def test_capacity_optimizer_and_feasible_baselines(api):
    r=api.post('/demo/scenarios/E/run',{'approved':True,'seed':5});assert r.status_code==200,r.text;p=r.json()['proposal']
    assert p['order_count']==100;assert p['assigned']==100;assert p['unassigned']==0
    assert all(x['used']<=x['available'] for x in p['capacity'])
    assert p['optimized_cost']<=p['baseline_cheapest']['expected_cost'];assert p['optimized_cost']<=p['baseline_default']['expected_cost']
    for a in p['allocations']:
        q=next(q for q in a['alternatives'] if q['id']==a['courier_id']);assert q['eligible']
    r=api.post('/routing/commit',{'proposal_id':p['id'],'approved':True});assert r.status_code==200,r.text;assert r.json()['booked']==100
    assert api.post('/routing/commit',{'proposal_id':p['id'],'approved':True}).status_code==409

def test_capacity_shortfall_and_missing_rate(api):
    for q in api.get('/couriers').json()['items']:
        api.put('/couriers/'+q['id'],{'capacity':1,'forward':q['forward'],'reverse':None if q['code']=='SWF' else q['reverse'],'cod_fee':q['cod_fee'],'active':True})
    p=api.post('/demo/scenarios/E/run',{'approved':True,'seed':4}).json()['proposal'];assert p['assigned']<=3;assert p['unassigned']>=97;assert p['hypothetical_difference'] is None
    for a in p['allocations']:
        swf=next(q for q in a['alternatives'] if q['code']=='SWF');assert not swf['eligible'];assert any('unknown' in s for s in swf['excluded_reasons'])

def test_stale_proposal_rolls_back_batch(api):
    a=ready(api);b=ready(api);p=api.post('/routing/preview',{'order_ids':[a['id'],b['id']]}).json()
    # A quote change invalidates the full proposal without partial bookings.
    q=api.get('/couriers').json()['items'][0]
    api.put('/couriers/'+q['id'],{'capacity':q['capacity'],'forward':q['forward']+100,'reverse':q['reverse'],'cod_fee':q['cod_fee'],'active':True})
    assert api.post('/routing/commit',{'proposal_id':p['id'],'approved':True}).status_code==409
    assert api.get('/orders/'+a['id']).json()['order']['status']=='ready_to_ship'

def test_tracking_state_machine_duplicate_and_out_of_order(api):
    o=book(api);assert tracking(api,o,'delivered').status_code==409
    event_id=str(uuid.uuid4());assert tracking(api,o,'in_transit',event_id).status_code==200
    assert tracking(api,o,'in_transit',event_id).json()['duplicate'] is True
    for i in range(10):
        r=api.post('/orders/'+o['id']+'/tracking',{'target':'out_for_delivery','event_id':'out-'+str(i),'occurred_at':f'2025-01-{10-i:02}T00:00:00Z','approved':True})
        assert r.json()['review_required']
    d=api.get('/orders/'+o['id']).json();assert d['order']['status']=='in_transit';assert len([e for e in d['events'] if e['kind']=='out_of_order_review'])==10
    assert [e['occurred_at'] for e in d['events']]==sorted(e['occurred_at'] for e in d['events'])

def test_ndr_rescue_cost_and_consent(api):
    o=book(api)
    for target in ['in_transit','out_for_delivery','NDR']: assert tracking(api,o,target).status_code==200
    p={'action':'retry','reason':'Customer requested corrected retry','approved':True,'customer_approved':False}
    assert api.post('/orders/'+o['id']+'/rescue',p).status_code==422
    p['customer_approved']=True;r=api.post('/orders/'+o['id']+'/rescue',p);assert r.status_code==200;assert r.json()['status']=='reattempt'
    for target in ['out_for_delivery','delivered']: assert tracking(api,o,target).status_code==200
    d=api.get('/orders/'+o['id']).json();o=d['order'];assert o['actual_cost']==o['forward']+o['cod_fee']+3500
    assert o['revenue']==o['cod'];assert d['realized_margin']==o['cod']-o['cogs']-o['actual_cost']-o['packaging']-o['marketing']-o['service_cost']

def test_return_restocks_cogs(api):
    o=book(api)
    for target in ['in_transit','NDR','RTO_initiated','returned']: assert tracking(api,o,target).status_code==200
    d=api.get('/orders/'+o['id']).json();o=d['order'];assert o['revenue']==0;assert o['actual_cost']==o['forward']+o['reverse']
    assert d['realized_margin']==-o['actual_cost']-o['packaging']-o['marketing']-o['service_cost']

def test_finance_detects_and_resolves_without_changing_sales(api):
    r=api.post('/demo/scenarios/G/run',{'approved':True});assert r.status_code==200,r.text
    s=next(x for x in api.get('/finance').json()['items'] if x['id']==r.json()['cases'][0]['statement_id'])
    before=api.get('/orders/'+s['order_id']).json()['order']
    bad=api.post('/finance/'+s['id']+'/resolve',{'actual':s['expected']-2,'reason':'Review incorrect synthetic deduction','approved':True});assert bad.json()['status']=='disputed'
    good=api.post('/finance/'+s['id']+'/resolve',{'actual':s['expected']-1,'reason':'One paisa tolerance accepted','approved':True});assert good.json()['status']=='reconciled'
    after=api.get('/orders/'+s['order_id']).json()['order'];assert before['revenue']==after['revenue'];assert before['actual_cost']==after['actual_cost']

def test_statement_import_unknown_reference(api):
    s=api.get('/finance').json()['items'][0]
    text=f'booking_ref,actual_pkr\n{s["booking_ref"]},{s["expected"]/100:.2f}\nSIM-UNKNOWN,300'
    r=api.post('/reconciliation/import',{'csv_text':text}).json();assert len(r['accepted'])==1;assert len(r['rejected'])==1

def test_analytics_matches_source_ledger(api):
    a=api.get('/analytics?days=365').json()
    with connect(str(api.db)) as c:
        data=rows(c,'SELECT * FROM orders WHERE tenant_id="t1"')
    assert a['placed']==len(data);assert sum(a['counts'].values())==a['placed'];assert a['revenue']==sum(o['revenue'] for o in data);assert a['realized_contribution']==sum(realized(o) or 0 for o in data)
    assert sum(x['realized'] for x in a['cities'])==a['realized_contribution'];assert sum(x['shipping'] for x in a['couriers'])==a['shipping_cost']

@pytest.mark.parametrize('role',['viewer','csr','finance'])
def test_roles_cannot_commit_or_change_settings(api,role):
    api.login(role);assert api.post('/routing/preview',{}).status_code==403
    assert api.put('/settings',{'default_courier':'SWF','sla_penalty':18000,'handling':1200,'retention_days':180,'consent_required':True}).status_code==403
    assert api.post('/demo/reset',{'confirmation':'RESET SYNTHETIC DATA'}).status_code==403

def test_csr_and_finance_boundaries(api):
    o=new(api);s=api.get('/finance').json()['items'][0]
    api.login('csr');assert api.post('/orders/'+o['id']+'/verification',{'response':'confirm','approved':True}).status_code==200
    assert api.post('/finance/'+s['id']+'/resolve',{'actual':s['expected'],'reason':'Unauthorized CSR finance operation','approved':True}).status_code==403
    api.login('finance');assert api.post('/orders',payload()).status_code==403
    assert api.post('/finance/'+s['id']+'/resolve',{'actual':s['expected'],'reason':'Finance reviewed remittance evidence','approved':True}).status_code==200

def test_tenant_isolation_all_boundaries(api):
    o=ready(api);s=api.get('/finance').json()['items'][0];q=api.get('/couriers').json()['items'][0];p=api.post('/routing/preview',{'order_ids':[o['id']]}).json()
    api.login('other');assert api.get('/orders/'+o['id']).status_code==404
    assert api.get('/orders?q='+o['external_id']).json()['total']==0
    assert api.post('/orders/'+o['id']+'/risk').status_code==404
    assert api.post('/finance/'+s['id']+'/resolve',{'actual':s['expected'],'reason':'Cross tenant attempt is blocked','approved':True}).status_code==404
    assert api.put('/couriers/'+q['id'],{'capacity':40,'forward':20000,'reverse':10000,'cod_fee':3000}).status_code==404
    assert api.post('/routing/commit',{'proposal_id':p['id'],'approved':True}).status_code==404

def test_audit_append_only(api):
    o=new(api)
    with connect(str(api.db)) as c:
        assert row(c,'SELECT count(*) n FROM audit WHERE tenant_id="t1" AND action="order.create"')['n']==1
        with pytest.raises(sqlite3.IntegrityError):c.execute('DELETE FROM audit WHERE tenant_id="t1"')
        with pytest.raises(sqlite3.IntegrityError):c.execute('UPDATE audit SET actor="attacker" WHERE tenant_id="t1"')

def test_retryable_connector_survives_and_drains(api):
    o=new(api);j=api.post('/jobs/queue',{'order_id':o['id'],'inject_timeout':True}).json()
    first=api.post('/demo/clock',{'hours':1}).json();assert first['processed'][0]['status']=='retry'
    second=api.post('/demo/clock',{'hours':1}).json();assert second['processed'][0]['status']=='completed'
    assert api.get('/orders/'+o['id']).json()['order']['status']=='verification_pending'

@pytest.mark.parametrize('key',list('ABCDEFGHI'))
def test_every_demo_scenario_executes(api,key):
    before=api.get('/orders').json()['total'];r=api.post('/demo/scenarios/'+key+'/run',{'approved':True,'seed':20261108})
    assert r.status_code==200,r.text;d=r.json();assert d['simulated'];assert d['order_ids'];assert api.get('/orders').json()['total']>before
    if key=='H':assert d['order']['status'] in {'delivered','returned'};assert isinstance(d['realized_contribution'],int)
    if key=='I':assert any(x['kind']=='human_override' for x in api.get('/orders/'+d['order_ids'][0]).json()['events'])

def test_reproducible_seed_and_foreign_keys(tmp_path):
    hashes=[]
    for i in range(2):
        with connect(str(tmp_path/f'{i}.db')) as c:
            from app.db import migrate
            migrate(c);seed(c,total=120);hashes.append(checksum(c));assert not rows(c,'PRAGMA foreign_key_check')
    assert hashes[0]==hashes[1]

def test_csv_formula_sanitization(api):
    o=new(api,city='=formula')
    text=api.c.get('/api/v1/orders/export').text
    assert "'=formula" in text;assert 'SIMULATED DATA' in text

def test_opt_out_blocks_simulated_contact(api):
    o=new(api)
    with connect(str(api.db)) as c:c.execute('UPDATE customers SET opt_out_at=? WHERE id=?',('2026-11-08T05:00:00+00:00',o['customer_id']));c.commit()
    assert api.post('/orders/'+o['id']+'/verification',{'response':'confirm','approved':True}).status_code==409

def test_unauthenticated_and_rate_limit(env):
    client,path=env;assert client.get('/api/v1/orders').status_code==401
    for i in range(10):assert client.post('/api/v1/auth/login',json={'email':'owner@profitguard.example','password':'wrong'}).status_code==401
    assert client.post('/api/v1/auth/login',json={'email':'owner@profitguard.example','password':'wrong'}).status_code==429

def test_privacy_action_is_tenant_safe_and_blocks_contact(api):
    o=new(api);api.login('csr')
    assert api.post('/customers/'+o['customer_id']+'/privacy',{'action':'anonymize','reason':'Fictional privacy request received','approved':True}).status_code==403
    api.login('owner');r=api.post('/customers/'+o['customer_id']+'/privacy',{'action':'anonymize','reason':'Fictional privacy request received','approved':True});assert r.status_code==200
    d=api.get('/orders/'+o['id']).json()['order'];assert d['customer']=='Anonymized fictional customer';assert d['opt_out_at'];assert d['address']=='Removed by demo privacy request'
    assert api.post('/orders/'+o['id']+'/verification',{'response':'confirm','approved':True}).status_code==409

def test_pending_estimate_includes_shipping_and_unpriced_is_explicit(api):
    o=new(api);assert o['expected_cost']>0
    d=api.get('/orders/'+o['id']).json();assert d['estimated_margin']==o['cod']-o['cogs']-o['expected_cost']-o['packaging']-o['marketing']
    u=new(api,city='Unpriced Lane');assert api.get('/orders/'+u['id']).json()['estimated_margin'] is None

def test_simulation_adapter_is_reproducible_and_can_fail():
    from app.connectors import SimulationCourier
    adapter=SimulationCourier();assert adapter.outcome(6)==adapter.outcome(6)
    assert adapter.outcome(1,10000).code=='NDR';assert adapter.outcome(1,0).code=='delivered'
    with pytest.raises(TimeoutError):adapter.poll(True)

def test_owner_reset_preserves_other_tenant_and_audit(api):
    o=new(api)
    with connect(str(api.db)) as c:
        before=row(c,'SELECT count(*) n FROM orders WHERE tenant_id="t2"')['n']
        audits=row(c,'SELECT count(*) n FROM audit WHERE tenant_id="t1"')['n']
    r=api.post('/demo/reset',{'confirmation':'RESET SYNTHETIC DATA','seed':20261108});assert r.status_code==200,r.text
    assert api.get('/orders').json()['total']==6200;assert api.get('/orders/'+o['id']).status_code==404
    with connect(str(api.db)) as c:
        assert row(c,'SELECT count(*) n FROM orders WHERE tenant_id="t2"')['n']==before
        assert row(c,'SELECT count(*) n FROM audit WHERE tenant_id="t1"')['n']>audits
        assert not rows(c,'PRAGMA foreign_key_check')

def test_expired_session_is_rejected(api):
    with connect(str(api.db)) as c:c.execute('UPDATE sessions SET expires_at="2020-01-01T00:00:00+00:00"');c.commit()
    assert api.get('/orders').status_code==401
