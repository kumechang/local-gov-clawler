# ユーザーが補完したCSV(data/input/grandgolf_facilities_merged_enriched_*.csv)の元ページを取得し直して照合する(1回限りの作業。D-136)。使い方: python scripts/verify_user_enrichment.py <作業ディレクトリ> <CSV>(作業ディレクトリに pages.json が必要)
import csv,json,re,collections,sys,warnings
warnings.filterwarnings("ignore")
sys.path.insert(0,'src')
from localgov_crawler.nav import norm_text
from localgov_crawler.survey import KeywordSpec
SPEC=KeywordSpec.load('config/keywords/grandgolf.json')
SP=sys.argv[1]; F=sys.argv[2]
pages=json.load(open(SP+'/pages.json'))
rows=list(csv.DictReader(open(F,encoding='utf-8-sig')))
master={}
for m in csv.DictReader(open('data/input/municipalities_master.csv',encoding='utf-8-sig')):
    if m['is_current']=='True' or True: master.setdefault((m['prefecture_name'],m['municipality_name']),[]).append(m['municipality_code'])
def nz(s):
    s=norm_text(s); s=re.sub(r'^.{2,3}[都道府県]','',s) if re.match(r'^.{2,3}[都道府県]',s) else s
    s=re.sub(r'[丁目番地号の－−ー‐\-]+','-',s); s=re.sub(r'[\s　]','',s); return s.strip('-')
def core(n):
    n=norm_text(n); n=re.sub(r'^[\d]+[.]\s*','',n); n=re.sub(r'[(（].*?[)）]','',n); return n.strip()
def near_gg(t,nm):
    if not nm: return False
    for m in re.finditer(re.escape(nm),t):
        seg=t[max(0,m.start()-200):m.end()+200]
        if SPEC.in_text(seg): return True
    return False
out=[]
for r in rows:
    r=dict(r); cat=r['情報補完']; r['_cat']=cat
    if cat in ('Web補完','未補完'):
        pg=pages.get(r['元ページ'],{})
        if pg.get('status')!=200:
            r['_page']='取得できず:'+str(pg.get('error') or pg.get('status'))
            r['_name']=r['_gg']=r['_addr']=r['_tel']=''
        else:
            t=pg['text']; nm=core(r['施設名']); tn=nz(t)
            r['_page']='取得済み'
            r['_name']='あり' if nm and nm in t else 'なし'
            r['_gg']='近く' if near_gg(t,nm) else ('ページ内' if SPEC.in_text(t) else 'なし')
            r['_addr']='' if not r['住所'] else ('確認' if nz(r['住所'])[:14] in tn else '未確認')
            r['_tel']='' if not r['電話番号'] else ('確認' if norm_text(r['電話番号']) in t else '未確認')
    out.append(r)
json.dump(out,open(SP+'/verified.json','w'),ensure_ascii=False)
c=collections.Counter((r['_cat'],r.get('_page'),r.get('_name'),r.get('_gg'),r.get('_addr'),r.get('_tel')) for r in out if r['_cat'] in ('Web補完','未補完'))
for k,v in sorted(c.items(),key=lambda x:-x[1]): print(v,k)
