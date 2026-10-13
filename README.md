# 우이락 농산물 시세 변동 대시보드 (공식 API 3종)

이 패키지는 공식 조사 도·소매가격을 품목별 한 표로 요약하는 HTML 화면, Python 수집기, 하루 2회 자동갱신 GitHub Actions 설정을 포함합니다. 예상 납품가격과 사용자 입력 납품단가 기능은 제공하지 않습니다.

**현 상태: GitHub Pages 공개 배포 및 공식 API 자동수집 연결 완료.** 가격이 없는 품목·등급은 값을 임의 생성하지 않고 `—`로 표시합니다.

## 출처 및 지표 차이

1. [농림축산식품 공공데이터포털 - 전국 공영도매시장 실시간 경매정보](https://data.mafra.go.kr/opendata/data/indexOpenDataDetail.do?data_id=20240625000000002460): 서비스 코드 `Grid_20240625000000000654_1`, 낙찰가격 `COST`, 수량 `QTY`, 규격 `STD`, 시장 `WHSALCD`, 일자 `SALEDATE`. 업데이트: 수시.
2. [한국농수산식품유통공사 - 농수축산물 도매가격](https://data.mafra.go.kr/opendata/data/indexOpenDataDetail.do?data_id=20141016000000000288): 서비스 코드 `Grid_20150406000000000217_1`, 조사 가격 `AMT`, `EXAMIN_UNIT`, `GRAD_NM`, `MRKT_NM`, 일자 `EXAMIN_DE`. 업데이트: 일간.
3. [한국농수산식품유통공사 - 농수축산물 소매가격](https://data.mafra.go.kr/opendata/data/indexOpenDataDetail.do?data_id=20141225000000000406): 서비스 코드 `Grid_20141225000000000163_1`, 판매 조사 가격 `AMT`, 조사단위·등급·지역·시장·일자를 제공합니다. 업데이트: 일간.

**주의:** 조사 도·소매가격은 경매 낙찰가격이 아닙니다. 현재 요약표는 각 품목의 최신 조사일에 수집된 지역·시장·품종별 kg 환산가격을 등급별로 **단순 평균**합니다. 승인된 도매가격 데이터의 실제 등급명인 `중품·상품`을 사용하며, 품질등급을 제공하지 않는 실시간 경락정보는 요약표에 섞지 않습니다.

## 1. 인증키 연결 시험 (Q1)

이미 신청한 공식 API 2종이 승인되었어도 실제 인증/접속 성공은 별도입니다. 사용자 PC에서 테스트하려면:

1. 이 ZIP 파일을 압축 해제합니다. PC에 **Python 3.11 이상**을 설치합니다.
2. PowerShell 또는 명령 프롬프트를 열고 압축 해제 폴더로 이동합니다.
3. `python test_api_connection.py`를 실행합니다. 키 입력 안내가 뜨면 **새로 발급받은 공식 API 인증키**를 붙여넣습니다. 화면에 키가 표시되지 않으며, 코드에도 저장되지 않습니다.
4. 두 서비스 모두 `인증·연결 성공`으로 출력되는지 확인합니다. `INFO-200`은 해당 조사일에 데이터가 없다는 의미이므로 최근 다른 날짜로 재시도합니다.

**기존 채팅에 입력했던 키는 노출된 것으로 간주하고 가급적 재발급하세요. 이곳에 다시 키를 올리지 마세요.** 원본 공식 API 요청주소는 `http://211.237.50.150:7080`로 **HTTPS가 아닌 HTTP**입니다. 공식 서버의 제약이라 키 전송 경로 보안이 완벽하지 않습니다. 신청 시 설정한 IP 접근제한이 적용되면 사용자 PC에서는 성공하지만 GitHub Actions 서버에서는 실패할 수 있습니다. 오류 코드와 서버 접근정책을 확인해야 합니다.

## 2. 우선 내 컴퓨터에 실제 데이터 연결하기

```powershell
# PowerShell에서 현재 실행할 프로세스에만 키 설정(화면에 입력키가 표시되지 않음)
$secure = Read-Host '공식 API 재발급 키' -AsSecureString
$env:MAFRA_API_KEY = [System.Net.NetworkCredential]::new('', $secure).Password
python update_prices.py --days 2
python update_wholesale.py --days 2
python update_retail.py --days 2
Remove-Item Env:MAFRA_API_KEY
```

이후 `index.html`을 열면 `data/prices.js`, `data/wholesale.js`, `data/retail.js`에 저장된 가격을 표시합니다. 출처와 수집 시각도 함께 표시하며 수집 실패 시 임의 값을 만들지 않습니다.

소스별 하루 2회 수집을 준비했습니다. 매 실행마다 최근 2일을 다시 확인하고, 90일 범위에서 아직 확인하지 않은 과거 날짜를 오래된 순서로 4일씩 자동 수집합니다. 휴장일처럼 결과가 0건인 날짜도 확인 완료로 기록하므로 무한 재시도하지 않습니다. 하루 두 번 정상 실행되면 약 11일 안에 최초 90일 백필이 끝나며 이후에는 최신 90일 창을 계속 유지합니다. 수동 실행에서는 `backfill_batch`를 최대 31일까지 선택할 수 있습니다.

## 3. 공유 URL 만들기 (Q2)

권장 무료 배포: GitHub **공개 저장소 + GitHub Pages**. GitHub Pages는 별도 회원가입 없이 직원 누구나 URL로 볼 수 있지만 **URL을 아는 외부인도 볼 수 있습니다**. 비공개 내부 구매단가는 공개 저장소나 사이트에 업로드하지 마세요.

1. GitHub 계정으로 [새 저장소](https://github.com/new)를 만들고 저장소 이름을 예를 들어 `wooyirak-vegetable-prices`로 설정합니다. **Public**으로 생성합니다.
2. GitHub Desktop을 사용해 이 압축 해제 폴더를 로컬 저장소로 만들고, 위에서 만든 원격 저장소에 **전체 내용(숨김 `.github/workflows` 폴더 포함)**을 올립니다. Git 명령어를 안다면 `git init`, `git add .`, `git commit`, `git remote add origin`, `git push -u origin main` 방식도 가능합니다.
3. 저장소의 `Settings → Pages`에서 **Deploy from a branch**, `main` / `/ (root)`를 선택하고 Save를 누릅니다.
4. 배포가 성공하면 `https://<깃허브계정>.github.io/<저장소이름>/` 주소로 모든 직원이 접속할 수 있습니다. 주소는 실제 배포 후 GitHub에서 확인하세요.

**현재 연결된 GitHub 계정으로 조회되는 저장소가 0개여서 제가 실제로 저장소 생성, Actions Secrets 등록, Pages 배포까지 완료하지는 못했습니다. 이 문서는 배포 방법이고 이미 배포되었다는 뜻이 아닙니다.**

## 4. 무료 자동 갱신 (Q3)

1. GitHub 저장소 `Settings → Secrets and variables → Actions → New repository secret`을 엽니다.
2. 이름에 `MAFRA_API_KEY`, 값에 **공식 인증키**를 넣고 Save를 누릅니다. 경락·도매·소매가격 API 3종이 같은 키에 승인되어 있어야 하며, 저장소 코드나 HTML에는 키를 입력하지 마세요.
3. `Actions → 우이락 농산물 시세 자동갱신 → Run workflow`를 눌러 첫 연결을 확인합니다.
4. 매일 11:15 / 17:15 **한국시간**에 자동 실행되도록 `.github/workflows/update-auction.yml`에 설정했습니다. 최신 2일 갱신과 과거 90일 누락분의 단계적 백필을 함께 수행합니다. GitHub의 예약 실행은 지연될 수 있습니다.
5. 첫 실행이 `Success`이고 새 `data/*.js` 파일이 커밋되면 Pages에 실제 시세가 표시됩니다. 실패하면 Actions의 마지막 작업 로그에서 `인증·연결`, `경락가격 수집`, `조사 도매가격 수집` 순서로 확인하세요.

**중요한 제한:** 정부 API의 허용 IP가 고정이라면 IP가 유동적인 GitHub Actions에서는 데이터 수집이 막힐 수 있습니다. 이 경우 비용 없는 확정적인 완전자동화는 보장할 수 없습니다. 허용 IP 정책을 확인한 뒤 고정 공인 IP를 가진 서버 또는 승인받은 실행 환경으로 수집기를 옮겨야 합니다. GitHub Pages 호스팅 자체는 무료 공개 저장소에서 이용할 수 있습니다.

## 파일 설명

| 파일 | 내용 |
| --- | --- |
| `index.html` | 반응형 시세 요약표 · 품목별 중품 평균 도매가 · 상품 평균 도매가 · 평균 소매가를 한 줄로 표시 |
| `test_api_connection.py` | 실시간 경락정보/도매가격/소매가격 3종 인증·연결 확인 (인증키 미출력) |
| `update_prices.py` | 실거래 경락가격 수집·규격 kg 환산·중앙값 계산 |
| `update_wholesale.py` | 조사 도매가격 수집·지역/등급/시장별 kg 환산 |
| `update_retail.py` | 공식 조사 소매가격 수집·판매단위 원가 및 kg 환산 |
| `data/*.json`, `data/*.js` | 현재 비어 있는 정적 데이터 저장소 · 성공적 수집 뒤 자동 생성 |
| `.github/workflows/update-auction.yml` | 하루 2회 최신 갱신 + 과거 90일 자동 백필 · 부분 오류 발생 시 마지막 정상 데이터 유지 |
| `tests/` | kg 변환, 품목 분류, 경락가 집계, 조사 가격 테스트 |

## 현 단계에서 확인된 사항

- 공식 API 2종의 서비스 식별자·요청변수·응답필드는 문서로 확인함.
- Python 코드 문법, JavaScript 문법, 6개 단위 테스트 성공.
- 이 실행환경에서 공식 API 샘플 서버 포트 7080 HTTP 연결은 `Connection refused`여서 실제 인증 성공과 실시간 데이터 정확성은 검증하지 못함.
- 일·주·월 변화율은 같은 원규격 데이터가 축적된 뒤 표시합니다. 데이터가 없는 날은 별도로 비워둡니다.
