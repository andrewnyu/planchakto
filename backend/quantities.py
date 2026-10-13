import math
from .geometry import wall_geometry,openings
from .structure import CATALOG

def takeoff(b,structure,routing):
    walls=wall_geometry(b);doors=openings(b);e=b.engineering
    def route_items(kind):return [r for r in routing['routes'] if r['kind']==kind]
    steel=sum(x['length'] for x in structure['beams'])*CATALOG[e.section]['kg_m']
    data={
      'slab':(b.width*b.depth*.1,[b.slab_id],'width × depth × 0.10 m assumed slab thickness'),
      'roof':(b.width*b.depth,[b.roof_id],'width × depth; flat projected roof, no overhang'),
      'steel':(steel,[x['id'] for x in structure['beams']],'Σ beam lengths × theoretical RHS kg/m; sharp-corner section assumption'),
      'columns':(sum(c.active for c in b.columns)*b.height,[c.id for c in b.columns if c.active],'active column count × storey height; section adequacy not evaluated'),
      'foundations':(sum(c.active for c in b.columns)*e.footing_width**2*e.footing_thickness,[f'foundation-{c.id}' for c in b.columns if c.active],'count × width² × thickness; preliminary pads'),
      'walls':(max(0,sum(w['length'] for w in walls)*b.height*2-sum(d['width']*d['height'] for d in doors)*2),[w['id'] for w in walls]+[d['id'] for d in doors],'unique wall centerline length × height × 2 faces − modeled door areas × 2; no window deductions (windows not modeled)'),
      'floor':(sum(r.w*r.h for r in b.rooms),[r.id for r in b.rooms],'Σ room rectangles including circulation'),
      'fixtures':(len(b.fixtures),[f.id for f in b.fixtures],'count of modeled plumbing fixtures'),
      'equipment':(len(b.equipment),[x.id for x in b.equipment],'count of modeled electrical equipment'),
      'fittings':(sum(len(r['fittings']) for r in routing['routes']),[f['id'] for r in routing['routes'] for f in r['fittings']],'count of explicitly modeled route elbows; terminals included in fixture allowances'),
    }
    for kind in ['water','drain','conduit']:data[kind]=(sum(r['length'] for r in route_items(kind)),[r['id'] for r in route_items(kind)],'Σ physical polyline lengths; dedicated home runs')
    items=[]
    for rate in b.rates:
        if rate.id not in data:continue
        net,ids,formula=data[rate.id];with_waste=net*(1+rate.waste)
        purchased=math.ceil(round(with_waste/rate.stock,10))*rate.stock if rate.stock else (math.ceil(with_waste) if rate.unit=='each' else with_waste)
        items.append({'id':rate.id,'name':rate.name,'unit':rate.unit,'net':net,'waste':rate.waste,'waste_quantity':net*rate.waste,'stock':rate.stock,'purchased':purchased,'rate':rate.rate,'cost':round(purchased*rate.rate,2),'source_ids':ids,'formula':formula,'rate_source':rate.source,'rate_date':rate.date,'provisional':any(r['status']!='pass' for r in route_items(rate.id)) if rate.id in ['water','drain','conduit'] else False})
    return {'items':items,'total':round(sum(x['cost'] for x in items),2),'currency':'PHP','catalog':'Editable demonstration rates — not current Philippine market prices','exclusions':['Labor beyond any unit-rate allowance','Detailed reinforcement','Windows and facade systems','Connections and fasteners','Electrical conductors and protection','Hydraulic sizing, valves and vents','Taxes, permits and professional fees'],'walls':walls,'openings':doors}

def compare(before,after,before_model,after_model):
    a={x['id']:x for x in before['quantities']['items']};c={x['id']:x for x in after['quantities']['items']}
    rows=[{'id':id,'name':c[id]['name'],'unit':c[id]['unit'],'before':a.get(id,{}).get('net',0),'after':c[id]['net'],'delta':c[id]['net']-a.get(id,{}).get('net',0),'cost_delta':c[id]['cost']-a.get(id,{}).get('cost',0)} for id in c]
    geometry=[]
    for group in ['rooms','columns','furniture']:
        old={x['id']:x for x in before_model[group]};new={x['id']:x for x in after_model[group]}
        for id in sorted(set(old)|set(new)):
            if old.get(id)!=new.get(id):geometry.append({'id':id,'kind':group,'before':old.get(id),'after':new.get(id)})
    return {'quantities':rows,'cost_delta':after['quantities']['total']-before['quantities']['total'],'geometry':geometry,'before_total':before['quantities']['total'],'after_total':after['quantities']['total'],'checks_before':before['summary'],'checks_after':after['summary']}
