"""Permit drawing set for one revision: discipline sheets (A, S, E, P, FP) built once as model-space primitives,
rendered to a vector PDF with a PH permit title block (reportlab) and to a layered DXF (ezdxf).
The set is preliminary: every sheet carries blank sign-and-seal fields and a not-for-construction mark."""
import io,math,datetime
from typing import Literal
from pydantic import Field
from shapely.geometry import LineString,box
from shapely.ops import unary_union
from .domain import Model,Building
from .geometry import openings,wall_geometry
from .fire import exit_segments

SHEET_SIZES={'20x30':(762.,508.),'A3':(420.,297.)}  # mm, landscape
SCALES=[50,75,100,125,150,200,250,300,400,500]
PROFESSIONS={'A':'Architect','S':'Civil / Structural Engineer','E':'Professional Electrical Engineer','P':'Sanitary Engineer / Master Plumber','FP':'Professional Mechanical Engineer (fire protection)'}
SIZE_SOURCE='Sheet size per local OBO checklists (20" × 30" standard; A3 accepted for residential by some LGUs). Confirm with the Office of the Building Official.'

class Professional(Model):
    name:str=Field(default='',max_length=120)
    prc_no:str=Field(default='',max_length=40)
    prc_validity:str=Field(default='',max_length=40)
    apo_no:str=Field(default='',max_length=40)
    ptr_no:str=Field(default='',max_length=40)
    ptr_date:str=Field(default='',max_length=40)
    ptr_place:str=Field(default='',max_length=80)
    tin:str=Field(default='',max_length=40)
class PermitRequest(Model):
    sheet:Literal['20x30','A3']='20x30'
    project_title:str=Field(default='',max_length=160)
    location:str=Field(default='',max_length=200)
    owner:str=Field(default='',max_length=160)
    disciplines:list[Literal['A','S','E','P','FP']]=Field(default_factory=lambda:['A','S','E','P','FP'])
    professionals:dict[Literal['A','S','E','P','FP'],Professional]=Field(default_factory=dict)
    date:str=Field(default_factory=lambda:datetime.date.today().isoformat(),max_length=40)

# ---------------------------------------------------------------- primitives
class View:
    """Model-space drawing (metres, y down as in the app plan). `underlay` is base geometry drawn grey in PDF only."""
    def __init__(self,title,bounds,dxf=True):
        self.title=title;self.bounds=bounds;self.items=[];self.underlay=[];self.dxf=dxf;self.scale=None
    def _add(self,item,under):(self.underlay if under else self.items).append(item)
    def line(self,layer,a,b,w=.25,dash=False,under=False):self._add(('line',layer,tuple(a),tuple(b),w,dash),under)
    def poly(self,layer,pts,closed=False,w=.25,dash=False,fill=None,under=False):self._add(('poly',layer,[tuple(p) for p in pts],closed,w,dash,fill),under)
    def rect(self,layer,x,y,wd,ht,**k):self.poly(layer,[(x,y),(x+wd,y),(x+wd,y+ht),(x,y+ht)],closed=True,**k)
    def circle(self,layer,c,r,w=.25,fill=None,dash=False,under=False):self._add(('circle',layer,tuple(c),r,w,fill,dash),under)
    def text(self,layer,p,s,h=2.5,align='center',bold=False,under=False):self._add(('text',layer,tuple(p),str(s),h,align,bold),under)

def arc(c,r,a0,a1,n=12):return [(c[0]+r*math.cos(a0+(a1-a0)*i/n),c[1]+r*math.sin(a0+(a1-a0)*i/n)) for i in range(n+1)]

def doors(b,r):
    """Door openings as (id, hinge, along-unit-vector, swing-unit-vector, width)."""
    out=[];rooms={x.id:x for x in b.rooms}
    for d in openings(b):
        if d['kind']=='door':
            room=rooms[d['room_id']];swing=-1 if room.y<d['y'] else 1
            out.append((d['id'],(d['x'],d['y']),(1,0),(0,swing),d['width']))
    # Exterior doors swing outward, in the direction of egress; added fire exits only when the fire screen is on.
    for s in [x for x in exit_segments(b) if b.fire.enabled or x['id']=='door-entry']:
        (x0,y0),(x1,y1)=s['a'],s['b'];vertical=x0==x1
        out_dir=(-1 if x0==0 else 1,0) if vertical else (0,-1 if y0==0 else 1)
        out.append((s['id'],(x0,y0),(0,1) if vertical else (1,0),out_dir,s['width']))
    return out

def plan_base(v,b,r,under=False,furniture=False):
    """Walls cut at door openings, door leaves and swings, room labels, grid."""
    for i,x in enumerate(b.grid_x):
        v.line('A-GRID',(x,-1.0),(x,b.depth+.6),w=.13,dash=True,under=under);v.circle('A-GRID',(x,-1.25),.25,w=.18,under=under);v.text('A-GRID',(x,-1.25),str(i+1),h=2.2,under=under)
    for j,y in enumerate(b.grid_y):
        v.line('A-GRID',(-1.0,y),(b.width+.6,y),w=.13,dash=True,under=under);v.circle('A-GRID',(-1.25,y),.25,w=.18,under=under);v.text('A-GRID',(-1.25,y),chr(65+j),h=2.2,under=under)
    ds=doors(b,r)
    cuts=unary_union([box(min(h[0],h[0]+a[0]*w),min(h[1],h[1]+a[1]*w),max(h[0],h[0]+a[0]*w),max(h[1],h[1]+a[1]*w)).buffer(.01) for _,h,a,_,w in ds]) if ds else None
    walls=unary_union([LineString([x['a'],x['b']]) for x in wall_geometry(b)])
    if cuts is not None:walls=walls.difference(cuts)
    for seg in getattr(walls,'geoms',[walls]):
        if not seg.is_empty:v.line('A-WALL',seg.coords[0],seg.coords[-1],w=.6,under=under)
    for _,h,a,s,w in ds:
        tip=(h[0]+s[0]*w,h[1]+s[1]*w);v.line('A-DOOR',h,tip,w=.2,under=under)
        a0=math.atan2(s[1],s[0]);delta=(math.atan2(a[1],a[0])-a0+math.pi)%(2*math.pi)-math.pi  # ±90°: open leaf back to the wall
        v.poly('A-DOOR',arc(h,w,a0,a0+delta),w=.13,under=under)
    for room in b.rooms:
        v.text('A-ANNO',(room.x+room.w/2,room.y+room.h/2-.15),room.name.upper(),h=2.4,bold=True,under=under)
        v.text('A-ANNO',(room.x+room.w/2,room.y+room.h/2+.35),f'{room.w*room.h:.1f} m²',h=2.0,under=under)
    if furniture:
        rooms={x.id:x for x in b.rooms}
        for f in b.furniture:
            room=rooms[f.room_id];v.rect('A-FURN',room.x+f.dx,room.y+f.dy,f.w,f.h,w=.13,under=under)

def dimensions(v,b,layer='A-DIMS'):
    y=b.depth+1.2
    for x0,x1 in zip(b.grid_x,b.grid_x[1:]):
        v.line(layer,(x0,y),(x1,y),w=.13);v.text(layer,((x0+x1)/2,y-.2),f'{x1-x0:.2f}',h=2.0)
    for x in b.grid_x:v.line(layer,(x-.12,y+.12),(x+.12,y-.12),w=.25)
    v.line(layer,(0,y+.6),(b.width,y+.6),w=.13);v.text(layer,(b.width/2,y+.4),f'{b.width:.2f} m',h=2.2)
    x=b.width+1.0
    for y0,y1 in zip(b.grid_y,b.grid_y[1:]):
        v.line(layer,(x,y0),(x,y1),w=.13);v.text(layer,(x+.45,(y0+y1)/2),f'{y1-y0:.2f}',h=2.0)
    for g in b.grid_y:v.line(layer,(x-.12,g+.12),(x+.12,g-.12),w=.25)

def plan_bounds(b):return (-1.8,-1.8,b.width+2.0,b.depth+2.2)

# ---------------------------------------------------------------- sheets
def sheet_set(b:Building,r,req:PermitRequest):
    sheets=[];f=r.get('fire',{});s=r.get('solar',{})
    title=req.project_title or b.name
    def sheet(code,discipline,name,views,panels):sheets.append({'number':code,'discipline':discipline,'title':name,'views':views,'panels':panels})
    summary=r['summary']
    if 'A' in req.disciplines:
        bd=[(p.x,p.y) for p in b.site.boundary];xs=[p[0] for p in bd];ys=[p[1] for p in bd]
        site=View('SITE DEVELOPMENT PLAN',(min(xs)-2,min(ys)-2,max(xs)+2,max(ys)+2.5))
        site.poly('C-SITE',bd,closed=True,w=.35,dash=True);site.text('C-SITE',(min(xs)+.2,min(ys)-.5),'PROPERTY LINE',h=2,align='left')
        from shapely.geometry import Polygon
        inner=Polygon(bd).buffer(-b.site.setback)
        if not inner.is_empty:site.poly('C-SITE',list(inner.exterior.coords),closed=True,w=.13,dash=True);site.text('C-SITE',(inner.bounds[0]+.2,inner.bounds[1]+.35),f'SETBACK {b.site.setback:g} m (user criterion)',h=1.8,align='left')
        site.rect('A-WALL',0,0,b.width,b.depth,w=.6,fill=.88);site.text('A-ANNO',(b.width/2,b.depth/2),f'PROPOSED {b.name.upper()}',h=2.6,bold=True);site.text('A-ANNO',(b.width/2,b.depth/2+.6),f'{b.width:g} × {b.depth:g} m · {b.width*b.depth:.0f} m² · 1 storey',h=2)
        points={}
        for label,p in [('ACCESS',b.site.access),('WATER',b.site.water),('OUTFALL',b.site.drain),('PANEL',b.site.panel)]:points.setdefault((round(p.x,3),round(p.y,3)),[]).append(label)
        for (px,py),labels in points.items():  # coincident utility points share one marker
            site.circle('C-SITE',(px,py),.15,w=.25,fill=0);site.text('C-SITE',(px+.3,py-.25),' / '.join(labels),h=1.8,align='left')
        nx,ny=max(xs)+1.0,min(ys)-.8;ang=math.radians(b.site.north)
        tip=(nx+math.sin(ang)*1.0,ny-math.cos(ang)*1.0);site.line('C-SITE',(nx,ny),tip,w=.35);site.poly('C-SITE',[tip,(nx+math.sin(ang-.35)*.6,ny-math.cos(ang-.35)*.6),(nx+math.sin(ang+.35)*.6,ny-math.cos(ang+.35)*.6)],closed=True,w=.2,fill=0);site.circle('C-SITE',(nx,ny),.5,w=.18);site.text('C-SITE',(tip[0],tip[1]-.35),'N',h=2.6,bold=True)
        plan=View('GROUND FLOOR PLAN',plan_bounds(b));plan_base(plan,b,r,furniture=True);dimensions(plan,b)
        notes=['All dimensions in metres unless noted. Gridlines per structural grid.',f'Gross floor area {b.width*b.depth:.1f} m²; building height {b.height:g} m; storeys 1.',f'Site setback {b.site.setback:g} m is a user criterion ({b.site.setback_source}).',f"Design review at export: {summary.get('pass',0)} pass, {summary.get('fail',0)} fail, {summary.get('missing_input',0)} missing input, {summary.get('unsupported',0)} unsupported checks.",'Vicinity / location map to be attached by the architect (not generated).','Elevations, sections and details are not generated and are required for a complete permit set.']
        sheet('A-1','A','SITE DEVELOPMENT PLAN, GENERAL NOTES & SHEET INDEX',[site],[('notes','GENERAL NOTES',notes),('index','SHEET INDEX',None)])
        rooms=[[x.name,f'{x.w:.2f} × {x.h:.2f}',f'{x.w*x.h:.2f}'] for x in b.rooms]+[['TOTAL','',f'{sum(x.w*x.h for x in b.rooms):.2f}']]
        sheet('A-2','A','GROUND FLOOR PLAN & ROOM SCHEDULE',[plan],[('table','ROOM SCHEDULE',(['ROOM','SIZE (m)','AREA (m²)'],rooms,[.5,.28,.22]))])
    if 'S' in req.disciplines:
        e=b.engineering;st=r['structure']
        fnd=View('FOUNDATION PLAN',plan_bounds(b));plan_base(fnd,b,r,under=True)
        for x in st['foundations']:
            c=next(c for c in b.columns if c.id==x['column_id']);w=e.footing_width
            fnd.rect('S-FNDN',c.x-w/2,c.y-w/2,w,w,w=.35,dash=True);fnd.rect('S-COLS',c.x-.1,c.y-.1,.2,.2,w=.35,fill=0);fnd.text('S-ANNO',(c.x+w/2+.05,c.y-w/2-.1),'F1',h=1.8,align='left')
        roof=View('ROOF FRAMING PLAN',plan_bounds(b));plan_base(roof,b,r,under=True)
        for c in b.columns:
            if c.active:roof.rect('S-COLS',c.x-.1,c.y-.1,.2,.2,w=.35,fill=0,under=True)
        for i,beam in enumerate(st['beams']):
            roof.line('S-BEAM',(beam['x1'],beam['y']),(beam['x2'],beam['y']),w=.7);roof.text('S-ANNO',((beam['x1']+beam['x2'])/2,beam['y']-.25),f"B{i+1:02d} {beam['section']}",h=1.9)
        if s.get('enabled') and s['layout']['y_extent']:
            y0,y1=s['layout']['y_extent'];sb=b.solar.edge_setback;roof.rect('E-PV',sb,y0,b.width-2*sb,y1-y0,w=.25,dash=True);roof.text('E-PV',(sb+.15,y0+.3),f"PV ARRAY ZONE +{s['layout']['dead_load_kPa']:.3f} kPa",h=1.9,align='left')
        dimensions(fnd,b,'S-ANNO')
        beams=[[f'B{i+1:02d}',f"{x['x1']:g}–{x['x2']:g} / {x['y']:g}",x['section'],f"{x['length']:.2f}",f"{x['service_q_kNm']:.2f}",f"{max(x['yield_utilization'],x['deflection_utilization'])*100:.0f}%",x['status'].upper()] for i,x in enumerate(st['beams'])]
        pads=[[x['column_id'],f'{e.footing_width:g} × {e.footing_width:g} × {e.footing_thickness:g}',f"{x['pressure_kPa']:.1f}",f"{x['allowable_kPa']}",x['status'].upper()] for x in st['foundations']]
        notes=[f'Dead load {e.dead.value} kPa, live load {e.live.value} kPa ({e.dead.source}).',f'Combination {e.dead_factor}D + {e.live_factor}L — {e.combination_source}.',f'Steel E = {e.elastic_modulus:g} MPa, fy = {e.yield_strength:g} MPa; deflection limit L/{e.deflection_ratio:g}.',f"Allowable soil bearing {e.soil.value} kPa ({e.soil.basis}).",st.get('scope',''),'Wind, seismic, frame stability, connections and column buckling are NOT designed. Structural analysis and design by a licensed civil/structural engineer is required.']
        if s.get('enabled'):notes.insert(1,f"PV superimposed dead load {s['layout']['dead_load_kPa']:.3f} kPa over the array zone; wind uplift not evaluated.")
        sheet('S-1','S','FOUNDATION PLAN, ROOF FRAMING PLAN & SCHEDULES',[fnd,roof],[('table','BEAM SCHEDULE',(['MARK','GRID','SECTION','SPAN m','w kN/m','UTIL','SCREEN'],beams,[.1,.2,.16,.12,.14,.12,.16])),('table','FOOTING SCHEDULE',(['COLUMN','PAD B×B×t (m)','q kPa','ALLOW','SCREEN'],pads,[.2,.3,.15,.15,.2])),('notes','STRUCTURAL NOTES',notes)])
    if 'E' in req.disciplines:
        el=View('ELECTRICAL LAYOUT',plan_bounds(b));plan_base(el,b,r,under=True);rooms={x.id:x for x in b.rooms}
        for route in [x for x in r['routing']['routes'] if x['kind']=='conduit']:
            if len(route['points'])>1:el.poly('E-POWR',route['points'],w=.3,dash=True)
        for q in b.equipment:
            room=rooms[q.room_id];p=(room.x+q.dx,room.y+q.dy);el.circle('E-POWR',p,.18,w=.3);el.text('E-POWR',p,q.circuit_id[-1],h=1.6,bold=True);el.text('E-ANNO',(p[0],p[1]+.42),f'{q.name} {q.watts or "?"} W',h=1.6)
        pn=b.site.panel;el.rect('E-POWR',pn.x-.3,pn.y-.2,.6,.4,w=.4,fill=.4);el.text('E-ANNO',(pn.x+.45,pn.y-.3),'PANEL BOARD',h=1.8,align='left')
        if s.get('enabled'):
            for m in s['layout']['modules']:el.rect('E-PV',m['x']+.02,m['y']+.02,m['w']-.04,m['h']-.04,w=.1,dash=True)
            el.text('E-PV',(b.width/2,-.45),f"ROOF-MOUNTED PV ARRAY {s['layout']['kwp']:.2f} kWp ({s['layout']['count']} MODULES, AT ROOF LEVEL)",h=1.9)
        circuits=[[c['id'],c['name'],f"{c['connected_W']}",f"{c['voltage']:g}",f"{c['current_A']:.2f}" if c['current_A'] is not None else '—'] for c in r['routing']['circuits']]
        panels=[('table','SCHEDULE OF LOADS',(['CKT','DESCRIPTION','LOAD W','V','I (A)'],circuits,[.12,.4,.18,.12,.18]))]
        if s.get('enabled'):panels.append(('oneline','PV SINGLE-LINE DIAGRAM',(b,s)))
        notes=['Load arithmetic only: conductor sizing, protection coordination and voltage drop are NOT designed.','Electrical plans require the signature and seal of a Professional Electrical Engineer.']
        if s.get('enabled'):notes+=['PV system per PEC 2017 Art. 6.90 and RA 9514 RIRR 10.2.19.9: DC/AC disconnects and protection, rapid shutdown, labeling; PEE-sealed Electrical Installation Clearance.','Transformer and hosting-capacity values must come from the distribution utility.']
        panels.append(('notes','ELECTRICAL NOTES',notes))
        sheet('E-1','E','ELECTRICAL LAYOUT, SCHEDULE OF LOADS'+(' & PV SINGLE-LINE' if s.get('enabled') else ''),[el],panels)
    if 'P' in req.disciplines:
        pl=View('PLUMBING & SANITARY LAYOUT',plan_bounds(b));plan_base(pl,b,r,under=True);rooms={x.id:x for x in b.rooms}
        for route in r['routing']['routes']:
            if route['kind']=='conduit' or len(route['points'])<2:continue
            water=route['kind']=='water';pl.poly('P-WATR' if water else 'P-SANR',route['points'],w=.3 if water else .5,dash=water)
            if not water and route['slope'] is not None:
                a,c=route['points'][-2],route['points'][-1];pl.text('P-ANNO',((a[0]+c[0])/2,(a[1]+c[1])/2-.2),f"{route['slope']*100:.1f}% →",h=1.6)
        for fx in b.fixtures:
            room=rooms[fx.room_id];p=(room.x+fx.dx,room.y+fx.dy);pl.rect('P-FIXT',p[0]-.2,p[1]-.2,.4,.4,w=.3);pl.text('P-ANNO',(p[0],p[1]+.45),fx.kind.upper(),h=1.6)
        for label,p in [('WATER SOURCE',b.site.water),('OUTFALL',b.site.drain)]:pl.circle('P-ANNO',(p.x,p.y),.15,w=.3,fill=0);pl.text('P-ANNO',(p.x+.25,p.y-.25),label,h=1.7,align='left')
        fixtures=[[x.id,x.name,x.kind,rooms[x.room_id].name,f'{x.elevation:.2f}'] for x in b.fixtures]
        sheet('P-1','P','PLUMBING & SANITARY LAYOUT, FIXTURE SCHEDULE',[pl],[('table','FIXTURE SCHEDULE',(['MARK','FIXTURE','TYPE','ROOM','INV. m'],fixtures,[.14,.3,.14,.28,.14])),('notes','LEGEND & NOTES',['Dashed line: cold-water supply. Solid line: gravity sanitary drain with slope and flow direction.',f'Minimum drain slope used {b.engineering.drain_slope*100:.1f}% (project criterion).','Pipe sizing, venting, traps, cleanouts and hydraulic adequacy are NOT designed.','Sanitary/plumbing plans require the signature and seal of a Sanitary Engineer or Master Plumber.'])])
    if 'FP' in req.disciplines and f.get('enabled'):
        fp=View('FIRE PROTECTION & EGRESS PLAN',plan_bounds(b));plan_base(fp,b,r,under=True);rooms={x.id:x for x in b.rooms}
        for x in f['exits']:
            fp.line('FP-EGRS',x['a'],x['b'],w=1.0);mx,my=(x['a'][0]+x['b'][0])/2,(x['a'][1]+x['b'][1])/2
            fp.text('FP-EGRS',(mx+(-.9 if x['a'][0]==0 else .9 if x['a'][0]==x['b'][0] else 0),my+(0 if x['a'][0]==x['b'][0] else (-.6 if my==0 else .6))),'EXIT',h=2.2,bold=True)
        if len(f['travel']['critical_path'])>1:
            fp.poly('FP-EGRS',f['travel']['critical_path'],w=.35,dash=True);p=f['travel']['critical_path'][0];fp.circle('FP-EGRS',p,.12,fill=0)
            fp.text('FP-ANNO',(p[0],p[1]-.35),f"MAX TRAVEL {f['travel']['max_m']:.1f} m",h=1.8)
        for e in b.fire.extinguishers:
            room=rooms[e.room_id];p=(room.x+e.dx,room.y+e.dy);fp.poly('FP-EQPM',[(p[0],p[1]-.18),(p[0]+.16,p[1]+.1),(p[0]-.16,p[1]+.1)],closed=True,w=.3,fill=0)
            fp.text('FP-ANNO',(p[0]+.35,p[1]-.05),f'FE {e.rating}',h=1.7,align='left')
        load=[['Occupancy',f['occupancy'].replace('_',' ').title()+(f" (Class {f['mercantile_class']})" if f['mercantile_class'] else '')],['Gross floor area',f"{f['gross_area_m2']:.1f} m²"],['Occupant load',str(f['occupant_load'])],['Exits provided',str(len(f['exits']))],['Sprinklers','Yes' if b.fire.sprinklered else 'No'],['Fire alarm',b.fire.alarm.title()],['Emergency lighting','Yes' if b.fire.emergency_lighting else 'No'],['Exit signs','Yes' if b.fire.exit_signs else 'No']]
        checks=[[c['rule'].replace('FIRE-',''),c['status'].replace('_',' ').upper(),c['clause'].replace('RIRR ','')] for c in f['checks'] if c['rule']!='FIRE-SCOPE']
        sheet('FP-1','FP','FIRE PROTECTION & EGRESS PLAN',[fp],[('table','OCCUPANCY & PROVISIONS',(['ITEM','VALUE'],load,[.5,.5])),('table','RA 9514 SCREEN',(['CHECK','RESULT','RIRR CLAUSE'],checks,[.24,.24,.52])),('notes','NOTES',['Travel measured along a 0.25 m grid through modeled doors; furniture ignored.','Dashed line: longest travel path to the nearest exit.',f['source'],'Fire safety plans are subject to BFP evaluation (FSEC) prior to permit issuance.'])])
    return sheets

# ---------------------------------------------------------------- PDF
def latin(s):
    for a,b in {'≤':'<=','≥':'>=','→':'->','—':'-','–':'-','√':'sqrt','Σ':'sum','·':'·','≈':'~','′':"'",'″':'"','“':'"','”':'"','’':"'"}.items():s=s.replace(a,b)
    return s.encode('latin-1','replace').decode('latin-1')

def render_pdf(b:Building,r,req:PermitRequest,revision_id:str)->bytes:
    from reportlab.pdfgen import canvas as rl
    from reportlab.lib.units import mm
    from reportlab.lib.utils import simpleSplit
    W,H=SHEET_SIZES[req.sheet];k=1 if req.sheet=='20x30' else .72;TB=120*k
    sheets=sheet_set(b,r,req);buf=io.BytesIO();c=rl.Canvas(buf,pagesize=(W*mm,H*mm));c.setTitle(latin(f"{req.project_title or b.name} - permit drawing set"))
    def font(h,bold=False):c.setFont('Helvetica-Bold' if bold else 'Helvetica',h*k/0.3528)
    def txt(x,y,s,h,align='left',bold=False):
        font(h,bold);s=latin(s)
        (c.drawCentredString if align=='center' else c.drawRightString if align=='right' else c.drawString)(x*mm,y*mm,s)
    def draw_view(v,region):
        x0,y0,x1,y1=region;bx0,by0,bx1,by1=v.bounds;head=7*k
        v.scale=next((s for s in SCALES if (bx1-bx0)*1000/s<=x1-x0 and (by1-by0)*1000/s<=y1-y0-head),SCALES[-1])
        f=1000/v.scale;ox=x0+((x1-x0)-(bx1-bx0)*f)/2;top=y1-head-max(0,((y1-y0-head-8*k)-(by1-by0)*f)/2)  # centre vertically
        P=lambda p:((ox+(p[0]-bx0)*f)*mm,(top-(p[1]-by0)*f)*mm)
        for items,grey in [(v.underlay,True),(v.items,False)]:
            for it in items:
                kind=it[0];c.setStrokeGray(.62 if grey else 0);c.setFillGray(.62 if grey else 0)
                if kind=='text':
                    _,_,p,s,h,align,bold=it;X,Y=P(p);font(h,bold);s=latin(s);Y-=h*k*mm*.35
                    (c.drawCentredString if align=='center' else c.drawRightString if align=='right' else c.drawString)(X,Y,s);continue
                if kind=='line':_,_,a,bb,w,dash=it
                elif kind=='poly':_,_,pts,closed,w,dash,fill=it
                else:_,_,cc,rad,w,fill,dash=it
                c.setLineWidth(w*mm*(.7 if grey else 1));c.setDash([2.2*mm,1.2*mm] if dash else [])
                if kind=='line':c.line(*P(a),*P(bb))
                elif kind=='poly':
                    path=c.beginPath();path.moveTo(*P(pts[0]))
                    for p in pts[1:]:path.lineTo(*P(p))
                    if closed:path.close()
                    if fill is not None and not grey:c.setFillGray(fill)
                    c.drawPath(path,stroke=1,fill=1 if fill is not None and closed else 0)
                else:
                    if fill is not None and not grey:c.setFillGray(fill)
                    c.circle(*P(cc),rad*f*mm,stroke=1,fill=1 if fill is not None else 0)
        c.setDash([]);c.setStrokeGray(0);c.setFillGray(0)
        txt(x0,y1-4*k,v.title,3.2,bold=True);txt(x0+(len(v.title)*2.05+4)*k,y1-4*k,f'SCALE 1:{v.scale}',2.2)
        # scale bar: 0–1–2 m
        sb=(ox,max(y0+2*k,top-(by1-by0)*f-6*k));c.setLineWidth(.3*mm);[c.rect((sb[0]+i*f)*mm,sb[1]*mm,f*mm,1.2*k*mm,stroke=1,fill=1 if i%2==0 else 0) for i in range(2)];txt(sb[0],sb[1]+2*k,'0',1.8);txt(sb[0]+2*f,sb[1]+2*k,'2 m',1.8,'center')
    def table(x,ytop,width,title,headers,rows,fr):
        rh=4.2*k;txt(x,ytop-3.5*k,title,2.6,bold=True);y=ytop-6*k
        cols=[x+sum(fr[:i])*width for i in range(len(fr))];c.setLineWidth(.25*mm);c.line(x*mm,y*mm,(x+width)*mm,y*mm)
        for cx,hd in zip(cols,headers):txt(cx+1,y-3*k,hd,1.8,bold=True)
        y-=rh;c.line(x*mm,y*mm,(x+width)*mm,y*mm)
        for row in rows:
            for cx,cell,fw in zip(cols,row,fr):
                s=latin(str(cell));font(1.8)
                while s and c.stringWidth(s)>(fw*width-2)*mm:s=s[:-4]+'...' if len(s)>4 else ''
                txt(cx+1,y-3*k,s,1.8)
            y-=rh;c.setLineWidth(.1*mm);c.line(x*mm,y*mm,(x+width)*mm,y*mm)
        return y-3*k
    def notes(x,ytop,width,title,lines):
        txt(x,ytop-3.5*k,title,2.6,bold=True);y=ytop-7*k;font(1.9)
        for i,line in enumerate(lines):
            for j,part in enumerate(simpleSplit(latin(f'{i+1}. {line}'),'Helvetica',1.9*k/0.3528,(width-2)*mm)):
                txt(x+(0 if j==0 else 3*k),y,part,1.9);y-=3*k
            y-=1*k
        return y-2*k
    def oneline(x,ytop,width,title,data):
        bb,s=data;e=s['electrical'];sol=bb.solar;txt(x,ytop-3.5*k,title,2.6,bold=True)
        boxes=[f"PV ARRAY|{s['layout']['kwp']:.2f} kWp DC",f"INVERTER|{e['inverter_kw'] or '?'} kW AC {sol.phases}-ph",f"PV BREAKER|{e['pv_breaker_A'] or '?'} A",f"PANEL BOARD|MAIN {sol.service_main_a or '?'} A / BUS {sol.busbar_a or '?'} A",'BI-DIRECTIONAL|kWh METER',f"DU TRANSFORMER|{sol.transformer_kva or '___'} kVA"]
        bw,bh,gap=(width-4)/3,10*k,6*k;y=ytop-8*k
        for i,label in enumerate(boxes):
            # Second row snakes back so the flow reads breaker -> panel -> meter -> transformer.
            row=i//3;col=i%3 if row==0 else 2-i%3;bx=x+col*(bw+2);by=y-row*(bh+gap)-bh
            c.setLineWidth(.35*mm);c.rect(bx*mm,by*mm,(bw-2)*mm,bh*mm);a,bt=label.split('|');txt(bx+(bw-2)/2,by+bh-4*k,a,1.9,'center',True);txt(bx+(bw-2)/2,by+2.5*k,bt,1.8,'center')
            if i%3<2:c.line(((bx+bw-2) if row==0 else (bx-2))*mm,(by+bh/2)*mm,((bx+bw) if row==0 else bx)*mm,(by+bh/2)*mm)
        c.line((x+2*(bw+2)+(bw-2)/2)*mm,(y-bh)*mm,(x+2*(bw+2)+(bw-2)/2)*mm,(y-bh-gap)*mm)
        return y-2*bh-gap-5*k
    total=len(sheets)
    for n,sh in enumerate(sheets,1):
        c.setStrokeGray(0);c.setFillGray(0);c.setLineWidth(.7*mm);c.rect(25*mm,10*mm,(W-35)*mm,(H-20)*mm)
        tbx=W-10-TB;c.line(tbx*mm,10*mm,tbx*mm,(H-10)*mm)
        area=(30,15,tbx-5,H-15)
        side=.36 if len(sh['views'])==1 else .38;split=area[0]+(area[2]-area[0])*(1-side)
        vregion=(area[0],area[1],split-4,area[3])
        if len(sh['views'])==1:draw_view(sh['views'][0],vregion)
        else:
            mid=(vregion[1]+vregion[3])/2;draw_view(sh['views'][0],(vregion[0],mid+2,vregion[2],vregion[3]));draw_view(sh['views'][1],(vregion[0],vregion[1],vregion[2],mid-2))
        y=area[3];px=split;pw=area[2]-split
        for kind,title,data in sh['panels']:
            if kind=='table':y=table(px,y,pw,title,*data)
            elif kind=='notes':y=notes(px,y,pw,title,data)
            elif kind=='oneline':y=oneline(px,y,pw,title,data)
            elif kind=='index':y=table(px,y,pw,title,['SHEET','CONTENTS'],[[x['number'],x['title']] for x in sheets],[.16,.84])
        # title block
        x=tbx+3;w=TB-6;yy=H-14
        txt(x,yy-4*k,'PROJECT',1.7);yy-=4*k
        for part in simpleSplit(latin(req.project_title or b.name),'Helvetica-Bold',3.6*k/0.3528,w*mm)[:2]:yy-=5*k;txt(x,yy,part,3.6,bold=True)
        for label,val in [('LOCATION',req.location or '________________'),('OWNER / APPLICANT',req.owner or '________________')]:
            yy-=6*k;txt(x,yy,label,1.7);yy-=4*k;txt(x,yy,val,2.4)
        yy-=4*k;c.setLineWidth(.35*mm);c.line(tbx*mm,yy*mm,(W-10)*mm,yy*mm)
        yy-=5*k;txt(x,yy,'SHEET CONTENTS',1.7)
        for part in simpleSplit(latin(sh['title']),'Helvetica-Bold',2.6*k/0.3528,w*mm)[:3]:yy-=4*k;txt(x,yy,part,2.6,bold=True)
        yy-=5*k;c.line(tbx*mm,yy*mm,(W-10)*mm,yy*mm)
        pro=req.professionals.get(sh['discipline'],Professional())
        yy-=5*k;txt(x,yy,'PREPARED, SIGNED AND SEALED BY',1.7);yy-=4*k;txt(x,yy,PROFESSIONS[sh['discipline']].upper(),2.2,bold=True)
        seal=34*k;yy-=seal+2*k;c.setLineWidth(.25*mm);c.setDash([1.5*mm,1*mm]);c.rect(x*mm,yy*mm,seal*mm,seal*mm);c.setDash([])
        txt(x+seal/2,yy+seal/2,'SEAL',2,'center');c.line((x+seal+4)*mm,(yy+8*k)*mm,(x+w)*mm,(yy+8*k)*mm);txt(x+seal+4,yy+4*k,'SIGNATURE OVER PRINTED NAME',1.6)
        txt(x+seal+4,yy+11*k,pro.name or '',2.4,bold=True)
        rows=[('PRC No.',pro.prc_no),('Validity',pro.prc_validity),('IAPOA / APO No.',pro.apo_no),('PTR No.',pro.ptr_no),('Date issued',pro.ptr_date),('Place issued',pro.ptr_place),('TIN',pro.tin)]
        for label,val in rows:yy-=4.2*k;txt(x,yy,label,1.8);txt(x+30*k,yy,val or '________________',1.9)
        yy-=4*k;c.line(tbx*mm,yy*mm,(W-10)*mm,yy*mm)
        yy-=6*k;c.line(x*mm,yy*mm,(x+w)*mm,yy*mm);txt(x,yy-3*k,'LOT OWNER / APPLICANT - SIGNATURE OVER PRINTED NAME',1.6)
        # status stamp
        yy-=9*k;c.setLineWidth(.5*mm);c.rect(x*mm,(yy-17*k)*mm,w*mm,17*k*mm);txt(x+w/2,yy-5*k,'PRELIMINARY - NOT FOR CONSTRUCTION',2.5,'center',True)
        for i,part in enumerate(simpleSplit(latin(f'Generated by BuildGraph from revision {revision_id}. Requires review, completion, signing and sealing by the responsible licensed professional before submission.'),'Helvetica',1.6*k/0.3528,(w-4)*mm)[:3]):txt(x+2,yy-9*k-i*2.6*k,part,1.6)
        # sheet number box
        c.setLineWidth(.35*mm);c.line(tbx*mm,(10+30*k)*mm,(W-10)*mm,(10+30*k)*mm)
        txt(x,10+25*k,f'DATE  {req.date}',1.9);txt(x,10+21*k,f'SCALE  AS SHOWN',1.9);txt(x,10+17*k,f'SIZE  {req.sheet}',1.9)
        txt(W-13,10+12*k,sh['number'],9,'right',True);txt(W-13,10+4*k,f'SHEET {n} OF {total}',1.9,'right')
        c.showPage()
    c.save();return buf.getvalue()

# ---------------------------------------------------------------- DXF
LAYERS={'A-WALL':(7,.5),'A-DOOR':(7,.18),'A-ANNO':(7,.18),'A-GRID':(8,.13),'A-DIMS':(8,.13),'A-FURN':(8,.13),'C-SITE':(3,.25),
        'S-COLS':(1,.35),'S-FNDN':(1,.35),'S-BEAM':(1,.5),'S-ANNO':(1,.18),'E-POWR':(5,.3),'E-PV':(30,.25),'E-ANNO':(5,.18),
        'P-WATR':(4,.3),'P-SANR':(34,.5),'P-FIXT':(4,.3),'P-ANNO':(4,.18),'FP-EGRS':(10,.5),'FP-EQPM':(10,.35),'FP-ANNO':(10,.18)}
def render_dxf(b:Building,r,req:PermitRequest,revision_id:str)->bytes:
    import ezdxf
    from ezdxf.enums import TextEntityAlignment
    doc=ezdxf.new('R2018',setup=True);doc.units=ezdxf.units.M;doc.header['$INSUNITS']=6;msp=doc.modelspace()
    for name,(color,lw) in LAYERS.items():doc.layers.add(name,color=color,lineweight=int(lw*100))
    seen=set();sheets=sheet_set(b,r,req)
    P=lambda p:(p[0],-p[1])  # app plan is y-down; flip so CAD shows the same orientation
    align={'left':TextEntityAlignment.MIDDLE_LEFT,'center':TextEntityAlignment.MIDDLE_CENTER,'right':TextEntityAlignment.MIDDLE_RIGHT}
    for sh in sheets:
        for v in sh['views']:
            # Site plan sits beside the building plans so it does not overlap them.
            off=(0,0) if v.title!='SITE DEVELOPMENT PLAN' else (-(v.bounds[2]-v.bounds[0])-10,0)
            Q=lambda p:P((p[0]+off[0],p[1]+off[1]))
            for it in v.items:
                key=(it[0],it[1],repr(it[2:]),off)
                if key in seen:continue
                seen.add(key);kind,layer=it[0],it[1];attrs={'layer':layer}
                if kind in ['line','poly','circle'] and (it[5] if kind=='line' else it[5] if kind=='poly' else it[6]):attrs['linetype']='DASHED'
                if kind=='line':msp.add_line(Q(it[2]),Q(it[3]),dxfattribs=attrs)
                elif kind=='poly':msp.add_lwpolyline([Q(p) for p in it[2]],close=it[3],dxfattribs=attrs)
                elif kind=='circle':msp.add_circle(Q(it[2]),it[3],dxfattribs=attrs)
                else:
                    _,_,p,s,h,al,_=it;msp.add_text(s,height=h*100/1000*.9,dxfattribs=attrs).set_placement(Q(p),align=align[al])
    msp.add_text(f'BuildGraph {revision_id} - PRELIMINARY, NOT FOR CONSTRUCTION. Units: metres. Requires signing and sealing by licensed professionals.',height=.25,dxfattribs={'layer':'A-ANNO'}).set_placement((0,2.8),align=TextEntityAlignment.MIDDLE_LEFT)
    out=io.StringIO();doc.write(out);return out.getvalue().encode()
