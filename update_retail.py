#!/usr/bin/env python3
"""aT 농수축산물 소매가격 수집기. 경락가·도매가와 분리 저장합니다."""
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

from update_prices import ROOT, TZ, classify, select_target_dates, unit_kg, COLLECTION_VERSION

GRID = 'Grid_20141225000000000163_1'
BASE = 'http://211.237.50.150:7080/openapi/{key}/json/' + GRID + '/{start}/{end}'
TARGET = ROOT / 'data/retail.json'
JS = ROOT / 'data/retail.js'
SOURCE_URL = 'https://data.mafra.go.kr/opendata/data/indexOpenDataDetail.do?data_id=20141225000000000406'
CATEGORY_CODES = ('200', '300', '400')


def get_rows(key, date, category, max_pages=80):
    collected = []
    start = 1
    for _ in range(max_pages):
        params = urllib.parse.urlencode({'EXAMIN_DE': date, 'FRMPRD_CATGORY_CD': category})
        url = BASE.format(key=urllib.parse.quote(key, safe=''), start=start, end=start + 999) + '?' + params
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'Wooyirak-MarketMonitor/1.2'})
            with urllib.request.urlopen(request, timeout=35) as response:
                body = json.load(response)
        except (ValueError, urllib.error.URLError, TimeoutError) as ex:
            raise RuntimeError('공식 소매가격 API 요청 실패 (통신/인증/서비스 승인 확인)') from ex
        wrapper = body.get(GRID)
        if not isinstance(wrapper, dict):
            raise RuntimeError('소매가격 API 응답 스키마 오류 (서비스 승인 또는 인증 확인)')
        info = wrapper.get('result', {}) or {}
        code = str(info.get('code', ''))
        if code == 'INFO-200':
            return []
        if code != 'INFO-000':
            raise RuntimeError(f'소매가격 API 결과 코드 {code}: {info.get("message", "정상 아님")}')
        rows = wrapper.get('row', []) or []
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            raise RuntimeError('소매가격 API row 배열 오류')
        collected.extend(rows)
        total = int(wrapper.get('totalCnt', 0) or 0)
        if len(collected) >= total:
            return collected
        if not rows:
            raise RuntimeError('소매가격 일부 페이지만 반환되어 저장하지 않음')
        start += 1000
        time.sleep(.12)
    raise RuntimeError('소매가격 데이터 페이지 상한 도달, 불완전 데이터 저장 중단')


def transform(rows):
    items = {}
    for row in rows:
        if str(row.get('FRMPRD_CATGORY_CD', '')) not in CATEGORY_CODES:
            continue
        product = classify(row.get('PRDLST_NM', ''), row.get('SPCIES_NM', ''))
        if not product:
            continue
        unit = str(row.get('EXAMIN_UNIT') or '').strip()
        kg = unit_kg(unit)
        if not kg:
            continue
        try:
            amount = float(str(row.get('AMT', '')).replace(',', ''))
        except (ValueError, TypeError):
            continue
        date = str(row.get('EXAMIN_DE') or '')
        if not re.fullmatch(r'\d{8}', date) or not amount > 0:
            continue
        record = {
            'date': f'{date[:4]}-{date[4:6]}-{date[6:]}',
            'product': product,
            'variety': str(row.get('SPCIES_NM') or '미상').strip(),
            'grade': str(row.get('GRAD_NM') or '미표시').strip(),
            'region': str(row.get('AREA_NM') or '미상').strip(),
            'market': str(row.get('MRKT_NM') or '미상').strip(),
            'standard': unit,
            'kg_per_unit': kg,
            'price_unit': round(amount),
            'price_kg': round(amount / kg),
        }
        key = (record['date'], record['product'], record['variety'], record['grade'],
               record['region'], record['market'], unit)
        items[key] = record
    return sorted(items.values(), key=lambda r: (
        r['date'], r['product'], r['region'], r['market'], r['variety'], r['grade']))


def run(args):
    key = os.getenv('MAFRA_API_KEY', '').strip()
    if not key:
        print('MAFRA_API_KEY 미설정: 소매가격 수집 불가', file=sys.stderr)
        return 2
    try:
        previous = json.loads(TARGET.read_text(encoding='utf-8'))
        old = previous.get('records', []) if isinstance(previous.get('records'), list) else []
        checked_dates = previous.get('checked_dates', []) if isinstance(previous.get('checked_dates'), list) else []
    except (FileNotFoundError, ValueError):
        old, checked_dates = [], []
    if 'previous' in locals() and previous.get('collection_version') != COLLECTION_VERSION:
        checked_dates = []
    today = dt.datetime.now(TZ).date()
    dates = select_target_dates(old, checked_dates, today, args.days, args.history_days, args.backfill_batch)
    changed, errors = [], []
    for day in dates:
        date = day.strftime('%Y%m%d')
        for category in CATEGORY_CODES:
            try:
                fetched = get_rows(key, date, category, args.max_pages)
                found = transform(fetched)
                changed.extend(found)
                print(f'{date} 부류 {category} 소매가격 {len(fetched)}건 중 표시 가능 {len(found)}건')
            except RuntimeError as ex:
                errors.append(f'{date}/{category}: {ex}')
                print(errors[-1], file=sys.stderr)
    if errors:
        print('소매가격 소스의 부분 오류: 이전 데이터를 유지합니다.', file=sys.stderr)
        return 1
    searched = {day.isoformat() for day in dates}
    cutoff = (today - dt.timedelta(days=args.history_days - 1)).isoformat()
    records = [r for r in old if r.get('date') not in searched and r.get('date', '') >= cutoff] + changed
    records.sort(key=lambda r: (r['date'], r['product'], r['region'], r['market'], r['variety'], r['grade']))
    payload = {
        'status': 'connected',
        'updated_at': dt.datetime.now(TZ).isoformat(timespec='seconds'),
        'source': '한국농수산식품유통공사 / 농수축산물 소매가격',
        'source_url': SOURCE_URL,
        'method': '지역·시장·품목·품종·등급별 조사 소매가격을 조사단위 kg로 환산',
        'history_days': args.history_days,
        'collection_version': COLLECTION_VERSION,
        'checked_dates': sorted({d for d in checked_dates if d >= cutoff} | searched),
        'records': records,
    }
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    temp = TARGET.with_suffix('.json.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(TARGET)
    JS.write_text('window.__RETAIL_DATA__ = ' + json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + ';\n', encoding='utf-8')
    print(f'소매가격 저장: {len(records)}건')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=2)
    parser.add_argument('--history-days', type=int, default=30)
    parser.add_argument('--backfill-batch', type=int, default=4)
    parser.add_argument('--max-pages', type=int, default=80)
    options = parser.parse_args()
    if not 1 <= options.days <= 60:
        parser.error('--days 1~60')
    if not options.days <= options.history_days <= 365:
        parser.error('--history-days는 --days 이상 365 이하')
    if not 0 <= options.backfill_batch <= 31:
        parser.error('--backfill-batch 0~31')
    raise SystemExit(run(options))
