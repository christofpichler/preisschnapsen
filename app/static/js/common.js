/* Helpers shared by dashboard and admin */
(function (g) {
  const SVG = '#';  // the sprite is injected inline by suits.js
  const SUITS = ['eichel', 'gras', 'herz', 'schelln'];
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  function ic(name, cls) {
    return '<svg class="ic ' + (cls || '') + '" aria-hidden="true"><use href="' + SVG + name + '"/></svg>';
  }
  function heartsHtml(h) {
    const hz = s => s === 'full' ? 'herz' : 'herz-leer';  // lost or missing lives are drawn as outlines
    return '<span class="hearts" title="Leben">' + ic(hz(h[0]), 'heart ' + h[0]) + '<span class="nkgap"></span>' +
      ic(hz(h[1]), 'heart nk ' + h[1]) + ic(hz(h[2]), 'heart nk ' + h[2]) + '</span>';
  }
  function cellHtml(c) {
    if (!c) return '';
    switch (c.kind) {
      case 'bye': return '<span class="sym bye">F</span>';
      case 'win': return '<span class="num">' + c.table + '</span><span class="c-win">+</span>';
      case 'loss1': return '<span class="num">' + c.table + '</span><span class="c-loss1">–</span>';
      case 'loss2': return '<span class="num">' + c.table + '</span><span class="sym nk">–</span>';
      default: return '<span class="num">' + c.table + '</span><span class="c-open">…</span>';
    }
  }
  function money(v) {
    const n = Number(v) || 0;
    return (Number.isInteger(n) ? String(n) : n.toFixed(2).replace('.', ',')) + ' €';
  }
  function uuid() {
    const b = new Uint8Array(16);
    (g.crypto || g.msCrypto).getRandomValues(b);
    b[6] = (b[6] & 15) | 64; b[8] = (b[8] & 63) | 128;
    const h = Array.from(b, x => x.toString(16).padStart(2, '0')).join('');
    return h.slice(0, 8) + '-' + h.slice(8, 12) + '-' + h.slice(12, 16) + '-' + h.slice(16, 20) + '-' + h.slice(20);
  }
  /* Live connection: SSE with polling fallback and automatic reconnect */
  function live(base, onState, onConn, pollMs) {
    let es = null, lastV = null, busy = false, again = false, sseOk = false, lastBeat = Date.now();
    async function refresh() {
      if (busy) { again = true; return; }
      busy = true;
      try {
        const r = await fetch(base + 'state', { cache: 'no-store', credentials: 'same-origin' });
        if (r.status === 401) { location.reload(); return; }
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const s = await r.json();
        lastV = s.version;
        onConn(true);
        onState(s);
      } catch (e) { onConn(false); }
      busy = false;
      if (again) { again = false; refresh(); }
    }
    function open() {
      try { if (es) es.close(); } catch (e) { }
      if (!g.EventSource) return;
      es = new EventSource(base + 'events');
      es.addEventListener('version', ev => {
        let v = null; try { v = JSON.parse(ev.data).v; } catch (e) { }
        sseOk = true; lastBeat = Date.now();
        if (v !== lastV) refresh();
      });
      es.addEventListener('hb', () => { sseOk = true; lastBeat = Date.now(); });
      es.onopen = () => { sseOk = true; lastBeat = Date.now(); };
      es.onerror = () => { sseOk = false; try { es.close(); } catch (e) { } setTimeout(open, 2000); };
    }
    let tick = 0;
    setInterval(() => {
      tick++;
      if (sseOk && Date.now() - lastBeat > 25000) { sseOk = false; onConn(false); open(); }
      if (!sseOk || tick % 3 === 0) refresh();
    }, pollMs || 3000);
    g.addEventListener('online', () => { refresh(); open(); });
    refresh(); open();
    return { refresh };
  }
  g.SN = { esc, ic, heartsHtml, cellHtml, money, uuid, live, SUITS };
})(window);
