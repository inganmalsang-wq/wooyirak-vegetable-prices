#!/usr/bin/env python3
"""두 승인 API의 인증/네트워크/필수 파라미터 연결을 확인합니다. 키 또는 인증 URL을 출력하지 않습니다."""
import datetime as dt
import json
import getpass
import os
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ENDPOINTS=[
  ('실시간 경락정보','Grid_20240625000000000654_1',lambda d:{'SALEDATE':d,'WHSALCD':'110001'}),
  ('농수축산물 도매가격','Grid_20150406000000000217_1',lambda d:{'EXAMIN_DE':d,'FRMPRD_CATGORY_CD':'200'}),
]


def probe(key, name,grid,params,date):
    url=f'http://211.237.50.150:7080/openapi/{urllib.parse.quote(key,safe="")}/json/{grid}/1/1?'+urllib.parse.urlencode(params(date))
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Wooyirak-ConnectionProbe/1.0'}),timeout=15) as r:
            b=json.load(r)
    except (urllib.error.URLError, TimeoutError,ValueError) as e:
        print(f'  {name}: 접속 실패 ({type(e).__name__}). 신청 IP/포트 7080 차단/HTTP 접속 여부 확인')
        return False
    w=b.get(grid,{})
    info=w.get('result',{}) or {}
    code=str(info.get('code',''))
    if code=='INFO-000':
        print(f'  {name}: 인증·연결 성공 (샘플 1건 요청, 반환 {len(w.get("row",[]) or [])}건)')
        return True
    if code=='INFO-200':
        print(f'  {name}: API 응답 도달, 조회일 데이터 없음 (다른 날짜로 재확인)')
        return None
    print(f'  {name}: API 응답 코드 {code or "알 수 없음"}. 서비스 승인/인증키/IP 확인')
    return False


def main():
    key=os.getenv('MAFRA_API_KEY','').strip()
    if not key:
        key=getpass.getpass('재발급 API 인증키 입력 (화면 표시되지 않음): ').strip()
    if not key:
        print('인증키가 비어 있어 테스트를 중단합니다.')
        return 2
    today=dt.datetime.now(ZoneInfo('Asia/Seoul')).date()
    # 휴장/미공개로 인해 오늘 응답이 비면 과거 평일도 검사
    ok=0
    for name,grid,params in ENDPOINTS:
        success=False
        for offset in range(1,15):
            day=(today-dt.timedelta(days=offset)).strftime('%Y%m%d')
            check=probe(key,name,grid,params,day)
            if check is True:
                success=True
                break
            if check is False:  # 인증/접속 실패를 날짜를 바꿔 반복하지 않음
                break
        if success:ok+=1
    print(f'공식 API 2종 중 인증·연결 확인: {ok}/2')
    return 0 if ok==2 else 1

if __name__=='__main__':
    raise SystemExit(main())
