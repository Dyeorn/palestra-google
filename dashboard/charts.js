// Gráficos em SVG/HTML puro (sem dependências: roda 100% offline).
const NS = 'http://www.w3.org/2000/svg';
const nf = new Intl.NumberFormat('pt-BR');
export const fmt = {
  int: v => v == null ? '–' : nf.format(Math.round(v)),
  dec: (v, d = 1) => v == null ? '–' : v.toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d }),
  pct: v => v == null ? '–' : fmt.dec(v, 1) + '%',
  brl: (v, d = 2) => v == null ? '–' : 'R$ ' + v.toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d }),
  ms: v => v == null ? '–' : v >= 1000 ? fmt.dec(v / 1000, 1) + ' s' : Math.round(v) + ' ms',
  dia: s => s ? s.slice(8, 10) + '/' + s.slice(5, 7) : '',
};
export const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

const tip = () => document.getElementById('tip');
export function showTip(ev, html) {
  const t = tip(); t.innerHTML = html; t.style.opacity = 1;
  const r = t.getBoundingClientRect();
  let x = ev.clientX + 14, y = ev.clientY + 14;
  if (x + r.width > innerWidth - 8) x = ev.clientX - r.width - 14;
  if (y + r.height > innerHeight - 8) y = ev.clientY - r.height - 14;
  t.style.left = x + 'px'; t.style.top = y + 'px';
}
export const hideTip = () => { tip().style.opacity = 0; };
export function hover(el, htmlFn) {
  el.addEventListener('mousemove', e => showTip(e, htmlFn()));
  el.addEventListener('mouseleave', hideTip);
}

function s(tag, attrs = {}, parent) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}
// máximo do eixo = 4 passos "redondos" (1, 2, 5 ou 10 × 10^k), para os rótulos saírem inteiros
const niceMax = v => {
  if (!(v > 0)) return 1;
  const q = v / 4, p = Math.pow(10, Math.floor(Math.log10(q))), f = q / p;
  return 4 * (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p;
};

/**
 * Linhas / áreas. series: [{nome, cor, valores, area?}]  (valores pode ter null = buraco)
 * o: {labels, height, yFmt, tipFmt, yMax, yMin, stack, ref:{valor,texto}, xTicks}
 */
export function lineChart(el, series, o) {
  el.innerHTML = '';
  const W = Math.max(280, el.clientWidth), H = o.height || 220, m = { l: 58, r: 26, t: 12, b: 26 };
  const svg = s('svg', { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img', 'aria-label': o.aria || '' }, el);
  const n = o.labels.length;
  const stacked = o.stack ? series.map((_, i) => series[0].valores.map((_, k) => series.slice(0, i + 1).reduce((a, x) => a + (x.valores[k] || 0), 0))) : null;
  const all = stacked ? stacked[stacked.length - 1] : series.flatMap(x => x.valores).filter(v => v != null);
  if (o.ref) all.push(o.ref.valor);
  const yMax = o.yMax ?? niceMax(Math.max(...all, 0) * 1.05), yMin = o.yMin ?? 0;
  const X = i => m.l + (n <= 1 ? (W - m.l - m.r) / 2 : i * (W - m.l - m.r) / (n - 1));
  const Y = v => m.t + (H - m.t - m.b) * (1 - (v - yMin) / ((yMax - yMin) || 1));
  const yf = o.yFmt || fmt.int;
  m.l = Math.max(46, 14 + 7.4 * Math.max(...[0, 1, 2, 3, 4].map(k => yf(yMin + (yMax - yMin) * k / 4).length)));
  for (let k = 0; k <= 4; k++) {
    const v = yMin + (yMax - yMin) * k / 4, y = Y(v);
    s('line', { x1: m.l, x2: W - m.r, y1: y, y2: y, class: 'grid' }, svg);
    s('text', { x: m.l - 8, y: y + 4, 'text-anchor': 'end' }, svg).textContent = yf(v);
  }
  const ticks = o.xTicks || 6, step = Math.max(1, Math.ceil(n / ticks));
  o.labels.forEach((l, i) => { if (i % step === 0) s('text', { x: X(i), y: H - 6, 'text-anchor': 'middle' }, svg).textContent = l; });
  if (o.ref) {
    const y = Y(o.ref.valor);
    s('line', { x1: m.l, x2: W - m.r, y1: y, y2: y, class: 'ref' }, svg);
    s('text', { x: W - m.r - 4, y: y - 6, 'text-anchor': 'end', class: 'reftxt' }, svg).textContent = o.ref.texto;
  }
  const path = (vals, base) => {
    let d = '', pen = false;
    vals.forEach((v, i) => { if (v == null) { pen = false; return; } d += (pen ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1); pen = true; });
    return d;
  };
  if (stacked) {
    for (let i = series.length - 1; i >= 0; i--) {
      const top = stacked[i], bot = i ? stacked[i - 1] : top.map(() => 0);
      let d = 'M' + X(0) + ' ' + Y(top[0]);
      top.forEach((v, k) => { d += 'L' + X(k).toFixed(1) + ' ' + Y(v).toFixed(1); });
      for (let k = n - 1; k >= 0; k--) d += 'L' + X(k).toFixed(1) + ' ' + Y(bot[k]).toFixed(1);
      s('path', { d: d + 'Z', fill: series[i].cor, 'fill-opacity': .85, stroke: 'var(--surface)', 'stroke-width': 2 }, svg);
    }
  } else series.forEach(x => {
    if (x.area) {
      const pts = x.valores.map((v, i) => v == null ? null : [X(i), Y(v)]).filter(Boolean);
      if (pts.length) s('path', { d: 'M' + pts[0][0] + ' ' + Y(yMin) + pts.map(p => 'L' + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join('') + 'L' + pts[pts.length - 1][0] + ' ' + Y(yMin) + 'Z', fill: x.cor, 'fill-opacity': .14 }, svg);
    }
    s('path', { d: path(x.valores), fill: 'none', stroke: x.cor, 'stroke-width': 2.5, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }, svg);
    const last = x.valores.map((v, i) => v == null ? -1 : i).filter(i => i >= 0).pop();
    if (last != null && last >= 0) s('circle', { cx: X(last), cy: Y(x.valores[last]), r: 4.5, fill: x.cor, stroke: 'var(--surface)', 'stroke-width': 2 }, svg);
  });
  // hover: cursor vertical + tooltip
  const cur = s('line', { y1: m.t, y2: H - m.b, stroke: 'var(--ink-2)', 'stroke-width': 1, opacity: 0 }, svg);
  const dots = series.map(x => s('circle', { r: 5, fill: x.cor, stroke: 'var(--surface)', 'stroke-width': 2, opacity: 0 }, svg));
  const hit = s('rect', { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: 'transparent' }, svg);
  hit.addEventListener('mousemove', e => {
    const r = svg.getBoundingClientRect(), px = (e.clientX - r.left) * W / r.width;
    const i = Math.max(0, Math.min(n - 1, Math.round((px - m.l) / ((W - m.l - m.r) / Math.max(1, n - 1)))));
    cur.setAttribute('x1', X(i)); cur.setAttribute('x2', X(i)); cur.setAttribute('opacity', 1);
    const tf = o.tipFmt || yf;
    let html = `<b>${esc(o.labels[i])}</b>`;
    series.forEach((x, k) => {
      const v = x.valores[i];
      dots[k].setAttribute('opacity', v == null ? 0 : 1);
      if (v != null) { dots[k].setAttribute('cx', X(i)); dots[k].setAttribute('cy', Y(stacked ? stacked[k][i] : v)); }
      html += `<br><span class="sw" style="background:${x.cor}"></span>${esc(x.nome)}: ${v == null ? '–' : tf(v)}`;
    });
    showTip(e, html);
  });
  hit.addEventListener('mouseleave', () => { cur.setAttribute('opacity', 0); dots.forEach(d => d.setAttribute('opacity', 0)); hideTip(); });
}

/** Barras horizontais em HTML. rows: [{nome, sub, valores:[{v, cor, nome}], texto, chip, tip}] */
export function hbars(el, rows, o = {}) {
  const max = o.max ?? Math.max(1, ...rows.flatMap(r => r.valores.map(x => x.v)));
  el.innerHTML = '<div class="barras">' + rows.map((r, i) => `
    <div class="linha-barra" data-i="${i}">
      <div class="nome">${esc(r.nome)}${r.chip ? `<span class="chip ${r.chipNeutro ? 'neutro' : ''}">${esc(r.chip)}</span>` : ''}${r.sub ? `<small>${esc(r.sub)}</small>` : ''}</div>
      <div class="trilhos">${r.valores.map(x => `<div class="trilho"><div class="barra" style="width:${Math.max(0, x.v) / max * 100}%;background:${x.cor}"></div></div>`).join('')}</div>
      <div class="val">${esc(r.texto)}</div></div>`).join('') + '</div>';
  el.querySelectorAll('.linha-barra').forEach(n => { const r = rows[+n.dataset.i]; if (r.tip) hover(n, () => r.tip); });
}

export function legenda(items) {
  return '<div class="legenda">' + items.map(([c, t, q]) => `<span><i class="${q ? 'q' : ''}" style="background:${c}"></i>${esc(t)}</span>`).join('') + '</div>';
}

export function tabela(cols, rows) {
  return `<div class="tabela-wrap"><table class="tabela"><thead><tr>${cols.map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>` +
    rows.map(r => `<tr>${r.map(c => `<td>${esc(c)}</td>`).join('')}</tr>`).join('') + '</tbody></table></div>';
}

/** vermelho → cinza → verde para -1..+1 */
export function divergente(v) {
  const t = Math.max(-1, Math.min(1, v ?? 0)), g = [138, 138, 132];
  const end = t < 0 ? [230, 103, 103] : [63, 179, 127], a = Math.abs(t);
  return `rgb(${g.map((c, i) => Math.round(c + (end[i] - c) * a)).join(',')})`;
}

export const CAT = ['#199e70', '#9085e9', '#c98500', '#d55181', '#3987e5', '#d95926']; // validada (modo escuro)

/** Rosca com legenda. fatias: [{nome, valor, cor?}] */
export function donut(el, fatias, o = {}) {
  const tot = fatias.reduce((a, x) => a + x.valor, 0) || 1, S = o.size || 170, r = S / 2 - 16, sw = 26, L = 2 * Math.PI * r;
  fatias.forEach((f, i) => f.cor = f.cor || CAT[i % CAT.length]);
  let acc = 0;
  const arcs = fatias.map(f => {
    const len = f.valor / tot * L, gap = fatias.length > 1 ? 2.5 : 0;
    const c = `<circle class="fatia" data-i="${fatias.indexOf(f)}" cx="${S / 2}" cy="${S / 2}" r="${r}" fill="none" stroke="${f.cor}" stroke-width="${sw}"
      stroke-dasharray="${Math.max(0, len - gap)} ${L}" stroke-dashoffset="${-acc}" transform="rotate(-90 ${S / 2} ${S / 2})"/>`;
    acc += len; return c;
  }).join('');
  el.innerHTML = `<div class="rosca"><svg viewBox="0 0 ${S} ${S}" width="${S}" height="${S}" role="img" aria-label="${esc(o.aria || '')}">${arcs}
      <text x="${S / 2}" y="${S / 2 + 2}" text-anchor="middle" class="rosca-n">${esc(o.centro ?? fmt.int(tot))}</text>
      <text x="${S / 2}" y="${S / 2 + 22}" text-anchor="middle">${esc(o.centroTxt || 'total')}</text></svg>
    <ul class="rosca-leg">${fatias.map(f => `<li><i style="background:${f.cor}"></i><span class="n">${esc(f.nome)}</span><b>${esc(o.fmtValor ? o.fmtValor(f.valor) : fmt.int(f.valor))}</b><em>${fmt.dec(100 * f.valor / tot, 0)}%</em></li>`).join('')}</ul></div>`;
  el.querySelectorAll('.fatia').forEach(c => hover(c, () => { const f = fatias[+c.dataset.i]; return `<b>${esc(f.nome)}</b><br>${esc(o.fmtValor ? o.fmtValor(f.valor) : fmt.int(f.valor))} (${fmt.dec(100 * f.valor / tot, 1)}%)`; }));
}

/**
 * Barras verticais (agrupadas se houver >1 série). series: [{nome, cor, valores, cores?}]
 * o: {labels, height, yFmt, tipFmt, yMax, rotulos:boolean}
 */
export function barChart(el, series, o) {
  el.innerHTML = '';
  const W = Math.max(240, el.clientWidth), H = o.height || 200, m = { l: 40, r: 8, t: 18, b: 26 }, n = o.labels.length;
  const yf = o.yFmt || fmt.int;
  const max = o.yMax ?? (() => { const v = Math.max(...series.flatMap(x => x.valores.map(q => q || 0)), 0) * 1.08; if (!(v > 0)) return 1; const q = v / 4, p = Math.pow(10, Math.floor(Math.log10(q))), f = q / p; return 4 * (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p; })();
  m.l = Math.max(36, 12 + 7.2 * Math.max(...[0, 1, 2, 3, 4].map(k => yf(max * k / 4).length)));
  const svg = s('svg', { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img', 'aria-label': o.aria || '' }, el);
  const Y = v => m.t + (H - m.t - m.b) * (1 - v / max), band = (W - m.l - m.r) / n, k = series.length;
  for (let g = 0; g <= 4; g++) {
    const y = Y(max * g / 4);
    s('line', { x1: m.l, x2: W - m.r, y1: y, y2: y, class: 'grid' }, svg);
    s('text', { x: m.l - 6, y: y + 4, 'text-anchor': 'end' }, svg).textContent = yf(max * g / 4);
  }
  const step = Math.max(1, Math.ceil(n * 38 / (W - m.l - m.r)));
  o.labels.forEach((l, i) => { if (i % step === 0) s('text', { x: m.l + band * (i + .5), y: H - 8, 'text-anchor': 'middle' }, svg).textContent = l; });
  const bw = Math.min(40, band * (k > 1 ? .8 : .66) / k), base = Y(0);
  series.forEach((sr, si) => sr.valores.forEach((v, i) => {
    if (v == null) return;
    const x = m.l + band * (i + .5) - bw * k / 2 + si * bw + (k > 1 ? 0 : 0), y = Y(v), h = Math.max(0, base - y), rr = Math.min(4, bw / 2, h);
    const cor = sr.cores?.[i] || sr.cor;
    s('path', { d: `M${x} ${base}V${y + rr}Q${x} ${y} ${x + rr} ${y}H${x + bw - rr - (k > 1 ? 1.5 : 0)}Q${x + bw - (k > 1 ? 1.5 : 0)} ${y} ${x + bw - (k > 1 ? 1.5 : 0)} ${y + rr}V${base}Z`, fill: cor }, svg);
    if (o.rotulos && n <= 8) s('text', { x: x + bw / 2, y: y - 5, 'text-anchor': 'middle', style: 'fill:var(--ink);font-weight:700' }, svg).textContent = (o.tipFmt || yf)(v);
  }));
  const hit = s('rect', { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: 'transparent' }, svg);
  const hl = s('rect', { y: m.t, height: H - m.t - m.b, width: band, fill: 'var(--ink)', opacity: 0 }, svg); hl.style.pointerEvents = 'none';
  hit.addEventListener('mousemove', e => {
    const r = svg.getBoundingClientRect(), px = (e.clientX - r.left) * W / r.width, i = Math.max(0, Math.min(n - 1, Math.floor((px - m.l) / band)));
    hl.setAttribute('x', m.l + band * i); hl.setAttribute('opacity', .06);
    showTip(e, `<b>${esc(o.tipLabels?.[i] ?? o.labels[i])}</b>` + series.map(x => `<br><span class="sw" style="background:${x.cores?.[i] || x.cor}"></span>${esc(x.nome)}: ${x.valores[i] == null ? '–' : (o.tipFmt || yf)(x.valores[i])}`).join(''));
  });
  hit.addEventListener('mouseleave', () => { hl.setAttribute('opacity', 0); hideTip(); });
}
