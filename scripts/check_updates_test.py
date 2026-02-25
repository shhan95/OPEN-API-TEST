import os
import json
import hashlib
import urllib.parse
import time
import random
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Tuple, Optional, List

import requests

# ==========================
# Runtime config (TEST)
# ==========================
KST = timezone(timedelta(hours=9))
NOW = datetime.now(KST)
TODAY = NOW.strftime("%Y-%m-%d")

OUTPUT_DATA = os.getenv("OUTPUT_DATA", "data_test.json")
OUTPUT_SNAPSHOT = os.getenv("OUTPUT_SNAPSHOT", "snapshot_test.json")

# Default to test standards files to avoid touching production lists
STANDARDS_NFPC = os.getenv("STANDARDS_NFPC", "standards_nfpc_test.json")
STANDARDS_NFTC = os.getenv("STANDARDS_NFTC", "standards_nftc_test.json")

LAWGO_OC = (os.getenv("LAWGO_OC", "") or "").strip()
MOCK = (os.getenv("LAWGO_MOCK", "") or "").strip() == "1"

LAW_SEARCH = "https://www.law.go.kr/DRF/lawSearch.do"
LAW_SERVICE = "https://www.law.go.kr/DRF/lawService.do"

TIMEOUT = 30
MAX_RETRIES = 4

# ==========================
# Utilities
# ==========================

def load(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save(path: str, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def ymd_int_to_dot(v: Any) -> Any:
    if v is None:
        return None
    s = str(v).strip()
    if not s.isdigit() or len(s) != 8:
        return s
    return f"{s[0:4]}.{s[4:6]}.{s[6:8]}"


def sha256_text(t: str) -> str:
    return hashlib.sha256((t or "").encode("utf-8")).hexdigest()


def backoff(attempt: int) -> None:
    base = 0.6 * (2 ** (attempt - 1))
    time.sleep(base + random.random() * 0.4)


# ==========================
# HTTP / API wrappers
# ==========================

def _safe_json_response(r: requests.Response, url: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    ct = (r.headers.get("Content-Type") or "").lower()
    text = r.text or ""
    head = text[:200].replace("\n", " ")

    if r.status_code != 200:
        return None, {
            "kind": "http_error",
            "status": r.status_code,
            "contentType": ct,
            "head": head,
            "url": url,
        }

    if not text.strip():
        return None, {
            "kind": "empty_body",
            "status": r.status_code,
            "contentType": ct,
            "head": head,
            "url": url,
        }

    if "json" not in ct:
        return None, {
            "kind": "not_json",
            "status": r.status_code,
            "contentType": ct,
            "head": head,
            "url": url,
        }

    try:
        return r.json(), None
    except Exception as e:
        return None, {
            "kind": "json_parse_fail",
            "status": r.status_code,
            "contentType": ct,
            "head": head,
            "url": url,
            "error": str(e),
        }


def _request_json(url: str, params: Dict[str, str]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    # MOCK mode: never call external API
    if MOCK:
        return None, {"kind": "mock_enabled", "status": 200, "contentType": "mock", "head": "mock", "url": url}

    last_err = None
    with requests.Session() as s:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                r = s.get(url, params=params, timeout=TIMEOUT, allow_redirects=True)
                js, err = _safe_json_response(r, url)

                if err is None:
                    return js, None

                last_err = err
                # retry-worthy
                if err.get("status") in (429, 500, 502, 503, 504) or err.get("kind") in ("empty_body", "not_json", "json_parse_fail"):
                    backoff(attempt)
                    continue

                return None, err

            except requests.RequestException as e:
                last_err = {"kind": "request_exception", "url": url, "error": str(e)}
                backoff(attempt)
                continue

    return None, last_err


def lawgo_search(query: str, knd: int = 3, display: int = 20) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    if MOCK:
        # Minimal mock search result
        return {
            "admrul": [
                {
                    "행정규칙일련번호": "MOCK-001",
                    "소관부처명": "소방청",
                    "행정규칙종류": "고시",
                    "발령일자": "20260225",
                    "행정규칙상세링크": "https://www.law.go.kr/"
                }
            ]
        }, None

    params = {
        "OC": LAWGO_OC,
        "target": "admrul",
        "type": "JSON",
        "query": query,
        "knd": str(knd),
        "display": str(display),
        "sort": "ddes",
    }
    return _request_json(LAW_SEARCH, params)


def lawgo_detail(admrul_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    if MOCK:
        return {
            "행정규칙": {
                "행정규칙명": "MOCK NFPC/NFTC",
                "발령번호": "소방청고시 제2026-1호",
                "발령일자": "20260225",
                "시행일자": "20260301",
                "제개정구분명": "일부개정",
                "소관부처명": "소방청",
                "조문내용": "제1조(목적) ... (mock)",
                "부칙내용": "부칙 ... (mock)",
                "별표내용": ""
            }
        }, None

    params = {
        "OC": LAWGO_OC,
        "target": "admrul",
        "type": "JSON",
        "ID": str(admrul_id),
    }
    return _request_json(LAW_SERVICE, params)


# ==========================
# Parsing helpers
# ==========================

def _extract_items(search_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    for k in ("admrul", "Admrul", "admruls"):
        if k in search_json:
            v = search_json.get(k)
            return v if isinstance(v, list) else []
    if "행정규칙" in search_json and isinstance(search_json["행정규칙"], list):
        return search_json["행정규칙"]
    return []


def _extract_payload(detail_json: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(detail_json.get("행정규칙"), dict):
        return detail_json["행정규칙"]
    if isinstance(detail_json.get("admrul"), dict):
        return detail_json["admrul"]
    return detail_json


def pick_best_item(items: List[Dict[str, Any]], org_name: str = "소방청") -> Optional[Dict[str, Any]]:
    best = None
    best_score = -1
    for it in items or []:
        org = (it.get("소관부처명") or it.get("소관부처") or "")
        kind = (it.get("행정규칙종류") or "")
        score = 0
        if org_name and org_name in org:
            score += 100
        if "고시" in kind:
            score += 20
        if it.get("발령일자"):
            score += 1
        if score > best_score:
            best, best_score = it, score
    return best


# ==========================
# Core build
# ==========================

def build_snapshot_entry(std_item: Dict[str, Any], tab_key: str, prev_entry: Dict[str, Any]) -> Dict[str, Any]:
    query = std_item.get("query") or std_item.get("title") or std_item.get("code")
    knd = int(std_item.get("knd", 3))
    org_name = std_item.get("orgName", "소방청")

    # 1) search
    search_json, err = lawgo_search(query, knd=knd)
    if err:
        return {
            **(prev_entry or {}),
            "code": std_item.get("code"),
            "title": std_item.get("title"),
            "checkedAt": TODAY,
            "error": {"where": "search", **err, "query": query},
        }

    items = _extract_items(search_json or {})
    best = pick_best_item(items, org_name=org_name)
    if not best:
        return {
            **(prev_entry or {}),
            "code": std_item.get("code"),
            "title": std_item.get("title"),
            "checkedAt": TODAY,
            "error": {"where": "search", "kind": "no_results", "query": query},
        }

    adm_id = best.get("행정규칙일련번호") or best.get("일련번호") or best.get("id") or best.get("ID")
    if not adm_id:
        return {
            **(prev_entry or {}),
            "code": std_item.get("code"),
            "title": std_item.get("title"),
            "checkedAt": TODAY,
            "error": {"where": "search", "kind": "id_missing", "query": query},
        }

    # 2) detail
    det, derr = lawgo_detail(str(adm_id))
    if derr:
        return {
            **(prev_entry or {}),
            "code": std_item.get("code"),
            "title": std_item.get("title"),
            "checkedAt": TODAY,
            "lawgoId": str(adm_id),
            "error": {"where": "detail", **derr},
        }

    payload = _extract_payload(det or {})

    notice_no = payload.get("발령번호")
    announce = ymd_int_to_dot(payload.get("발령일자"))
    effective = ymd_int_to_dot(payload.get("시행일자"))
    rev = payload.get("제개정구분명")
    org = payload.get("소관부처명")
    name = payload.get("행정규칙명") or std_item.get("title")

    body_hash = sha256_text(payload.get("조문내용") or "")
    add_hash = sha256_text((payload.get("부칙내용") or "") + (payload.get("별표내용") or ""))

    html_url = best.get("행정규칙상세링크") or best.get("상세링크") or ""
    if not html_url:
        # DRF HTML (clickable) - safe for users
        html_url = f"{LAW_SERVICE}?OC={urllib.parse.quote(LAWGO_OC)}&target=admrul&ID={adm_id}&type=HTML"

    return {
        "code": std_item.get("code"),
        "title": std_item.get("title"),
        "checkedAt": TODAY,
        "lawgoId": str(adm_id),
        "noticeNo": notice_no,
        "announceDate": announce,
        "effectiveDate": effective,
        "revisionType": rev,
        "orgName": org,
        "ruleName": name,
        "htmlUrl": html_url,
        "bodyHash": body_hash,
        "suppHash": add_hash,
    }


def detect_change(prev: Dict[str, Any], cur: Dict[str, Any]) -> Tuple[bool, List[str]]:
    if not prev:
        return False, []
    if prev.get("error") or cur.get("error"):
        if (prev.get("error") or "") != (cur.get("error") or ""):
            return True, ["error"]
        return False, []

    keys = ["noticeNo", "announceDate", "effectiveDate", "revisionType", "bodyHash", "suppHash"]
    diffs = [k for k in keys if (prev.get(k) or "") != (cur.get(k) or "")]
    return (len(diffs) > 0), diffs


# ==========================
# Main
# ==========================

def main() -> None:
    if not MOCK and not LAWGO_OC:
        # No OC and not mock -> cannot proceed, but write an error record and exit 0
        data = load(OUTPUT_DATA, {"lastRun": None, "records": []})
        rec = {
            "id": TODAY,
            "date": TODAY,
            "scope": "NFPC / NFTC TEST",
            "result": "오류",
            "summary": "LAWGO_OC 미설정 (테스트는 LAWGO_MOCK=1 또는 LAWGO_OC 필요)",
            "changes": [],
            "errors": [{"kind": "missing_secret", "where": "runtime", "message": "LAWGO_OC empty"}],
            "refs": [],
        }
        data["lastRun"] = TODAY
        data["records"] = [r for r in data.get("records", []) if r.get("date") != TODAY]
        data["records"].insert(0, rec)
        save(OUTPUT_DATA, data)
        print("Done (missing LAWGO_OC).")
        return

    nfpc = load(STANDARDS_NFPC, {"items": []})
    nftc = load(STANDARDS_NFTC, {"items": []})

    snap = load(OUTPUT_SNAPSHOT, {"nfpc": {}, "nftc": {}})
    data = load(OUTPUT_DATA, {"lastRun": None, "records": []})

    changes: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for tab_key, std in (("nfpc", nfpc), ("nftc", nftc)):
        for item in std.get("items", []):
            code = item.get("code")
            if not code:
                continue

            prev = (snap.get(tab_key, {}) or {}).get(code, {})
            cur = build_snapshot_entry(item, tab_key, prev)
            snap.setdefault(tab_key, {})[code] = cur

            if cur.get("error"):
                e = cur["error"]
                errors.append({
                    "code": code,
                    "title": item.get("title"),
                    "where": e.get("where"),
                    "kind": e.get("kind"),
                    "status": e.get("status"),
                    "contentType": e.get("contentType"),
                    "head": e.get("head"),
                    "url": e.get("url"),
                    "query": e.get("query"),
                })
                continue

            changed, diff_keys = detect_change(prev, cur)
            if changed:
                changes.append({
                    "code": code,
                    "title": item.get("title"),
                    "noticeNo": cur.get("noticeNo"),
                    "announceDate": cur.get("announceDate"),
                    "effectiveDate": cur.get("effectiveDate"),
                    "reason": f"자동 감지: 메타/본문 해시 변경({', '.join(diff_keys)})",
                    "diff": [],
                    "supplementary": "부칙/경과규정은 원문 확인",
                    "impact": [
                        "설계: 시행일 기준 적용(도서·시방서에 적용기준 명시)",
                        "시공: 자재/설비 선정 시 개정기준 충족 여부 확인",
                        "유지관리: 점검대장에 적용기준/이력 기록",
                    ],
                    "refs": [{"label": "법제처(원문/DRF)", "url": cur.get("htmlUrl", "")}],
                })

    data["lastRun"] = TODAY

    if changes:
        result = "변경 있음"
        summary = f"자동 감지: {len(changes)}건 변경(원문 확인 권장)"
    else:
        result = "변경 없음"
        summary = "전일 대비 변경 감지 없음"

    rec = {
        "id": TODAY,
        "date": TODAY,
        "scope": "NFPC / NFTC TEST (법제처 OPEN API: 행정규칙)",
        "result": result,
        "summary": summary,
        "changes": changes,
        "errors": errors,
        "refs": [],
        "meta": {
            "mock": MOCK,
            "standards_nfpc": STANDARDS_NFPC,
            "standards_nftc": STANDARDS_NFTC,
        }
    }

    data["records"] = [r for r in data.get("records", []) if r.get("date") != TODAY]
    data["records"].insert(0, rec)

    save(OUTPUT_SNAPSHOT, snap)
    save(OUTPUT_DATA, data)

    print(f"Done. date={TODAY} changes={len(changes)} errors={len(errors)} mock={MOCK}")


if __name__ == "__main__":
    main()
