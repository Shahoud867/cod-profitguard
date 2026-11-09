"""Deterministic cooperating agents, exact economics and approved state machine."""
import json
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from .db import insert, uid, js, now, row, rows
CITIES = ['Islamabad','Rawalpindi','Lahore','Karachi','Faisalabad','Peshawar','Multan','Quetta']
TERMINAL = {'delivered','returned','cancelled_before_ship','lost_damaged_dispute'}
TRANSITIONS = {
 'imported':{'verification_pending'},'verification_pending':{'confirmed','hold_review','cancelled_before_ship'},
 'hold_review':{'confirmed','cancelled_before_ship'},'confirmed':{'ready_to_ship','hold_review','cancelled_before_ship'},
 'ready_to_ship':{'booked_simulated','hold_review','cancelled_before_ship'},
 'booked_simulated':{'in_transit','lost_damaged_dispute'},'in_transit':{'out_for_delivery','NDR','lost_damaged_dispute'},
 'out_for_delivery':{'delivered','NDR','lost_damaged_dispute'},'NDR':{'reattempt','RTO_initiated'},
 'reattempt':{'out_for_delivery','NDR'},'RTO_initiated':{'returned'}}
AGENTS = ['Intake','Verification','Risk','Courier','Allocator','Monitor','Rescue','Finance']

def time_at(c,t): return row(c,'SELECT virtual_time FROM tenants WHERE id=?',(t,))['virtual_time']
def audit(c,t,actor,action,entity=None,payload=None,request_id='system'):
    insert(c,'audit',id=uid(),tenant_id=t,actor=actor,action=action,entity_id=entity,payload=js(payload or {}),created_at=now(),request_id=request_id)
def event(c,t,o,kind,old=None,new=None,payload=None,at=None,event_id=None,source='simulation'):
    insert(c,'events',id=event_id or uid(),tenant_id=t,order_id=o,kind=kind,from_state=old,to_state=new,payload=js(payload or {}),occurred_at=at or time_at(c,t),ingested_at=now(),source=source)
def trace(c,t,o,agent,inputs,outputs,at=None):
    insert(c,'agent_runs',id=uid(),tenant_id=t,order_id=o,agent=agent,input=js(inputs),output=js(outputs),rule_version='rules-v1 / simulated',status='completed',created_at=at or time_at(c,t),correlation_id=o or uid())
def get_order(c,t,o):
    value = row(c,'SELECT o.*,c.name customer,c.contact,c.consent_source,c.opt_out_at FROM orders o JOIN customers c ON c.id=o.customer_id AND c.tenant_id=o.tenant_id WHERE o.tenant_id=? AND o.id=?',(t,o))
    if not value: raise HTTPException(404,'Order not found')
    return value

def assess(o):
    factors=[]
    if o['address_quality'] < 65: factors.append({'factor':'Incomplete address','points':35,'action':'Confirm a landmark and street before dispatch'})
    if o['cod'] > 1200000: factors.append({'factor':'High COD exposure','points':20,'action':'Human confirmation recommended'})
    if o['cod'] > 20000000: factors.append({'factor':'COD policy limit exceeded','points':100,'action':'Do not dispatch; policy review required'})
    if o['weight_g']>3000: factors.append({'factor':'Heavy parcel; cost exposure','points':10,'action':'Compare weight surcharges'})
    if o['city'] not in CITIES: factors.append({'factor':'Unrecognized serviceability zone','points':40,'action':'Correct city or arrange an approved fallback'})
    score=min(100,sum(x['points'] for x in factors))
    return {'score':score,'tier':'review' if score>=35 else 'medium' if score>=20 else 'low','factors':factors,'uncertainty':'Rule-based review priority, not a fraud probability or validated delivery prediction. Non-response alone adds zero points.','hold_opportunity_cost':(o['cod']-o['cogs'])*1000//10000,'recommendation':'Human review before release' if score>=35 else 'Eligible for human-approved routing'}

def save_risk(c,t,o):
    a=assess(o)
    c.execute('UPDATE orders SET risk_score=?,risk_reasons=? WHERE tenant_id=? AND id=?',(a['score'],js(a),t,o['id']))
    trace(c,t,o['id'],'Risk',{'address_quality':o['address_quality'],'cod_paisa':o['cod'],'weight_g':o['weight_g'],'city':o['city']},a)
    return a

def advance(c,t,o,target,actor='system',payload=None,at=None,event_id=None):
    old=o['status']
    if target not in TRANSITIONS.get(old,set()): raise HTTPException(409,f'Cannot move {old} → {target}')
    if target=='ready_to_ship' and (o['cod']>20000000 or o['city'] not in CITIES): raise HTTPException(409,'Policy limit or unknown delivery zone requires correction')
    if target=='cancelled_before_ship':
        c.execute('UPDATE orders SET packaging=0 WHERE id=? AND tenant_id=?',(o['id'],t))
    if target=='delivered':
        c.execute('UPDATE orders SET revenue=cod,actual_cost=forward+cod_fee+CASE WHEN status="out_for_delivery" THEN actual_cost ELSE 0 END WHERE id=? AND tenant_id=?',(o['id'],t))
    if target=='returned': c.execute('UPDATE orders SET revenue=0,actual_cost=forward+reverse+actual_cost WHERE id=? AND tenant_id=?',(o['id'],t))
    if target=='lost_damaged_dispute': c.execute('UPDATE orders SET revenue=0,actual_cost=forward+cogs WHERE id=? AND tenant_id=?',(o['id'],t))
    c.execute('UPDATE orders SET status=?,updated_at=?,version=version+1 WHERE tenant_id=? AND id=?',(target,at or time_at(c,t),t,o['id']))
    event(c,t,o['id'],'state_transition',old,target,{'approved_by':actor,**(payload or {})},at,event_id)
    o['status']=target
    if target in {'NDR','delivered','returned'}:
        trace(c,t,o['id'],'Rescue' if target=='NDR' else 'Monitor',{'status':target}, {'recommendation':'Human-approved address correction or reschedule; retry outcome is uncertain' if target=='NDR' else 'Record outcome and calculate ledger','simulated':True},at)
    return get_order(c,t,o['id'])

def verify(c,t,o,response,actor,address=None):
    if o['status'] not in {'verification_pending','hold_review','confirmed'}: raise HTTPException(409,'Order is not in the verification queue')
    if o.get('opt_out_at') and response not in {'no_response','cancel'}: raise HTTPException(409,'Customer opted out: simulated contact is blocked')
    if response=='address_change':
        if not address or len(address.strip())<10: raise HTTPException(422,'Provide a corrected address with at least 10 characters')
        c.execute('UPDATE orders SET address=?,address_quality=95 WHERE tenant_id=? AND id=?',(address,t,o['id']))
        o['address_quality']=95
    target={'confirm':'confirmed','cancel':'cancelled_before_ship','no_response':'hold_review','address_change':'confirmed'}[response]
    if target != o['status']: o=advance(c,t,o,target,actor,{'response':response})
    c.execute('UPDATE orders SET verification=?,service_cost=service_cost+1500 WHERE tenant_id=? AND id=?',(response,t,o['id']))
    trace(c,t,o['id'],'Verification',{'response':response,'contact':'synthetic adapter; no network send'}, {'state':target,'note':'Non-response is not fraud. Human follow-up is optional; never automatically reject.'})
    event(c,t,o['id'],'verification_response',payload={'response':response,'approved_by':actor,'simulated':True})
    a=save_risk(c,t,get_order(c,t,o['id']))
    if target=='confirmed':
        o=get_order(c,t,o['id'])
        if a['score']>=35: advance(c,t,o,'hold_review',actor,{'reason':'Review risk factors; manual release available'})
        else: advance(c,t,o,'ready_to_ship',actor)
    return get_order(c,t,o['id'])

def quotes(c,t,o):
    settings=json.loads(row(c,'SELECT settings FROM tenants WHERE id=?',(t,))['settings'])
    today=datetime.fromisoformat(time_at(c,t)).date().isoformat()
    used={x['courier_id']:x['n'] for x in rows(c,'SELECT courier_id,count(*) n FROM orders WHERE tenant_id=? AND substr(dispatch_at,1,10)=? GROUP BY courier_id',(t,today))}
    result=[]
    for carrier in rows(c,'SELECT * FROM couriers WHERE tenant_id=? ORDER BY code',(t,)):
        reasons=[]
        if not carrier['active']: reasons.append('Disabled by merchant')
        if o['city'] not in json.loads(carrier['zones']): reasons.append('City is not serviceable')
        if o['weight_g']>carrier['max_weight']: reasons.append('Weight exceeds service limit')
        if o['cod']>min(carrier['max_cod'],20000000): reasons.append('COD exceeds limit')
        if carrier['reverse'] is None: reasons.append('Return fee unknown; estimate incomplete')
        capacity=max(0,carrier['capacity']-used.get(carrier['id'],0))
        if capacity==0: reasons.append('Daily capacity exhausted')
        forward=carrier['forward']+max(0,(o['weight_g']-1)//500)*3500 + (4500 if o['city'] in {'Quetta','Multan'} else 0)
        rto=min(6500,carrier['rto_bp']+(100-o['address_quality'])*35)
        reverse=carrier['reverse'] or 0
        penalty=settings['sla_penalty']
        expected=forward+carrier['cod_fee']+(rto*reverse+5000)//10000+(carrier['late_bp']*penalty+5000)//10000+settings['handling']
        result.append({**carrier,'zones':json.loads(carrier['zones']),'eligible':not reasons,'excluded_reasons':reasons,'available_capacity':capacity,'forward':forward,'expected_cost':expected,'rto_bp':rto,'expected_return':(rto*reverse+5000)//10000,'expected_late':(carrier['late_bp']*penalty+5000)//10000,'handling':settings['handling'],'low_cost':forward+carrier['cod_fee']+500*reverse//10000+settings['handling'],'high_cost':forward+carrier['cod_fee']+min(8500,rto+1500)*reverse//10000+carrier['late_bp']*penalty//10000+settings['handling']})
    return result

def realized(o):
    # COGS on delivered sales only; returned merchandise is restocked. Loss cost already in actual_cost.
    return o['revenue']-(o['cogs'] if o['status']=='delivered' else 0)-o['actual_cost']-o['packaging']-o['marketing']-o['service_cost']-o['refund'] if o['status'] in TERMINAL else None

def expected_margin(o):
    if o['expected_cost']==0: return None
    return o['cod']-o['cogs']-o['expected_cost']-o['packaging']-o['marketing']-o['service_cost']

def ensure_statement(c,t,o):
    if o['status'] not in {'delivered','returned','lost_damaged_dispute'}: raise HTTPException(409,'Only completed shipments may have remittances')
    existing=row(c,'SELECT * FROM statements WHERE tenant_id=? AND order_id=?',(t,o['id']))
    if existing: return existing
    expected=o['revenue']-o['actual_cost']
    s=insert(c,'statements',id=uid(),tenant_id=t,order_id=o['id'],booking_ref='SIM-'+o['external_id'],expected=expected,actual=None,status='missing',note='Synthetic payout not yet received',created_at=time_at(c,t))
    trace(c,t,o['id'],'Finance',{'revenue':o['revenue'],'recorded_shipping':o['actual_cost']},{'expected_remittance':expected,'status':'missing'})
    return s

def ingest(c,t,data,actor='system',at=None,order_id=None):
    ext=data['external_id'].strip()
    if row(c,'SELECT id FROM orders WHERE tenant_id=? AND external_id=?',(t,ext)): raise HTTPException(409,'Duplicate merchant order reference')
    store=row(c,'SELECT id FROM stores WHERE tenant_id=? ORDER BY id LIMIT 1',(t,))
    customer_id=uid()
    insert(c,'customers',id=customer_id,tenant_id=t,name=data.get('customer','Fictional customer'),contact='SYN-PK-'+customer_id,consent_source='synthetic_demo_opt_in',consent_at=at or time_at(c,t),opt_out_at=None)
    oid=order_id or uid()
    amount=data['cod']; cost=data.get('cogs',amount*55//100)
    insert(c,'orders',id=oid,tenant_id=t,store_id=store['id'],customer_id=customer_id,external_id=ext,city=data['city'],address=data['address'],address_quality=data.get('address_quality',90),cod=amount,cogs=cost,weight_g=data['weight_g'],packaging=2500,marketing=8000,status='imported',verification='pending',risk_score=0,risk_reasons='{}',created_at=at or time_at(c,t),updated_at=at or time_at(c,t))
    product=row(c,'SELECT id FROM products WHERE tenant_id=? ORDER BY id LIMIT 1',(t,))
    insert(c,'order_items',id=uid(),tenant_id=t,order_id=oid,product_id=product['id'],qty=1,unit_price=amount,cogs=cost)
    trace(c,t,oid,'Intake',{'external_id':ext,'city':data['city']},{'valid':True,'duplicate':False,'simulated':True},at)
    event(c,t,oid,'order_received',payload={'synthetic':True,'seed_version':'PG-1'},at=at)
    o=get_order(c,t,oid)
    advance(c,t,o,'verification_pending',actor,at=at)
    current=get_order(c,t,oid)
    options=[q['expected_cost'] for q in quotes(c,t,current) if q['eligible']]
    if options: c.execute('UPDATE orders SET expected_cost=? WHERE tenant_id=? AND id=?',(min(options),t,oid))
    return get_order(c,t,oid)
