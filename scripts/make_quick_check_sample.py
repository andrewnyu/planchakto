"""Draw the Quick check sample sheets (a synthetic roof framing plan and a synthetic floor plan) and their recorded readings.

A recorded reading is what a correct read of the sheet returns. It is generated from the same numbers that draw the
sheet, so it doubles as ground truth for evals of the live Gemini reading. Run from the repo root:
    .venv/bin/python scripts/make_quick_check_sample.py
"""
import json,textwrap
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

OUT=Path(__file__).resolve().parent.parent/'examples'/'quick-check'
W,H=1800,1200
X0,Y0,S=230,250,70  # plan origin (grid A-1) in px and px per metre
GX=[('A',0),('B',5),('C',10),('D',15)];GY=[('1',0),('2',4),('3',8)]
INK=(30,38,34);GREY=(150,156,150);RED=(176,60,40)
font=lambda n:ImageFont.load_default(size=n)
px=lambda x:X0+x*S;py=lambda y:Y0+y*S

def dashed(d,a,b,fill,width=1,dash=14,gap=8):
    (x1,y1),(x2,y2)=a,b;length=((x2-x1)**2+(y2-y1)**2)**.5;n=int(length//(dash+gap))+1
    for k in range(n):
        t0=k*(dash+gap)/length;t1=min(1,(k*(dash+gap)+dash)/length)
        d.line([(x1+(x2-x1)*t0,y1+(y2-y1)*t0),(x1+(x2-x1)*t1,y1+(y2-y1)*t1)],fill=fill,width=width)

def draw():
    img=Image.new('RGB',(W,H),'white');d=ImageDraw.Draw(img)
    d.rectangle([20,20,W-20,H-20],outline=INK,width=3)
    right,bottom=px(GX[-1][1]),py(GY[-1][1])
    for label,x in GX:  # vertical grid lines, bubbles on top
        dashed(d,(px(x),150),(px(x),bottom+70),GREY);d.ellipse([px(x)-22,88,px(x)+22,132],outline=INK,width=2);d.text((px(x),110),label,fill=INK,font=font(22),anchor='mm')
    for label,y in GY:  # horizontal grid lines, bubbles on the left
        dashed(d,(150,py(y)),(right+70,py(y)),GREY);d.ellipse([73,py(y)-22,117,py(y)+22],outline=INK,width=2);d.text((95,py(y)),label,fill=INK,font=font(22),anchor='mm')
    # dimension chains in millimetres
    d.line([(px(0),205),(right,205)],fill=INK);d.line([(px(0),170),(right,170)],fill=INK)
    for (_,a),(_,b) in zip(GX,GX[1:]):d.text(((px(a)+px(b))/2,196),f'{(b-a)*1000:.0f}',fill=INK,font=font(16),anchor='ms')
    d.text(((px(0)+right)/2,161),f'{GX[-1][1]*1000:.0f}',fill=INK,font=font(16),anchor='ms')
    for _,x in GX:d.line([(px(x),160),(px(x),212)],fill=INK)
    d.line([(165,py(0)),(165,bottom)],fill=INK)
    for (_,a),(_,b) in zip(GY,GY[1:]):d.text((172,(py(a)+py(b))/2),f'{(b-a)*1000:.0f}',fill=INK,font=font(16),anchor='lm')
    for _,y in GY:d.line([(158,py(y)),(172,py(y))],fill=INK)
    # girders on grid lines (dashed), roof beams along rows (heavy), columns at every intersection
    for i,(_,x) in enumerate(GX):dashed(d,(px(x),py(0)),(px(x),bottom),INK,width=3,dash=18,gap=10)
    n=0
    for _,y in GY:
        for (_,a),(_,b) in zip(GX,GX[1:]):
            n+=1;d.line([(px(a),py(y)),(px(b),py(y))],fill=INK,width=6);d.text(((px(a)+px(b))/2,py(y)-12),f'RB-{n}',fill=INK,font=font(15),anchor='ms')
    d.text((px(0)+8,(py(0)+py(1*4))/2),'G-1 (TYP.)',fill=INK,font=font(15),anchor='lm')
    cols={}
    for j,(ly,y) in enumerate(GY):
        for i,(lx,x) in enumerate(GX):
            d.rectangle([px(x)-9,py(y)-9,px(x)+9,py(y)+9],fill=INK);cols[f'{lx}-{ly}']=(py(y),px(x))
            d.text((px(x)+14,py(y)+14),'C1',fill=INK,font=font(13),anchor='lt')
    d.text(((px(0)+right)/2,bottom+110),'ROOF FRAMING PLAN',fill=INK,font=font(26),anchor='ms');d.text(((px(0)+right)/2,bottom+138),'SCALE 1:100',fill=INK,font=font(16),anchor='ms')
    d.line([((px(0)+right)/2-150,bottom+118),((px(0)+right)/2+150,bottom+118)],fill=INK,width=2)
    # notes and member schedule
    x=1430;y=90;boxes={}
    d.text((x,y),'GENERAL NOTES',fill=INK,font=font(20));y+=40
    notes=[('units','1. ALL DIMENSIONS ARE IN MILLIMETRES UNLESS NOTED OTHERWISE.'),
           ('dead','2. ROOF SUPERIMPOSED DEAD LOAD: 0.65 kPa'),
           ('live','3. ROOF LIVE LOAD: 0.75 kPa (NSCP 2015 TABLE 205-3)'),
           ('soil','4. ALLOWABLE SOIL BEARING: 96 kPa (ASSUMED - VERIFY BY GEOTECHNICAL INVESTIGATION)'),
           ('height','5. EAVE HEIGHT 3.5 m ABOVE FINISHED FLOOR. SINGLE STOREY.'),
           ('steel','6. STRUCTURAL STEEL ASTM A36, fy = 250 MPa.'),
           ('frame','7. ROOF BEAMS SPAN BETWEEN COLUMNS; RIGID BEAM-COLUMN CONNECTIONS.')]
    for key,text in notes:
        top=y
        for line in textwrap.wrap(text,34):d.text((x,y),line,fill=INK,font=font(15));y+=21
        boxes[key]=(top-4,x-4,y,1770);y+=10
    y+=20;d.text((x,y),'MEMBER SCHEDULE',fill=INK,font=font(20));y+=38
    for key,mark,desc,size in [('roof_beam','RB','ROOF BEAM','RHS 150x100x5'),('girder','G','GRID GIRDER','RHS 150x100x5'),('column','C1','COLUMN','SHS 150x150x6'),('footing','F1','PAD FOOTING','1200 x 1200 x 300 THK')]:
        d.text((x,y),mark,fill=INK,font=font(15));d.text((x+50,y),desc,fill=INK,font=font(15));d.text((x+50,y+20),size,fill=INK,font=font(15))
        boxes[key]=(y+16,x+46,y+40,1770);y+=54
    # title block
    d.rectangle([1410,H-250,W-20,H-20],outline=INK,width=2)
    for k,(text,size) in enumerate([('SAMPLE WAREHOUSE ANNEX',20),('ROOF FRAMING PLAN',18),('SHEET S-101',18),('SYNTHETIC SAMPLE - NOT A REAL PROJECT',13),('PLANCHAKTO QUICK CHECK',13)]):
        d.text((1430,H-230+k*40),text,fill=RED if k==3 else INK,font=font(size))
    return img,cols,boxes

def norm(y,x):return [round(y/H*1000,1),round(x/W*1000,1)]
def nbox(b):return [round(b[0]/H*1000,1),round(b[1]/W*1000,1),round(b[2]/H*1000,1),round(b[3]/W*1000,1)]

def reading(cols,boxes):
    return {'sheet_kind':'framing_plan','title':'S-101 Roof framing plan — Sample warehouse annex','units':'mm','storeys':1,
        'grid_x':[{'label':l,'position':x*1000,'page':round(px(x)/W*1000,1)} for l,x in GX],
        'grid_y':[{'label':l,'position':y*1000,'page':round(py(y)/H*1000,1)} for l,y in GY],
        'columns':[{'grid':g,'mark':'C1','point':norm(*p)} for g,p in cols.items()],'columns_at_all_intersections':False,
        'sections':[{'applies_to':k,'text':t,'box':nbox(boxes[k])} for k,t in [('roof_beam','RHS 150x100x5'),('girder','RHS 150x100x5'),('column','SHS 150x150x6'),('footing','1200 x 1200 x 300 THK')]],
        'loads':[{'kind':'dead','value':.65,'unit':'kPa','text':'ROOF SUPERIMPOSED DEAD LOAD: 0.65 kPa','box':nbox(boxes['dead'])},
                 {'kind':'live','value':.75,'unit':'kPa','text':'ROOF LIVE LOAD: 0.75 kPa (NSCP 2015 TABLE 205-3)','box':nbox(boxes['live'])},
                 {'kind':'soil','value':96,'unit':'kPa','text':'ALLOWABLE SOIL BEARING: 96 kPa (ASSUMED - VERIFY BY GEOTECHNICAL INVESTIGATION)','box':nbox(boxes['soil'])}],
        'height_m':3.5,'footing_width_m':1.2,'footing_thickness_m':.3,'outside_supported':[],
        'unread':['Seismic design parameters (R, Na, Nv) are not shown on this sheet']}

# ---------------------------------------------------------------- floor plan for the fire screen
FW,FD=20,12  # overall outside dimensions, m
FX0,FY0,FS=150,230,58  # outer corner of the plan in px and px per metre
EXT,INT=.2,.12  # wall thicknesses, m
ROOMS=[('OFFICE A',0,0,6,5),('OFFICE B',6,0,6,5),('CONFERENCE',12,0,8,5),('CORRIDOR',0,5,20,2),('LOBBY',0,7,6,5),('PANTRY',6,7,4,5),('TOILET',10,7,3,5),('STORAGE',13,7,7,5)]
DOORS=[('OFFICE A','CORRIDOR',3,5),('OFFICE B','CORRIDOR',9,5),('CONFERENCE','CORRIDOR',14,5),('LOBBY','CORRIDOR',4.5,7),('PANTRY','CORRIDOR',8,7),('TOILET','CORRIDOR',11.5,7),('STORAGE','CORRIDOR',15,7)]
EXITS=[('E1','bottom','LOBBY',3,1.8),('E2','left','CORRIDOR',6,.9),('E3','right','CORRIDOR',6,.9)]  # mark, wall, room, centre along the wall (m), clear width (m)
EXTINGUISHERS=[(2.4,5.35,'2-A:10-B:C')]
fx=lambda x:FX0+x*FS;fy=lambda y:FY0+y*FS

def inner(x0,y0,x1,y1):
    """A room's floor inside its walls: exterior walls sit inside the outline, interior walls straddle the room line."""
    t=lambda v,end:EXT if v in (0,end) else INT/2
    return x0+t(x0,FW),y0+t(y0,FD),x1-t(x1,FW),y1-t(y1,FD)

def draw_fire():
    img=Image.new('RGB',(W,H),'white');d=ImageDraw.Draw(img);boxes={}
    d.rectangle([20,20,W-20,H-20],outline=INK,width=3)
    # walls: fill the footprint, then clear each room's floor, which leaves solid walls between them
    d.rectangle([fx(0),fy(0),fx(FW),fy(FD)],fill=INK)
    for name,x,y,w,h in ROOMS:
        a,b,c,e=inner(x,y,x+w,y+h);d.rectangle([fx(a),fy(b),fx(c),fy(e)],fill='white')
    # interior doors: a 0.9 m gap with a leaf and a quarter-circle swing into the room
    for room,_,x,y in DOORS:
        r=next(r for r in ROOMS if r[0]==room);into=-1 if r[2]<y else 1;a,b=fx(x-.45),fx(x+.45)
        d.rectangle([a,fy(y-INT/2)-1,b,fy(y+INT/2)+1],fill='white')
        d.line([(a,fy(y)),(a,fy(y)+into*.9*FS)],fill=INK,width=2)
        d.arc([a-.9*FS,fy(y)-.9*FS,a+.9*FS,fy(y)+.9*FS],*((270,360) if into<0 else (0,90)),fill=GREY,width=1)
    # exits: openings in the exterior wall with outward-swinging leaves, a mark and an exit sign
    for mark,side,_,c,w in EXITS:
        if side=='bottom':
            a,b=fx(c-w/2),fx(c+w/2);d.rectangle([a,fy(FD-EXT)-1,b,fy(FD)+1],fill='white');leaves=[(a,1),(b,-1)] if w>1.2 else [(a,1)];leaf=w/len(leaves)*FS
            for x0,dirn in leaves:d.line([(x0,fy(FD)),(x0,fy(FD)+leaf)],fill=INK,width=2);d.arc([x0-leaf,fy(FD)-leaf,x0+leaf,fy(FD)+leaf],*((0,90) if dirn>0 else (90,180)),fill=GREY)
            box=(fy(FD-EXT)-4,a-4,fy(FD)+leaf+4,b+4);d.text((b+16,fy(FD)+leaf/2),mark,fill=INK,font=font(16),anchor='lm');sign=((a+b)/2,fy(FD-EXT)-22)
        else:
            x=fx(0) if side=='left' else fx(FW);inward=EXT*FS;a,b=fy(c-w/2),fy(c+w/2);out=-1 if side=='left' else 1;leaf=w*FS
            d.rectangle([min(x,x-out*inward)-1,a,max(x,x-out*inward)+1,b],fill='white')
            d.line([(x,a),(x+out*leaf,a)],fill=INK,width=2);d.arc([x-leaf,a-leaf,x+leaf,a+leaf],*((90,180) if out<0 else (0,90)),fill=GREY)
            box=(a-4,min(x,x+out*leaf)-4,b+4,max(x,x+out*leaf)+4);d.text((x+out*leaf/2,a-14),mark,fill=INK,font=font(16),anchor='mm');sign=(x-out*44,(a+b)/2-30)
        boxes[mark]=box;d.rectangle([sign[0]-20,sign[1]-9,sign[0]+20,sign[1]+9],outline=RED,width=2);d.text(sign,'EXIT',fill=RED,font=font(11),anchor='mm')
    for name,x,y,w,h in ROOMS:
        d.text((fx(x+w/2),fy(y+h/2)-9),name,fill=INK,font=font(17),anchor='mm');d.text((fx(x+w/2),fy(y+h/2)+13),f'{w*h:.1f} SQ.M',fill=GREY,font=font(13),anchor='mm')
    for x,y,rating in EXTINGUISHERS:
        d.ellipse([fx(x)-11,fy(y)-11,fx(x)+11,fy(y)+11],fill=RED);d.text((fx(x),fy(y)),'FE',fill='white',font=font(10),anchor='mm')
        d.text((fx(x)+16,fy(y)+2),f'FE-1  {rating}',fill=RED,font=font(12),anchor='lm')
    # dimension strings in millimetres: overall, and room widths along the top and bottom
    top,left=fy(0)-35,fx(0)-40
    d.line([(fx(0),top),(fx(FW),top)],fill=INK);d.line([(fx(0),top-35),(fx(FW),top-35)],fill=INK)
    d.text(((fx(0)+fx(FW))/2,top-44),f'{FW*1000}',fill=INK,font=font(16),anchor='ms')
    for xs,yline in [([0,6,12,20],top),([0,6,10,13,20],fy(FD)+105)]:
        d.line([(fx(0),yline),(fx(FW),yline)],fill=INK)
        for a,b in zip(xs,xs[1:]):d.text(((fx(a)+fx(b))/2,yline-8),f'{(b-a)*1000}',fill=INK,font=font(15),anchor='ms')
        for x in xs:d.line([(fx(x),yline-7),(fx(x),yline+7)],fill=INK)
    d.line([(fx(0),top-42),(fx(0),top+7)],fill=INK);d.line([(fx(FW),top-42),(fx(FW),top+7)],fill=INK)
    d.line([(left,fy(0)),(left,fy(FD))],fill=INK);d.text((left-8,fy(FD*.25)),f'{FD*1000}',fill=INK,font=font(16),anchor='rm')
    for y in [0,FD]:d.line([(left-7,fy(y)),(left+7,fy(y))],fill=INK)
    d.text(((fx(0)+fx(FW))/2,fy(FD)+165),'GROUND FLOOR PLAN',fill=INK,font=font(26),anchor='ms');d.text(((fx(0)+fx(FW))/2,fy(FD)+193),'SCALE 1:100',fill=INK,font=font(16),anchor='ms')
    # notes, legend and title block; the occupancy is deliberately not printed, so the user must choose it
    x=1420;y=90
    d.text((x,y),'GENERAL NOTES',fill=INK,font=font(20));y+=40
    for text in ['1. ALL DIMENSIONS ARE IN MILLIMETRES UNLESS NOTED OTHERWISE.','2. SINGLE STOREY. NO MEZZANINE.','3. E1 MAIN ENTRANCE: DOUBLE DOOR, 1800 CLEAR.','4. E2, E3 AND ALL INTERIOR DOORS: 900 CLEAR.']:
        for line in textwrap.wrap(text,34):d.text((x,y),line,fill=INK,font=font(15));y+=21
        y+=10
    y+=20;d.text((x,y),'LEGEND',fill=INK,font=font(20));y+=38
    d.rectangle([x,y-9,x+40,y+9],outline=RED,width=2);d.text((x+20,y),'EXIT',fill=RED,font=font(11),anchor='mm');d.text((x+54,y),'ILLUMINATED EXIT SIGN',fill=INK,font=font(15),anchor='lm');boxes['signs']=(y-14,x-4,y+14,1770);y+=36
    d.ellipse([x+9,y-11,x+31,y+11],fill=RED);d.text((x+20,y),'FE',fill='white',font=font(10),anchor='mm');d.text((x+54,y),'PORTABLE FIRE EXTINGUISHER',fill=INK,font=font(15),anchor='lm')
    d.rectangle([1410,H-250,W-20,H-20],outline=INK,width=2)
    for k,(text,size) in enumerate([('SAMPLE OFFICE ANNEX',20),('GROUND FLOOR PLAN',18),('SHEET A-101',18),('SYNTHETIC SAMPLE - NOT A REAL PROJECT',13),('PLANCHAKTO QUICK CHECK',13)]):
        d.text((1430,H-230+k*40),text,fill=RED if k==3 else INK,font=font(size))
    return img,boxes

def fire_reading(boxes):
    page=lambda x,y:norm(fy(y),fx(x))
    return {'sheet_kind':'floor_plan','title':'A-101 Ground floor plan — Sample office annex','units':'mm','storeys':1,
        'footprint':{'width':FW*1000,'depth':FD*1000,'box':nbox((fy(0),fx(0),fy(FD),fx(FW)))},
        'rooms':[{'name':n,'box':nbox((fy(b),fx(a),fy(e),fx(c)))} for n,*r in ROOMS for a,b,c,e in [inner(r[0],r[1],r[0]+r[2],r[1]+r[3])]],
        'doors':[{'between':[a,b],'point':page(x,y)} for a,b,x,y in DOORS],
        'exits':[{'side':side,'room':room,'width':w*1000,'text':mark,'box':nbox(boxes[mark])} for mark,side,room,_,w in EXITS],
        'extinguishers':[{'rating':r,'point':page(x,y)} for x,y,r in EXTINGUISHERS],
        'occupancy_text':None,
        'provisions':[{'kind':'exit_signs','provided':True,'text':'ILLUMINATED EXIT SIGN','box':nbox(boxes['signs'])}],
        'outside_supported':[],'unread':[]}

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True);img,cols,boxes=draw()
    img.save(OUT/'structure-sample.png',optimize=True)
    (OUT/'structure-sample.sheet.json').write_text(json.dumps(reading(cols,boxes),indent=1)+'\n')
    img,boxes=draw_fire();img.save(OUT/'fire-sample.png',optimize=True)
    (OUT/'fire-sample.sheet.json').write_text(json.dumps(fire_reading(boxes),indent=1)+'\n')
    print('wrote',*(OUT/f'{k}-sample{e}' for k in ('structure','fire') for e in ('.png','.sheet.json')))
