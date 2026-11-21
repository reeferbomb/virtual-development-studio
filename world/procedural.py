"""Deterministic arena designs and conservative capsule-clearance route planning."""
import argparse
from collections import deque
import json
import math
from pathlib import Path
import random

CLEARANCE = .65  # 0.35 m player radius plus steering and grid margin.


def rectangles(spec, margin=CLEARANCE):
    result = []
    for item in spec.get('blocks', []) + spec.get('placements', []):
        if 'size' in item:
            w,h,d = item['size']; x,y,z = item['position']
            if y+h/2 <= 0 or y-h/2 >= 1.8: continue
        elif 'collider_size' in item:
            w,h,d = item['collider_size']; x,y,z = item['position']
            if y+h <= 0 or y >= 1.8: continue
            angle = math.radians(item.get('yaw_deg',0))
            w,d = abs(math.cos(angle))*w+abs(math.sin(angle))*d, abs(math.sin(angle))*w+abs(math.cos(angle))*d
        else:
            continue
        result.append((x-w/2-margin,z-d/2-margin,x+w/2+margin,z+d/2+margin))
    return result


def intersects(a,b,rect):
    low,high=0.,1.
    for start, end, lower, upper in ((a[0],b[0],rect[0],rect[2]),(a[1],b[1],rect[1],rect[3])):
        delta=end-start
        if abs(delta)<1e-10:
            if start<lower or start>upper: return False
        else:
            t,u=sorted(((lower-start)/delta,(upper-start)/delta))
            low,high=max(low,t),min(high,u)
            if low>high: return False
    return True


def _clear(a,b,rects,limit):
    return max(abs(v) for v in (*a,*b)) <= limit and not any(intersects(a,b,r) for r in rects)


def clear_segment(spec,a,b):
    t=spec['terrain']
    limit=min(t['flat_radius'],t['width']/2,t['depth']/2)-CLEARANCE
    return _clear((a[0],a[2]),(b[0],b[2]),rectangles(spec),limit)


def plan_route(spec):
    """Search the flat core on a 1 m grid; link exact endpoints and smooth only clear segments."""
    t=spec['terrain']; limit=min(t['flat_radius'],t['width']/2,t['depth']/2)-CLEARANCE
    rects=rectangles(spec)
    start=(spec['spawn'][0],spec['spawn'][2]); goal=(spec['goal'][0],spec['goal'][2])
    def clear(a,b): return _clear(a,b,rects,limit)
    if clear(start,goal): return [spec['spawn'],spec['goal']]
    if not clear(start,start) or not clear(goal,goal): raise ValueError('No clearance-safe route: endpoint blocked')
    def neighbors(p):
        x,z=p
        for i in range(math.floor(x)-1,math.ceil(x)+2):
            for j in range(math.floor(z)-1,math.ceil(z)+2):
                if math.dist(p,(i,j))<=1.6 and clear(p,(i,j)):
                    yield (i,j)
    targets=set(neighbors(goal)); parents={p:start for p in neighbors(start)}
    parents[start]=None; queue=deque(p for p in parents if p!=start)
    if start in targets: queue.append(start)
    end=None
    while queue:
        current=queue.popleft()
        if current in targets: end=current; break
        for dx,dz in ((1,0),(-1,0),(0,1),(0,-1)):
            nxt=(current[0]+dx,current[1]+dz)
            if nxt not in parents and clear(current,nxt):
                parents[nxt]=current; queue.append(nxt)
    if end is None: raise ValueError('No clearance-safe route through flat core')
    points=[goal]; node=end
    while node is not None:
        if node!=points[-1]: points.append(node)
        node=parents[node]
    points.reverse()
    smooth=[points[0]]; index=0
    while index<len(points)-1:
        nxt=len(points)-1
        while not clear(points[index],points[nxt]): nxt-=1
        smooth.append(points[nxt]); index=nxt
    return [[x,0,z] for x,z in smooth]


def generate(seed, count=24):
    if type(seed) is not int or not 0<=seed<=2147483647: raise ValueError('Seed must be an integer 0–2147483647')
    if type(count) is not int or not 1<=count<=40: raise ValueError('Cover count must be 1–40')
    rng=random.Random(seed)
    design={'id':f'procedural_{seed}','terrain':{'width':48,'depth':48,'flat_radius':20,'segments':48,'amplitude':round(rng.uniform(.5,1.5),2)},'spawn':[-18,0,0],'goal':[18,0,0],'blocks':[{'id':'central_barrier','position':[0,1,0],'size':[2,2,6],'color':[.32,.38,.41]}],'placements':[]}
    cells=[(x,z) for x in range(-15,16,5) for z in range(-15,16,5) if (x,z)!=(0,0)]
    rng.shuffle(cells)
    for index,(x,z) in enumerate(cells[:count-1],1):
        w,d=rng.choice([(2,2),(3,.8),(.8,3),(2,1.5)])
        h=rng.choice([1.1,1.8,2.5])
        design['blocks'].append({'id':f'cover_{index:02d}','position':[x,h/2,z],'size':[w,h,d],'color':[round(rng.uniform(.25,.48),2) for _ in range(3)]})
    for index,(x,z) in enumerate(cells[count-1:count+5],1):
        asset,size=rng.choice([('supply_crate',[1.1,1.11,1.05]),('industrial_barrel',[.68,.94,.68]),('road_barricade',[1.85,1.08,.75])])
        design['placements'].append({'id':f'prop_{index:02d}','asset':asset,'position':[x,0,z],'yaw_deg':rng.choice([0,90,180,270]),'collider_size':size})
    plan_route(design)
    return design


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('seed',type=int);p.add_argument('output',type=Path);p.add_argument('--cover',type=int,default=24);a=p.parse_args()
    with a.output.open('x') as stream: json.dump(generate(a.seed,a.cover),stream,indent=2)
