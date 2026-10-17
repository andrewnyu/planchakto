"""Draw the Quick check sample sheet (a synthetic roof framing plan) and its recorded reading.

The recorded reading is what a correct read of the sheet returns. It is generated from the same numbers that draw the
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

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True);img,cols,boxes=draw()
    img.save(OUT/'structure-sample.png',optimize=True)
    (OUT/'structure-sample.sheet.json').write_text(json.dumps(reading(cols,boxes),indent=1)+'\n')
    print('wrote',OUT/'structure-sample.png',OUT/'structure-sample.sheet.json')
