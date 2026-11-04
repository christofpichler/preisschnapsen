/* Admin UI */
(function () {
  const { esc, ic, heartsHtml, cellHtml, money, live, uuid } = SN;
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  const TABS = [['players', 'Spieler'], ['round', 'Runde'], ['table', 'Tabelle'], ['rank', 'Rangliste'], ['cash', 'Kassa'], ['dash', 'Dashboard'], ['tourn', 'Turnier']];
  let S = null, D = null, T = null, pm = {};
  let tab = 'players';
  try { tab = localStorage.getItem('sn_tab') || 'players'; } catch (e) { }
  if (!TABS.some(x => x[0] === tab)) tab = 'players';
  const ui = { filter: 'all', search: '', roundSel: null, mode: 'digital', manual: { assign: {}, sel: null }, order: {}, addNg: true, showAudit: false, showWarn: false };
  let pendingRender = false;
  let modal = null; // {render, handlers}

  /* ---------------- API ---------------- */
  async function api(method, path, body) {
    const id = uuid();
    let lastErr = null;
    for (let attempt = 0; attempt < 4; attempt++) {
      try {
        const r = await fetch('/admin/api/' + path, {
          method, credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json', 'X-Schnapsen': '1', 'X-Request-Id': id },
          body: JSON.stringify(body || {})
        });
        if (r.status === 401) { location.reload(); return null; }
        let j = null;
        try { j = await r.json(); } catch (e) { j = { ok: false, error: 'Ungültige Serverantwort (' + r.status + ')' }; }
        if (j && j.state) { setState(j.state); }
        if (!r.ok) { const er = new Error(j.error || ('Fehler ' + r.status)); er.code = j.code; er.status = r.status; throw er; }
        return j;
      } catch (e) {
        if (e.status) throw e;
        lastErr = e; await sleep(500 * (attempt + 1));
      }
    }
    throw new Error('Keine Verbindung zum Server. Bitte erneut versuchen.');
  }
  async function act(fn, okMsg) {
    try { const r = await fn(); if (okMsg) toast(okMsg, 'ok'); if (r && r.warning) toast(r.warning, 'warn'); return r || true; }
    catch (e) { toast(e.message, 'err'); return null; }
  }
  function toast(msg, kind) {
    const el = document.createElement('div');
    el.className = kind || ''; el.textContent = msg;
    $('#toast').appendChild(el);
    setTimeout(() => el.remove(), kind === 'err' ? 6000 : 3500);
  }

  /* ---------------- State ---------------- */
  function setState(s) {
    S = s; T = s.tournament; D = s.derived || null;
    pm = {};
    if (D) D.players.forEach(p => pm[p.id] = p);
    render();
  }
  const name = id => (pm[id] ? pm[id].name : '?');
  const label = id => { const p = pm[id]; return p ? p.name + (p.nickname ? ' „' + p.nickname + '“' : '') : '?'; };
  function inPairing(pid) {
    const rs = D.rounds.concat(D.draft ? [D.draft] : []);
    return rs.some(r => r.pairings.some(x => x.a === pid || x.b === pid));
  }
  function statusText() {
    if (!D) return 'Kein Turnier';
    const cur = D.round_progress;
    switch (D.phase) {
      case 'signup': return 'Anmeldung';
      case 'ready': return 'Gestartet – Auslosung steht an';
      case 'drawing': return 'Runde ' + D.next_round + ': Auslosung (Entwurf)';
      case 'running': return 'Runde ' + cur.number + ' läuft – ' + cur.done + '/' + cur.total + ' Tische fertig';
      case 'closed': return 'Runde ' + cur.number + ' abgeschlossen';
      case 'finished': return 'Turnier beendet';
    }
    return '';
  }

  /* ---------------- Modal ---------------- */
  function showModal(render, handlers) {
    modal = { render, handlers: handlers || {} };
    paintModal();
  }
  function paintModal() {
    const m = $('#modal');
    if (!modal) { m.hidden = true; m.innerHTML = ''; return; }
    m.hidden = false;
    const keep = m.querySelector('.mbox');
    const st = keep ? keep.scrollTop : 0;
    const vals = {};
    Array.from(m.querySelectorAll('input[type=text]')).forEach(el => { if (el.id) vals[el.id] = el.value; });
    m.innerHTML = '<div class="mback" data-act="m-back"><div class="mbox" role="dialog">' + modal.render() + '</div></div>';
    const nb = m.querySelector('.mbox'); if (nb) nb.scrollTop = st;
    Object.keys(vals).forEach(id => { const el = m.querySelector('#' + id); if (el && el.dataset.dirty !== '0' && vals[id] !== undefined && keep) el.value = vals[id]; });
  }
  function closeModal() { modal = null; paintModal(); }
  function confirmBox(title, text, okLabel, danger) {
    return new Promise(res => {
      showModal(() => '<h2>' + esc(title) + '</h2><p>' + esc(text || '') + '</p><div class="btns"><button class="btn sec" data-act="m-no">Abbrechen</button><button class="btn ' + (danger ? 'red' : '') + '" data-act="m-yes">' + esc(okLabel || 'OK') + '</button></div>',
        { 'm-yes': () => { closeModal(); res(true); }, 'm-no': () => { closeModal(); res(false); }, 'm-back': (el, ev) => { if (ev.target === el) { closeModal(); res(false); } } });
    });
  }

  /* ---------------- Render ---------------- */
  function render() {
    if (!S) return;
    $('#a-name').textContent = T ? T.name : 'Preisschnapsen';
    $('#a-status').textContent = statusText();
    const u = $('#a-undo');
    u.disabled = !(S.undo && S.undo.available);
    u.title = S.undo && S.undo.available ? 'Rückgängig: ' + S.undo.label : '';
    renderTabs();
    const ae = document.activeElement;
    const typing = ae && $('#view').contains(ae) && /^(INPUT|TEXTAREA|SELECT)$/.test(ae.tagName) && ae.dataset.keep !== 'ok';
    if (!typing) { pendingRender = false; renderView(); } else pendingRender = true;
    if (modal && modal.render && !modal.static) {
      const mb = $('#modal');
      if (!(mb.contains(document.activeElement) && /^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName))) paintModal();
    }
  }
  document.addEventListener('focusout', () => { setTimeout(() => { if (pendingRender && S) { const ae = document.activeElement; if (!(ae && /^(INPUT|TEXTAREA|SELECT)$/.test(ae.tagName))) render(); } }, 150); });

  function renderTabs() {
    const badge = { round: D && D.nk_pending.length ? D.nk_pending.length : 0, rank: D ? D.ranking.open_playoffs.length : 0 };
    $('#tabs').innerHTML = TABS.map(([k, l]) => '<button role="tab" data-act="tab" data-tab="' + k + '" class="' + (k === tab ? 'on' : '') + '">' + l + (badge[k] ? '<span class="badge">' + badge[k] + '</span>' : '') + '</button>').join('');
  }
  function renderView() {
    const v = $('#view');
    if (!T) { v.innerHTML = '<div class="card"><h2>Kein Turnier</h2><p>Bitte im Tab „Turnier“ ein neues Turnier anlegen.</p></div>'; return; }
    const scr = {};
    $$('[data-keep]', v).forEach(el => { if (el.dataset.keep !== 'ok') scr[el.dataset.keep] = [el.scrollLeft, el.scrollTop]; });
    if (tab === 'players') renderPlayers(v);
    else {
      const f = { round: viewRound, table: viewTable, rank: viewRank, cash: viewCash, dash: viewDash, tourn: viewTourn }[tab];
      v.innerHTML = f();
    }
    $$('[data-keep]', v).forEach(el => { const s = scr[el.dataset.keep]; if (s) { el.scrollLeft = s[0]; el.scrollTop = s[1]; } });
  }
  function warnBanner() {
    const w = D.warnings, n = D.notices;
    let h = '';
    if (w.length) {
      h += '<div class="banner warn"><b>⚠ ' + w.length + ' Warnung' + (w.length > 1 ? 'en' : '') + ' (Daten nach Korrektur nicht mehr stimmig)</b><ul>' + w.map(x => '<li>' + esc(x.text) + '</li>').join('') + '</ul><div class="small muted">Es wurde nichts verändert. Bitte die betroffenen Ergebnisse prüfen bzw. korrigieren.</div></div>';
    }
    if (n.length) h += '<div class="banner">' + n.map(x => 'ℹ ' + esc(x.text)).join('<br>') + '</div>';
    return h;
  }

  /* ---------------- Tab: players ---------------- */
  function renderPlayers(v) {
    if (!$('#p-list')) {
      v.innerHTML = '<div id="p-head"></div><div class="card"><div class="add"><input id="p-name" type="text" data-keep="ok" placeholder="Name eintippen und Enter …" autocomplete="off" autocapitalize="words" enterkeyhint="done"><label class="sw"><input type="checkbox" id="p-ng" ' + (ui.addNg ? 'checked' : '') + '><i></i>NG bezahlt</label><button class="btn" data-act="p-add">Hinzufügen</button></div></div>' +
        '<div class="card"><div class="row" style="margin-bottom:8px" id="p-chips"></div><input id="p-search" type="search" data-keep="ok" placeholder="Suchen …" autocomplete="off"></div><div class="card plist" id="p-list"></div>';
      $('#p-search').value = ui.search;
    }
    const pl = D.players;
    const alive = pl.filter(p => p.status !== 'out').length;
    let head = '';
    if (D.phase === 'signup') head = '<div class="card row sp"><div><b>' + pl.length + ' Spieler angemeldet.</b><div class="muted small">Die Anmeldung läuft. Nach dem Start sind Nachmeldungen nur mit Bestätigung möglich.</div></div><button class="btn big gold" data-act="t-start" ' + (pl.length < 2 ? 'disabled' : '') + '>Turnier starten</button></div>';
    else if (D.phase === 'finished') head = '<div class="banner">Turnier beendet. Neue Spieler können nicht mehr angelegt werden.</div>';
    else head = '<div class="banner">Das Turnier läuft: Neu angelegte Spieler steigen ab der nächsten Runde ein (Bestätigung nötig).</div>';
    $('#p-head').innerHTML = head + (D.warnings.length ? warnBanner() : '');
    const flt = [['all', 'Alle (' + pl.length + ')'], ['alive', 'Im Spiel (' + alive + ')'], ['nk', 'NK offen (' + D.counts.nk_open + ')'], ['out', 'Ausgeschieden (' + (pl.length - alive) + ')']];
    $('#p-chips').innerHTML = flt.map(([k, l]) => '<button class="chip ' + (ui.filter === k ? 'on' : '') + '" data-act="p-filter" data-f="' + k + '">' + l + '</button>').join('');
    const dup = {}; pl.forEach(p => { const k = p.name.toLowerCase(); dup[k] = (dup[k] || 0) + 1; });
    const q = ui.search.trim().toLowerCase();
    const list = pl.filter(p => {
      if (ui.filter === 'alive' && p.status === 'out') return false;
      if (ui.filter === 'nk' && p.status !== 'nk_open') return false;
      if (ui.filter === 'out' && p.status !== 'out') return false;
      if (q && !(p.name.toLowerCase().includes(q) || (p.nickname || '').toLowerCase().includes(q) || String(p.number) === q)) return false;
      return true;
    });
    $('#p-list').innerHTML = list.length ? list.map(p => {
      let tags = '';
      if (p.nk_bought) tags += '<span class="tag">NK</span>';
      if (p.status === 'nk_open') tags += '<span class="tag r">NK offen</span>';
      if (p.status === 'out') tags += '<span class="tag m">' + (p.withdrawn ? 'aufgegeben' : 'raus') + ' R' + p.elim_round + '</span>';
      if (p.joined_round > 1) tags += '<span class="tag g">ab R' + p.joined_round + '</span>';
      if (dup[p.name.toLowerCase()] > 1) tags += '<span class="tag r">Doppelt?</span>';
      return '<div class="pr ' + (p.status === 'out' ? 'out' : '') + '"><span class="no">' + p.number + '</span><div class="nm" data-act="p-edit" data-id="' + p.id + '">' + esc(p.name) + tags + (p.nickname ? '<small>„' + esc(p.nickname) + '“</small>' : '') + '</div>' +
        (D.phase === 'signup' ? '<span></span>' : heartsHtml(p.hearts)) +
        '<div class="acts"><button class="btn sm ngb ' + (p.ng_paid ? 'paid' : 'open') + '" data-act="p-ng" data-id="' + p.id + '">' + (p.ng_paid ? 'NG ✓' : 'NG offen') + '</button><button class="btn sm sec" data-act="p-edit" data-id="' + p.id + '" aria-label="Bearbeiten">⋯</button></div></div>';
    }).join('') : '<div class="muted">Keine Spieler.</div>';
  }

  async function addPlayer() {
    const inp = $('#p-name');
    const nm = inp.value.trim();
    if (!nm) return;
    const ng = $('#p-ng').checked; ui.addNg = ng;
    let confirm_late = false;
    if (D && D.phase !== 'signup') {
      const ok = await confirmBox('Nachmeldung', nm + ' steigt ab Runde ' + (D.next_round) + ' ein. Nachmelden?', 'Ja, nachmelden');
      if (!ok) { setTimeout(() => $('#p-name') && $('#p-name').focus(), 50); return; }
      confirm_late = true;
    }
    inp.value = '';
    const r = await act(() => api('POST', 'players', { name: nm, ng_paid: ng, confirm_late }));
    if (!r) { const i2 = $('#p-name'); if (i2) i2.value = nm; }
    const i3 = $('#p-name'); if (i3) i3.focus();
  }

  function playerModal(id) {
    const p = pm[id]; if (!p) return;
    const canDel = !inPairing(id);
    const canWd = D.phase !== 'signup' && D.phase !== 'finished' && p.status !== 'out' && D.rounds.length > 0;
    const nkInfo = p.bummerl >= 1 && !p.withdrawn;
    showModal(() => {
      const q = pm[id] || p;
      return '<h2>Nr. ' + q.number + ' – ' + esc(q.name) + '</h2>' +
        '<label class="f">Name</label><input type="text" id="e-name" value="' + esc(q.name) + '"><label class="f">Spitzname (optional, erscheint auf dem Dashboard)</label><input type="text" id="e-nick" value="' + esc(q.nickname) + '">' +
        '<label class="f">Notiz (nur Admin)</label><input type="text" id="e-note" value="' + esc(q.note) + '">' +
        '<div class="row" style="margin-top:10px"><button class="btn sm ' + (q.ng_paid ? '' : 'sec red') + '" data-act="e-ng">' + (q.ng_paid ? 'NG bezahlt ✓ (antippen = offen)' : 'NG offen (antippen = bezahlt)') + '</button>' +
        (q.nk_bought ? '<button class="btn sm ' + (q.nk_paid ? '' : 'sec red') + '" data-act="e-nkpaid">' + (q.nk_paid ? 'NK bezahlt ✓' : 'NK offen (antippen = bezahlt)') + '</button>' : '') + '</div>' +
        (nkInfo ? '<h3 style="margin-top:14px">Nachkauf: ' + (q.nk_bought === true ? 'ja' : q.nk_bought === false ? 'nein' : 'noch offen') + '</h3><div class="nkrow"><div class="opts">' + nkButtons(q.id) + '</div></div>' : '') +
        '<div class="btns">' + (canDel ? '<button class="btn sec red" data-act="e-del">Löschen</button>' : '') + (canWd ? '<button class="btn sec red" data-act="e-wd">Aufgegeben</button>' : '') +
        '<button class="btn sec" data-act="m-close">Schließen</button><button class="btn" data-act="e-save">Speichern</button></div>';
    }, {
      'm-close': () => closeModal(), 'm-back': (el, ev) => { if (ev.target === el) closeModal(); },
      'e-save': async () => { const r = await act(() => api('PATCH', 'players/' + id, { name: $('#e-name').value, nickname: $('#e-nick').value, note: $('#e-note').value }), 'Gespeichert'); if (r) closeModal(); },
      'e-ng': () => act(() => api('PATCH', 'players/' + id, { ng_paid: !pm[id].ng_paid })),
      'e-nkpaid': () => act(() => api('PATCH', 'players/' + id, { nk_paid: !pm[id].nk_paid })),
      'e-del': async () => { if (await confirmBox('Spieler löschen?', name(id) + ' wird gelöscht.', 'Löschen', true)) { await act(() => api('DELETE', 'players/' + id)); } },
      'e-wd': async () => { if (await confirmBox('Aufgegeben?', name(id) + ' als aufgegeben markieren? Läuft gerade eine Paarung ohne Ergebnis, gewinnt der Gegner.', 'Ja, aufgegeben', true)) { await act(() => api('POST', 'players/' + id + '/withdraw')); } },
      'nk': (el) => nkSet(id, el.dataset.d)
    });
  }
  function nkButtons(id) {
    const nk = money(T.nk_amount);
    return '<button class="btn sm" data-act="nk" data-d="yes_paid">Ja, ' + nk + ' bezahlt</button><button class="btn sm gold" data-act="nk" data-d="yes_later">Ja, zahlt später</button><button class="btn sm sec red" data-act="nk" data-d="no">Nein → scheidet aus</button>' +
      (pm[id] && pm[id].nk_bought !== null ? '<button class="btn sm sec" data-act="nk" data-d="reset">Zurücksetzen</button>' : '');
  }
  async function nkSet(id, d) {
    if (d === 'no' && !(await confirmBox('Kein Nachkauf?', name(id) + ' scheidet damit aus.', 'Ja, scheidet aus', true))) { return; }
    await act(() => api('POST', 'players/' + id + '/nk', { decision: d }));
    if (modal && modal.nkDialog) { if (!D.nk_pending.length) closeModal(); }
  }
  function nkDialog() {
    showModal(() => {
      if (!D.nk_pending.length) return '<h2>Nachkauf</h2><p>Alle Entscheidungen sind getroffen. Die nächste Runde kann ausgelost werden.</p><div class="btns"><button class="btn" data-act="m-close">Weiter</button></div>';
      return '<h2>Nachkauf?</h2><p class="muted">Diese Spieler haben ihr erstes Bummerl bekommen. Die nächste Runde kann erst ausgelost werden, wenn alle entschieden sind.</p>' +
        D.nk_pending.map(n => '<div class="nkrow"><div class="nm">' + esc(label(n.id)) + ' <span class="muted small">– 1. Bummerl in Runde ' + n.round + '</span></div><div class="opts">' + nkButtons(n.id).replace(/data-act="nk"/g, 'data-act="nk" data-id="' + n.id + '"') + '</div></div>').join('') +
        '<div class="btns"><button class="btn sec" data-act="m-close">Später</button></div>';
    }, { 'm-close': () => closeModal(), 'm-back': (el, ev) => { if (ev.target === el) closeModal(); }, 'nk': (el) => nkSet(parseInt(el.dataset.id, 10), el.dataset.d) });
    modal.nkDialog = true;
  }

  /* ---------------- Tab: round ---------------- */
  function selRound() {
    if (ui.roundSel === 'draft' && D.draft) return 'draft';
    if (ui.roundSel && D.rounds.some(r => r.number === ui.roundSel)) return ui.roundSel;
    return D.draft ? 'draft' : (D.current_round || null);
  }
  function viewRound() {
    let h = warnBanner();
    const sel = selRound();
    if (D.phase === 'signup') return h + '<div class="card"><h2>Noch nicht gestartet</h2><p>Das Turnier startet im Tab „Spieler“ oder „Turnier“.</p></div>';
    // open rebuy decisions
    if (D.nk_pending.length) {
      h += '<div class="card" style="border-color:var(--red)"><div class="row sp"><div><h2 style="color:var(--red-d)">Nachkauf offen (' + D.nk_pending.length + ')</h2><div class="muted small">' + D.nk_pending.map(n => esc(name(n.id))).join(', ') + '</div></div><button class="btn big red" data-act="nk-dialog">Nachkauf entscheiden</button></div></div>';
    }
    // round selector
    const chips = D.rounds.map(r => '<button class="chip ' + (sel === r.number ? 'on' : '') + '" data-act="r-sel" data-r="' + r.number + '">R' + r.number + '</button>').concat(D.draft ? ['<button class="chip ' + (sel === 'draft' ? 'on' : '') + '" data-act="r-sel" data-r="draft">Entwurf R' + D.draft.number + '</button>'] : []);
    if (chips.length) h += '<div class="row" style="margin-bottom:12px">' + chips.join('') + '</div>';
    // draft / draw
    if (D.draft && sel === 'draft') h += draftPanel();
    else if (D.can_draw) h += drawPanel();
    else if (!D.draft && D.phase !== 'finished' && D.phase !== 'running') h += '<div class="card"><h2>Nächste Auslosung</h2><p class="muted">' + esc(D.can_draw_reason) + '</p></div>';
    if (D.phase === 'finished') h += '<div class="card" style="border-color:var(--gold)"><h2>Turnier beendet' + (D.winner ? ' – Sieger: ' + esc(name(D.winner)) : '') + '</h2><p>Platzierung und Siegerehrung im Tab „Rangliste“.</p></div>';
    // selected round
    if (sel !== 'draft' && sel != null) {
      const r = D.rounds.find(x => x.number === sel);
      if (r) h += roundPanel(r);
    }
    return h;
  }
  function pairName(pr) { return pr.bye ? 'Freilos' : 'Tisch ' + pr.table; }
  function draftPanel() {
    const dr = D.draft;
    const viol = D.draft_violations;
    return '<div class="card" style="border:3px dashed var(--gold)"><div class="row sp"><h2>Runde ' + dr.number + ' – Entwurf <span class="tag">nur im Admin sichtbar</span></h2></div>' +
      (viol ? '<div class="banner">Hinweis: ' + viol + ' weicher Verstoß (Wiederholung der Paarung bzw. zweites Freilos) war nicht vermeidbar. „Neu auslosen“ versucht es erneut.</div>' : '') +
      '<div class="tiles">' + dr.pairings.map(pr => pr.bye ? '<div class="tile bye"><div class="th"><span>Freilos</span>' + ic('schelln') + '</div><div class="pb" style="cursor:default">' + esc(name(pr.a)) + '</div></div>' :
        '<div class="tile"><div class="th"><span>Tisch ' + pr.table + '</span></div><div class="pb" style="cursor:default">' + esc(name(pr.a)) + '</div><div class="vs">gegen</div><div class="pb" style="cursor:default">' + esc(name(pr.b)) + '</div></div>').join('') + '</div>' +
      '<div class="row" style="margin-top:14px"><button class="btn sec red" data-act="d-discard">Verwerfen</button><button class="btn sec" data-act="d-redraw">' + (dr.mode === 'manual' ? 'Neu eingeben' : 'Neu auslosen') + '</button><span class="grow"></span><button class="btn big gold" data-act="d-publish">Veröffentlichen</button></div></div>';
  }
  function drawPanel() {
    const di = D.draw_info;
    let h = '<div class="card"><div class="row sp"><h2>Runde ' + D.next_round + ' auslosen</h2><div class="row"><button class="chip ' + (ui.mode === 'digital' ? 'on' : '') + '" data-act="d-mode" data-m="digital">Auto</button><button class="chip ' + (ui.mode === 'manual' ? 'on' : '') + '" data-act="d-mode" data-m="manual">Manuell</button></div></div>';
    if (di) h += '<div class="banner">' + ic('eichel') + ' ' + esc(di.text) + '</div>';
    if (ui.mode === 'digital') {
      h += '<button class="btn big" data-act="d-draw">Runde ' + D.next_round + ' auslosen</button><p class="muted small">Zufällige Auslosung (kryptografisch). Das Ergebnis ist zunächst ein Entwurf und erscheint erst nach „Veröffentlichen“ auf dem Dashboard.</p></div>';
    } else h += manualPanel() + '</div>';
    return h;
  }
  function manualState() {
    const ids = D.draw_ids, tables = Math.floor(ids.length / 2), odd = ids.length % 2 === 1;
    const A = ui.manual.assign, cnt = {};
    ids.forEach(i => { if (A[i] != null) cnt[A[i]] = (cnt[A[i]] || 0) + 1; });
    const errs = [];
    ids.forEach(i => { if (A[i] == null) return; });
    const missing = ids.filter(i => A[i] == null).length;
    for (let t = 1; t <= tables; t++) if ((cnt[t] || 0) > 2) errs.push('Zettel ' + t + ' mehr als 2×');
    if ((cnt.F || 0) > 1) errs.push('F mehr als 1×');
    const ok = !missing && !errs.length && Object.keys(cnt).every(k => k === 'F' || (+k >= 1 && +k <= tables)) && Array.from({ length: tables }, (_, i) => cnt[i + 1] === 2).every(Boolean) && (odd ? cnt.F === 1 : !cnt.F);
    return { ids, tables, odd, cnt, missing, errs, ok };
  }
  function manualPanel() {
    const m = manualState();
    const A = ui.manual.assign;
    if (ui.manual.sel == null || !m.ids.includes(ui.manual.sel)) ui.manual.sel = m.ids.find(i => A[i] == null) || m.ids[0];
    let pad = '';
    for (let t = 1; t <= m.tables; t++) pad += '<button class="btn sec" data-act="mk" data-t="' + t + '" ' + ((m.cnt[t] || 0) >= 2 && A[ui.manual.sel] !== t ? 'disabled' : '') + '>' + t + '</button>';
    if (m.odd) pad += '<button class="btn sec" style="color:var(--green-d);border-color:var(--green)" data-act="mk" data-t="F" ' + ((m.cnt.F || 0) >= 1 && A[ui.manual.sel] !== 'F' ? 'disabled' : '') + '>F</button>';
    const list = m.ids.map(i => '<div class="mrow ' + (ui.manual.sel === i ? 'sel' : '') + '" data-act="m-sel" data-id="' + i + '"><span class="muted">' + pm[i].number + '</span> <b>' + esc(name(i)) + '</b><span class="tk ' + (A[i] === 'F' ? 'F' : '') + '">' + (A[i] != null ? A[i] : '–') + '</span></div>').join('');
    return '<div class="draw2"><div><h3>Spieler (antippen, dann Zahl)</h3>' + list + '</div><div><h3>Gezogener Zettel' + (ui.manual.sel != null ? ' für ' + esc(name(ui.manual.sel)) : '') + '</h3><div class="pad">' + pad + '</div>' +
      '<div class="row" style="margin-top:12px"><button class="btn sm sec" data-act="mk" data-t="">Zettel entfernen</button><button class="btn sm sec" data-act="mk-reset">Alles leeren</button></div>' +
      '<p class="' + (m.ok ? 'okc' : 'muted') + '">' + (m.ok ? '✓ Alle Zettel passen: jede Nummer 2×' + (m.odd ? ', F 1×' : '') + '.' : (m.missing ? m.missing + ' Spieler ohne Zettel. ' : '') + esc(m.errs.join('. '))) + '</p>' +
      '<button class="btn big" data-act="d-manual" ' + (m.ok ? '' : 'disabled') + '>Entwurf erstellen</button></div></div>';
  }
  function roundPanel(r) {
    const open = r.open_tables;
    const prog = r.total + ' Tische: ' + r.done + ' von ' + r.total + ' fertig' + (open.length ? ' – offen: Tisch ' + open.join(', ') : '');
    const last = r.number === D.rounds[D.rounds.length - 1].number;
    let h = '<div class="card"><div class="row sp"><div><h2>Runde ' + r.number + (r.status === 'closed' ? ' <span class="tag g">abgeschlossen</span>' : ' <span class="tag">läuft</span>') + '</h2><div class="' + (open.length ? 'muted' : 'okc') + '">' + esc(prog) + '</div></div><div class="row">' +
      (r.status === 'published' ? '<button class="btn big gold" data-act="r-close" data-r="' + r.number + '" ' + (open.length ? 'disabled' : '') + '>Runde abschließen</button>' : '') +
      (r.status === 'closed' && last && !D.draft ? '<button class="btn sec" data-act="r-reopen" data-r="' + r.number + '">Wieder öffnen</button>' : '') + '</div></div>';
    if (r.status === 'closed') h += '<p class="muted small">Ergebnisse einer abgeschlossenen Runde lassen sich per Tipp auf einen Tisch korrigieren (mit Bestätigung).</p>';
    h += '<div class="tiles" style="margin-top:10px">' + r.pairings.map(pr => tile(r, pr)).join('') + '</div></div>';
    return h;
  }
  function tile(r, pr) {
    if (pr.bye) return '<div class="tile bye"><div class="th"><span>Freilos</span>' + ic('schelln') + '</div><div class="pb" style="cursor:default">' + esc(name(pr.a)) + '<span class="sub">kampflos weiter</span></div></div>';
    const done = pr.winner != null;
    const btn = id => {
      let cls = 'pb', sub = '';
      if (done) { cls += id === pr.winner ? ' win' : ' lose'; sub = id === pr.winner ? '✓ Sieger' : 'Bummerl'; }
      const act = (done || r.status === 'closed') ? 'res-open' : 'res-set';
      return '<button class="' + cls + '" data-act="' + act + '" data-p="' + pr.id + '" data-w="' + id + '">' + esc(name(id)) + '<span class="sub">' + sub + '</span></button>';
    };
    return '<div class="tile ' + (done ? 'done' : '') + '"><div class="th"><span>Tisch ' + pr.table + '</span>' + (done ? '<button class="btn sm sec edit" data-act="res-open" data-p="' + pr.id + '">Ändern</button>' : '') + '</div>' + btn(pr.a) + '<div class="vs">gegen</div>' + btn(pr.b) + '</div>';
  }
  function findPairing(id) {
    for (const r of D.rounds) { const pr = r.pairings.find(x => x.id === id); if (pr) return { r, pr }; }
    return null;
  }
  function resultModal(pid) {
    const f = findPairing(pid); if (!f || f.pr.bye) return;
    showModal(() => {
      const g = findPairing(pid); if (!g) return '';
      const pr = g.pr;
      return '<h2>Runde ' + g.r.number + ' · Tisch ' + pr.table + '</h2>' + (g.r.status === 'closed' ? '<div class="banner">Diese Runde ist bereits abgeschlossen. Eine Korrektur berechnet alles neu und kann spätere Runden ungültig machen (Warnung).</div>' : '') +
        '<div class="stack"><button class="btn big ' + (pr.winner === pr.a ? '' : 'sec') + '" data-act="rs" data-w="' + pr.a + '">' + esc(name(pr.a)) + ' gewinnt</button><button class="btn big ' + (pr.winner === pr.b ? '' : 'sec') + '" data-act="rs" data-w="' + pr.b + '">' + esc(name(pr.b)) + ' gewinnt</button>' +
        (pr.winner != null ? '<button class="btn sec red" data-act="rs" data-w="">Ergebnis zurücksetzen</button>' : '') + '</div><div class="btns"><button class="btn sec" data-act="m-close">Schließen</button></div>';
    }, {
      'm-close': () => closeModal(), 'm-back': (el, ev) => { if (ev.target === el) closeModal(); },
      'rs': async (el) => {
        const g = findPairing(pid); const w = el.dataset.w === '' ? null : parseInt(el.dataset.w, 10);
        let confirm = false;
        if (g.r.status === 'closed') {
          closeModal();
          if (!(await confirmBox('Ergebnis korrigieren?', 'Runde ' + g.r.number + ' ist abgeschlossen. Wirklich ändern?', 'Ja, ändern', true))) return;
          confirm = true;
        }
        const r = await act(() => api('POST', 'pairings/' + pid + '/result', { winner_id: w, confirm }));
        if (r && !confirm) closeModal();
        if (r && D.warnings.length) toast('Achtung: Die Korrektur erzeugt Warnungen – bitte prüfen.', 'warn');
      }
    });
  }

  /* ---------------- Tab: table ---------------- */
  function viewTable() {
    const nr = Math.max(D.current_round, 1);
    const head = '<tr><th class="c1">Nr.</th><th class="c2">Name</th><th>NG</th><th>NK</th>' + Array.from({ length: nr }, (_, i) => '<th>R' + (i + 1) + '</th>').join('') + '</tr>';
    const rows = D.players.map(p => {
      const nk = p.nk_bought ? (p.nk_paid ? '<span class="okc">' + money(T.nk_amount) + '</span>' : '<span class="badc">offen</span>') : (p.nk_bought === false ? '<span class="muted">–</span>' : '');
      const cells = Array.from({ length: nr }, (_, i) => {
        const c = p.cells[i + 1];
        return c && c.pairing_id && c.kind !== 'bye' ? '<td class="cell" data-act="res-open" data-p="' + c.pairing_id + '">' + cellHtml(c) + '</td>' : '<td>' + cellHtml(c) + '</td>';
      }).join('');
      return '<tr class="' + (p.status === 'out' ? 'out' : '') + '"><td class="c1 nr">' + p.number + '</td><td class="c2 nm">' + esc(p.name) + '</td><td>' + (p.ng_paid ? '<span class="okc">' + money(T.ng_amount) + '</span>' : '<span class="badc">offen</span>') + '</td><td>' + nk + '</td>' + cells + '</tr>';
    }).join('');
    return warnBanner() + '<div class="row sp" style="margin-bottom:8px"><div class="muted small">Tipp auf eine Zelle = Ergebnis korrigieren. <b>–</b> erstes Bummerl, <span class="sym nk" style="width:1.1em;height:1.1em">–</span> zweites/drittes (Nachkauf), <span class="sym bye" style="width:1.1em;height:1.1em">F</span> Freilos.</div><a class="btn sm sec" href="/admin/druck" target="_blank" rel="noopener">Druckansicht</a></div>' +
      '<div class="mxscroll" data-keep="mx"><table class="mx">' + head + rows + '</table></div>';
  }

  /* ---------------- Tab: ranking ---------------- */
  function viewRank() {
    const groups = D.ranking.groups;
    let h = '<div class="card row sp"><div><h2>Rangliste</h2><div class="muted small">' + (D.finished ? 'Endstand' : 'Zwischenstand – wer später ausscheidet, liegt weiter vorne.') + '</div></div>' +
      '<button class="btn ' + (T.dashboard.show_ceremony ? 'red' : 'gold') + '" data-act="ceremony">' + (T.dashboard.show_ceremony ? 'Siegerehrung auf dem Dashboard beenden' : 'Siegerehrung auf dem Dashboard zeigen') + '</button></div>';
    h += warnBanner();
    h += groups.map(g => {
      const ps = g.players;
      const editable = g.in_prizes && ps.length > 1 && (g.needs_playoff || g.decided) && (!g.active || D.finished);
      let body = '';
      if (editable && ps.length === 2) {
        body = '<div class="muted small">Platzierungsspiel ' + esc(g.pl_label) + (g.decided ? ' – entschieden' : ' – Sieger antippen') + '</div><div class="row" style="margin-top:6px">' +
          ps.map((id, i) => { const other = ps[1 - i]; const won = g.decided && ps[0] === id; return '<button class="btn ' + (won ? '' : 'sec') + ' grow" data-act="pl-win" data-k="' + g.key + '" data-w="' + id + '" data-o="' + other + '">' + (won ? '✓ ' : '') + esc(name(id)) + ' gewinnt</button>'; }).join('') +
          (g.decided ? '<button class="btn sm sec red" data-act="pl-clear" data-k="' + g.key + '">Zurücksetzen</button>' : '') + '</div>';
      } else if (editable) {
        const ord = ui.order[g.key] && sameSet(ui.order[g.key], ps) ? ui.order[g.key] : ps.slice();
        body = '<div class="muted small">Reihenfolge ' + esc(g.pl_label) + ' festlegen (Pfeile)' + (g.decided ? ' – gespeichert' : '') + '</div>' +
          ord.map((id, i) => '<div class="ord"><span class="pos">' + (g.place_from + i) + '.</span><span class="grow"><b>' + esc(name(id)) + '</b></span><button class="btn sm sec" data-act="ord-mv" data-k="' + g.key + '" data-i="' + i + '" data-d="-1" ' + (i === 0 ? 'disabled' : '') + ' aria-label="nach oben">▲</button><button class="btn sm sec" data-act="ord-mv" data-k="' + g.key + '" data-i="' + i + '" data-d="1" ' + (i === ord.length - 1 ? 'disabled' : '') + ' aria-label="nach unten">▼</button></div>').join('') +
          '<div class="row" style="margin-top:8px"><button class="btn" data-act="ord-save" data-k="' + g.key + '">Reihenfolge speichern</button>' + (g.decided ? '<button class="btn sm sec red" data-act="pl-clear" data-k="' + g.key + '">Zurücksetzen</button>' : '') + '</div>';
      } else body = '<ol start="' + g.place_from + '" style="list-style:none;padding:0">' + ps.map((id, i) => '<li>' + (g.decided ? (g.place_from + i) + '. ' : '') + esc(label(id)) + '</li>').join('') + '</ol>';
      const head = g.active && !D.finished ? 'Noch im Spiel (' + ps.length + ')' : (ps.length === 1 ? 'Platz ' + g.place_from : 'Plätze ' + g.place_from + '–' + g.place_to);
      return '<div class="grp ' + (editable && g.needs_playoff ? 'pl' : '') + '"><div class="gh"><span>' + head + '</span><span class="small muted">' + (g.active ? (D.finished ? 'Turniersieger' : '') : 'ausgeschieden Runde ' + g.elim_round) + '</span></div>' +
        (editable ? body : '<div>' + ps.map(id => esc(label(id))).join(' · ') + '</div>') + '</div>';
    }).join('');
    return h;
  }
  const sameSet = (a, b) => a.length === b.length && a.every(x => b.includes(x));

  /* ---------------- Tab: cash ---------------- */
  function viewCash() {
    const c = D.cash;
    const rowsOpen = (ids, kind) => ids.length ? ids.map(id => '<div class="row sp" style="padding:4px 0;border-bottom:1px solid var(--line)"><b>' + esc(label(id)) + '</b><button class="btn sm" data-act="pay" data-k="' + kind + '" data-id="' + id + '">' + (kind === 'ng' ? 'NG' : 'NK') + ' bezahlt ✓</button></div>').join('') : '<div class="okc">Alles bezahlt ✓</div>';
    return '<div class="card"><h2>Kassa</h2><table class="cash"><tr><td>Nenngeld: ' + c.ng_count + ' × ' + money(c.ng_amount) + '</td><td>' + money(c.ng_sum) + '</td></tr><tr><td>Nachkäufe: ' + c.nk_count + ' × ' + money(c.nk_amount) + '</td><td>' + money(c.nk_sum) + '</td></tr>' +
      '<tr class="tot"><td>Gesamtsumme</td><td>' + money(c.total) + '</td></tr><tr><td>davon bezahlt (' + (c.ng_paid_count + c.nk_paid_count) + ' Zahlungen)</td><td class="okc">' + money(c.paid) + '</td></tr><tr><td>davon noch offen</td><td class="' + (c.open > 0 ? 'badc' : 'okc') + '">' + money(c.open) + '</td></tr></table></div>' +
      '<div class="card"><h2>Nenngeld offen (' + c.open_ng.length + ')</h2>' + rowsOpen(c.open_ng, 'ng') + '</div><div class="card"><h2>Nachkauf offen (' + c.open_nk.length + ')</h2>' + rowsOpen(c.open_nk, 'nk') + '</div>';
  }

  /* ---------------- Tab: Dashboard ---------------- */
  function viewDash() {
    const b = T.dashboard;
    const views = [['tables', 'Tische'], ['players', 'Spieler'], ['matrix', 'Tabelle'], ['ranking', 'Rangliste']];
    const sw = (id, lab, on) => '<label class="sw"><input type="checkbox" id="' + id + '" data-chg="1" ' + (on ? 'checked' : '') + '><i></i>' + lab + '</label>';
    return '<div class="card"><h2>Dashboard-Einstellungen</h2><p class="muted small">Das Dashboard wechselt automatisch zwischen den Ansichten. Vor dem Start zeigt es die Anmeldeliste, nach dem Ende die Siegerehrung.</p>' +
      '<div class="fgrid"><div><label class="f">Wechseldauer</label><select id="b-rot" data-chg="1">' + [10, 15, 20, 30, 45, 60].map(s => '<option value="' + s + '" ' + (b.rotate_seconds === s ? 'selected' : '') + '>' + s + ' Sekunden</option>').join('') + '</select></div>' +
      '<div><label class="f">Ansicht anpinnen</label><select id="b-pin" data-chg="1"><option value="">Automatisch wechseln</option>' + [['tables', 'Tische'], ['players', 'Spieler'], ['matrix', 'Tabelle'], ['ranking', 'Rangliste'], ['cash', 'Kassa'], ['ceremony', 'Siegerehrung']].map(([k, l]) => '<option value="' + k + '" ' + (b.pinned === k ? 'selected' : '') + '>' + l + '</option>').join('') + '</select></div></div>' +
      '<label class="f" style="margin-top:12px">Ansichten in der Rotation</label><div class="row">' + views.map(([k, l]) => '<label class="sw"><input type="checkbox" data-view="' + k + '" data-chg="1" ' + (b.views.includes(k) ? 'checked' : '') + '><i></i>' + l + '</label>').join('') + '</div>' +
      '<div class="stack" style="margin-top:10px">' + sw('b-cash', 'Kassa / Preistopf auf dem Dashboard anzeigen', T.show_cashbox) + sw('b-anim', 'Auslosungs-Animation (2–5 s)', b.animation) + sw('b-cerauto', 'Siegerehrung automatisch nach Turnierende', b.ceremony_auto) + sw('b-cer', 'Siegerehrung jetzt anzeigen', b.show_ceremony) + '</div></div>' +
      '<div class="card"><a class="btn" href="/dashboard/" target="_blank" rel="noopener">Dashboard öffnen</a> <span class="muted small">(Vollbild-Taste unten rechts)</span></div>';
  }
  async function dashChange() {
    const views = $$('[data-view]').filter(x => x.checked).map(x => x.dataset.view);
    await act(() => api('PATCH', 'dashboard', { rotate_seconds: parseInt($('#b-rot').value, 10), pinned: $('#b-pin').value, views, show_cashbox: $('#b-cash').checked, animation: $('#b-anim').checked, ceremony_auto: $('#b-cerauto').checked, show_ceremony: $('#b-cer').checked }));
  }

  /* ---------------- Tab: tournament ---------------- */
  function viewTourn() {
    const t = T;
    const st = { signup: 'Anmeldung', running: 'läuft', finished: 'beendet' }[t.status];
    const f = (id, lab, val, type) => '<div><label class="f" for="' + id + '">' + lab + '</label><input id="' + id + '" type="' + (type || 'text') + '" value="' + esc(val) + '" ' + (type === 'number' ? 'inputmode="decimal"' : '') + '></div>';
    let h = '<div class="card"><div class="row sp"><h2>Turnier: ' + esc(t.name) + ' <span class="tag">' + st + '</span></h2><div class="row">' +
      (t.status === 'signup' ? '<button class="btn gold" data-act="t-start">Turnier starten</button>' : '') +
      (t.status === 'running' ? '<button class="btn sec red" data-act="t-finish">Turnier beenden</button>' : '') +
      (t.status === 'finished' && !D.finished_by_rules ? '<button class="btn sec" data-act="t-reopen">Wieder öffnen</button>' : '') + (t.status === 'finished' && D.finished_by_rules ? '<span class="muted small">Korrigieren: Tab „Runde“ → letzte Runde „Wieder öffnen“</span>' : '') + '</div></div>' +
      '<div class="fgrid">' + f('t-name', 'Name', t.name) + f('t-date', 'Datum', t.date, 'date') + f('t-place', 'Ort', t.place) + f('t-ng', 'Nenngeld (€)', t.ng_amount, 'number') + f('t-nk', 'Nachkauf (€)', t.nk_amount, 'number') + f('t-pr', 'Anzahl Preisränge', t.prize_ranks, 'number') + f('t-tables', 'Tische (0 = unbegrenzt)', t.tables_available, 'number') + '</div>' +
      '<label class="f">Preise je Platz (eine Zeile pro Platz, Platz 1 zuerst)</label><textarea id="t-prizes" placeholder="Platz 1&#10;Platz 2 …">' + esc((t.prizes || []).join('\n')) + '</textarea>' +
      '<div class="row" style="margin-top:8px"><label class="sw"><input type="checkbox" id="t-avrep" ' + (t.draw.avoid_repeat ? 'checked' : '') + '><i></i>Gleiche Paarung wie in der Vorrunde möglichst vermeiden</label><label class="sw"><input type="checkbox" id="t-avbye" ' + (t.draw.avoid_bye_repeat ? 'checked' : '') + '><i></i>Nicht zweimal hintereinander Freilos</label></div>' +
      '<div class="row" style="margin-top:10px"><button class="btn" data-act="t-save">Einstellungen speichern</button></div></div>';
    h += '<div class="card"><h2>Neues Turnier</h2><div class="row"><input id="n-name" type="text" class="grow" style="width:auto;flex:1" placeholder="Name des neuen Turniers"><button class="btn" data-act="t-new">Anlegen &amp; aktivieren</button></div><p class="muted small">Das bisherige Turnier bleibt im Archiv gespeichert.</p></div>';
    h += '<div class="card"><h2>Archiv</h2>' + S.tournaments.map(x => '<div class="row sp" style="padding:6px 0;border-bottom:1px solid var(--line)"><div><b>' + esc(x.name) + '</b> ' + (x.active ? '<span class="tag g">aktiv</span>' : '') + '<div class="muted small">' + esc(x.date || '') + ' · ' + x.players + ' Spieler · ' + ({ signup: 'Anmeldung', running: 'läuft', finished: 'beendet' }[x.status]) + '</div></div><div class="row">' +
      (x.active ? '' : '<button class="btn sm" data-act="t-act" data-id="' + x.id + '">Aktivieren</button><button class="btn sm sec red" data-act="t-del" data-id="' + x.id + '">Löschen</button>') + '</div></div>').join('') + '</div>';
    h += '<div class="card"><h2>Export &amp; Import</h2><div class="row"><a class="btn sec" href="/admin/api/export.csv" download>CSV (Tabelle)</a><a class="btn sec" href="/admin/druck" target="_blank" rel="noopener">Druckansicht (A4 quer)</a><a class="btn sec" href="/admin/api/backup.json" download>JSON-Backup</a>' +
      '<label class="btn sec" for="imp">JSON importieren …</label><input id="imp" type="file" accept="application/json,.json" style="display:none" data-keep="ok"></div><p class="muted small">Ein Import legt ein neues Turnier im Archiv an (mit neuen IDs) und überschreibt nichts.</p></div>';
    h += '<div class="card"><h2>Zurücksetzen</h2>' +
      '<p class="muted small"><b>Turnier zurücksetzen:</b> löscht alle Runden und Ergebnisse, die Spieler bleiben angelegt.<br>' +
      '<b>Alle Spieler entfernen:</b> löscht alle Spieler samt Runden und Ergebnissen.<br>' +
      'Die Turnier-Einstellungen bleiben jeweils erhalten. Beides ist mit „Rückgängig“ wiederherstellbar.</p>' +
      '<div class="row"><button class="btn sec red" data-act="t-reset">Turnier zurücksetzen …</button>' +
      '<button class="btn sec red" data-act="p-remove-all"' + (D.players.length ? '' : ' disabled') + '>Alle Spieler entfernen …</button></div></div>';
    h += '<div class="card"><div class="row sp"><h2>Protokoll</h2><button class="chip" data-act="audit">' + (ui.showAudit ? 'Verbergen' : 'Anzeigen') + '</button></div>' +
      (ui.showAudit ? '<div class="audit">' + S.audit.map(a => '<div><time>' + esc(a.ts.replace('T', ' ').slice(5, 19)) + '</time>' + esc(a.text) + '</div>').join('') + '</div>' : '') + '</div>';
    return h;
  }

  async function saveTournament() {
    const prizes = $('#t-prizes').value.split('\n').map(x => x.trim());
    while (prizes.length && !prizes[prizes.length - 1]) prizes.pop();
    await act(() => api('PATCH', 'tournament', {
      name: $('#t-name').value, date: $('#t-date').value, place: $('#t-place').value, ng_amount: $('#t-ng').value, nk_amount: $('#t-nk').value,
      prize_ranks: $('#t-pr').value, tables_available: $('#t-tables').value, prizes, draw: { avoid_repeat: $('#t-avrep').checked, avoid_bye_repeat: $('#t-avbye').checked }
    }), 'Gespeichert');
  }

  /* ---------------- Actions ---------------- */
  const H = {
    'tab': el => { tab = el.dataset.tab; try { localStorage.setItem('sn_tab', tab); } catch (e) { } window.scrollTo(0, 0); renderTabs(); renderView(); },
    'undo': async () => {
      if (!(S.undo && S.undo.available)) return;
      if (await confirmBox('Rückgängig?', 'Letzte Aktion rückgängig machen: ' + S.undo.label, 'Rückgängig machen')) await act(() => api('POST', 'undo'), 'Rückgängig gemacht');
    },
    'p-add': () => addPlayer(),
    'p-filter': el => { ui.filter = el.dataset.f; renderView(); },
    'p-ng': el => { const id = +el.dataset.id; return act(() => api('PATCH', 'players/' + id, { ng_paid: !pm[id].ng_paid })); },
    'p-edit': el => playerModal(+el.dataset.id),
    't-start': async () => { if (await confirmBox('Turnier starten?', 'Die Anmeldung wird gesperrt (' + D.players.length + ' Spieler). Nachmeldungen sind danach nur mit Bestätigung möglich.', 'Turnier starten')) { const r = await act(() => api('POST', 'tournament/start'), 'Turnier gestartet'); if (r) { tab = 'round'; renderTabs(); renderView(); } } },
    't-finish': async () => { if (await confirmBox('Turnier beenden?', 'Das Turnier wird als beendet markiert.', 'Beenden', true)) await act(() => api('POST', 'tournament/finish')); },
    't-reopen': async () => { await act(() => api('POST', 'tournament/reopen'), 'Turnier wieder geöffnet'); },
    't-save': () => saveTournament(),
    't-new': async () => { const n = $('#n-name').value.trim(); if (!n) { toast('Bitte einen Namen eingeben.', 'err'); return; } if (await confirmBox('Neues Turnier anlegen?', '„' + n + '“ wird angelegt und aktiviert. Das aktuelle Turnier bleibt im Archiv.', 'Anlegen')) { await act(() => api('POST', 'tournaments', { name: n, ng_amount: T.ng_amount, nk_amount: T.nk_amount, prize_ranks: T.prize_ranks, tables_available: T.tables_available }), 'Turnier angelegt'); } },
    't-act': async el => { if (await confirmBox('Turnier aktivieren?', 'Das Turnier wird im Dashboard angezeigt.', 'Aktivieren')) await act(() => api('POST', 'tournaments/' + el.dataset.id + '/activate'), 'Aktiviert'); },
    't-del': async el => {
      const x = S.tournaments.find(t => t.id === +el.dataset.id);
      if (!(await confirmBox('Turnier löschen?', '„' + x.name + '“ mit allen Daten löschen?', 'Weiter', true))) return;
      if (!(await confirmBox('Wirklich endgültig löschen?', 'Das kann nicht rückgängig gemacht werden (auch nicht mit „Rückgängig“).', 'Ja, endgültig löschen', true))) return;
      await act(() => api('DELETE', 'tournaments/' + x.id, { confirm: true }), 'Gelöscht');
    },
    'p-remove-all': async () => {
      const n = D.players.length, withRounds = D.rounds.length > 0 || !!D.draft;
      if (!(await confirmBox('Alle Spieler entfernen?', n + ' Spieler werden gelöscht' + (withRounds ? ', dazu alle Runden und Ergebnisse' : '') + '.', 'Weiter', true))) return;
      if (!(await confirmBox('Wirklich alle entfernen?', 'Bitte noch einmal bestätigen.', 'Ja, alle entfernen', true))) return;
      await act(() => api('POST', 'players/remove-all', { confirm: true }), 'Alle Spieler entfernt');
    },
    't-reset': async () => {
      if (!(await confirmBox('Turnier zurücksetzen?', 'Alle Runden und Ergebnisse werden gelöscht.', 'Weiter', true))) return;
      if (!(await confirmBox('Wirklich zurücksetzen?', 'Bitte noch einmal bestätigen. Spieler bleiben angelegt.', 'Ja, zurücksetzen', true))) return;
      await act(() => api('POST', 'tournament/reset', { confirm: true }), 'Zurückgesetzt');
    },
    'anim': async () => { await act(() => api('POST', 'dashboard/animate'), 'Animation gestartet'); },
    'audit': () => { ui.showAudit = !ui.showAudit; renderView(); },
    'r-sel': el => { ui.roundSel = el.dataset.r === 'draft' ? 'draft' : +el.dataset.r; renderView(); },
    'nk-dialog': () => nkDialog(),
    'd-mode': el => { ui.mode = el.dataset.m; renderView(); },
    'd-draw': async () => { const r = await act(() => api('POST', 'rounds/draw'), 'Ausgelost – Entwurf'); if (r) ui.roundSel = 'draft'; renderView(); },
    'd-redraw': async () => {
      if (D.draft.mode === 'manual') { if (await confirmBox('Neu eingeben?', 'Der Entwurf wird verworfen.', 'Verwerfen & neu eingeben', true)) { await act(() => api('POST', 'rounds/discard')); ui.mode = 'manual'; ui.manual = { assign: {}, sel: null }; ui.roundSel = null; renderView(); } return; }
      if (await confirmBox('Neu auslosen?', 'Der aktuelle Entwurf wird ersetzt.', 'Neu auslosen')) await act(() => api('POST', 'rounds/draw'), 'Neu ausgelost');
    },
    'd-discard': async () => { if (await confirmBox('Entwurf verwerfen?', '', 'Verwerfen', true)) { await act(() => api('POST', 'rounds/discard'), 'Entwurf verworfen'); ui.roundSel = null; renderView(); } },
    'd-publish': async () => { const r = await act(() => api('POST', 'rounds/publish'), 'Veröffentlicht – jetzt im Dashboard'); if (r) { ui.roundSel = null; renderView(); } },
    'm-sel': el => { ui.manual.sel = +el.dataset.id; renderView(); },
    'mk': el => {
      const sel = ui.manual.sel; if (sel == null) return;
      const t = el.dataset.t;
      if (t === '') delete ui.manual.assign[sel]; else ui.manual.assign[sel] = t === 'F' ? 'F' : +t;
      if (t !== '') { const nxt = D.draw_ids.find(i => ui.manual.assign[i] == null); if (nxt != null) ui.manual.sel = nxt; }
      renderView();
    },
    'mk-reset': () => { ui.manual = { assign: {}, sel: null }; renderView(); },
    'd-manual': async () => { const r = await act(() => api('POST', 'rounds/draw-manual', { assignment: ui.manual.assign }), 'Entwurf erstellt'); if (r) { ui.manual = { assign: {}, sel: null }; ui.roundSel = 'draft'; renderView(); } },
    'r-close': async el => {
      const n = +el.dataset.r;
      if (!(await confirmBox('Runde ' + n + ' abschließen?', 'Alle Ergebnisse sind eingetragen. Danach folgen die Nachkauf-Entscheidungen.', 'Runde abschließen'))) return;
      const r = await act(() => api('POST', 'rounds/' + n + '/close'), 'Runde abgeschlossen');
      if (r && D.nk_pending.length) nkDialog();
      else if (r && D.finished) toast('Turnier beendet – Sieger: ' + name(D.winner), 'ok');
    },
    'r-reopen': async el => { if (await confirmBox('Runde wieder öffnen?', 'Die Runde wird wieder bearbeitbar.', 'Öffnen')) await act(() => api('POST', 'rounds/' + el.dataset.r + '/reopen')); },
    'res-set': el => act(() => api('POST', 'pairings/' + el.dataset.p + '/result', { winner_id: +el.dataset.w })),
    'res-open': el => resultModal(+el.dataset.p),
    'pl-win': async el => { await act(() => api('POST', 'placements', { elim_round: +el.dataset.k, order: [+el.dataset.w, +el.dataset.o] }), 'Platzierung gespeichert'); },
    'pl-clear': async el => { await act(() => api('DELETE', 'placements/' + el.dataset.k)); delete ui.order[el.dataset.k]; },
    'ord-mv': el => {
      const k = +el.dataset.k, i = +el.dataset.i, d = +el.dataset.d;
      const g = D.ranking.groups.find(x => x.key === k);
      const ord = (ui.order[k] && sameSet(ui.order[k], g.players)) ? ui.order[k].slice() : g.players.slice();
      const j = i + d; if (j < 0 || j >= ord.length) return;
      [ord[i], ord[j]] = [ord[j], ord[i]]; ui.order[k] = ord; renderView();
    },
    'ord-save': async el => { const k = +el.dataset.k; const g = D.ranking.groups.find(x => x.key === k); const ord = (ui.order[k] && sameSet(ui.order[k], g.players)) ? ui.order[k] : g.players; await act(() => api('POST', 'placements', { elim_round: k, order: ord }), 'Reihenfolge gespeichert'); },
    'ceremony': () => act(() => api('PATCH', 'dashboard', { show_ceremony: !T.dashboard.show_ceremony }), T.dashboard.show_ceremony ? 'Siegerehrung beendet' : 'Siegerehrung wird im Dashboard angezeigt'),
    'pay': el => { const id = +el.dataset.id; return act(() => api('PATCH', 'players/' + id, el.dataset.k === 'ng' ? { ng_paid: true } : { nk_paid: true })); }
  };

  // toggle switches react only to the switch itself, not to the adjacent label text
  document.addEventListener('click', ev => {
    const l = ev.target.closest && ev.target.closest('label.sw');
    if (l && ev.target.tagName !== 'INPUT' && !ev.target.closest('.sw > i')) ev.preventDefault();
  }, true);

  document.addEventListener('click', ev => {
    const el = ev.target.closest('[data-act]');
    if (!el) return;
    const a = el.dataset.act;
    if (modal && modal.handlers[a]) {
      if (a === 'm-back') { modal.handlers[a](el, ev); return; }
      if (el.tagName === 'A') return;
      modal.handlers[a](el, ev); ev.stopPropagation(); return;
    }
    if (modal && a !== 'undo') {
      // ignore clicks on elements behind the modal
      if (!$('#modal').contains(el)) return;
    }
    if (H[a]) { ev.preventDefault(); H[a](el, ev); }
  });
  document.addEventListener('keydown', ev => {
    if (ev.key === 'Enter' && ev.target && ev.target.id === 'p-name') { ev.preventDefault(); addPlayer(); }
    if (ev.key === 'Escape' && modal) closeModal();
  });
  document.addEventListener('input', ev => {
    if (ev.target.id === 'p-search') { ui.search = ev.target.value; if (tab === 'players') renderPlayers($('#view')); }
    if (ev.target.id === 'p-ng') ui.addNg = ev.target.checked;
  });
  document.addEventListener('change', ev => {
    const t = ev.target;
    if (t.dataset && t.dataset.chg === '1') dashChange();
    if (t.id === 'imp' && t.files && t.files[0]) {
      const f = t.files[0];
      const rd = new FileReader();
      rd.onload = async () => {
        let j; try { j = JSON.parse(rd.result); } catch (e) { toast('Keine gültige JSON-Datei.', 'err'); return; }
        if (await confirmBox('Backup importieren?', 'Es wird ein neues Turnier im Archiv angelegt.', 'Importieren')) await act(() => api('POST', 'import', j), 'Importiert (im Archiv, noch nicht aktiv)');
        t.value = '';
      };
      rd.readAsText(f);
    }
  });

  /* ---------------- Startup ---------------- */
  live('/admin/api/', setState, ok => {
    const s = $('#a-sync'); s.className = 'sync ' + (ok ? 'ok' : 'bad'); s.innerHTML = ok ? '&#9679; live' : '&#9679; getrennt – verbinde neu …';
  }, 4000);
})();
