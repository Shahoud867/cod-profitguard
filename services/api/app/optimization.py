"""Exact minimum-cost bipartite assignment; courier capacities expanded into slots.
Unassigned dummy slots make partial coverage explicit. Hard eligibility is never softened.
"""
import json, hashlib
import numpy as np
from scipy.optimize import linear_sum_assignment
from .db import rows, row, insert, uid, js
from .domain import quotes, trace, time_at

def fingerprint(c,t):
    return hashlib.sha256(js({'couriers':rows(c,'SELECT * FROM couriers WHERE tenant_id=? ORDER BY id',(t,)),'settings':row(c,'SELECT settings FROM tenants WHERE id=?',(t,))}).encode()).hexdigest()

def optimize(c,t,order_ids=None,limit=100,fairness=0):
    if order_ids:
        placeholders=','.join('?' for _ in order_ids)
        orders=rows(c,f'SELECT * FROM orders WHERE tenant_id=? AND id IN ({placeholders}) AND status="ready_to_ship" ORDER BY created_at,id',(t,*order_ids))
    else: orders=rows(c,'SELECT * FROM orders WHERE tenant_id=? AND status="ready_to_ship" ORDER BY created_at,id LIMIT ?',(t,limit))
    matrix=[quotes(c,t,o) for o in orders]
    carriers=matrix[0] if orders else []
    slots=[(q['id'],k) for q in carriers for k in range(min(len(orders),q['available_capacity']))]
    forbidden=10**12; unassigned=10**10
    costs=np.full((len(orders),len(slots)+len(orders)),unassigned,dtype=np.int64)
    lookup=[{q['id']:q for q in options} for options in matrix]
    for i,options in enumerate(lookup):
        for j,(cid,k) in enumerate(slots):
            q=options[cid]
            costs[i,j]=q['expected_cost']+fairness*(2*k+1)//max(1,q['available_capacity']) if q['eligible'] else forbidden
    chosen={}
    if orders:
        rr,cc=linear_sum_assignment(costs)
        chosen={int(i):slots[int(j)][0] if j<len(slots) and costs[i,j]<unassigned else None for i,j in zip(rr,cc)}
    settings=json.loads(row(c,'SELECT settings FROM tenants WHERE id=?',(t,))['settings'])
    def baseline(strategy):
        remaining={q['id']:q['available_capacity'] for q in carriers}; total=0; assigned=0; routes=[]
        for i,o in enumerate(orders):
            candidates=[q for q in matrix[i] if q['eligible'] and remaining[q['id']]>0]
            candidates.sort(key=(lambda q:(q['forward']+q['cod_fee'],q['code'])) if strategy=='cheapest_forward' else (lambda q:(q['code']!=settings['default_courier'],q['expected_cost'],q['code'])))
            if candidates:
                q=candidates[0]; remaining[q['id']]-=1; total+=q['expected_cost']; assigned+=1; routes.append(q['id'])
            else: routes.append(None)
        return {'expected_cost':total,'assigned':assigned,'routes':routes}
    allocations=[]; total=0; usage={q['id']:0 for q in carriers}
    for i,o in enumerate(orders):
        cid=chosen.get(i); q=lookup[i].get(cid)
        if q: total+=q['expected_cost']; usage[cid]+=1
        allocations.append({'order_id':o['id'],'external_id':o['external_id'],'city':o['city'],'version':o['version'],'courier_id':cid,'courier':q['name'] if q else 'Unassigned','expected_cost':q['expected_cost'] if q else 0,'alternatives':matrix[i],'reason':'Minimum modeled batch objective subject to hard constraints' if q else 'No eligible courier or insufficient capacity; human follow-up required'})
    cheapest=baseline('cheapest_forward'); default=baseline('merchant_default')
    result={'allocations':allocations,'order_count':len(orders),'assigned':sum(usage.values()),'unassigned':len(orders)-sum(usage.values()),'optimized_cost':total,'baseline_cheapest':cheapest,'baseline_default':default,'hypothetical_difference':cheapest['expected_cost']-total if cheapest['assigned']==sum(usage.values()) and sum(usage.values())==len(orders) else None,'capacity':[{'id':q['id'],'name':q['name'],'used':usage[q['id']],'available':q['available_capacity'],'total':q['capacity']} for q in carriers],'objective':'F + pRTO × R + pLate × SLA penalty + COD fee + handling + optional convex capacity penalty','fairness_penalty':fairness,'algorithm':'SciPy linear_sum_assignment / exact capacitated assignment via courier slots','uncertainty':'Hypothetical costs, synthetic rates and uncalibrated scenario probabilities; no Nash equilibrium or proven savings claimed. Incomplete coverage is not comparable.','fingerprint':fingerprint(c,t),'created_at':time_at(c,t)}
    aid=uid(); result['id']=aid
    insert(c,'allocations',id=aid,tenant_id=t,proposal=js(result),status='proposed',created_at=time_at(c,t))
    trace(c,t,None,'Allocator',{'orders':len(orders),'fairness':fairness},{'proposal_id':aid,'cost':total,'assigned':result['assigned'],'baseline_cheapest':cheapest['expected_cost'],'algorithm':result['algorithm'],'objective':result['objective']})
    return result
