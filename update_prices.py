#!/usr/bin/env python3
"""우이락 농산물 경락정보 수집기. MAFRA 공영도매시장 실시간 경락정보.

Requires MAFRA_API_KEY environment variable from data.mafra.go.kr.
Never creates synthetic price data. Fails closed for partial, malformed, or unauthenticated responses.
"""
import argparse
import datetime as dt
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_URL = 'http://211.237.50.150:7080/openapi/{key}/json/Grid_20240625000000000654_1/{start}/{end}'
ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / 'data/prices.json'
JS_PATH = ROOT / 'data/prices.js'
TZ = ZoneInfo('Asia/Seoul')
MARKETS = {'110001': '서울가락', '210001':'부산엄궁', '210009':'부산반여', '220001':'대구북부'}
CATEGORIES = ['06','09','10','11','12','13','16']  # 과실, 과채, 엽경채, 근채, 조미채소, 양채, 버섯
COLLECTION_VERSION = 2
# 우이락에서 실제로 사용할 22개 품목. 순서는 홈페이지 표시 순서와 동일하다.
WATCH = [
 ('청경채',['청경채']), ('팽이버섯',['팽이버섯','팽이']),
 ('깻잎',['깻잎']), ('당근',['당근']), ('대파',['대파']),
 ('양파',['양파']), ('부추',['부추']),
 ('알배기배추',['알배기배추','알배기']), ('적양배추',['적양배추','적채']),
 ('양배추',['양배추']), ('오이고추',['오이고추','오이맛고추','아삭이고추']),
 ('오이',['오이']), ('청양고추',['청양']), ('홍고추',['홍고추','붉은고추']),
 ('쪽파',['쪽파']), ('두부',['두부']), ('다진마늘',['다진마늘','다진 마늘']),
 ('마늘',['마늘']), ('미나리',['미나리']), ('꽈리고추',['꽈리고추']),
 ('방울토마토',['방울토마토','대추방울']),
 ('배',['신고배','원황배','풍수배','화산배','추황배','만풍배','배(일반)']),
]


def select_target_dates(existing_records, checked_dates, today, refresh_days=2,
                        history_days=30, backfill_batch=4):
    """최근 자료를 갱신하면서 30일 창의 미수집 일자를 작은 배치로 채운다."""
    window = [today - dt.timedelta(days=i) for i in range(history_days)]
    refresh = window[:refresh_days]
    known = {
        str(row.get('date')) for row in existing_records
        if isinstance(row, dict) and row.get('date')
    } | {str(value) for value in checked_dates}
    refresh_keys = {day.isoformat() for day in refresh}
    # 오래된 누락일부터 채워 전체 30일 범위를 가능한 빨리 확보한다.
    missing = [day for day in reversed(window)
               if day.isoformat() not in known and day.isoformat() not in refresh_keys]
    return refresh + missing[:backfill_batch]


def classify(mid, small):
    mid_text = str(mid or '').replace(' ', '')
    small_text = str(small or '').replace(' ', '')
    if mid_text == '배' or small_text == '배':
        return '배'
    text = f'{mid_text}{small_text}'
    for name, aliases in WATCH:
        if any(alias.replace(' ','') in text for alias in aliases):
            # 혼동하기 쉬운 유사명 제외
            if name == '오이' and ('오이고추' in text or '아삭이고추' in text):
                continue
            if name == '마늘' and any(value in text for value in ('깐마늘','다진마늘')):
                continue
            if name == '무' and any(z in text for z in ('무청','무순','무화과')):
                continue
            if name == '호박' and '애호박' not in text:
                continue
            return name
    return None


def unit_kg(std):
    """단위가 명백히 kg/g로 표기된 건만 환산. 단, 박스/단 등 단위만 표기는 제외."""
    st = str(std or '').lower().replace(' ','')
    if '혼합' in st or '묶음' in st and not re.search(r'(\d+(?:\.\d+)?)\s*(kg|g)', st):
        return None
    m = re.search(r'(\d+(?:\.\d+)?)\s*(kg|㎏|킬로|g|ｇ|그램)(?![a-z])', st)
    if not m:
        return None
    n = float(m.group(1))
    kg = n if m.group(2) in ('kg','㎏','킬로') else n / 1000
    return round(kg, 5) if 0.025 <= kg <= 100 else None


def get_rows(key, when, market, category, limit_pages=100):
    """모든 페이지를 조회. 중간에 실패하거나 페이지 상한 도달 시 해당 조합을 통째로 제외."""
    gathered = []
    start = 1
    for page in range(limit_pages):
        end = start + 999
        url = BASE_URL.format(key=urllib.parse.quote(key, safe=''), start=start, end=end)
        query = urllib.parse.urlencode({'SALEDATE': when, 'WHSALCD': market, 'LARGE': category})
        req = urllib.request.Request(url + '?' + query, headers={'User-Agent':'Wooyirak-MarketMonitor/1.0'})
        try:
            with urllib.request.urlopen(req, timeout=35) as res:
                body = json.load(res)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise RuntimeError(f'{market}/{category}/{when}: 통신 실패: {exc}') from exc
        wrapper = body.get('Grid_20240625000000000654_1')
        if not isinstance(wrapper, dict):
            raise RuntimeError(f'{market}/{category}/{when}: API 구조 오류: {str(body)[:250]}')
        status = wrapper.get('result', {}) or {}
        code = str(status.get('code',''))
        if code == 'INFO-200':  # 휴장이나 공개 데이터 없음
            return []
        if code not in ('INFO-000',):
            raise RuntimeError(f'{market}/{category}/{when}: {code}: {status.get("message", "API 오류")}')
        rows = wrapper.get('row', []) or []
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            raise RuntimeError('예상하지 못한 row 형식')
        total = int(wrapper.get('totalCnt', 0) or 0)
        gathered.extend(rows)
        if len(gathered) >= total:
            return gathered
        if not rows:
            raise RuntimeError('API가 일부 페이지만 반환했습니다')
        start = end + 1
        time.sleep(0.07)
    raise RuntimeError(f'{market}/{category}/{when}: 페이지 상한({limit_pages}) 초과, 불완전 데이터 제외')


def transform_rows(raw_rows):
    """그룹별 kg 환산 실거래 가격의 중앙값 산출 (평균 경락가 아님)."""
    groups = defaultdict(list)
    for r in raw_rows:
        product = classify(r.get('MIDNAME', ''), r.get('SMALLNAME', ''))
        kg = unit_kg(r.get('STD'))
        if not product or not kg:
            continue
        try:
            cost = float(str(r.get('COST','')).replace(',',''))
        except ValueError:
            continue
        if cost <= 0:
            continue
        date = str(r.get('SALEDATE',''))
        mkt = str(r.get('WHSALCD',''))
        if not re.fullmatch(r'\d{8}', date) or mkt not in MARKETS:
            continue
        variant = str(r.get('SMALLNAME') or r.get('MIDNAME') or '미상').strip()
        packaging = str(r.get('STD') or '').strip()
        # 품종, 원규격, 시장이 동일한 거래끼리만 중앙값 집계.
        key = (date, mkt, product, variant, packaging, kg)
        groups[key].append(cost / kg)
    result = []
    for (date, market, product, variety, packaging, kg), values in groups.items():
        result.append({
            'date': f'{date[:4]}-{date[4:6]}-{date[6:]}',
            'market': market, 'market_name': MARKETS[market],
            'product': product, 'variety': variety, 'standard': packaging,
            'kg_per_package': kg,
            'price_kg': round(statistics.median(values)),
            'trade_count': len(values),
        })
    return sorted(result, key=lambda x:(x['date'],x['market'],x['product'],x['variety'],x['standard']))


def save(payload):
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    tmp = DATA_PATH.with_suffix('.json.tmp')
    tmp.write_text(content+'\n', encoding='utf-8')
    tmp.replace(DATA_PATH)
    JS_PATH.write_text('window.__AUCTION_DATA__ = '+json.dumps(payload, ensure_ascii=False, separators=(',',':'))+';\n',encoding='utf-8')


def run(args):
    key = os.getenv('MAFRA_API_KEY','').strip()
    if not key:
        print('MAFRA_API_KEY 환경변수가 없습니다. 실제 시세는 수집하지 않습니다.',file=sys.stderr)
        return 2
    today = dt.datetime.now(TZ).date()
    try:
        existing = json.loads(DATA_PATH.read_text(encoding='utf-8'))
        if not isinstance(existing.get('records'), list):
            existing = {'records': []}
    except (FileNotFoundError, ValueError):
        existing = {'records': []}
    changed = []
    errors = []
    checked_dates = existing.get('checked_dates', [])
    if not isinstance(checked_dates, list):
        checked_dates = []
    if existing.get('collection_version') != COLLECTION_VERSION:
        checked_dates = []
    targets = select_target_dates(
        existing.get('records', []), checked_dates, today,
        refresh_days=args.days, history_days=args.history_days,
        backfill_batch=args.backfill_batch,
    )
    for day in targets:
        d = day.strftime('%Y%m%d')
        for market, market_label in MARKETS.items():
            for cat in CATEGORIES:
                try:
                    fetched = get_rows(key, d, market, cat, args.max_pages)
                    transformed = transform_rows(fetched)
                    changed.extend(transformed)
                    print(f'{d} {market_label} 대분류 {cat}: 원거래 {len(fetched)}, 분석 {len(transformed)}')
                except RuntimeError as exc:
                    errors.append(str(exc))
                    print(f'오류: {exc}',file=sys.stderr)
                time.sleep(0.15)
    if errors:
        # 한 조합이라도 실패하면 배포 데이터 전체 갱신 중단: 불완전 가격을 시장 대표값으로 보여주지 않음
        print(f'{len(errors)}개 구간 실패. 이전 공개 데이터를 유지합니다.',file=sys.stderr)
        return 1
    # 최신 수집 대상 일자의 기존 기록만 교체. 오래된 데이터는 유지.
    target_dates = {d.isoformat() for d in targets}
    old = [x for x in existing.get('records',[]) if x.get('date') not in target_dates]
    cutoff = (today-dt.timedelta(days=args.history_days-1)).isoformat()
    result = [x for x in (old+changed) if x.get('date','') >= cutoff]
    # 최대 30일 스냅샷 유지
    result.sort(key=lambda x:(x['date'],x['market'],x['product'],x['variety'],x['standard']))
    payload = {
        'status': 'connected',
        'source': '농림축산식품 공공데이터포털 / 전국 공영도매시장 실시간 경락정보',
        'source_url': 'https://data.mafra.go.kr/opendata/data/indexOpenDataDetail.do?data_id=20240625000000002460',
        'method': '시장·품목·세부품종·동일 포장규격별 실거래 경락가격(원/kg)의 중앙값; 단위 식별 불가능한 거래 제외',
        'updated_at': dt.datetime.now(TZ).isoformat(timespec='seconds'),
        'markets': MARKETS,
        'products': [name for name,_ in WATCH],
        'collection_version': COLLECTION_VERSION,
        'history_days': args.history_days,
        'checked_dates': sorted({d for d in checked_dates if d >= cutoff} |
                                {d.isoformat() for d in targets}),
        'records': result,
    }
    save(payload)
    print(f'저장: {len(result):,}개 일별 그룹 / 신규 {len(changed):,}개, {len(targets)}일 수집')
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--days', type=int, default=2, help='과거 N일(오늘 포함)을 갱신. 첫 실행 시 --days 7 권장')
    p.add_argument('--history-days', type=int, default=30, help='보관·자동 백필할 전체 기간')
    p.add_argument('--backfill-batch', type=int, default=4, help='실행마다 추가로 채울 과거 누락 일수')
    p.add_argument('--max-pages', type=int, default=100, help='시장/부류/일자 최대 1000건 페이지 개수')
    a = p.parse_args()
    if not 1 <= a.days <= 60:
        p.error('--days 범위는 1~60')
    if not a.days <= a.history_days <= 365:
        p.error('--history-days는 --days 이상 365 이하')
    if not 0 <= a.backfill_batch <= 31:
        p.error('--backfill-batch 범위는 0~31')
    sys.exit(run(a))
