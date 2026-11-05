// Dashboard único: busca os 10 endpoints a cada poucos segundos e redesenha só o que mudou.
import { fmt } from './charts.js';
import { montarDash, desenharDash } from './dash.js';

const POLL_MS = 4000;
const dados = {}, json = {};
let coverage, ultimoOk = 0, resumo = null;
const root = document.getElementById('dash');

const acoes = {
  async toggleCaos(ativo) {
    await fetch('/api/caos', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ativo }) });
    await poll();
  },
};
const desenhar = () => desenharDash(dados, root, acoes);

async function poll() {
  try {
    let mudou = false;
    await Promise.all(coverage.paineis.map(async p => {
      const r = await fetch('/api/paineis/' + p.id); if (!r.ok) throw new Error(r.status);
      const t = await r.text();
      if (t !== json[p.id]) { json[p.id] = t; dados[p.id] = JSON.parse(t); mudou = true; }
    }));
    resumo = await (await fetch('/api/resumo')).json();
    ultimoOk = Date.now();
    document.getElementById('vivo').classList.remove('off');
    if (mudou) desenhar();
  } catch (e) { document.getElementById('vivo').classList.add('off'); }
  status();
}

function status() {
  if (!ultimoOk) return;
  const el = document.getElementById('vivo-texto'), seg = Math.round((Date.now() - ultimoOk) / 1000);
  if (seg > 15) { document.getElementById('vivo').classList.add('off'); el.textContent = 'sem conexão com a API'; return; }
  el.textContent = `ao vivo · ${fmt.int(resumo?.conversas)} conversas · atualizado há ${seg} s${resumo?.caos_ativo ? ' · CAOS LIGADO' : ''}`;
}

let rz; addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(desenhar, 150); });

(async function init() {
  coverage = await (await fetch('/api/coverage')).json();   // coverage.json = fonte única de rótulos
  const r = coverage.rotulos;
  document.getElementById('legenda-origem').innerHTML =
    `<span class="lg"><i class="traco bq"></i>${r.bq.texto}</span><span class="lg"><i class="traco ex"></i>${r.exclusivo.texto}</span>`;
  montarDash(root);
  await poll();
  setInterval(poll, POLL_MS); setInterval(status, 1000);
})();
