"""Reject unusable frames and ungrounded candidates before they can create listings.
No simulator labels, item catalog or object positions are consulted.
"""
from __future__ import annotations
import math,re
from PIL import Image,ImageStat

GENERIC=set('a an the small large big tiny dark light colored colour colored rectangular rectangle round square cylindrical flat object objects item items thing something personal portable belonging belongings unknown unclear unidentifiable other unidentified plastic metal rubber leather fabric wooden shape solid smooth surface raised edge black white red blue green yellow orange purple brown gray grey silver gold pink teal clear transparent multicolor navy olive rust'.split())
FIXTURES=set('bench benches slat slats armrest backrest furniture chair table desk wall building ground floor tile pavement path railing column pillar tree plant planter bin trashcan sign fixture'.split())
ALIASES={'rucksack':'backpack','knapsack':'backpack','macbook':'laptop','computer':'laptop','cellphone':'phone','smartphone':'phone','cell':'phone','flask':'bottle','tumbler':'bottle','notebook':'book','textbook':'book','soccer':'ball','football':'ball','ducky':'duck'}

def image_quality_reason(image: Image.Image) -> str | None:
 gray=image.convert('L').resize((96,72))
 if ImageStat.Stat(gray).stddev[0]<2.0 or gray.entropy()<0.3:return 'blank or near-uniform image'
 if sum(gray.histogram()[:8])/ (96*72)>.995:return 'black/loading image'
 return None

def type_words(item: dict) -> set[str]:
 title=str(item.get('title') or item.get('object_type') or '').lower()
 # Ignore placement/context prose when deciding what the candidate itself is.
 title=re.split(r'\b(?:on|near|beside|under|next to|sitting|resting|lying)\b',title)[0]
 tokens={ALIASES.get(w,w)for w in re.findall('[a-z]+',title)}
 if tokens&FIXTURES:return set()
 specific={w for w in tokens if len(w)>2 and w not in GENERIC}
 anchors=specific & set('backpack laptop phone bottle book duck ball wallet keys umbrella headphones glasses sunglasses jacket charger bag hat lunchbox shoe skateboard calculator watch purse'.split())
 return anchors or specific

def candidate_reason(item: dict,width: int,height: int,min_long_side: int=48) -> str | None:
 box=item.get('box',{})
 try:coords=[box[k]for k in ('x1','y1','x2','y2')]
 except (KeyError,TypeError):return 'missing bounding box'
 if any(isinstance(v,bool)or not isinstance(v,(int,float))or not math.isfinite(v)for v in coords):return 'invalid bounding box'
 x1,y1,x2,y2=coords;w=x2-x1;h=y2-y1
 if x1<0 or y1<0 or x2>width or y2>height or w<12 or h<12 or max(w,h)<min_long_side:return 'small, clipped or out-of-frame candidate'
 if w*h/(width*height)>.15:return 'candidate covers too much of the scene'
 if item.get('part_of_scene')is True or item.get('clearly_visible')is False or item.get('is_lost_item')is False:return 'model rejected candidate'
 if not type_words(item):return 'generic or structural identification'
 return None
