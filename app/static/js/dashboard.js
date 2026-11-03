/* Dashboard: display only, live via SSE */
(function () {
  const { esc, ic, heartsHtml, cellHtml, money, live, SUITS } = SN;
  const $ = id => document.getElementById(id);
  const stage = $('stage');
  let S = null;            // latest state
  let slotIdx = 0;         // index into the rotation
  let slotTimer = null;
  let baseline = null;     // draw identifier seen on first load
  let forceTables = false;
  const qs = new URLSearchParams(location.search);
  const FORCE = qs.get('view');   // debug: ?view=matrix&page=1
  const FORCE_PAGE = parseInt(qs.get('page') || '0', 10);

  /* ---------------- Header ---------------- */
  function header() {
    const t = S.tournament;
    $('t-name').textContent = t ? t.name : 'Preisschnapsen';
    const rn = $('t-round'), st = $('t-stat'), al = $('t-alive');
    if (!t) { rn.hidden = true; st.textContent = 'Kein Turnier'; al.textContent = ''; return; }
    const cur = S.round_progress;
    const total = S.counts.total;
    rn.hidden = true;
    let stat = '';
    switch (S.phase) {
      case 'signup': stat = 'Anmeldung offen'; break;
      case 'ready': stat = 'Auslosung folgt'; break;
      case 'drawing': stat = 'Auslosung läuft'; rn.hidden = !cur; if (cur) rn.textContent = 'Runde ' + (cur.number + 1); break;
      case 'running': stat = 'Runde läuft – ' + cur.done + '/' + cur.total + ' Tische fertig'; rn.hidden = false; rn.textContent = 'Runde ' + cur.number; break;
      case 'closed': stat = 'Runde abgeschlossen'; rn.hidden = false; rn.textContent = 'Runde ' + cur.number; break;
      case 'finished': stat = 'Turnier beendet'; break;
    }
    if (S.phase === 'drawing' && cur) rn.textContent = 'Runde ' + (cur.number + 1);
    if (S.phase === 'drawing' && !cur) { rn.hidden = false; rn.textContent = 'Runde 1'; }
    if (S.phase === 'ready') { rn.hidden = false; rn.textContent = 'Runde 1'; }
    st.textContent = stat;
    al.textContent = S.phase === 'signup' ? total + ' Teilnehmer' : 'noch im Spiel: ' + S.counts.alive + ' von ' + total;
  }
  function clock() {
    const d = new Date();
    $('t-clock').textContent = String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
  }

  /* ---------------- Helpers ---------------- */
  function P(id) { return S.players.find(p => p.id === id); }
  function name(id) { const p = P(id); return p ? p.label : '?'; }
  function currentRound() { return S.rounds.length ? S.rounds[S.rounds.length - 1] : null; }
  function chunk(arr, n) { const out = []; for (let i = 0; i < arr.length; i += n) out.push(arr.slice(i, i + n)); return out.length ? out : [[]]; }
  function sortedPlayers() {
    const rank = p => (p.status === 'out' ? 1 : 0);
    return S.players.slice().sort((a, b) => rank(a) - rank(b) || a.number - b.number);
  }
  const AVAIL_H = () => stage.clientHeight - 54;
  const AVAIL_W = () => stage.clientWidth - 72;

  /* ---------------- Views: each {pages, render(page)} ---------------- */
  const views = {};

  views.signup = {
    pages: () => 1,
    render() {
      const pl = S.players.slice().sort((a, b) => a.number - b.number);
      const n = pl.length;
      const cols = n > 60 ? 5 : 4;
      const rows = Math.ceil(n / cols) || 1;
      const fs = Math.max(20, Math.min(40, Math.floor((AVAIL_H() - 120) / Math.max(rows, 10) / 1.3)));
      return '<div class="signup"><h2>' + ic('eichel') + ' Anmeldung – ' + n + ' Teilnehmer ' + ic('gras') + '</h2>' +
        '<div class="names" style="columns:' + cols + ';font-size:' + fs + 'px">' +
        pl.map(p => '<div><b>' + p.number + '</b>' + esc(p.label) + '</div>').join('') + '</div></div>';
    }
  };

  function bestCols(T) {
    const W = AVAIL_W(), H = AVAIL_H(), gap = 18;
    let best = 1, bs = -1;
    for (let c = 1; c <= Math.min(T, 12); c++) {
      const rows = Math.ceil(T / c);
      const tw = (W - gap * (c - 1)) / c, th = (H - gap * (rows - 1)) / rows;
      // usable size of a card laid out at 1.75:1; portrait cards waste space, so prefer landscape
      const sc = Math.min(tw / 1.75, th) * (tw >= th ? 1 : 0.85);
      if (sc > bs) { bs = sc; best = c; }
    }
    return best;
  }
  views.tables = {
    pages: () => 1,
    render() {
      const r = currentRound();
      if (!r) return '<div class="empty">' + ic('schelln') + '<br>Auslosung folgt</div>';
      const tiles = r.pairings.slice();
      const T = tiles.length;
      const cols = bestCols(T), rows = Math.ceil(T / cols);
      const sc = (...ns) => '--s:' + Math.max(0.6, Math.min(1, 13 / Math.max(...ns.map(n => n.length)))).toFixed(2);
      // Playing-card style: one suit per corner, table number in a medallion.
      const corners = '<span class="cn tl">' + ic('eichel') + '</span><span class="cn tr">' + ic('gras') + '</span>' +
        '<span class="cn bl">' + ic('herz') + '</span><span class="cn br">' + ic('schelln') + '</span>';
      const tone = n => ['t-eichel', 't-gras', 't-herz', 't-schelln'][((n || 1) - 1) % 4];
      const medal = (label, cls) => '<div class="medal ' + cls + '"><b>' + label + '</b><small>' + (label === 'F' ? 'Freilos' : 'Tisch') + '</small></div>';
      const dots = n => '<span class="bummerl" title="' + n + '. Bummerl">' + Array.from({ length: Math.min(3, n) }, () => ic('bummerl')).join('') + '</span>';
      const cards = tiles.map(pr => {
        if (pr.bye) {
          return '<div class="card bye" style="' + sc(name(pr.a)) + '">' + corners + medal('F', 't-schelln') +
            '<div class="ci"><div class="pl"><span class="nmx">' + esc(name(pr.a)) + '</span></div>' +
            '<div class="vs">kampflos weiter</div></div></div>';
        }
        const done = pr.winner != null;
        const line = (id) => {
          let h = '<span class="nmx">' + esc(name(id)) + '</span>';
          if (done && id === pr.winner) h = '<span class="crown">✓</span>' + h;
          if (done && id !== pr.winner) {
            const c = P(id).cells.find(c => c.round === r.number);
            if (c && c.loss_no) h += dots(c.loss_no);
          }
          return '<div class="pl ' + (done ? (id === pr.winner ? 'win' : 'lose') : '') + '">' + h + '</div>';
        };
        const sty = sc(name(pr.a), name(pr.b));
        return '<div class="card ' + (done ? 'done' : 'open') + '" style="' + sty + '">' + corners + medal(pr.table, tone(pr.table)) +
          (done ? '' : '<span class="status">läuft</span>') +
          '<div class="ci">' + line(pr.a) + '<div class="vs">gegen</div>' + line(pr.b) + '</div></div>';
      }).join('');
      return '<div class="tgrid" style="grid-template-columns:repeat(' + cols + ',1fr);grid-template-rows:repeat(' + rows + ',1fr)">' + cards + '</div>';
    }
  };

  views.players = {
    pages() { return chunk(S.players, 36).length; },
    render(page) {
      const all = sortedPlayers();
      const pages = chunk(all, 36);
      const list = pages[Math.min(page, pages.length - 1)];
      const n = list.length;
      const cols = all.length > 16 ? 3 : 2;
      const rows = Math.max(Math.ceil(n / cols), all.length > 36 ? 12 : 6);
      const rowH = AVAIL_H() / rows;
      const fs = Math.max(20, Math.min(cols === 3 ? (all.length > 24 ? 30 : 34) : 44, Math.floor(rowH * 0.46)));
      const items = list.map(p => {
        const out = p.status === 'out';
        let st = '';
        if (out) st = '<span class="st">R' + p.elim_round + '</span>';
        else if (p.status === 'nk_open') st = '<span class="st nkopen">NK?</span>';
        return '<div class="prow ' + (out ? 'out' : '') + '"><span class="no">' + p.number + '</span><span class="nm">' + esc(p.label) + '</span>' +
          (p.nk_bought ? '<span class="nktag">NK</span>' : '') + st + heartsHtml(p.hearts) + '</div>';
      }).join('');
      return '<div class="pgrid" style="font-size:' + fs + 'px;grid-template-columns:repeat(' + cols + ',1fr);grid-template-rows:repeat(' + rows + ',1fr)">' + items + '</div>';
    }
  };

  views.matrix = {
    perPage() { const n = S.players.length; if (n <= 18) return Math.max(n, 1); return Math.ceil(n / Math.ceil(n / 18)); },
    pages() { return chunk(sortedMatrix(), this.perPage()).length; },
    render(page) {
      const pages = chunk(sortedMatrix(), this.perPage());
      const list = pages[Math.min(page, pages.length - 1)];
      const nr = Math.max(S.current_round, 1);
      const rowH = Math.min(62, (AVAIL_H() - 6) / (list.length + 1));
      const fs = Math.max(16, Math.floor(rowH * 0.56));
      const head = '<tr><th>Nr.</th><th>Name</th><th>NK</th>' + Array.from({ length: nr }, (_, i) => '<th>' + (i + 1) + '</th>').join('') + '</tr>';
      const rows = list.map(p => {
        const byR = {}; p.cells.forEach(c => byR[c.round] = c);
        return '<tr class="' + (p.status === 'out' ? 'out' : '') + '" style="height:' + rowH + 'px"><td class="nr">' + p.number + '</td><td class="nm">' + esc(p.label) + '</td><td>' + (p.nk_bought ? '✓' : '') + '</td>' +
          Array.from({ length: nr }, (_, i) => '<td>' + cellHtml(byR[i + 1]) + '</td>').join('') + '</tr>';
      }).join('');
      return '<div class="mxwrap"><table class="mx" style="font-size:' + fs + 'px">' + head + rows + '</table></div>';
    }
  };
  function sortedMatrix() { return S.players.slice().sort((a, b) => a.number - b.number); }

  function entryHtml(e, cls) {
    const names = e.players.map(name);
    let who;
    if (e.active && !S.finished) who = 'Noch im Spiel (' + names.length + ')<small>' + esc(names.join(' · ')) + '</small>';
    else if (names.length > 8) who = names.length + ' Spieler';
    else who = esc(names.join(' · '));
    const sub = e.needs_playoff ? '<small>Platzierungsspiel offen</small>' : '';
    if (e.active && !S.finished) {
      return '<div class="rk-item live" style="grid-column:1/-1"><span class="pl">' + e.label + '</span><span class="who" style="font-size:.8em">' + who + '</span></div>';
    }
    return '<div class="rk-item ' + (e.place_from === 1 && S.finished ? 'first' : '') + ' ' + (cls || '') + '"><span class="pl">' + e.label + '</span><span class="who">' + who + sub + '</span>' +
      (e.prize ? '<span class="pr">' + esc(e.prize) + '</span>' : '') + '</div>';
  }
  views.ranking = {
    pages() { return this.split().length; },
    split() {
      const es = S.ranking.entries;
      const act = es.filter(e => e.active && !S.finished);
      const rest = es.filter(e => !(e.active && !S.finished));
      const pages = [];
      let first = true, i = 0;
      while (i < rest.length || first) {
        const cap = first && act.length ? 12 : 16;
        pages.push((first ? act : []).concat(rest.slice(i, i + cap)));
        i += cap; first = false;
      }
      return pages;
    },
    render(page) {
      const pages = this.split();
      const list = pages[Math.min(page, pages.length - 1)];
      const rowsN = Math.max(Math.ceil((list.length + 1) / 2), 6);
      const fs = Math.max(24, Math.min(46, Math.floor(AVAIL_H() / rowsN / 1.55)));
      return '<div class="rk" style="font-size:' + fs + 'px">' + list.map(e => entryHtml(e)).join('') + '</div>';
    }
  };

  views.cash = {
    pages: () => 1,
    render() {
      const c = S.cash;
      if (!c) return '<div class="empty">Kassa nicht freigegeben</div>';
      return '<div class="cash"><h2 style="font-size:64px;color:#ffe9a6">' + ic('schelln') + ' Preistopf</h2><table>' +
        '<tr><td>Nenngeld (' + c.ng_count + ' × ' + money(c.ng_amount) + ')</td><td>' + money(c.ng_sum) + '</td></tr>' +
        '<tr><td>Nachkäufe (' + c.nk_count + ' × ' + money(c.nk_amount) + ')</td><td>' + money(c.nk_sum) + '</td></tr>' +
        '<tr class="tot"><td>Gesamt</td><td>' + money(c.total) + '</td></tr></table></div>';
    }
  };

  views.ceremony = {
    pages: () => 1,
    render() {
      if (!S.finished) return '<div class="empty">' + ic('schelln') + '<br>Siegerehrung folgt</div>';
      const es = S.ranking.entries.filter(e => !(e.active && !S.finished));
      const pr = S.tournament.prize_ranks;
      const podium = es.slice(0, 3);
      const rest = es.slice(3).filter(e => e.place_from <= pr).slice(0, 18);
      const nm = e => e.players.map(name).join(' / ');
      const pod = (e, cls) => e ? '<div class="pod ' + cls + '"><div class="who">' + esc(nm(e)) + '</div>' + (e.prize ? '<div class="prz">' + esc(e.prize) + '</div>' : '') +
        '<div class="blk">' + e.label.replace('.–', '–').replace(/\.$/, '') + '</div></div>' : '<div></div>';
      const fsRest = rest.length > 12 ? 26 : 32;
      return '<div class="cer"><h2>' + ic('schelln') + ' Siegerehrung ' + ic('schelln') + '</h2><div class="podium">' +
        pod(podium[1], 'p2') + pod(podium[0], 'p1') + pod(podium[2], 'p3') + '</div>' +
        '<div class="cer-rest" style="font-size:' + fsRest + 'px">' + rest.map(e => '<div><b>' + e.label + '</b><span>' + esc(nm(e)) + '</span>' + (e.prize ? '<em>' + esc(e.prize) + '</em>' : '') + '</div>').join('') + '</div></div>';
    }
  };

  /* ---------------- Rotation ---------------- */
  function effective() {
    const t = S.tournament;
    if (!t) return { forced: null, list: [] };
    if (FORCE) return { forced: FORCE, list: [] };
    const b = t.dashboard;
    if (S.phase === 'signup') return { forced: 'signup', list: [] };
    if (b.show_ceremony || (S.finished && b.ceremony_auto)) return { forced: 'ceremony', list: [] };
    if (b.pinned && views[b.pinned]) {
      if (b.pinned === 'cash' && !t.show_cashbox) { /* cash view not enabled: fall through to rotation */ } else return { forced: b.pinned, list: [] };
    }
    let list = (b.views || ['tables', 'players', 'matrix', 'ranking']).filter(v => views[v]);
    if (t.show_cashbox && !list.includes('cash')) list = list.concat(['cash']);
    if (!t.show_cashbox) list = list.filter(v => v !== 'cash');
    if (S.phase === 'ready' || !S.rounds.length) list = list.filter(v => v === 'players' || v === 'tables');
    if (!list.length) list = ['tables'];
    return { forced: null, list };
  }
  function slots() {
    const e = effective();
    const secs = Math.max(3, (S.tournament && S.tournament.dashboard.rotate_seconds) || 20);
    const names = e.forced ? [e.forced] : e.list;
    const out = [];
    names.forEach(v => {
      const n = views[v].pages();
      for (let p = 0; p < n; p++) out.push({ view: v, page: p, ms: (n > 1 ? Math.max(8, secs / n) : secs) * 1000, solo: !!e.forced });
    });
    if (e.forced && out.length === 1) out[0].ms = 0;
    else if (e.forced) out.forEach(o => { o.ms = Math.max(8, secs / out.length) * 1000; });
    return out;
  }

  /* ---------------- Rendering with crossfade ---------------- */
  const REDUCED = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  let cur = null, curKey = '', curHtml = '';
  let rotTimer = null, rotMs = -1, rotKey = '';

  function paint(key, html, dur) {
    if (cur && key === curKey && html === curHtml) return;   // unchanged: leave the DOM alone
    const old = cur;
    Array.from(stage.children).forEach(c => { if (c !== old) c.remove(); });
    const el = document.createElement('div');
    el.className = 'view';
    el.innerHTML = html;
    const d = REDUCED ? 0 : dur;
    if (!old || d === 0) {
      if (old) old.remove();
      stage.appendChild(el);
    } else {
      el.style.opacity = '0';
      stage.appendChild(el);
      void el.offsetWidth;
      const tr = 'opacity ' + d + 'ms ease-in-out';
      el.style.transition = tr; old.style.transition = tr;
      el.style.opacity = '1'; old.style.opacity = '0';
      setTimeout(() => { if (old.parentNode) old.remove(); }, d + 60);
    }
    cur = el; curKey = key; curHtml = html;
  }

  function schedule(ms, key) {
    if (!ms) { clearTimeout(rotTimer); rotTimer = null; rotKey = ''; rotMs = -1; return; }
    if (rotTimer && rotKey === key && rotMs === ms) return;  // a running timer is not reset by updates
    clearTimeout(rotTimer);
    rotMs = ms; rotKey = key;
    rotTimer = setTimeout(() => {
      rotTimer = null;
      slotIdx = (slotIdx + 1) % Math.max(1, slots().length);
      show();
    }, ms);
  }

  function show() {
    if (!S) return;
    header();
    $('adminlink').hidden = S.role !== 'admin';
    if (!S.tournament) { paint('none', '<div class="empty">Kein aktives Turnier</div>', 600); return; }
    let sl = slots();
    if (FORCE) { sl = [{ view: FORCE, page: FORCE_PAGE, ms: 0 }]; }
    if (forceTables) {
      const i = sl.findIndex(s => s.view === 'tables');
      if (i >= 0) slotIdx = i;
      forceTables = false; rotKey = '';
    }
    if (slotIdx >= sl.length) slotIdx = 0;
    const s = sl[slotIdx];
    const v = views[s.view];
    const key = s.view + '|' + s.page;
    const html = v.render(s.page) + (sl.length > 1 && s.view !== 'tables' && v.pages() > 1 ? '<div class="vtitle pager">Seite ' + (s.page + 1) + '/' + v.pages() + '</div>' : '');
    paint(key, html, key !== curKey ? 700 : 300);
    schedule(s.ms, key);
  }

  /* ---------------- Draw animation ---------------- */
  function drawKey() { const ev = S.draw_event; return ev ? ev.round + '|' + ev.published_at : null; }
  function maybeAnimate() {
    const key = drawKey();
    if (key && key !== baseline) {
      baseline = key;
      if (S.tournament.dashboard.animation && S.phase === 'running' && !FORCE) { animate(S.draw_event.round); return; }
      forceTables = true;
    }
  }
  // Card pool: scans from static/img/cards (preloaded); drawn SVG cards when the pool is empty.
  let CARD_POOL = [];
  try { CARD_POOL = JSON.parse(($('cards-data') || {}).textContent || '[]'); } catch (e) { CARD_POOL = []; }
  CARD_POOL.forEach(src => { const im = new Image(); im.src = src; });
  function pickCards() {
    const pool = CARD_POOL.slice();
    for (let i = pool.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [pool[i], pool[j]] = [pool[j], pool[i]]; }
    return pool.slice(0, 4);
  }
  function cardFront(k) {
    return k.indexOf('/') >= 0 ? '<img src="' + esc(k) + '" alt="" draggable="false">'
      : '<svg viewBox="0 0 200 340" preserveAspectRatio="none" aria-hidden="true"><use href="#karte-' + k + '"/></svg>';
  }
  function animate(round) {
    const a = $('anim');
    const r = currentRound();
    const tables = r ? r.pairings.filter(p => !p.bye).length : 0;
    a.innerHTML = '<h2>Runde ' + round + ' wird ausgelost</h2><div class="deck">' +
      (CARD_POOL.length ? pickCards() : ['herz', 'schelln', 'gras', 'eichel']).map(k => '<div class="acard"><div class="inner">' +
        '<div class="face front">' + cardFront(k) + '</div>' +
        '<div class="face back"><svg viewBox="0 0 200 345" aria-hidden="true"><use href="#karte-rueckseite"/></svg></div></div></div>').join('') + '</div>' +
      '<h2 style="font-size:56px;margin-top:40px;color:#cfe8d5">' + tables + (tables === 1 ? ' Tisch' : ' Tische') + '</h2>';
    a.classList.add('show');
    forceTables = true;
    setTimeout(() => { a.classList.remove('show'); forceTables = true; show(); }, 3800);
  }

  /* ---------------- Startup ---------------- */
  function onState(s) {
    const first = !S;
    if (!first && s.version === S.version && s.role === S.role) return;   // identical state: nothing to do
    S = s;
    if (first) baseline = drawKey(); else maybeAnimate();
    if (!$('anim').classList.contains('show')) show();
  }
  live('api/', onState, ok => $('conn').classList.toggle('show', !ok), 3000);
  setInterval(clock, 5000); clock();
  let rsT; window.addEventListener('resize', () => { clearTimeout(rsT); rsT = setTimeout(() => { if (S) show(); }, 250); });

  /* Fullscreen button and cursor hiding */
  $('fs').addEventListener('click', () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else if (document.documentElement.requestFullscreen) document.documentElement.requestFullscreen();
  });
  let idleT;
  function wake() { document.body.classList.remove('idle'); clearTimeout(idleT); idleT = setTimeout(() => document.body.classList.add('idle'), 3000); }
  ['mousemove', 'mousedown', 'keydown', 'touchstart'].forEach(e => window.addEventListener(e, wake));
  wake();
})();
