// Aba "Dashboard": só dados, em grade, com barras, rosca e linhas. Usa os mesmos endpoints dos painéis.
import { fmt, esc, lineChart, barChart, donut, hbars, divergente, CAT } from './charts.js';

const C = { s1: '#199e70', s2: '#9085e9', bad: '#e66767' };
const NOMES = { buscar_produtos: 'Buscar produtos', consultar_estoque: 'Consultar estoque', recomendar_produtos: 'Recomendar produtos',
  aplicar_cupom: 'Aplicar cupom', criar_pedido: 'Criar pedido', registrar_reclamacao: 'Registrar reclamação' };
const NEED = ['conversas-por-dia', 'tempo-primeira-resposta', 'falhas-ferramentas', 'tokens-por-conversa', 'funil-vendas', 'motivos-abandono',
  'custo-por-venda', 'produtos-cupons-perfil', 'intencao-resolucao-sentimento', 'venda-perdida'];

// [id, título, origem do dado, colunas (de 12)]
const CARDS = [
  ['dia', 'Conversas por dia', 'bq', 6], ['funil', 'Funil de vendas', 'ex', 3], ['aband', 'Motivos de abandono', 'ex', 3],
  ['hora', 'Conversas por hora do dia (pico em amarelo)', 'bq', 4], ['tools', 'Taxa de erro por ferramenta (%)', 'bq', 4], ['perda', 'Conversão: lentidão e erro (%)', 'ex', 4],
  ['vivo', 'Conversão ao vivo (%/min)', 'ex', 4], ['intent', 'Conversas por intenção', 'ex', 4], ['perfil', 'Pedidos por perfil de cliente', 'ex', 4],
  ['prod', 'Produtos: citações × vendidos', 'ex', 5], ['ttft', 'Tempo até a 1ª resposta', 'bq', 4], ['cupom', 'Pedidos por cupom', 'ex', 3],
  ['rec', 'Receita por dia (R$)', 'ex', 4], ['tok', 'Tokens por conversa', 'bq', 4], ['sent', 'Sentimento médio por dia', 'ex', 4],
];

export function montarDash(root) {
  root.innerHTML = `<div class="kpi-faixa" id="d-kpis"></div><div class="dgrade">` + CARDS.map(([id, t, o, w]) =>
    `<section class="dcard" style="--w:${w}" data-w="${w}"><header><h3>${esc(t)}</h3><span class="traco ${o}" title="${o === 'bq' ? 'Também no plugin do BQ' : 'Exclusivo do nosso plugin'}"></span></header>
     <div class="dcorpo" id="d-${id}"></div></section>`).join('') + '</div>';
}

const kpi = (v, l, cls = '') => `<div class="dk ${cls}"><div class="v">${v}</div><div class="l">${esc(l)}</div></div>`;

export function desenharDash(dados, root, acoes) {
  if (!NEED.every(k => dados[k])) return;
  const D = k => dados[k].dados, $ = id => root.querySelector('#d-' + id);
  const dia = D('conversas-por-dia'), ttft = D('tempo-primeira-resposta'), ft = D('falhas-ferramentas'), tok = D('tokens-por-conversa'),
    fun = D('funil-vendas'), ab = D('motivos-abandono'), cv = D('custo-por-venda'), pr = D('produtos-cupons-perfil'),
    it = D('intencao-resolucao-sentimento'), vp = D('venda-perdida');

  // KPIs
  const erroTools = 100 * ft.total_falhas / Math.max(1, ft.total_chamadas);
  $('kpis').innerHTML = [kpi(fmt.int(dia.total), 'conversas'), kpi(fmt.pct(fun.de_cada_100), 'conversão'), kpi(fmt.brl(cv.receita, 0), `receita · ${fmt.int(cv.pedidos)} pedidos`),
    kpi(fmt.brl(cv.ticket_medio), 'ticket médio'), kpi(fmt.brl(cv.custo_por_venda, 3), 'custo por venda'), kpi(fmt.pct(it.geral.pct_resolvido), 'resolvidas'),
    kpi(fmt.pct(erroTools), 'erro de ferramentas', erroTools > 8 ? 'ruim' : ''), kpi(fmt.ms(ttft.p95_ms), '1ª resposta (p95)', ttft.p95_ms > ttft.meta_ms ? 'ruim' : '')].join('');

  // linhas / barras
  lineChart($('dia'), [{ nome: 'Conversas', cor: C.s1, valores: dia.por_dia.map(x => x.conversas), area: true }], { labels: dia.por_dia.map(x => fmt.dia(x.dia)), height: 210, aria: 'Conversas por dia' });
  const porHora = Array(24).fill(0); dia.mapa_calor.forEach(c => porHora[c.hora] += c.conversas);
  const pico = Math.max(...porHora);
  barChart($('hora'), [{ nome: 'Conversas', cor: C.s1, cores: porHora.map(v => v === pico ? '#c98500' : C.s1), valores: porHora }], { labels: porHora.map((_, h) => h + 'h'), height: 210, aria: 'Conversas por hora' });

  // funil: barras horizontais
  hbars($('funil'), fun.etapas.map((e, i) => ({ nome: e.nome.replace('Recebeu recomendação', 'Recomendação'), valores: [{ v: e.valor, cor: i === fun.maior_vazamento ? C.bad : C.s1 }], texto: fmt.int(e.valor),
    tip: `<b>${esc(e.nome)}</b><br>${e.valor} conversas (${fmt.pct(e.pct_do_total)})` })), { max: fun.etapas[0].valor });

  donut($('aband'), ab.motivos.map(m => ({ nome: m.motivo, valor: m.conversas })), { centroTxt: 'abandonos', aria: 'Motivos de abandono' });
  hbars($('tools'), ft.ferramentas.map((f, i) => ({ nome: NOMES[f.ferramenta] || f.ferramenta, valores: [{ v: f.taxa_erro_pct, cor: i === 0 ? C.bad : C.s2 }], texto: fmt.pct(f.taxa_erro_pct),
    tip: `<b>${esc(NOMES[f.ferramenta])}</b><br>${f.falhas} falhas em ${f.chamadas} chamadas` })), { max: Math.max(10, ...ft.ferramentas.map(f => f.taxa_erro_pct)) });

  // conversão x lentidão/erro (barras verticais)
  const lab = [...vp.por_latencia.map(x => x.faixa), ...vp.por_erro.map(x => x.grupo)];
  const vals = [...vp.por_latencia.map(x => x.conversao_pct), ...vp.por_erro.map(x => x.conversao_pct)];
  const bl = vp.por_latencia[0]?.conversao_pct ?? 0, be = vp.por_erro[0]?.conversao_pct ?? 0; // vermelho só se cair > 5 pontos vs. a base
  const cores = [...vp.por_latencia.map((x, i) => i && x.conversao_pct < bl - 5 ? C.bad : C.s1), ...vp.por_erro.map((x, i) => i && x.conversao_pct < be - 5 ? C.bad : C.s1)];
  barChart($('perda'), [{ nome: 'Conversão', cor: C.s1, cores, valores: vals }], { labels: lab.map(l => l.replace('sem erro', 'sem erro').replace('com erro', 'com erro')), height: 210, yMax: 100, yFmt: x => fmt.int(x) + '%', tipFmt: fmt.pct, rotulos: true,
    tipLabels: [...vp.por_latencia.map(x => `Resposta ${x.faixa} · ${x.conversas} conversas`), ...vp.por_erro.map(x => `${x.grupo} · ${x.conversas} conversas`)] });

  // ao vivo
  const vivo = vp.ao_vivo, el = $('vivo');
  const btn = `<button class="btn-caos ${vp.caos_ativo ? 'on' : ''}" id="d-caos">${vp.caos_ativo ? 'Desativar caos' : 'Ativar caos'}</button>`;
  el.innerHTML = btn + '<div class="graf" id="d-vivo-g"></div>';
  el.querySelector('#d-caos').onclick = () => acoes.toggleCaos(!vp.caos_ativo);
  const g = el.querySelector('#d-vivo-g');
  if (vivo.length < 2) g.innerHTML = '<div class="vazio">Sem tráfego ao vivo.<br><code>uv run python -m simulator.run --live</code></div>';
  else {
    const toMin = x => +x.slice(0, 2) * 60 + +x.slice(3), by = {}; vivo.forEach(x => by[toMin(x.minuto)] = x);
    let a = toMin(vivo[0].minuto); const z = toMin(vivo[vivo.length - 1].minuto), L = [], V = []; if (z < a) a -= 1440;
    for (let t = a; t <= z; t++) { const k = ((t % 1440) + 1440) % 1440; L.push(String(Math.floor(k / 60)).padStart(2, '0') + ':' + String(k % 60).padStart(2, '0')); V.push(by[k] ? by[k].conversao_pct : null); }
    lineChart(g, [{ nome: 'Conversão', cor: vp.caos_ativo ? C.bad : C.s1, valores: V }], { labels: L, height: 170, yMin: 0, yMax: 100, yFmt: x => fmt.int(x) + '%', tipFmt: fmt.pct });
  }

  donut($('intent'), it.intencoes.map(x => ({ nome: x.intencao, valor: x.conversas })), { centroTxt: 'conversas', aria: 'Conversas por intenção' });
  donut($('perfil'), pr.perfis.map(x => ({ nome: x.perfil, valor: x.pedidos })), { centroTxt: 'pedidos', aria: 'Pedidos por perfil' });

  barChart($('prod'), [{ nome: 'Citações', cor: C.s1, valores: pr.produtos.slice(0, 8).map(p => p.citacoes) }, { nome: 'Vendidos', cor: C.s2, valores: pr.produtos.slice(0, 8).map(p => p.vendidos) }],
    { labels: pr.produtos.slice(0, 8).map((p, i) => '#' + (i + 1)), tipLabels: pr.produtos.slice(0, 8).map(p => p.produto), height: 210 });
  $('prod').insertAdjacentHTML('beforeend', '<div class="legenda" style="margin-top:4px"><span><i class="q" style="background:#199e70"></i>citações</span><span><i class="q" style="background:#9085e9"></i>vendidos</span><span style="color:var(--ink-3)">#1 a #8 = produtos mais citados (passe o mouse)</span></div>');

  const h = [...Array(24).keys()], by = {}; ttft.por_hora.forEach(x => by[x.hora] = x);
  lineChart($('ttft'), [{ nome: 'p50', cor: C.s1, valores: h.map(x => by[x]?.p50_ms ?? null) }, { nome: 'p95', cor: C.s2, valores: h.map(x => by[x]?.p95_ms ?? null) }],
    { labels: h.map(x => x + 'h'), height: 210, yFmt: fmt.ms, tipFmt: fmt.ms, ref: { valor: ttft.meta_ms, texto: 'meta' }, xTicks: 8 });

  barChart($('cupom'), [{ nome: 'Pedidos', cor: '#c98500', valores: pr.cupons.map(c => c.pedidos) }], { labels: pr.cupons.map(c => c.cupom.replace('PRIMEIRA10', 'PRIM.10')), tipLabels: pr.cupons.map(c => c.cupom), height: 210, rotulos: true });
  lineChart($('rec'), [{ nome: 'Receita', cor: C.s1, valores: cv.por_dia.map(x => x.receita), area: true }], { labels: cv.por_dia.map(x => fmt.dia(x.dia)), height: 210, yFmt: x => fmt.brl(x, 0), tipFmt: x => fmt.brl(x) });
  lineChart($('tok'), [{ nome: 'Tokens por conversa', cor: C.s2, valores: tok.por_dia.map(x => x.tokens_por_conversa) }], { labels: tok.por_dia.map(x => fmt.dia(x.dia)), height: 210, yFmt: fmt.int });
  lineChart($('sent'), [{ nome: 'Sentimento', cor: C.s1, valores: it.sentimento_por_dia.map(x => x.sentimento) }],
    { labels: it.sentimento_por_dia.map(x => fmt.dia(x.dia)), height: 210, yMin: -1, yMax: 1, yFmt: x => fmt.dec(x, 1), tipFmt: x => fmt.dec(x, 2), ref: { valor: 0, texto: 'neutro' } });
}
