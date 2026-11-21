"""Review-only drawing and data packages from one hash-bound approved design."""
import io,json,csv,zipfile,html
from collections import Counter
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,Flowable,KeepTogether
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape,A3
from shapely.geometry import Polygon
from .planning_workflow import view
from .store import Conflict

GREEN=colors.HexColor('#244c41');INK=colors.HexColor('#20322d')

class PlanDrawing(Flowable):
    def __init__(self,plan,details,site,strategy,building=False,services=None):
        Flowable.__init__(self);self.width=1090;self.height=550;self.plan=plan;self.details=details;self.site=site;self.strategy=strategy;self.building=building;self.services=services
    def draw(self):
        c=self.canv;shell=Polygon(self.plan['footprint'])
        from shapely.ops import unary_union
        p=shell if self.building else Polygon(self.site['boundary']) if self.site else unary_union([shell]+[Polygon(z['polygon']) for z in self.plan['zones']]);x0,y0,x1,y1=p.bounds;s=min((self.width-40)/(x1-x0),(self.height-40)/(y1-y0));ox=(self.width-(x1-x0)*s)/2;oy=20
        def pt(v):return ox+(v[0]-x0)*s,oy+(v[1]-y0)*s
        def poly(points,fill=None,stroke=INK,width=.5,closed=True):
            path=c.beginPath();path.moveTo(*pt(points[0]));[path.lineTo(*pt(v)) for v in points[1:]]
            if closed:path.close()
            c.setStrokeColor(stroke);c.setLineWidth(width);c.setFillColor(fill or colors.white);c.drawPath(path,stroke=1,fill=int(fill is not None))
        if self.site and not self.building:
            poly(self.site['boundary'],colors.HexColor('#f1f3e9'),GREEN,1)
            if self.site['road_edge']:poly([self.site['boundary'][i] for i in self.site['road_edge']],stroke=colors.HexColor('#bd7446'),width=3,closed=False)
        for index,z in enumerate(self.plan['zones']):
            if self.building and z['location']!='inside':continue
            poly(z['polygon'],colors.HexColor('#dce9df') if z['location']=='inside' else colors.HexColor('#ecece1'))
            p=Polygon(z['polygon']).representative_point();c.setFillColor(INK);c.setFont('Helvetica-Bold',8);c.drawCentredString(*pt((p.x,p.y)),str(index+1))
        for r in self.details['rooms']:poly(r['polygon'],colors.HexColor('#f8f4e7'))
        for item in self.details['items']:
            if self.building and next(z for z in self.plan['zones'] if z['id']==item['zone_id'])['location']!='inside':continue
            poly(item['polygon'],colors.HexColor('#b3c9bf') if item['kind'] not in ('parking','accessible_parking') else colors.white,width=.3)
            if item['kind'] in ('parking','accessible_parking','cashier'):
                p=Polygon(item['polygon']).centroid;c.setFillColor(INK);c.setFont('Helvetica',max(3,min(6,s*.55)));c.drawCentredString(*pt((p.x,p.y)),item['name'].split()[-1])
        for r in self.strategy['routes']+self.details['routes']:
            from shapely.geometry import LineString
            line=LineString(r['points']);line=line.intersection(shell) if self.building else line
            for segment in ([line] if line.geom_type=='LineString' else getattr(line,'geoms',[])):
                if segment.geom_type=='LineString' and segment.length:poly(list(segment.coords),stroke=colors.HexColor('#367a95') if r['kind'] in ('pedestrian','interior','egress') else colors.HexColor('#a96738'),width=1,closed=False)
        for o in self.plan['openings']:poly(o['segment'],stroke=colors.white,width=3,closed=False)
        if self.services:
            for kind,colour in [('pipes','#267b98'),('wires','#8252a2')]:
                for connection in self.services.get(kind,[]):poly(connection['points'],stroke=colors.HexColor(colour),width=.8,closed=False)
        c.setFillColor(INK);c.setFont('Helvetica',8);c.drawString(20,4,f'Local XY metres. Scale bar: 10 m');c.setLineWidth(2);c.line(210,7,210+10*s,7)
        if self.site and self.site['north_degrees'] is not None:c.drawRightString(self.width-20,4,f'North: {self.site["north_degrees"]:g} degrees from local +Y')
        else:c.drawRightString(self.width-20,4,'North unconfirmed')


def bundle(store,session):
    v=view(store,session)
    if not v['analysis_current']:raise Conflict('Run screens against the current accepted design and inputs before exporting.')
    return v


def render_pdf(v):
    a=v['accepted'];plan=a['layout']['plan'];details=a['details'];result=v['analysis'];styles=getSampleStyleSheet();out=io.BytesIO()
    doc=SimpleDocTemplate(out,pagesize=landscape(A3),leftMargin=40,rightMargin=40,topMargin=40,bottomMargin=40)
    story=[]
    def p(text,style='BodyText'):return Paragraph(html.escape(str(text)),styles[style])
    def title(text):story.extend([p(text,'Title'),Spacer(1,12)])
    def table(headers,rows,widths=None):
        t=Table([[p(x) for x in headers]]+[[p(x) for x in r] for r in rows],colWidths=widths,repeatRows=1,hAlign='LEFT');t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e1eae3')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#c9d2cb')),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]));story.append(t)
    title(a['programme']['name']+' / Site and access')
    story+=[p('PRELIMINARY REVIEW - NOT FOR CONSTRUCTION. '+a['approval']['meaning']),p(f'Design {result["design_hash"]}'),p(a['strategy']['rationale']),PlanDrawing(plan,details,v['site'],a['strategy']),PageBreak()]
    title('Detailed planning layout');story+=[p(plan['rationale']),PlanDrawing(plan,details,v['site'],a['strategy'],True),PageBreak()]
    title('Indicative services and circulation')
    story+=[p('Blue: direct fixture-to-drain connections. Violet: indicative zone-to-panel connections. Lines appear only where the required points were supplied. No sizing, protection, invert coordination or buildable routing is established.'),p(f'{len(result["pipes"])} drainage connections; {len(result.get("wires",[]))} electrical connections. Missing services inputs remain listed in the findings.'),PlanDrawing(plan,details,v['site'],a['strategy'],True,result),PageBreak()]
    title('Spaces, placed objects and decisions')
    table(['Ref','Space','Area m2','Purpose'],[[str(i+1),z['name'],f'{Polygon(z["polygon"]).area:,.2f}',z['purpose']] for i,z in enumerate(plan['zones'])],[40,220,100,730])
    story.append(Spacer(1,16));table(['Object type','Placed count'],[[k,str(n)] for k,n in sorted(Counter(i['kind'] for i in details['items']).items())],[400,160])
    story.append(Spacer(1,16));table(['Support room','Area m2','Requirement'],[[r['name'],f'{Polygon(r["polygon"]).area:.2f}',r['requirement_id'] or 'Unbound'] for r in details['rooms']],[400,150,300])
    story+=[Spacer(1,16),p('Unresolved at planning acceptance','Heading2')]+[p('- '+x) for x in a['approval']['unresolved']]+[PageBreak()]
    title('Screen findings and coverage')
    story+=[p('Pass applies only to the named screen and supplied criteria. Missing and unsupported items require professional resolution.'),p('Result '+result['result_hash']),Spacer(1,12)]
    table(['Discipline','Status','Screen','Evidence'],[[f['discipline'],f['status'],f['title'],f['evidence']] for f in result['findings']],[85,85,200,720])
    if v.get('agent_reviews'):
        story.append(PageBreak());title('Specialist advisory reviews')
        story.append(p('AI advice is separate from deterministic findings. Each review uses the design and input hashes above and cannot change the accepted plan.'))
        for role,review in v['agent_reviews'].items():
            story += [p(role.replace('_',' ').title(),'Heading2'),p(review['summary'])]
            for recommendation in review['recommendations']:
                story += [p(recommendation['title'],'Heading3'),p(recommendation['rationale']),p('Evidence: '+', '.join(recommendation['finding_ids']+recommendation['input_paths']))]
            for question in review['questions']:story.append(p('Question: '+question['question']+' / '+', '.join(question['finding_ids']+question['input_paths'])))
    story.append(PageBreak());title('Geometric takeoff and pricing')
    q=result['quantities'];story+=[p(f'Priced partial subtotal: PHP {q["partial_cost_php"]:,.2f}. '+('Modelled scope fully priced.' if q['total_cost_php'] is not None else 'Incomplete pricing; no project total is available.')),Spacer(1,12)]
    table(['Item','Quantity','Unit','Rate PHP','Cost PHP','Formula / source'],[[r['name'],'Missing' if r['quantity'] is None else f'{r["quantity"]:,.3f}',r['unit'],'Unpriced' if r['rate'] is None else str(r['rate']),'Unpriced' if r['cost_php'] is None else str(r['cost_php']),r['formula']+' / '+r['rate_basis']] for r in q['items']],[170,80,50,90,100,600])
    story.append(KeepTogether([Spacer(1,16),p('Excluded scope','Heading2'),p('; '.join(q['exclusions']))]))
    story+=[PageBreak()];title('Engineering inputs and provenance')
    rows=[]
    def flatten(value,prefix=''):
        if isinstance(value,dict):
            if 'value' in value and 'source' in value:rows.append([prefix,'Missing' if value['value'] is None else str(value['value']),value['source'],value['basis']])
            else:
                for k,x in value.items():flatten(x,(prefix+'.' if prefix else '')+k)
        elif isinstance(value,list):
            for i,x in enumerate(value):flatten(x,f'{prefix}[{i}]')
    flatten(a['inputs']);table(['Input','Value','Source','Basis'],rows,[260,100,100,630])
    def footer(c,doc):
        c.saveState();c.setFont('Helvetica',8);c.setFillColor(INK);c.drawString(40,22,'BuildGraph | Planning screens only. Licensed professional review required.');c.drawRightString(1150,22,f'{doc.page}');c.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer);return out.getvalue()


def render_dxf(v):
    import ezdxf
    d=ezdxf.new('R2010');d.units=6;m=d.modelspace();a=v['accepted'];plan=a['layout']['plan']
    for layer,color in [('SITE',3),('ZONES',8),('ROOMS',2),('OBJECTS',4),('OPENINGS',1),('ROUTES',5),('DRAIN',4),('ELECTRICAL',6),('LABELS',7)]:d.layers.new(layer,dxfattribs={'color':color})
    def poly(points,layer,close=True):m.add_lwpolyline(points,close=close,dxfattribs={'layer':layer})
    if v['site']:poly(v['site']['boundary'],'SITE')
    for z in plan['zones']:
        poly(z['polygon'],'ZONES');p=Polygon(z['polygon']).representative_point();m.add_text(z['name'],dxfattribs={'height':.5,'insert':(p.x,p.y),'layer':'LABELS'})
    for r in a['details']['rooms']:poly(r['polygon'],'ROOMS');poly(r['door'],'OPENINGS',False)
    for i in a['details']['items']:poly(i['polygon'],'OBJECTS')
    for o in plan['openings']:poly(o['segment'],'OPENINGS',False)
    for r in a['details']['routes']+a['strategy']['routes']:poly(r['points'],'ROUTES',False)
    for p in v['analysis']['pipes']:poly(p['points'],'DRAIN',False)
    for p in v['analysis'].get('wires',[]):poly(p['points'],'ELECTRICAL',False)
    m.add_text('PRELIMINARY REVIEW - NOT FOR CONSTRUCTION',dxfattribs={'height':1,'insert':(0,-5),'layer':'LABELS'})
    out=io.StringIO();d.write(out);return out.getvalue().encode()


def render_csv(v):
    out=io.StringIO();w=csv.writer(out);w.writerow(['id','item','quantity','unit','rate_PHP','cost_PHP','formula','rate_source','rate_basis','source_ids'])
    def safe(x):return "'"+x if isinstance(x,str) and x[:1] in '=+-@' else x
    for r in v['analysis']['quantities']['items']:w.writerow([safe(x) for x in [r['id'],r['name'],r['quantity'],r['unit'],r['rate'],r['cost_php'],r['formula'],r['rate_source'],r['rate_basis'],';'.join(r['source_ids'])]])
    return out.getvalue().encode()


def render_zip(v):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('review.pdf',render_pdf(v));z.writestr('layout.dxf',render_dxf(v));z.writestr('quantities.csv',render_csv(v));z.writestr('project.json',json.dumps({'schema_version':'planning-1','accepted':v['accepted'],'site':v['site'],'analysis':v['analysis'],'artifact_refs':v['refs'],'agent_reviews':v.get('agent_reviews',{})},indent=2));z.writestr('README.txt','Preliminary review only. Not for construction or certification.\nDesign hash: '+v['analysis']['design_hash']+'\nResult hash: '+v['analysis']['result_hash']+'\nMissing/unsupported coverage is listed in review.pdf and project.json. DXF units: metres. Pricing is partial unless explicitly marked complete for modelled scope.\n')
    return out.getvalue()
