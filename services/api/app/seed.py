"""PG-1 seeded event replay. No real personal identities or network integrations."""
import random, math, json, hashlib
from datetime import datetime,timedelta,timezone
from argon2 import PasswordHasher
from . import domain
from .db import stable,insert,js,row,rows,now
from .domain import advance,get_order,trace,event,assess
SEED=20261108
SETTINGS={'default_courier':'SWF','sla_penalty':18000,'handling':1200,'retention_days':180,'consent_required':True}
NAMES=['Ayesha','Hamza','Zara','Bilal','Mariam','Usman','Hira','Ali','Sana','Omar']
PRODUCTS=['Everyday cotton kurta','Botanical face serum','Linen co-ord set','Ceramic serving set','Classic tote bag','Daily care bundle']

def checksum(c):
    data=rows(c,'SELECT id,tenant_id,external_id,city,cod,cogs,status,verification,courier_id,actual_cost,revenue,created_at FROM orders ORDER BY id')
    return hashlib.sha256(js(data).encode()).hexdigest()

def seed_tenant(c,t,count,seed=SEED):
    rng=random.Random(seed+(0 if t=='t1' else 1)); counter=[0]
    original=domain.uid
    def sid():
        counter[0]+=1
        return stable(f'{seed}/{t}/generated/{counter[0]}')
    domain.uid=sid
    try:
        store_count=2 if t=='t1' else 1
        for i in range(store_count): insert(c,'stores',id=stable(t+'store'+str(i)),tenant_id=t,name=(['Gul Studio','Noor Essentials'] if t=='t1' else ['Meher Home'])[i],platform='CSV simulation')
        for i,name in enumerate(PRODUCTS): insert(c,'products',id=stable(t+'sku'+str(i)),tenant_id=t,sku=f'PG-{i+1:03}',name=name,price=(i+2)*120000,cogs=(i+1)*65000,weight_g=400+i*150)
        for i,(name,code,color,cap,fwd,rev,rto,late,days) in enumerate([
            ('SwiftPak','SWF','#165e4a',40,19500,18000,1350,1200,3),('Raabta Express','RBT','#7871b6',35,21500,11500,900,600,2),('Mehr Logistics','MHR','#d59840',25,17500,26000,2400,1800,4),('Atlas Parcel','ATL','#5380a2',30,24500,10500,700,400,2)]):
            zones=domain.CITIES[:] if i!=2 else domain.CITIES[:5]
            insert(c,'couriers',id=stable(t+code),tenant_id=t,name=name+' · simulated',code=code,color=color,capacity=cap,max_weight=5000 if i!=2 else 2500,max_cod=20000000 if i!=2 else 1500000,zones=js(zones),forward=fwd,reverse=rev,cod_fee=3000,rto_bp=rto,late_bp=late,sla_days=days)
        carriers=rows(c,'SELECT * FROM couriers WHERE tenant_id=? ORDER BY code',(t,))
        start=datetime(2026,5,7,5,0,tzinfo=timezone.utc)
        completed=[]
        for i in range(count):
            at=start+timedelta(seconds=(i*180*86400//max(1,count)))
            day=lambda n:(at+timedelta(hours=n)).isoformat()
            city=rng.choices(domain.CITIES,[25,22,18,15,8,7,3,2])[0]
            cod=int(max(700,min(25000,math.exp(rng.gauss(8.1,.55)))))*100
            quality=40 if i%80==0 else rng.randint(68,100)
            desired=rng.choices(['delivered','returned','NDR','in_transit','ready_to_ship','verification_pending','hold_review','cancelled_before_ship','lost_damaged_dispute'],[65,10,3,4,5,3,3,6,1])[0]
            oid=stable(f'{t}:order:{seed}:{i}')
            data={'external_id':f'PG-{1 if t=="t1" else 2}{i+1:05}','customer':NAMES[i%10]+' Demo '+str(i+1),'city':city,'address':f'Fictional block {i%20+1}, Demo Street {i%15+1}, {city}','address_quality':quality,'cod':cod,'cogs':cod*rng.randint(43,65)//100,'weight_g':rng.choice([350,500,750,1000,1500,2200,3500])}
            o=domain.ingest(c,t,data,'seed',day(0),oid)
            c.execute('UPDATE orders SET store_id=? WHERE tenant_id=? AND id=?',(stable(t+'store'+str(i%store_count)),t,oid))
            a=assess(o); c.execute('UPDATE orders SET risk_score=?,risk_reasons=? WHERE id=?',(a['score'],js(a),oid))
            if desired=='verification_pending': continue
            if desired in {'hold_review','cancelled_before_ship'}:
                advance(c,t,o,desired,'seed',{'response':'no_response' if desired=='hold_review' else 'cancel'},day(1))
                c.execute('UPDATE orders SET verification=? WHERE id=?',('no_response' if desired=='hold_review' else 'cancel',oid))
                trace(c,t,oid,'Verification',{'synthetic':True},{'response':'no_response' if desired=='hold_review' else 'cancel','note':'No response is not fraud'},day(1))
                continue
            o=advance(c,t,o,'confirmed','seed',at=day(1))
            c.execute('UPDATE orders SET verification="confirm" WHERE id=?',(oid,))
            trace(c,t,oid,'Verification',{'synthetic':True},{'response':'confirm'},day(1))
            o=advance(c,t,o,'ready_to_ship','seed',at=day(2))
            if desired=='ready_to_ship': continue
            eligible=[q for q in carriers if city in json.loads(q['zones']) and o['weight_g']<=q['max_weight'] and cod<=q['max_cod']]
            q=rng.choice(eligible)
            fwd=q['forward']+max(0,(o['weight_g']-1)//500)*3500
            expected=fwd+q['cod_fee']+q['rto_bp']*q['reverse']//10000+q['late_bp']*18000//10000+1200
            c.execute('UPDATE orders SET courier_id=?,forward=?,reverse=?,cod_fee=?,expected_cost=?,dispatch_at=? WHERE id=?',(q['id'],fwd,q['reverse'],q['cod_fee'],expected,day(3),oid))
            o=advance(c,t,o,'booked_simulated','seed',at=day(3))
            o=advance(c,t,o,'in_transit','seed',at=day(12))
            if desired=='in_transit': continue
            if desired=='lost_damaged_dispute':
                o=advance(c,t,o,desired,'seed',at=day(48)); completed.append(oid); continue
            o=advance(c,t,o,'out_for_delivery','seed',at=day(36))
            if desired in {'NDR','returned'} or (desired=='delivered' and i%11==0):
                o=advance(c,t,o,'NDR','seed',{'reason':'Address clarification requested'},day(40))
                if desired=='NDR': continue
                if desired=='returned':
                    o=advance(c,t,o,'RTO_initiated','seed',at=day(60))
                    o=advance(c,t,o,'returned','seed',at=day(96))
                else:
                    c.execute('UPDATE orders SET actual_cost=3500,service_cost=1500 WHERE id=?',(oid,))
                    o=advance(c,t,o,'reattempt','seed',{'customer_approved':True},day(48))
                    o=advance(c,t,o,'out_for_delivery','seed',at=day(60))
                    o=advance(c,t,o,'delivered','seed',at=day(65))
            else: o=advance(c,t,o,'delivered','seed',at=day(40))
            completed.append(oid)
        for i,oid in enumerate(completed[-(300 if t=='t1' else 80):]):
            o=get_order(c,t,oid); expected=o['revenue']-o['actual_cost']
            actual=None if i<10 else expected-7500 if i<30 else expected
            status='missing' if actual is None else 'disputed' if actual!=expected else 'reconciled'
            insert(c,'statements',id=stable(t+'statement'+str(i)),tenant_id=t,order_id=oid,booking_ref='SIM-'+o['external_id'],expected=expected,actual=actual,status=status,note='Synthetic missing payout' if i<10 else 'Synthetic rate discrepancy' if i<30 else 'Matched synthetic remittance',created_at=day(120))
            if i<30: domain.audit(c,t,'seed','reconciliation_exception',oid,{'delta':None if actual is None else actual-expected})
    finally: domain.uid=original

def seed(c,seed=SEED,total=8000):
    if row(c,'SELECT id FROM tenants LIMIT 1'): return checksum(c)
    for t,name in [('t1','Gul Studio'),('t2','Meher Home')]: insert(c,'tenants',id=t,name=name+' · fictional',settings=js(SETTINGS),virtual_time='2026-11-08T05:00:00+00:00',seed=seed)
    ph=PasswordHasher(); hashed=ph.hash('DemoProfit2026!')
    for role in ['owner','manager','csr','finance','viewer']:
        user=stable('user'+role)
        insert(c,'users',id=user,email=role+'@profitguard.example',password_hash=hashed)
        insert(c,'memberships',user_id=user,tenant_id='t1',role=role)
    user=stable('otherowner'); insert(c,'users',id=user,email='other@profitguard.example',password_hash=hashed)
    insert(c,'memberships',user_id=user,tenant_id='t2',role='owner')
    n=int(total*.775)
    seed_tenant(c,'t1',n,seed); seed_tenant(c,'t2',total-n,seed)
    for t in ['t1','t2']: domain.audit(c,t,'system','dataset_seeded',payload={'seed':seed,'total':total,'checksum':checksum(c)})
    c.commit(); return checksum(c)
