#!/usr/bin/env python3
"""aT 농수축산물 도매가격(조사가격) 수집기. 실제 경락가와 혼합하지 않습니다."""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo
from update_prices import ROOT, WATCH, classify, unit_kg, TZ

GRID = 'Grid_20150406000000000217_1'
BASE = 'http://211.237.50.150:7080/openapi/{key}/json/' + GRID + '/{start}/{end}'
TARGET = ROOT / 'data/wholesale.json'
JS = ROOT / 'data/wholesale.js'
SOURCE_URL = 'https://data.mafra.go.kr/opendata/data/indexOpenDataDetail.do?data_id=20141016000000000288'


def get_rows(key, date, max_pages=80):
    collected=[]
    start=1
    for _ in range(max_pages):
        # 채소류 부류(200)로 필터링해 호출수를 줄인다.
        params=urllib.parse.urlencode({'EXAMIN_DE':date, 'FRMPRD_CATGORY_CD':'200'})
        url=BASE.format(key=urllib.parse.quote(key,safe=''),start=start,end=start+999)+'?'+params
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Wooyirak-MarketMonitor/1.1'}),timeout=35) as r:
                body=json.load(r)
        except (ValueError,urllib.error.URLError,TimeoutError) as ex:
            raise RuntimeError('공식 API 요청 실패 (통신/인증/서버 접근권한 확인)') from ex
        w=body.get(GRID)
        if not isinstance(w,dict):
            raise RuntimeError('도매가격 API 응답 스키마 오류 (서비스명 또는 인증 확인)')
        info=w.get('result',{}) or {}
        code=str(info.get('code',''))
        if code=='INFO-200':
            return []
        if code!='INFO-000':
            raise RuntimeError(f'도매가격 API 결과 코드 {code}: {info.get("message", "정상 아님")}')
        rows=w.get('row',[]) or []
        if isinstance(rows,dict):rows=[rows]
        if not isinstance(rows,list):raise RuntimeError('도매가격 API row 배열 오류')
        collected.extend(rows)
        total=int(w.get('totalCnt',0) or 0)
        if len(collected)>=total:
            return collected
        if not rows:
            raise RuntimeError('도매가격 일부 페이지만 반환되어 저장하지 않음')
        start+=1000
        time.sleep(.12)
    raise RuntimeError('도매가격 데이터 페이지 상한 도달, 불완전 데이터 저장 중단')


def transform(rows):
    items={}
    for r in rows:
        if str(r.get('FRMPRD_CATGORY_CD',''))!='200':continue
        product=classify(r.get('PRDLST_NM',''),r.get('SPCIES_NM',''))
        if not product:continue
        unit=str(r.get('EXAMIN_UNIT') or '').strip()
        kg=unit_kg(unit)
        if not kg:continue
        try:amt=float(str(r.get('AMT','')).replace(',',''))
        except (ValueError,TypeError):continue
        date=str(r.get('EXAMIN_DE') or '')
        if not re.fullmatch(r'\d{8}',date) or not (amt>0):continue
        rec={
            'date':f'{date[:4]}-{date[4:6]}-{date[6:]}',
            'product':product,
            'variety':str(r.get('SPCIES_NM') or '미상').strip(),
            'grade':str(r.get('GRAD_NM') or '미표시').strip(),
            'region':str(r.get('AREA_NM') or '미상').strip(),
            'market':str(r.get('MRKT_NM') or '미상').strip(),
            'standard':unit,
            'kg_per_unit':kg,
            'price_kg':round(amt/kg),
        }
        # 동일 일자·시장·품목·품종·등급·규격에 대한 동일 키 중복만 제거.
        k=(rec['date'],rec['product'],rec['variety'],rec['grade'],rec['region'],rec['market'],unit)
        items[k]=rec
    return sorted(items.values(),key=lambda r:(r['date'],r['product'],r['region'],r['market'],r['variety'],r['grade']))


def run(args):
    key=os.getenv('MAFRA_API_KEY','').strip()
    if not key:
        print('MAFRA_API_KEY 미설정: 도매 조사 가격 수집 불가',file=sys.stderr)
        return 2
    try:
        previous=json.loads(TARGET.read_text(encoding='utf-8'))
        old=previous.get('records',[]) if isinstance(previous.get('records'),list) else []
    except (FileNotFoundError,ValueError):old=[]
    today=dt.datetime.now(TZ).date()
    dates=[today-dt.timedelta(days=i) for i in range(args.days)]
    changed=[]
    errs=[]
    for day in dates:
        d=day.strftime('%Y%m%d')
        try:
            fetched=get_rows(key,d,args.max_pages)
            found=transform(fetched)
            changed.extend(found)
            print(f'{d} 조사 도매가격 {len(fetched)}건 중 비교 가능 {len(found)}건')
        except RuntimeError as e:
            errs.append(f'{d}: {e}')
            print(errs[-1],file=sys.stderr)
    if errs:
        print('도매 조사 가격 소스의 부분 오류: 이전 데이터를 유지합니다.',file=sys.stderr)
        return 1
    searched_dates={d.isoformat() for d in dates}
    cutoff=(today-dt.timedelta(days=90)).isoformat()
    result=[r for r in old if r.get('date') not in searched_dates and r.get('date','')>=cutoff] + changed
    result.sort(key=lambda r:(r['date'],r['product'],r['region'],r['market'],r['variety'],r['grade']))
    payload={
        'status':'connected',
        'updated_at':dt.datetime.now(TZ).isoformat(timespec='seconds'),
        'source':'한국농수산식품유통공사 / 농수축산물 도매가격 (조사 가격)',
        'source_url':SOURCE_URL,
        'method':'품목·지역·시장·품종·등급별 조사 도매가격을 조사단위 kg 환산. 실시간 경매 낙찰가 아님',
        'records':result,
    }
    TARGET.parent.mkdir(parents=True,exist_ok=True)
    tmp=TARGET.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    tmp.replace(TARGET)
    JS.write_text('window.__WHOLESALE_DATA__ = '+json.dumps(payload,ensure_ascii=False,separators=(',',':'))+';\n',encoding='utf-8')
    print(f'조사 도매가격 저장: {len(result)}건')
    return 0

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--days',type=int,default=2)
    p.add_argument('--max-pages',type=int,default=80)
    a=p.parse_args()
    if not 1<=a.days<=60:p.error('--days 1~60')
    sys.exit(run(a))
