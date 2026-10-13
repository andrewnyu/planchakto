from ortools.sat.python import cp_model
from .domain import Building,MoveRoom,apply_commands
from .geometry import layout_checks
import time,math

def generate_layouts(b:Building,count=3):
    t=time.perf_counter();candidates=[];excluded=[]
    halls=[r for r in b.rooms if r.kind=='corridor']
    if len(halls)!=1:raise ValueError('Generator supports exactly one fixed horizontal circulation corridor')
    hall=halls[0];rooms=[r for r in b.rooms if r.kind!='corridor'];scale=2
    if any(abs(v*scale-round(v*scale))>1e-6 for r in b.rooms for v in [r.x,r.y,r.w,r.h]):raise ValueError('Layout generation requires coordinates and dimensions on the 0.5 m planning grid')
    for index in range(count):
        model=cp_model.CpModel();xs={};ws={};ends={};intervals={0:[],1:[]};terms=[]
        for r in rooms:
            band=0 if r.y<hall.y else 1;h=hall.y if band==0 else b.depth-hall.y-hall.h
            if h<=0:raise ValueError('Corridor must leave two positive room strips')
            minw=math.ceil(max(r.min_dimension,r.min_area/h)*scale);maxw=math.floor(min(b.width,r.max_area/h)*scale)
            if minw>maxw or h<r.min_dimension:raise ValueError(f'Infeasible room {r.name}: area or dimension bounds cannot fit its corridor strip')
            xs[r.id]=x=model.new_int_var(0,round(b.width*scale),f'x-{r.id}');ws[r.id]=w=model.new_int_var(minw,maxw,f'w-{r.id}');ends[r.id]=end=model.new_int_var(0,round(b.width*scale),f'end-{r.id}')
            model.add(end==x+w);intervals[band].append(model.new_interval_var(x,w,end,f'interval-{r.id}'))
            if r.locked or any(f.locked and f.room_id==r.id for f in b.furniture):
                if abs(r.h-h)>1e-6:raise ValueError(f'Locked room {r.name} is incompatible with fixed corridor strips')
                model.add(x==round(r.x*scale));model.add(w==round(r.w*scale))
            change=model.new_int_var(0,100,'change-'+r.id);model.add_abs_equality(change,x-round(r.x*scale))
            fit=model.new_int_var(0,100,'fit-'+r.id);model.add_abs_equality(fit,w-round(r.w*scale))
            # Alternatives expose their objective weights; no claim beyond this bounded model.
            terms.append(fit*b.brief.area_weight*([8,3,2][index%3])+change*(b.brief.change_weight if index==0 else 0))
        for band,ivs in intervals.items():
            model.add_no_overlap(ivs);ids=[r.id for r in rooms if (0 if r.y<hall.y else 1)==band]
            model.add(sum(ws[id] for id in ids)==round(b.width*scale))
        kitchen=next((r for r in rooms if r.kind=='kitchen'),None);bath=next((r for r in rooms if r.kind=='bathroom'),None)
        if kitchen and bath:
            if b.brief.wet_adjacency:
                if (kitchen.y<hall.y)!=(bath.y<hall.y):raise ValueError('Required wet-room adjacency conflicts with the fixed corridor strip assignment')
                side=model.new_bool_var('wet-side');model.add(ends[kitchen.id]==xs[bath.id]).only_enforce_if(side);model.add(ends[bath.id]==xs[kitchen.id]).only_enforce_if(side.Not())
            distance=model.new_int_var(0,100,'wet-distance');model.add_abs_equality(distance,2*xs[bath.id]+ws[bath.id]-round(2*b.site.water.x*scale));terms.append(distance*b.brief.wet_weight*(1 if index!=2 else 3))
        keys=[v for r in rooms for v in [xs[r.id],ws[r.id]]]
        if excluded:model.add_forbidden_assignments(keys,excluded)
        model.minimize(sum(terms));solver=cp_model.CpSolver();solver.parameters.max_time_in_seconds=2;solver.parameters.random_seed=42;solver.parameters.num_search_workers=1
        status=solver.solve(model)
        if status not in [cp_model.OPTIMAL,cp_model.FEASIBLE]:
            if not candidates:return {'candidates':[],'status':solver.status_name(status),'diagnostic':'No solution for fixed corridor strips, room area/dimension bounds, locks, no-overlap, envelope and required wet adjacency. This is the tested constraint set, not a minimal unsatisfiable core.','elapsed_ms':(time.perf_counter()-t)*1000}
            break
        values=[solver.value(v) for v in keys];excluded.append(values);commands=[]
        for r in rooms:
            band=0 if r.y<hall.y else 1;y=0 if band==0 else hall.y+hall.h;h=hall.y if band==0 else b.depth-y
            x=solver.value(xs[r.id])/scale;w=solver.value(ws[r.id])/scale
            if (x,y,w,h)!=(r.x,r.y,r.w,r.h):commands.append(MoveRoom(type='move_room',room_id=r.id,x=x,y=y,w=w,h=h))
        if not commands:continue
        candidate,_=apply_commands(b,commands);checked=layout_checks(candidate)
        if checked['status']!='pass':raise ValueError('CP-SAT result failed independent geometry validation')
        candidates.append({'label':['Closest to current','Wet services first','Compact alternative'][index%3],'commands':[c.model_dump() for c in commands],'solver_status':solver.status_name(status),'objective':solver.objective_value,'best_bound':solver.best_objective_bound,'seed':42,'elapsed_ms':round(solver.wall_time*1000,2),'objective_description':f'Area-fit weight {b.brief.area_weight*[8,3,2][index%3]}, change weight {b.brief.change_weight if index==0 else 0}, wet-service distance weight {b.brief.wet_weight*(3 if index==2 else 1)}','optimality_scope':'OPTIMAL only means proven for this discrete strip model, not a globally optimal building'})
    return {'candidates':candidates,'status':'complete','elapsed_ms':round((time.perf_counter()-t)*1000,2),'baseline':{'name':'Unchanged input arrangement','feasible':layout_checks(b)['status']=='pass'},'scope':'Two fixed room strips, fixed full-width corridor, half-metre width/position grid. Rooms stay in their original strip; roof columns remain fixed.'}
