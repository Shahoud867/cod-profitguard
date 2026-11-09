"""COD ProfitGuard API: local, synthetic-only operational MVP."""
import os, json, hashlib, secrets, csv, io, time, threading
from contextlib import asynccontextmanager
from datetime import datetime,timedelta,timezone
from typing import Literal
from fastapi import FastAPI, Depends, HTTPException, Request, Response, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from .db import connect,migrate,row,rows,insert,uid,js,now
from .domain import *
from .optimization import optimize,fingerprint
from .seed import seed,seed_tenant,checksum,SETTINGS
from .connectors import SimulationCourier

@asynccontextmanager
async def lifespan(app):
    with connect() as c:
        migrate(c)
        if os.environ.get('AUTO_SEED','true')=='true': seed(c)
    c.close()
    yield
app=FastAPI(title='COD ProfitGuard',version='1.0.0',lifespan=lifespan,description='Synthetic-only operations API. All amounts integer paisa. No external integrations.')
app.add_middleware(CORSMiddleware,allow_origins=os.environ.get('CORS_ORIGINS','http://localhost:5173,http://127.0.0.1:5173').split(','),allow_credentials=True,allow_methods=['GET','POST','PUT'],allow_headers=['Content-Type','X-CSRF-Token','Idempotency-Key','X-Request-ID'])

@app.middleware('http')
async def security(request,call_next):
    try: size=int(request.headers.get('content-length','0') or 0)
    except ValueError: return Response('Invalid Content-Length',status_code=400)
    if size>2_000_000: return Response('Upload exceeds 2 MB',status_code=413)
    response=await call_next(request)
    response.headers.update({'X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'same-origin','Cache-Control':'no-store','X-Request-ID':request.headers.get('X-Request-ID',uid())})
    return response

def db():
    c=connect()
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback(); raise
    finally: c.close()

def auth(request:Request,c=Depends(db)):
    token=request.cookies.get('pg_session','')
    u=row(c,'SELECT u.id,u.email,s.tenant_id,s.csrf,m.role FROM sessions s JOIN users u ON u.id=s.user_id JOIN memberships m ON m.user_id=s.user_id AND m.tenant_id=s.tenant_id WHERE s.token_hash=? AND s.expires_at>?',(hashlib.sha256(token.encode()).hexdigest(),now()))
    if not u: raise HTTPException(401,'Sign in to continue')
    if request.method not in {'GET','HEAD','OPTIONS'}:
        if not secrets.compare_digest(request.headers.get('X-CSRF-Token',''),u['csrf']): raise HTTPException(403,'CSRF token required')
        origin=request.headers.get('origin')
        allowed=set(os.environ.get('CORS_ORIGINS','http://localhost:5173,http://127.0.0.1:5173').split(','))|{str(request.base_url).rstrip('/')}
        # Vite proxy forwards the public Host, so same-origin previews remain valid.
        if origin and origin not in allowed: raise HTTPException(403,'Origin is not allowed')
    return u

def allow(u,roles):
    if u['role'] not in roles: raise HTTPException(403,'Your role cannot perform this action')
OPS={'owner','manager'}; CSR=OPS|{'csr'}; FIN=OPS|{'finance'}
def command(request,u,c,name,payload,operation,roles=OPS):
    allow(u,roles)
    key=request.headers.get('Idempotency-Key')
    if not key or len(key)>150: raise HTTPException(400,'A unique Idempotency-Key (max 150 characters) is required')
    digest=hashlib.sha256(js(payload).encode()).hexdigest()
    c.execute('BEGIN IMMEDIATE')
    old=row(c,'SELECT * FROM idempotency WHERE tenant_id=? AND key=?',(u['tenant_id'],key))
    if old:
        if old['command']!=name or old['payload_hash']!=digest: raise HTTPException(409,'Idempotency key reused for a different request')
        return json.loads(old['response'])
    result=operation()
    audit(c,u['tenant_id'],u['email'],name,payload={'request':payload},request_id=request.headers.get('X-Request-ID',key))
    insert(c,'idempotency',tenant_id=u['tenant_id'],key=key,command=name,payload_hash=digest,response=js(result))
    return result

class Model(BaseModel): model_config=ConfigDict(extra='forbid')
class Login(Model):
    email:str=Field(max_length=100)
    password:str=Field(max_length=150)
class OrderInput(Model):
    external_id:str=Field(min_length=1,max_length=80,pattern=r'^[A-Za-z0-9_.-]+$')
    customer:str=Field(default='Fictional customer',min_length=1,max_length=100)
    city:str=Field(min_length=2,max_length=80)
    address:str=Field(min_length=5,max_length=300)
    address_quality:int=Field(default=90,ge=0,le=100)
    cod:int=Field(gt=0,le=1000000000,description='Integer paisa')
    cogs:int|None=Field(default=None,ge=0,le=1000000000)
    weight_g:int=Field(gt=0,le=50000)
class VerifyInput(Model):
    response:Literal['confirm','cancel','no_response','address_change']
    address:str|None=Field(default=None,max_length=300)
    approved:bool
class Reason(Model):
    reason:str=Field(min_length=8,max_length=500)
    approved:bool
class ImportInput(Model):
    csv_text:str=Field(max_length=1900000)
    dry_run:bool=False
class RoutingInput(Model):
    order_ids:list[str]|None=Field(default=None,max_length=100)
    limit:int=Field(default=100,ge=1,le=100)
    fairness:int=Field(default=0,ge=0,le=50000)
class CommitInput(Model):
    proposal_id:str
    approved:bool
class OverrideInput(Reason): courier_id:str
class TrackingInput(Model):
    target:Literal['in_transit','out_for_delivery','delivered','NDR','RTO_initiated','returned','lost_damaged_dispute']
    reason:str=Field(default='Human-approved synthetic tracking event',max_length=500)
    event_id:str=Field(min_length=1,max_length=100)
    occurred_at:datetime|None=None
    approved:bool
class RescueInput(Reason):
    action:Literal['retry','return']
    address:str|None=Field(default=None,max_length=300)
    customer_approved:bool=False
class SettleInput(Reason):
    actual:int|None=Field(default=None,ge=-1000000000,le=1000000000)
class SettingsInput(Model):
    default_courier:Literal['SWF','RBT','MHR','ATL']
    sla_penalty:int=Field(ge=0,le=100000)
    handling:int=Field(ge=0,le=50000)
    retention_days:int=Field(ge=1,le=3650)
    consent_required:Literal[True]=True
class CourierInput(Model):
    capacity:int=Field(ge=0,le=1000)
    forward:int=Field(ge=0,le=1000000)
    reverse:int|None=Field(default=None,ge=0,le=1000000)
    cod_fee:int=Field(ge=0,le=100000)
    active:bool=True
class DemoInput(Model):
    approved:bool
    seed:int=Field(default=20261108,ge=0,le=2147483647)
    response:Literal['confirm','cancel','no_response','address_change']='confirm'
class ResetInput(Model):
    confirmation:Literal['RESET SYNTHETIC DATA']
    seed:int=Field(default=20261108,ge=0,le=2147483647)
class ClockInput(Model): hours:int=Field(ge=1,le=168)
class QueueInput(Model):
    order_id:str
    inject_timeout:bool=False

attempts={}; attempts_lock=threading.Lock()
@app.post('/api/v1/auth/login')
def login(data:Login,request:Request,response:Response,c=Depends(db)):
    ip=request.client.host if request.client else 'local'
    with attempts_lock:
        recent=[x for x in attempts.get(ip,[]) if x>time.time()-60]
        if len(recent)>=10: raise HTTPException(429,'Too many attempts; retry in one minute')
        recent.append(time.time()); attempts[ip]=recent
    user=row(c,'SELECT * FROM users WHERE email=?',(data.email.lower(),))
    try:
        if not user: PasswordHasher().verify('$argon2id$v=19$m=65536,t=3,p=4$ZGVtby1maWN0aW9uYWw$4YR5R2yTq4CpGMi4OW0cFtWQX4bQ8P02FLZSpzJwFZg',data.password); raise VerificationError('invalid')
        PasswordHasher().verify(user['password_hash'],data.password)
    except VerificationError: raise HTTPException(401,'Incorrect email or password')
    membership=row(c,'SELECT * FROM memberships WHERE user_id=? ORDER BY tenant_id LIMIT 1',(user['id'],))
    token=secrets.token_urlsafe(40); csrf=secrets.token_urlsafe(24)
    insert(c,'sessions',token_hash=hashlib.sha256(token.encode()).hexdigest(),user_id=user['id'],tenant_id=membership['tenant_id'],csrf=csrf,expires_at=(datetime.now(timezone.utc)+timedelta(hours=8)).isoformat())
    response.set_cookie('pg_session',token,httponly=True,secure=os.environ.get('COOKIE_SECURE','false')=='true',samesite='strict',max_age=28800,path='/')
    audit(c,membership['tenant_id'],data.email,'auth.login')
    return {'email':user['email'],'role':membership['role'],'tenant_id':membership['tenant_id'],'csrf':csrf}
@app.get('/api/v1/auth/me')
def me(u=Depends(auth),c=Depends(db)):
    return {**u,'tenant':row(c,'SELECT name,virtual_time,seed FROM tenants WHERE id=?',(u['tenant_id'],))}
@app.post('/api/v1/auth/logout')
def logout(request:Request,response:Response,u=Depends(auth),c=Depends(db)):
    c.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(request.cookies.get('pg_session','').encode()).hexdigest(),))
    response.delete_cookie('pg_session',path='/'); audit(c,u['tenant_id'],u['email'],'auth.logout'); return {'ok':True}
@app.get('/api/health')
def health(): return {'status':'ok','mode':'synthetic-only','money_unit':'paisa'}

@app.get('/api/v1/orders')
def list_orders(q:str=Query('',max_length=100),status:str='',city:str='',limit:int=Query(40,ge=1,le=200),offset:int=Query(0,ge=0),u=Depends(auth),c=Depends(db)):
    clauses=['o.tenant_id=?']; args=[u['tenant_id']]
    if q: clauses.append('(o.external_id LIKE ? OR cu.name LIKE ? OR o.city LIKE ?)'); args += ['%'+q+'%']*3
    if status: clauses.append('o.status=?'); args.append(status)
    if city: clauses.append('o.city=?'); args.append(city)
    where=' AND '.join(clauses)
    base=' FROM orders o JOIN customers cu ON cu.id=o.customer_id AND cu.tenant_id=o.tenant_id LEFT JOIN couriers co ON co.id=o.courier_id AND co.tenant_id=o.tenant_id WHERE '+where
    total=row(c,'SELECT count(*) n'+base,tuple(args))['n']
    result=rows(c,'SELECT o.*,cu.name customer,co.name courier'+base+' ORDER BY o.created_at DESC,o.id LIMIT ? OFFSET ?',(*args,limit,offset))
    for o in result: o['realized_margin']=realized(o); o['estimated_margin']=expected_margin(o)
    return {'items':result,'total':total,'offset':offset,'limit':limit}

def safe_cell(v):
    s=str(v) if v is not None else ''
    return "'"+s if s.lstrip().startswith(('=','+','-','@','\t','\r')) else s
@app.get('/api/v1/orders/export')
def export_orders(u=Depends(auth),c=Depends(db)):
    data=rows(c,'SELECT external_id,city,cod,status,verification,actual_cost,revenue,simulated FROM orders WHERE tenant_id=? ORDER BY external_id',(u['tenant_id'],))
    stream=io.StringIO(); writer=csv.writer(stream); writer.writerow(['SIMULATED DATA — amounts in paisa']); writer.writerow(list(data[0]) if data else ['external_id'])
    for item in data: writer.writerow([safe_cell(v) for v in item.values()])
    return Response(stream.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="profitguard-synthetic-orders.csv"'})
@app.get('/api/v1/orders/{oid}')
def detail(oid:str,u=Depends(auth),c=Depends(db)):
    t=u['tenant_id']; o=get_order(c,t,oid)
    return {'order':o,'events':rows(c,'SELECT * FROM events WHERE tenant_id=? AND order_id=? ORDER BY occurred_at,ingested_at,id',(t,oid)),'risk':assess(o),'quotes':quotes(c,t,o),'items':rows(c,'SELECT oi.*,p.name FROM order_items oi JOIN products p ON p.id=oi.product_id AND p.tenant_id=oi.tenant_id WHERE oi.tenant_id=? AND oi.order_id=?',(t,oid)),'realized_margin':realized(o),'estimated_margin':expected_margin(o)}
@app.post('/api/v1/orders')
def create(data:OrderInput,request:Request,u=Depends(auth),c=Depends(db)):
    return command(request,u,c,'order.create',data.model_dump(),lambda:ingest(c,u['tenant_id'],data.model_dump(exclude_none=True),u['email']),CSR)
@app.post('/api/v1/orders/import')
def import_orders(data:ImportInput,request:Request,u=Depends(auth),c=Depends(db)):
    def op():
        reader=csv.DictReader(io.StringIO(data.csv_text)); accepted=[]; errors=[]; duplicates=[]; seen=set()
        entries=list(reader)
        if len(entries)>1000: raise HTTPException(422,'Maximum 1,000 CSV rows per import')
        required={'external_id','city','address','cod_pkr','weight_g'}
        if not required.issubset(set(reader.fieldnames or [])): raise HTTPException(422,'Required columns: external_id,city,address,cod_pkr,weight_g; optional: customer,cogs_pkr,address_quality')
        from decimal import Decimal,InvalidOperation
        for i,item in enumerate(entries,2):
            try:
                cod_decimal=Decimal(item['cod_pkr'])*100
                if cod_decimal!=cod_decimal.to_integral_value(): raise ValueError('COD must have at most two decimal places')
                payload={'external_id':item['external_id'].strip(),'city':item['city'].strip().title(),'address':item['address'].strip(),'cod':int(cod_decimal),'weight_g':int(item['weight_g']),'customer':item.get('customer') or 'Fictional CSV customer','address_quality':int(item.get('address_quality') or 90)}
                if item.get('cogs_pkr'): payload['cogs']=int(Decimal(item['cogs_pkr'])*100)
                validated=OrderInput(**payload).model_dump(exclude_none=True)
                if payload['external_id'] in seen or row(c,'SELECT id FROM orders WHERE tenant_id=? AND external_id=?',(u['tenant_id'],payload['external_id'])):
                    duplicates.append({'row':i,'external_id':payload['external_id']}); continue
                seen.add(payload['external_id'])
                warning='COD above policy limit: manual review; dispatch blocked' if payload['cod']>20000000 else None
                if not data.dry_run:
                    o=ingest(c,u['tenant_id'],validated,u['email']); accepted.append({'row':i,'id':o['id'],'external_id':o['external_id'],'warning':warning})
                else: accepted.append({'row':i,'external_id':payload['external_id'],'warning':warning})
            except (ValueError,TypeError,InvalidOperation) as e: errors.append({'row':i,'error':str(e)[:400]})
        return {'accepted':accepted,'rejected':errors,'duplicates':duplicates,'dry_run':data.dry_run}
    return command(request,u,c,'order.import',data.model_dump(),op,CSR)
@app.post('/api/v1/orders/{oid}/verification')
def verification(oid:str,data:VerifyInput,request:Request,u=Depends(auth),c=Depends(db)):
    if not data.approved: raise HTTPException(422,'Human approval required')
    return command(request,u,c,'verification.'+oid,data.model_dump(),lambda:verify(c,u['tenant_id'],get_order(c,u['tenant_id'],oid),data.response,u['email'],data.address),CSR)
@app.post('/api/v1/orders/{oid}/risk')
def risk(oid:str,request:Request,u=Depends(auth),c=Depends(db)):
    return command(request,u,c,'risk.'+oid,{},lambda:save_risk(c,u['tenant_id'],get_order(c,u['tenant_id'],oid)),CSR)
@app.post('/api/v1/orders/{oid}/release')
def release(oid:str,data:Reason,request:Request,u=Depends(auth),c=Depends(db)):
    def op():
        if not data.approved: raise HTTPException(422,'Human approval required')
        o=get_order(c,u['tenant_id'],oid)
        if o['status']!='hold_review': raise HTTPException(409,'Only held orders can be released')
        o=advance(c,u['tenant_id'],o,'confirmed',u['email'],{'override_reason':data.reason})
        return advance(c,u['tenant_id'],o,'ready_to_ship',u['email'],{'override_reason':data.reason})
    return command(request,u,c,'risk.release.'+oid,data.model_dump(),op)

@app.get('/api/v1/couriers')
def couriers(u=Depends(auth),c=Depends(db)):
    return {'items':rows(c,'SELECT * FROM couriers WHERE tenant_id=? ORDER BY code',(u['tenant_id'],)),'note':'All couriers, rate cards and outcome assumptions are fictional. Rates are integer paisa.'}
@app.put('/api/v1/couriers/{cid}')
def edit_courier(cid:str,data:CourierInput,request:Request,u=Depends(auth),c=Depends(db)):
    def op():
        if not row(c,'SELECT id FROM couriers WHERE tenant_id=? AND id=?',(u['tenant_id'],cid)): raise HTTPException(404,'Courier not found')
        c.execute('UPDATE couriers SET capacity=?,forward=?,reverse=?,cod_fee=?,active=? WHERE tenant_id=? AND id=?',(data.capacity,data.forward,data.reverse,data.cod_fee,int(data.active),u['tenant_id'],cid))
        return {'ok':True}
    return command(request,u,c,'courier.update.'+cid,data.model_dump(),op,{'owner'})
@app.post('/api/v1/couriers/rate-cards/import')
def import_rates(data:ImportInput,request:Request,u=Depends(auth),c=Depends(db)):
    def op():
        entries=list(csv.DictReader(io.StringIO(data.csv_text))); parsed=[]
        if len(entries)>100: raise HTTPException(422,'Rate import is limited to 100 rows')
        from decimal import Decimal
        try:
            for item in entries:
                q=row(c,'SELECT * FROM couriers WHERE tenant_id=? AND code=?',(u['tenant_id'],item['code']))
                if not q: raise ValueError('Unknown courier code')
                d=CourierInput(capacity=int(item['capacity']),forward=int(Decimal(item['forward_pkr'])*100),reverse=int(Decimal(item['reverse_pkr'])*100) if item['reverse_pkr'] else None,cod_fee=int(Decimal(item['cod_fee_pkr'])*100),active=True)
                parsed.append((q['id'],d))
        except (ValueError,KeyError) as e: raise HTTPException(422,str(e))
        if not data.dry_run:
            for cid,d in parsed: c.execute('UPDATE couriers SET capacity=?,forward=?,reverse=?,cod_fee=? WHERE tenant_id=? AND id=?',(d.capacity,d.forward,d.reverse,d.cod_fee,u['tenant_id'],cid))
        return {'accepted':len(parsed),'dry_run':data.dry_run}
    return command(request,u,c,'courier.import',data.model_dump(),op,{'owner'})
@app.post('/api/v1/routing/preview')
def preview(data:RoutingInput,request:Request,u=Depends(auth),c=Depends(db)):
    return command(request,u,c,'routing.preview',data.model_dump(),lambda:optimize(c,u['tenant_id'],data.order_ids,data.limit,data.fairness))

def book(c,u,o,q,reason):
    if o['status']!='ready_to_ship': raise HTTPException(409,'Only released, ready orders can be allocated')
    if not q['eligible']: raise HTTPException(409,'Courier is ineligible: '+', '.join(q['excluded_reasons']))
    t=u['tenant_id']
    c.execute('UPDATE orders SET courier_id=?,forward=?,reverse=?,cod_fee=?,expected_cost=?,dispatch_at=? WHERE tenant_id=? AND id=?',(q['id'],q['forward'],q['reverse'],q['cod_fee'],q['expected_cost'],time_at(c,t),t,o['id']))
    trace(c,t,o['id'],'Courier',{'city':o['city'],'weight_g':o['weight_g'],'cod':o['cod']},{'selected':q['name'],'quote':q,'reason':reason,'approved_by':u['email']})
    return advance(c,t,o,'booked_simulated',u['email'],{'courier':q['name'],'reason':reason})
@app.post('/api/v1/routing/commit')
def commit(data:CommitInput,request:Request,u=Depends(auth),c=Depends(db)):
    def op():
        if not data.approved: raise HTTPException(422,'Human approval required')
        a=row(c,'SELECT * FROM allocations WHERE tenant_id=? AND id=?',(u['tenant_id'],data.proposal_id))
        if not a: raise HTTPException(404,'Proposal not found')
        if a['status']!='proposed': raise HTTPException(409,'Proposal already committed')
        proposal=json.loads(a['proposal'])
        if proposal['fingerprint']!=fingerprint(c,u['tenant_id']): raise HTTPException(409,'Courier rates or settings changed; preview again')
        for item in proposal['allocations']:
            if not item['courier_id']: continue
            o=get_order(c,u['tenant_id'],item['order_id'])
            if o['version']!=item['version']: raise HTTPException(409,'Order changed; preview allocation again')
            q=next(q for q in quotes(c,u['tenant_id'],o) if q['id']==item['courier_id'])
            if q['expected_cost']!=item['expected_cost']: raise HTTPException(409,'Quote changed; preview again')
            book(c,u,o,q,'Approved batch proposal '+data.proposal_id)
        c.execute('UPDATE allocations SET status="committed",approved_by=? WHERE tenant_id=? AND id=?',(u['email'],u['tenant_id'],data.proposal_id))
        return {'booked':proposal['assigned'],'proposal_id':data.proposal_id}
    return command(request,u,c,'routing.commit',data.model_dump(),op)
@app.post('/api/v1/orders/{oid}/override-courier')
def override(oid:str,data:OverrideInput,request:Request,u=Depends(auth),c=Depends(db)):
    def op():
        if not data.approved: raise HTTPException(422,'Approval required')
        o=get_order(c,u['tenant_id'],oid)
        options=quotes(c,u['tenant_id'],o); q=next((q for q in options if q['id']==data.courier_id),None)
        if not q: raise HTTPException(404,'Courier not found')
        eligible=[x['expected_cost'] for x in options if x['eligible']]
        consequence=q['expected_cost']-min(eligible) if eligible else None
        result=book(c,u,o,q,data.reason)
        event(c,u['tenant_id'],oid,'human_override',payload={'reason':data.reason,'incremental_modeled_cost':consequence,'approved_by':u['email']})
        return {'order':result,'incremental_modeled_cost':consequence}
    return command(request,u,c,'courier.override.'+oid,data.model_dump(),op)
@app.post('/api/v1/orders/{oid}/tracking')
def tracking(oid:str,data:TrackingInput,request:Request,u=Depends(auth),c=Depends(db)):
    def op():
        if not data.approved: raise HTTPException(422,'Synthetic tracking approval required')
        o=get_order(c,u['tenant_id'],oid)
        old=row(c,'SELECT * FROM events WHERE tenant_id=? AND id=?',(u['tenant_id'],data.event_id))
        if old:
            if old['order_id']!=oid or old['to_state']!=data.target: raise HTTPException(409,'Event ID conflicts with existing payload')
            return {'order':o,'duplicate':True}
        at=data.occurred_at.astimezone(timezone.utc).isoformat() if data.occurred_at and data.occurred_at.tzinfo else time_at(c,u['tenant_id'])
        latest=row(c,'SELECT max(occurred_at) at FROM events WHERE tenant_id=? AND order_id=?',(u['tenant_id'],oid))['at']
        if at<latest:
            event(c,u['tenant_id'],oid,'out_of_order_review',payload={'requested_target':data.target,'reason':data.reason},at=at,event_id=data.event_id)
            return {'order':o,'review_required':True,'message':'Out-of-order event preserved; current state unchanged'}
        o=advance(c,u['tenant_id'],o,data.target,u['email'],{'reason':data.reason},at,data.event_id)
        if data.target in {'delivered','returned','lost_damaged_dispute'}: ensure_statement(c,u['tenant_id'],o)
        return {'order':o,'duplicate':False}
    return command(request,u,c,'tracking.'+oid,data.model_dump(mode='json'),op,CSR)
@app.post('/api/v1/orders/{oid}/rescue')
def rescue(oid:str,data:RescueInput,request:Request,u=Depends(auth),c=Depends(db)):
    def op():
        if not data.approved: raise HTTPException(422,'Human approval required')
        o=get_order(c,u['tenant_id'],oid)
        if o['status']!='NDR': raise HTTPException(409,'Order must have an active NDR')
        if data.action=='retry':
            if not data.customer_approved: raise HTTPException(422,'Customer approval must be recorded before retry')
            if o['opt_out_at']: raise HTTPException(409,'Customer has opted out of contact')
            if data.address:
                if len(data.address)<10: raise HTTPException(422,'Corrected address is incomplete')
                c.execute('UPDATE orders SET address=?,address_quality=95 WHERE tenant_id=? AND id=?',(data.address,u['tenant_id'],oid))
            c.execute('UPDATE orders SET actual_cost=actual_cost+3500,service_cost=service_cost+1500 WHERE tenant_id=? AND id=?',(u['tenant_id'],oid))
        return advance(c,u['tenant_id'],o,'reattempt' if data.action=='retry' else 'RTO_initiated',u['email'],{'reason':data.reason,'customer_approved':data.customer_approved})
    return command(request,u,c,'rescue.'+oid,data.model_dump(),op,CSR)

@app.get('/api/v1/finance')
def finance(u=Depends(auth),c=Depends(db)):
    t=u['tenant_id']
    return {'items':rows(c,'SELECT s.*,o.external_id,o.status order_status,co.name courier FROM statements s JOIN orders o ON o.id=s.order_id AND o.tenant_id=s.tenant_id LEFT JOIN couriers co ON co.id=o.courier_id AND co.tenant_id=o.tenant_id WHERE s.tenant_id=? ORDER BY CASE s.status WHEN "missing" THEN 0 WHEN "disputed" THEN 1 ELSE 2 END,s.created_at DESC LIMIT 500',(t,)),'totals':row(c,'SELECT count(*) count,sum(expected) expected,sum(coalesce(actual,0)) actual,sum(CASE WHEN status!="reconciled" THEN 1 ELSE 0 END) exceptions FROM statements WHERE tenant_id=?',(t,))}
@app.post('/api/v1/finance/{sid}/resolve')
def resolve(sid:str,data:SettleInput,request:Request,u=Depends(auth),c=Depends(db)):
    def op():
        if not data.approved: raise HTTPException(422,'Finance approval required')
        s=row(c,'SELECT * FROM statements WHERE tenant_id=? AND id=?',(u['tenant_id'],sid))
        if not s: raise HTTPException(404,'Statement not found')
        actual=s['actual'] if data.actual is None else data.actual
        if actual is None: raise HTTPException(422,'Record the received remittance amount before resolving')
        status='reconciled' if abs(actual-s['expected'])<=1 else 'disputed'
        c.execute('UPDATE statements SET actual=?,status=?,note=?,resolved_by=? WHERE tenant_id=? AND id=?',(actual,status,data.reason,u['email'],u['tenant_id'],sid))
        trace(c,u['tenant_id'],s['order_id'],'Finance',{'expected':s['expected'],'actual':actual},{'delta':actual-s['expected'],'status':status,'tolerance_paisa':1})
        event(c,u['tenant_id'],s['order_id'],'settlement_review',payload={'actual':actual,'expected':s['expected'],'status':status})
        return {'status':status,'delta':actual-s['expected']}
    return command(request,u,c,'finance.resolve.'+sid,data.model_dump(),op,FIN)
@app.post('/api/v1/reconciliation/import')
def import_statements(data:ImportInput,request:Request,u=Depends(auth),c=Depends(db)):
    def op():
        entries=list(csv.DictReader(io.StringIO(data.csv_text))); good=[]; rejected=[]
        if len(entries)>1000: raise HTTPException(422,'Statement import maximum is 1,000 rows')
        from decimal import Decimal
        for i,item in enumerate(entries,2):
            try:
                ref=item['booking_ref']; value=Decimal(item['actual_pkr'])*100
                if value!=value.to_integral_value(): raise ValueError('Maximum two decimal places')
                actual=int(value)
                if abs(actual)>1000000000: raise ValueError('Amount out of range')
                s=row(c,'SELECT * FROM statements WHERE tenant_id=? AND booking_ref=?',(u['tenant_id'],ref))
                if not s: raise ValueError('Unknown booking reference; manual review required')
                status='reconciled' if abs(actual-s['expected'])<=1 else 'disputed'
                if not data.dry_run:
                    c.execute('UPDATE statements SET actual=?,status=?,note=? WHERE tenant_id=? AND id=?',(actual,status,'Imported synthetic courier statement',u['tenant_id'],s['id']))
                    event(c,u['tenant_id'],s['order_id'],'statement_import',payload={'actual':actual,'delta':actual-s['expected'],'status':status})
                    trace(c,u['tenant_id'],s['order_id'],'Finance',{'booking_ref':ref,'actual':actual},{'status':status,'delta':actual-s['expected']})
                good.append({'row':i,'booking_ref':ref,'status':status})
            except (ValueError,KeyError,ArithmeticError) as e: rejected.append({'row':i,'error':str(e)})
        return {'accepted':good,'rejected':rejected,'dry_run':data.dry_run}
    return command(request,u,c,'finance.import',data.model_dump(),op,FIN)

@app.get('/api/v1/analytics')
def analytics(days:int=Query(180,ge=1,le=3650),u=Depends(auth),c=Depends(db)):
    t=u['tenant_id']; end=datetime.fromisoformat(time_at(c,t)); start=(end-timedelta(days=days)).isoformat()
    data=rows(c,'SELECT o.*,co.name courier,co.color FROM orders o LEFT JOIN couriers co ON co.id=o.courier_id AND co.tenant_id=o.tenant_id WHERE o.tenant_id=? AND o.created_at>=? AND o.created_at<=?',(t,start,end.isoformat()))
    counts={}; trend={}; cities={}; carriers={}
    for o in data:
        counts[o['status']]=counts.get(o['status'],0)+1
        date=o['created_at'][:7]; realized_value=realized(o)
        for container,key in [(trend,date),(cities,o['city']),(carriers,o['courier'] or 'Unallocated')]:
            group=container.setdefault(key,{'name':key,'orders':0,'delivered':0,'returned':0,'revenue':0,'realized':0,'expected':0,'shipping':0,'color':o['color'] or '#95a99c'})
            group['orders']+=1; group['delivered']+=o['status']=='delivered'; group['returned']+=o['status']=='returned'; group['revenue']+=o['revenue']; group['realized']+=realized_value or 0; group['expected']+=expected_margin(o) or 0; group['shipping']+=o['actual_cost']
    terminal=[o for o in data if o['status'] in TERMINAL]; pending=[o for o in data if o['status'] not in TERMINAL]
    delivered=counts.get('delivered',0); returns=counts.get('returned',0)
    return {'simulated':True,'seed_version':'PG-1','period_days':days,'counts':counts,'placed':len(data),'delivered':delivered,'returned':returns,'revenue':sum(o['revenue'] for o in data),'realized_contribution':sum(realized(o) or 0 for o in terminal),'realized_per_placed_order':sum(realized(o) or 0 for o in terminal)//max(1,len(data)),'pending_estimated_contribution':sum(expected_margin(o) or 0 for o in pending),'unpriced_pending_orders':sum(expected_margin(o) is None for o in pending),'shipping_cost':sum(o['actual_cost'] for o in data),'rto_percent':round(100*returns/max(1,delivered+returns),2),'trend':sorted(trend.values(),key=lambda x:x['name']),'cities':sorted(cities.values(),key=lambda x:-x['orders']),'couriers':list(carriers.values()),'open_settlements':row(c,'SELECT count(*) n FROM statements WHERE tenant_id=? AND status!="reconciled"',(t,))['n'],'active_rescues':counts.get('NDR',0),'virtual_time':time_at(c,t),'assumptions':'Recorded contribution from simulated outcomes; pending estimates separate. RTO denominator = delivered + returned. COGS charged only on delivered goods; returns assumed restocked. Scenario costs are not validated predictions.'}
@app.get('/api/v1/traces')
def traces(agent:str='',u=Depends(auth),c=Depends(db)):
    q='SELECT a.*,o.external_id FROM agent_runs a LEFT JOIN orders o ON o.id=a.order_id AND o.tenant_id=a.tenant_id WHERE a.tenant_id=?'; args=[u['tenant_id']]
    if agent: q+=' AND a.agent=?'; args.append(agent)
    return {'items':rows(c,q+' ORDER BY a.created_at DESC,a.rowid DESC LIMIT 150',args),'agents':AGENTS}
@app.get('/api/v1/audit')
def audit_log(u=Depends(auth),c=Depends(db)):
    allow(u,OPS|{'finance'}); return {'items':rows(c,'SELECT * FROM audit WHERE tenant_id=? ORDER BY created_at DESC LIMIT 200',(u['tenant_id'],))}
@app.get('/api/v1/settings')
def settings(u=Depends(auth),c=Depends(db)):
    tenant=row(c,'SELECT * FROM tenants WHERE id=?',(u['tenant_id'],)); tenant['settings']=json.loads(tenant['settings'])
    return {'tenant':tenant,'users':rows(c,'SELECT u.email,m.role FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.tenant_id=?',(u['tenant_id'],)) if u['role']=='owner' else [],'dataset':row(c,'SELECT count(*) orders,sum(simulated) synthetic_orders FROM orders WHERE tenant_id=?',(u['tenant_id'],))}
@app.put('/api/v1/settings')
def update_settings(data:SettingsInput,request:Request,u=Depends(auth),c=Depends(db)):
    def op():
        c.execute('UPDATE tenants SET settings=? WHERE id=?',(js(data.model_dump()),u['tenant_id'])); return {'ok':True}
    return command(request,u,c,'settings.update',data.model_dump(),op,{'owner'})

# Durable connector jobs are processed synchronously in this local MVP. Pending retries
# survive restart and are drained by advancing virtual time (one SQLite worker).
@app.post('/api/v1/jobs/queue')
def queue_job(data:QueueInput,request:Request,u=Depends(auth),c=Depends(db)):
    def op():
        o=get_order(c,u['tenant_id'],data.order_id)
        job=insert(c,'jobs',id=uid(),tenant_id=u['tenant_id'],kind='monitor_poll',payload=js({'order_id':o['id'],'inject_timeout':data.inject_timeout}),status='pending',retry_count=0,locked_until=None,last_error=None,created_at=time_at(c,u['tenant_id']))
        return job
    return command(request,u,c,'job.queue',data.model_dump(),op,CSR)
@app.get('/api/v1/jobs')
def jobs(u=Depends(auth),c=Depends(db)):
    return {'items':rows(c,'SELECT * FROM jobs WHERE tenant_id=? ORDER BY created_at DESC LIMIT 100',(u['tenant_id'],))}
@app.post('/api/v1/demo/clock')
def clock(data:ClockInput,request:Request,u=Depends(auth),c=Depends(db)):
    def op():
        t=u['tenant_id']; new=(datetime.fromisoformat(time_at(c,t))+timedelta(hours=data.hours)).isoformat()
        c.execute('UPDATE tenants SET virtual_time=? WHERE id=?',(new,t)); processed=[]
        for job in rows(c,'SELECT * FROM jobs WHERE tenant_id=? AND status IN ("pending","retry") AND (locked_until IS NULL OR locked_until<=?)',(t,new)):
            p=json.loads(job['payload'])
            if p.get('inject_timeout') and job['retry_count']==0:
                c.execute('UPDATE jobs SET status="retry",retry_count=1,last_error="SIMULATED_CONNECTOR_TIMEOUT",locked_until=? WHERE tenant_id=? AND id=?',((datetime.fromisoformat(new)+timedelta(hours=1)).isoformat(),t,job['id']))
                event(c,t,p['order_id'],'connector_retry_scheduled',payload={'job_id':job['id'],'error':'SIMULATED_CONNECTOR_TIMEOUT','retry_after_hours':1})
                processed.append({'job_id':job['id'],'status':'retry'})
            else:
                c.execute('UPDATE jobs SET status="completed",locked_until=NULL,last_error=NULL WHERE tenant_id=? AND id=?',(t,job['id']))
                trace(c,t,p['order_id'],'Monitor',{'job_id':job['id'],'retry_count':job['retry_count']},{'status':'polled','shipment_state':get_order(c,t,p['order_id'])['status'],'note':'No automatic delivery or contact'})
                processed.append({'job_id':job['id'],'status':'completed'})
        return {'virtual_time':new,'processed':processed}
    return command(request,u,c,'demo.clock',data.model_dump(),op)

@app.post('/api/v1/demo/scenarios/{key}/run')
def demo(key:Literal['A','B','C','D','E','F','G','H','I'],data:DemoInput,request:Request,u=Depends(auth),c=Depends(db)):
    def op():
        import random
        if not data.approved: raise HTTPException(422,'Approve the listed synthetic scenario actions before running')
        t=u['tenant_id']; rng=random.Random(data.seed); created=[]; operations=[]
        def new(city=None,quality=95):
            o=ingest(c,t,{'external_id':'LAB-'+uid()[:12],'customer':'Demo Lab fictional customer','city':city or rng.choice(CITIES[:6]),'address':'Fictional House 12, Demo Road, Block C','address_quality':quality,'cod':rng.randint(20,80)*10000,'cogs':160000,'weight_g':rng.choice([350,500,750,1000])},u['email'])
            created.append(o['id']); return o
        def ready(o): return verify(c,t,o,'confirm',u['email'])
        def single_book(o,alternative=False):
            options=[q for q in quotes(c,t,o) if q['eligible']]
            options.sort(key=lambda q:(q['expected_cost'],q['code']))
            if not options: raise HTTPException(409,'No remaining courier capacity; advance virtual time one day or adjust rate-card capacity')
            q=options[min(1,len(options)-1)] if alternative else options[0]
            result=book(c,u,o,q,'Preapproved Demo Lab '+key+' synthetic route')
            if alternative:
                delta=q['expected_cost']-options[0]['expected_cost']
                audit(c,t,u['email'],'courier.override',o['id'],{'reason':'Demo manager selected faster SLA alternative','incremental_modeled_cost':delta})
                event(c,t,o['id'],'human_override',payload={'reason':'Demo manager selected SLA alternative','incremental_modeled_cost':delta})
            return result
        def drive(o,target): return advance(c,t,o,target,u['email'],{'demo_run':key,'seed':data.seed,'preapproved':True})
        def finish(o,delivered=True):
            o=drive(o,'in_transit'); o=drive(o,'out_for_delivery')
            if delivered: o=drive(o,'delivered')
            else:
                o=drive(o,'NDR'); o=drive(o,'RTO_initiated'); o=drive(o,'returned')
            return o
        result={'scenario':key,'seed':data.seed,'simulated':True,'order_ids':created}
        if key=='A':
            o=new(); result.update(message='Order received, validated and queued for verification.',order=o)
        elif key=='B':
            o=new(); o=verify(c,t,o,data.response,u['email'],'Fictional corrected House 14, Demo Street, Block D' if data.response=='address_change' else None)
            result.update(message='Verification response recorded. Non-response is a review hold, never a fraud label.',order=o)
        elif key=='C':
            o=new(quality=40); a=save_risk(c,t,o); o=verify(c,t,o,'no_response',u['email'])
            result.update(message='Legitimate-customer edge case: incomplete address contributes 35 points; non-response contributes zero. Manager can correct and release.',risk=a,order=o)
        elif key=='D':
            o=ready(new()); options=quotes(c,t,o)
            trace(c,t,o['id'],'Courier',{'city':o['city'],'weight_g':o['weight_g']},{'alternatives':options,'uncertainty':'Synthetic rate and outcome assumptions'})
            result.update(message='Rate cards, eligibility exclusions and cost components compared.',quotes=options,order=o)
        elif key=='E':
            for i in range(100): ready(new(CITIES[i%len(CITIES)]))
            p=optimize(c,t,created)
            result.update(message='100-order exact assignment computed. Review and approve this proposal in Allocation Studio.',proposal=p)
        elif key=='F':
            o=single_book(ready(new())); o=drive(o,'in_transit'); o=drive(o,'out_for_delivery'); o=drive(o,'NDR')
            result.update(message='Delivery failed with address clarification needed. Rescue Queue requires recorded customer approval before a retry.',order=o)
        elif key=='G':
            cases=[]
            for i in range(3):
                o=finish(single_book(ready(new()))); s=ensure_statement(c,t,o)
                actual=None if i==0 else s['expected']-7500 if i==1 else s['expected']
                state='missing' if actual is None else 'disputed' if actual!=s['expected'] else 'reconciled'
                c.execute('UPDATE statements SET actual=?,status=?,note=? WHERE tenant_id=? AND id=?',(actual,state,'Demo remittance: missing / incorrect deduction / matched',t,s['id']))
                trace(c,t,o['id'],'Finance',{'expected':s['expected'],'actual':actual},{'status':state})
                cases.append({'statement_id':s['id'],'status':state,'delta':None if actual is None else actual-s['expected']})
            result.update(message='Three courier payouts processed: missing, incorrect deduction, matched.',cases=cases)
        elif key=='H':
            o=finish(single_book(ready(new())),SimulationCourier().outcome(data.seed).code=='delivered'); s=ensure_statement(c,t,o)
            c.execute('UPDATE statements SET actual=expected,status="reconciled",note="Synthetic full-lifecycle payout matched",resolved_by=? WHERE tenant_id=? AND id=?',(u['email'],t,s['id']))
            trace(c,t,o['id'],'Finance',{'expected_remittance':s['expected']},{'status':'reconciled','recorded_contribution':realized(o)})
            result.update(message='Complete lifecycle recorded. The reproducible outcome can deliver or return; analytics now reflect the ledger.',order=o,realized_contribution=realized(o))
        elif key=='I':
            o=single_book(ready(new()),True)
            result.update(message='Manager override booked an eligible alternative. The incremental modeled cost and reason are in the audit timeline.',order=o)
        insert(c,'jobs',id=uid(),tenant_id=t,kind='demo_scenario_'+key,payload=js({'seed':data.seed,'orders':created,'approved_by':u['email']}),status='completed',retry_count=0,created_at=time_at(c,t))
        return result
    return command(request,u,c,'demo.scenario.'+key,data.model_dump(),op)

@app.post('/api/v1/demo/reset')
def reset(data:ResetInput,request:Request,u=Depends(auth),c=Depends(db)):
    def op():
        t=u['tenant_id']
        for table in ['jobs','allocations','statements','agent_runs','events','order_items','orders','customers','products','couriers','stores']:
            c.execute(f'DELETE FROM {table} WHERE tenant_id=?',(t,))
        c.execute('UPDATE tenants SET settings=?,virtual_time=?,seed=? WHERE id=?',(js(SETTINGS),'2026-11-08T05:00:00+00:00',data.seed,t))
        seed_tenant(c,t,6200 if t=='t1' else 1800,data.seed)
        return {'ok':True,'orders':6200 if t=='t1' else 1800,'seed':data.seed,'note':'Tenant dataset reset; append-only audit history and sessions preserved.'}
    return command(request,u,c,'demo.reset',data.model_dump(),op,{'owner'})

class PrivacyInput(Reason): action:Literal['opt_out','anonymize']
@app.post('/api/v1/customers/{cid}/privacy')
def privacy(cid:str,data:PrivacyInput,request:Request,u=Depends(auth),c=Depends(db)):
    def op():
        if not data.approved: raise HTTPException(422,'Privacy action requires human approval')
        cu=row(c,'SELECT * FROM customers WHERE tenant_id=? AND id=?',(u['tenant_id'],cid))
        if not cu: raise HTTPException(404,'Customer not found')
        c.execute('UPDATE customers SET opt_out_at=? WHERE tenant_id=? AND id=?',(time_at(c,u['tenant_id']),u['tenant_id'],cid))
        if data.action=='anonymize':
            c.execute('UPDATE customers SET name="Anonymized fictional customer",contact=? WHERE tenant_id=? AND id=?',('SYN-REMOVED-'+cid,u['tenant_id'],cid))
            c.execute('UPDATE orders SET address="Removed by demo privacy request",address_quality=0,risk_score=35,version=version+1 WHERE tenant_id=? AND customer_id=?',(u['tenant_id'],cid))
        return {'ok':True,'action':data.action,'note':'Operational amounts and append-only audit evidence retained; contact blocked. Demo-only anonymization is not a production deletion service.'}
    return command(request,u,c,'customer.privacy.'+cid,data.model_dump(),op,{'owner'})
@app.get('/api/v1/tenants/current')
def current_tenant(u=Depends(auth),c=Depends(db)): return row(c,'SELECT id,name,virtual_time,seed FROM tenants WHERE id=?',(u['tenant_id'],))
