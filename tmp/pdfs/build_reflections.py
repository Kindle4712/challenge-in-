from pathlib import Path
import re
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'output/pdf'; OUT.mkdir(exist_ok=True)
pdfmetrics.registerFont(TTFont('SimHei',r'C:\Windows\Fonts\simhei.ttf'))
S={'t':ParagraphStyle('t',fontName='SimHei',fontSize=20,leading=28,textColor=colors.HexColor('#1C3743'),spaceAfter=14),'h':ParagraphStyle('h',fontName='SimHei',fontSize=12,leading=18,textColor=colors.HexColor('#117474'),spaceBefore=12,spaceAfter=5),'b':ParagraphStyle('b',fontName='SimHei',fontSize=9.1,leading=15.2,textColor=colors.HexColor('#28343A'),spaceAfter=6),'l':ParagraphStyle('l',fontName='SimHei',fontSize=8.9,leading=14.8,leftIndent=15,firstLineIndent=-10,textColor=colors.HexColor('#28343A'),spaceAfter=4)}
def deco(c,d):
 c.saveState(); w,h=A4; c.setFillColor(colors.HexColor('#117474')); c.rect(48,h-46,w-96,3,fill=1,stroke=0); c.setStrokeColor(colors.HexColor('#D6E0E0')); c.line(48,47,w-48,47); c.setFont('SimHei',8); c.setFillColor(colors.HexColor('#657578')); c.drawString(48,33,'第一次挑战 · 复盘材料'); c.drawRightString(w-48,33,str(d.page)); c.restoreState()
def clean_inline(x):
 x=re.sub(r'\[([^\]]+)\]\([^)]*\)',r'\1',x)
 x=x.replace('**','').replace('__','').replace('`','')
 return x
def build(src,dst):
 story=[]
 for x in src.read_text(encoding='utf-8').splitlines():
  x=x.strip()
  if not x: continue
  x=clean_inline(x)
  if x.startswith('# '): p=S['t']; x=x[2:]
  elif x.startswith('## '): p=S['h']; x=x[3:]
  elif x.startswith('- '): p=S['l']; x='- '+x[2:]
  else: p=S['b']
  story.append(Paragraph(escape(x),p))
 d=BaseDocTemplate(str(dst),pagesize=A4,leftMargin=49,rightMargin=49,topMargin=63,bottomMargin=61); f=Frame(d.leftMargin,d.bottomMargin,d.width,d.height,leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0); d.addPageTemplates(PageTemplate(id='m',frames=[f],onPage=deco)); d.build(story)
build(ROOT/'作业感受.md',OUT/'作业感受.pdf'); build(ROOT/'AI使用说明.md',OUT/'AI使用说明情况.pdf')
build(ROOT/'理论重点回答.md',OUT/'理论重点回答.pdf')
