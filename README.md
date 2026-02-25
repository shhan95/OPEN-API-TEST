# NFPC/NFTC 자동검토 – 테스트 페이지 패키지

이 패키지는 **기존(운영) Pages/데이터를 건드리지 않고**, 별도의 **테스트 페이지(/test)** 와 **테스트용 GitHub Actions 워크플로**로 NFPC/NFTC 자동검토 파이프라인이 정상 동작하는지 검증하기 위한 구성입니다.

## 구성 요약
- `test/` : 테스트 페이지(정적) — 기존 index.html을 변경하지 않음
- `scripts/check_updates_test.py` : 테스트용 체크 스크립트(견고한 에러 처리/재시도/모의(MOCK) 지원)
- `.github/workflows/daily_check_test.yml` : 테스트 워크플로(수동 실행 + 스케줄)
- 출력 파일(테스트용, 운영 파일과 분리)
  - `data_test.json`
  - `snapshot_test.json`

## 빠른 시작
1) 이 ZIP을 **기존 저장소 루트에 그대로 업로드/덮어쓰기**(운영 파일은 건드리지 않도록 테스트 전용 파일명만 사용)

2) GitHub → **Settings → Secrets and variables → Actions** 에 아래 Secret 추가
- `LAWGO_OC` : 법제처 OPEN API OC 값(이메일 ID)

3) 승인/권한이 아직 불확실하면, 먼저 **MOCK 모드로 테스트**
- Secret 추가: `LAWGO_MOCK` = `1`

4) Actions → **NFPC NFTC Test Check** → **Run workflow** 실행

5) Pages에서 테스트 페이지 확인
- `https://<username>.github.io/<repo>/test/`

## MOCK 모드
- `LAWGO_MOCK=1`이면 외부 API 호출 없이도 `data_test.json/snapshot_test.json`이 생성되어 페이지가 정상 표시되는지 확인할 수 있습니다.
- 승인이 완료되면 `LAWGO_MOCK` Secret을 삭제하거나 값을 `0`으로 변경하세요.

## 운영 파일과 분리되는 지점
- 테스트는 `scripts/check_updates_test.py`만 사용
- 테스트 출력은 `data_test.json`, `snapshot_test.json`
- 페이지는 `/test/` 하위만 사용

