# 照合結果(verified.json)から data/export/grandgolf_facilities_verified.csv と grandgolf_facilities_to_check.csv を作る(D-136)。使い方: python scripts/build_verified_facilities.py <作業ディレクトリ>
import csv,json,re,collections,sys,warnings
warnings.filterwarnings("ignore")
sys.path.insert(0,'src')
from localgov_crawler.nav import norm_text
from localgov_crawler.survey import KeywordSpec
SPEC=KeywordSpec.load('config/keywords/grandgolf.json')
SP=sys.argv[1]
pages=json.load(open(SP+'/pages.json')); ver=json.load(open(SP+'/verified.json'))
master={}
for m in csv.DictReader(open('data/input/municipalities_master.csv',encoding='utf-8-sig')):
    master.setdefault((m['prefecture_name'],m['municipality_name']),[]).append(m['municipality_code'])
def core(n):
    n=norm_text(n); n=re.sub(r'^[\d]+[.]\s*','',n); n=re.sub(r'[(（].*?[)）]','',n); return n.strip()
def evidence(t,nm):
    for m in re.finditer(re.escape(nm),t):
        seg=t[max(0,m.start()-200):m.end()+200]; g=SPEC.find(seg)
        if g:
            a=max(0,g[0].start()-50); return seg[a:g[0].end()+50]
    return ''
base=list(csv.DictReader(open('data/export/grandgolf_facilities_all.csv',encoding='utf-8-sig')))
cols=['prefecture','municipality_code','municipality_name','facility_name','address','phone','inquiry_dept','inquiry_phone','contact_phone','contact_phone_kind','page_url','keyword_evidence','grandgolf_basis','data_source','verification']
def contact(r):
    if r.get('phone'): return r['phone'],'施設'
    if r.get('inquiry_phone'): return r['inquiry_phone'],'問い合わせ先'
    return '',''
out=[]; keyidx={}
for r in base:
    c,k=contact(r)
    o={'prefecture':r['prefecture'],'municipality_code':r['municipality_code'],'municipality_name':r['municipality_name'],'facility_name':r['facility_name'],'address':r['address'],'phone':r['phone'],'inquiry_dept':r['inquiry_dept'],'inquiry_phone':r['inquiry_phone'],'contact_phone':c,'contact_phone_kind':k,'page_url':r['page_url'],'keyword_evidence':r['keyword_evidence'],'grandgolf_basis':r['grandgolf_basis'],'data_source':'自動抽出','verification':''}
    out.append(o); keyidx[(r['prefecture'],r['municipality_name'],core(r['facility_name']))]=o
check=[]; added=filled=held=0
for r in ver:
    if r['_cat'] not in ('Web補完','未補完'): continue
    pref,muni,name=r['都道府県'],r['市区町村'],r['施設名']
    codes=master.get((pref,muni),[])
    code=codes[0] if len(codes)==1 else ''
    reason=''
    if not r['_page']=='取得済み': reason='元ページを取得できず確認不可('+r['_page']+')'
    elif r['_name']!='あり': reason='ページに施設名が見つからない'
    elif r['_gg']!='近く': reason='施設名の近くにグラウンドゴルフの記述がない(ページ内のみ)'
    elif not code: reason='市区町村コードを特定できない'
    pg=pages.get(r['元ページ'],{}); t=pg.get('text','')
    if reason:
        check.append({'prefecture':pref,'municipality_name':muni,'facility_name':name,'address':r['住所'],'phone':r['電話番号'],'page_url':r['元ページ'],'reason':reason,'source_category':r['_cat']}); held+=1; continue
    addr=r['住所'] if r['_addr']=='確認' else ''; tel=r['電話番号'] if r['_tel']=='確認' else ''
    notes=[]
    if r['住所'] and not addr: check.append({'prefecture':pref,'municipality_name':muni,'facility_name':name,'address':r['住所'],'phone':'','page_url':r['元ページ'],'reason':'住所が元ページで確認できない(補完値のみ)','source_category':r['_cat']}); notes.append('住所は補完値あり・未確認')
    if r['電話番号'] and not tel: check.append({'prefecture':pref,'municipality_name':muni,'facility_name':name,'address':'','phone':r['電話番号'],'page_url':r['元ページ'],'reason':'電話が元ページで確認できない(補完値のみ)','source_category':r['_cat']}); notes.append('電話は補完値あり・未確認')
    ver_txt='ページで確認'+(':住所' if addr else '')+(':電話' if tel else '')
    key=(pref,muni,core(name))
    if key in keyidx:
        o=keyidx[key]; ch=False
        if addr and not o['address']: o['address']=addr; ch=True
        if tel and not o['phone']: o['phone']=tel; ch=True
        if ch:
            o['contact_phone'],o['contact_phone_kind']=contact(o); o['data_source']='自動抽出+ユーザー補完'; o['verification']=ver_txt+(' / '+';'.join(notes) if notes else ''); filled+=1
        continue
    c,k=(tel,'施設') if tel else ('','')
    inq=r['問い合わせ電話'] if r['問い合わせ電話'] and norm_text(r['問い合わせ電話']) in t else ''
    if not tel and inq: c,k=inq,'問い合わせ先'
    o={'prefecture':pref,'municipality_code':code,'municipality_name':muni,'facility_name':name,'address':addr,'phone':tel,'inquiry_dept':r['問い合わせ先'] if inq else '','inquiry_phone':inq,'contact_phone':c,'contact_phone_kind':k,'page_url':r['元ページ'],'keyword_evidence':evidence(t,core(name)),'grandgolf_basis':'施設の記述にワードあり','data_source':'ユーザー補完','verification':ver_txt+(' / '+';'.join(notes) if notes else '')}
    out.append(o); keyidx[key]=o; added+=1
out.sort(key=lambda r:(r['municipality_code'],r['page_url'],r['facility_name']))
with open('data/export/grandgolf_facilities_verified.csv','w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=cols); w.writeheader(); w.writerows(out)
ccols=['prefecture','municipality_name','facility_name','address','phone','page_url','reason','source_category']
with open('data/export/grandgolf_facilities_to_check.csv','w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=ccols); w.writeheader(); w.writerows(check)
n=len(out)
print('master',n,'munis',len({r['municipality_code'] for r in out}),'added',added,'filled existing',filled,'held rows',held,'check rows',len(check))
print('addr',sum(1 for r in out if r['address']),'contact',sum(1 for r in out if r['contact_phone']),'both',sum(1 for r in out if r['address'] and r['contact_phone']))
print(collections.Counter(r['reason'] for r in check))
# 転記 stat
t=[r for r in ver if r['_cat']=='問い合わせ電話を転記']; print('転記 rows',len(t))
