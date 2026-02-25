async function fetchJson(path){
  const r = await fetch(path, { cache: 'no-store' });
  if(!r.ok) throw new Error(`HTTP ${r.status} ${path}`);
  const ct = (r.headers.get('content-type')||'').toLowerCase();
  const text = await r.text();
  if(!text.trim()) throw new Error(`EMPTY ${path}`);
  if(!ct.includes('json')){
    // GitHub Pages sometimes serves application/octet-stream for json; tolerate if it parses
    try { return JSON.parse(text); }
    catch { throw new Error(`NOT_JSON ${path} ct=${ct} head=${text.slice(0,120)}`); }
  }
  return JSON.parse(text);
}

function pill(el, type){
  el.classList.remove('ok','warn','bad');
  if(type) el.classList.add(type);
}

function esc(s){
  return (s??'').toString().replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
}

function renderLog(rec){
  const changes = rec.changes || [];
  const errors = rec.errors || [];

  const rowsChanges = changes.map(c => `
    <tr>
      <td>${esc(c.code)}</td>
      <td>${esc(c.title)}</td>
      <td>${esc(c.noticeNo||'')}</td>
      <td>${esc(c.announceDate||'')}</td>
      <td>${esc(c.effectiveDate||'')}</td>
      <td>${esc(c.reason||'')}</td>
      <td>${(c.refs||[]).map(x=> x.url ? `<a href="${esc(x.url)}" target="_blank" rel="noreferrer">원문</a>`:'' ).join(' ')}</td>
    </tr>
  `).join('');

  const rowsErrors = errors.map(e => `
    <tr>
      <td>${esc(e.code||'')}</td>
      <td>${esc(e.title||'')}</td>
      <td>${esc(e.where||'')}</td>
      <td>${esc(e.kind||'')}</td>
      <td>${esc(e.status||'')}</td>
      <td>${esc(e.contentType||'')}</td>
      <td title="${esc(e.head||'')}">${esc((e.head||'').slice(0,60))}${(e.head||'').length>60?'…':''}</td>
    </tr>
  `).join('');

  return `
    <div style="margin-top:10px">
      <div class="row">
        <span class="pill">${esc(rec.date)}</span>
        <span class="pill">${esc(rec.result)}</span>
        <span class="pill">changes ${changes.length}</span>
        <span class="pill">errors ${errors.length}</span>
        <span class="pill">mock ${(rec.meta&&rec.meta.mock)?'true':'false'}</span>
      </div>
      <div class="small" style="margin-top:6px">${esc(rec.summary||'')}</div>

      <details style="margin-top:10px" ${changes.length? 'open':''}>
        <summary>변경 감지 상세</summary>
        ${changes.length ? `
          <table>
            <thead><tr>
              <th>코드</th><th>제명</th><th>발령번호</th><th>발령일</th><th>시행일</th><th>사유</th><th>원문</th>
            </tr></thead>
            <tbody>${rowsChanges}</tbody>
          </table>
        ` : '<div class="small" style="margin-top:6px">변경 없음</div>'}
      </details>

      <details style="margin-top:10px" ${errors.length? 'open':''}>
        <summary>오류/진단</summary>
        ${errors.length ? `
          <table>
            <thead><tr>
              <th>코드</th><th>제명</th><th>구간</th><th>종류</th><th>HTTP</th><th>Content-Type</th><th>HEAD</th>
            </tr></thead>
            <tbody>${rowsErrors}</tbody>
          </table>
        ` : '<div class="small" style="margin-top:6px">오류 없음</div>'}
      </details>
    </div>
  `;
}

function renderList(items){
  if(!items || !items.length) return '<div class="small">항목 없음</div>';
  return `
    <table>
      <thead><tr><th>코드</th><th>제명</th><th>검색어</th></tr></thead>
      <tbody>
        ${items.map(it=>`<tr><td>${esc(it.code)}</td><td>${esc(it.title)}</td><td class="mono">${esc(it.query||'')}</td></tr>`).join('')}
      </tbody>
    </table>
  `;
}

(async () => {
  const runPill = document.getElementById('runPill');
  const modePill = document.getElementById('modePill');
  const changesPill = document.getElementById('changesPill');
  const errorsPill = document.getElementById('errorsPill');
  const statusText = document.getElementById('statusText');

  try{
    const data = await fetchJson('../data_test.json');
    const rec = (data.records && data.records[0]) ? data.records[0] : null;

    if(!rec){
      pill(runPill,'warn');
      runPill.textContent = '데이터 없음';
      statusText.textContent = 'data_test.json에 records가 없습니다. Actions(Test Check)를 1회 실행하세요.';
    }else{
      runPill.textContent = `최근 실행: ${rec.date}`;
      const mock = rec.meta && rec.meta.mock;
      modePill.textContent = mock ? 'MODE: MOCK' : 'MODE: LIVE';
      pill(modePill, mock ? 'warn' : 'ok');

      const c = (rec.changes||[]).length;
      const e = (rec.errors||[]).length;

      changesPill.textContent = `CHANGES: ${c}`;
      errorsPill.textContent = `ERRORS: ${e}`;

      pill(changesPill, c ? 'warn' : 'ok');
      pill(errorsPill, e ? 'bad' : 'ok');

      statusText.textContent = rec.summary || '';

      document.getElementById('log').innerHTML = renderLog(rec);
    }

    // Lists
    const nfpc = await fetchJson('../standards_nfpc_test.json');
    const nftc = await fetchJson('../standards_nftc_test.json');
    document.getElementById('nfpcList').innerHTML = renderList(nfpc.items);
    document.getElementById('nftcList').innerHTML = renderList(nftc.items);

  }catch(err){
    pill(runPill,'bad');
    runPill.textContent = '로딩 실패';
    statusText.textContent = String(err);
    console.error(err);
  }
})();
