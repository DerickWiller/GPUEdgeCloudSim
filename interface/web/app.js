// Tela da interface do GPUEdgeCloudSim. Lê e dispara tudo pela API de interface/servidor.py.
"use strict";

const CORES = ["#2a78d6", "#eb6834", "#1baf7a", "#4a3aa7", "#eda100"];
// Cor fixa por política, a mesma dos slides; demais variáveis seguem CORES em ordem.
const COR_POLITICA = { LOCAL: "#eb6834", AUTO: "#2a78d6", LOCAL_FIRST: "#1baf7a" };
const corSerie = (campo, valor, i) => (campo === "politica" && COR_POLITICA[valor]) || CORES[i % CORES.length];
const NOME_POLITICA = { AUTO: "rodízio", LOCAL: "só local", LOCAL_FIRST: "menor tempo estimado" };
const PASTA_POLITICA = { AUTO: "rodizio", LOCAL: "local", LOCAL_FIRST: "local-primeiro" };
const CAMPOS = {
  politica: { rotulo: "Política de escolha da GPU", curto: "política", pasta: PASTA_POLITICA },
  dispositivos: { rotulo: "Dispositivos (total)", curto: "dispositivos", pasta: "{v:02d}-dispositivos" },
  "dispositivos_por_ponto.0": { rotulo: "Dispositivos no ponto de acesso 0", curto: "dispositivos no ponto 0", pasta: "{v:02d}-no-ponto-0" },
  "servidores.com_gpu": { rotulo: "Servidores com GPU", curto: "servidores com GPU", pasta: "{v:02d}-gpus" },
  "man.propagacao_ms": { rotulo: "Propagação da MAN (ms)", curto: "propagação da MAN (ms)", pasta: "prop-{v}ms" },
  "man.banda_mbps": { rotulo: "Banda da MAN (Mbps)", curto: "banda da MAN (Mbps)", pasta: "man-{v}mbps" },
};
const PADRAO = {
  nome: "", titulo: "", pergunta: "", duracao_min: 60, aquecimento_min: 5,
  servidores: { quantidade: 4, com_gpu: 4, modelo: "tocze" }, atratividade: "constante",
  carga: "yolo", dispositivos: 8, dispositivos_por_ponto: [4, 2, 1, 1], mobilidade: "por_ponto",
  ponto_fixo: 0, man: { ligada: true, banda_mbps: 1000, propagacao_ms: 10 }, politica: "AUTO",
  nuvem: "escala", variar: [{ campo: "politica", valores: ["LOCAL", "AUTO", "LOCAL_FIRST"] }], excluir: [],
};

let estado = { ambiente: {}, experimentos: [], baterias: [] };
let atual = null;          // experimento aberto
let pontoSel = null;       // pasta do ponto selecionado
let vista = "exp";
let assistente = null;     // { passo, cen, previa }
let temporizador = null;
const publicacoes = {};    // id da bateria -> mensagem do resultado da publicação

const $ = (s, r = document) => r.querySelector(s);
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (v, casas = 1) => (v == null || isNaN(v) ? "–" : Number(v).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas }));
const copia = (o) => JSON.parse(JSON.stringify(o));

async function api(caminho, corpo) {
  const r = await fetch(caminho, corpo === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.erro || `erro ${r.status}`);
  return d;
}

function rotuloValor(campo, v) {
  return campo === "politica" ? NOME_POLITICA[v] || v : (typeof v === "number" ? num(v, Number.isInteger(v) ? 0 : 2) : v);
}


async function atualizarEstado() {
  try {
    const antes = estado.baterias.filter((b) => !b.terminada).length;
    estado = await api("/api/estado");
    definirLimites(estado.limites);
    desenharCabecalho();
    desenharLista();
    if (vista === "exp" && atual) {
      desenharBaterias();
      const agora = estado.baterias.filter((b) => !b.terminada).length;
      if (agora < antes) await atualizarDados();
    }
  } catch (e) { console.error(e); }
  clearTimeout(temporizador);
  temporizador = setTimeout(atualizarEstado, estado.baterias.some((b) => !b.terminada) ? 2500 : 10000);
}

function desenharCabecalho() {
  const a = estado.ambiente;
  const java = /version "([^"]+)"/.exec(a.java || "");
  $("#ambiente").innerHTML = [
    `<span class="tag" title="branch do Git em uso">branch ${esc(a.branch || "?")}</span>`,
    `<span class="tag ${java ? "ok" : "nao"}">Java ${esc(java ? java[1] : "ausente")}</span>`,
    `<span class="tag ok">Python ${esc(a.python)}</span>`,
    `<span class="tag ${a.compilado ? "ok" : "nao"}">${a.compilado ? "compilado" : "não compilado"}</span>`,
    `<span class="tag" title="memória da máquina e simulações sugeridas ao mesmo tempo">${num(a.memoria_gb, 0)} GB · ${a.paralelo_max} simulações por vez</span>`,
  ].join("");
}

function desenharLista() {
  const pub = estado.experimentos.filter((e) => e.publicado);
  const outros = estado.experimentos.filter((e) => !e.publicado);
  const item = (e) => `<a data-exp="${esc(e.nome)}" class="${vista === "exp" && atual && atual.nome === e.nome ? "ativo" : ""}">${esc(e.titulo)} <small>${e.pontos} pontos</small></a>`;
  $("#lista").innerHTML = `<h4>Experimentos publicados</h4>${pub.map(item).join("")}` +
    `<h4>Outros cenários</h4>${outros.length ? outros.map(item).join("") : '<p class="vazio" style="padding:0 10px">Nenhum ainda. Use “Novo cenário”.</p>'}`;
  document.querySelectorAll("#lista a").forEach((a) => (a.onclick = () => abrirExperimento(a.dataset.exp)));
}


let pedidoExperimento = 0;
async function abrirExperimento(nome, rolar = true) {
  vista = "exp";
  const meu = ++pedidoExperimento;
  try {
    atual = await api(`/api/experimento?nome=${encodeURIComponent(nome)}`);
    atual.cenario = estado.experimentos.find((x) => x.nome === nome)?.tem_cenario
      ? await api(`/api/cenario?nome=${encodeURIComponent(nome)}`) : null;
  } catch (e) { $("#conteudo").innerHTML = `<div class="card span2 msg er">${esc(e.message)}</div>`; return; }
  if (meu !== pedidoExperimento || vista !== "exp") return;
  if (!atual.pontos.some((p) => p.pasta === pontoSel)) pontoSel = atual.pontos[0]?.pasta;
  desenharLista();
  desenharExperimento();
  if (rolar) window.scrollTo(0, 0);
}

// Nome legível do ponto, pelos valores das variáveis: "só local · câmeras no ponto quente = 2".
function rotuloPonto(p) {
  const vars = atual?.variaveis || [];
  if (!vars.length) return p.pasta.split("/").slice(1).join("/") || p.pasta;
  return vars.map((v) => (v.campo === "politica" ? rotuloValor(v.campo, p.valores[v.campo]) : `${v.rotulo} = ${rotuloValor(v.campo, p.valores[v.campo])}`)).join(" · ");
}

// Recarrega os números do experimento aberto sem refazer o formulário de bateria.
async function atualizarDados() {
  const nome = atual.nome;
  const novo = await api(`/api/experimento?nome=${encodeURIComponent(nome)}`);
  if (vista !== "exp" || !atual || atual.nome !== nome) return;
  novo.cenario = atual.cenario;
  atual = novo;
  $("#grafico").innerHTML = grafico(atual);
  $("#card-pontos").innerHTML = cardPontos(atual);
  ligarTabela();
  desenharBaterias();
}

function valorDoPonto(p) {
  const m = p.publicado || p.local;
  return { lat: m?.latencia_ms, falha: m?.falha_pct, fonte: p.publicado ? "publicado" : "local" };
}

function desenharExperimento() {
  const e = atual;
  $("#conteudo").innerHTML = `
    <section class="card span2">
      <h2>${esc(e.titulo)}</h2>
      <p class="sub">${esc(e.pergunta || "")}</p>
      <p class="nota">experimentos/${esc(e.nome)} · ${e.pontos.length} pontos ·
        ${e.publicado ? "configurações geradas por experimentos/gerar_configs.py" : "configurações geradas do cenario.json"} ·
        <a href="/api/tabela.csv?nome=${encodeURIComponent(e.nome)}">baixar tabela (CSV)</a></p>
    </section>
    ${e.cenario ? `<section class="card span2"><details open><summary class="sum-titulo">O que é simulado</summary><div class="desenho-rolagem">${desenhoTopologia(e.cenario)}</div></details></section>` : ""}
    <section class="card" id="grafico">${grafico(e)}</section>
    <section class="card" id="form-bateria"></section>
    <section class="card" id="card-pontos">${cardPontos(e)}</section>
    <section class="card" id="baterias"></section>
    ${figuras(e)}`;
  ligarTabela();
  desenharFormBateria();
  desenharBaterias();
}

function cardPontos(e) {
  return `<h3>Pontos</h3>${tabelaPontos(e)}
    <p class="nota">Latência média do YOLO, com o intervalo de confiança de 95%, e taxa de falha. Oficial: a amostra publicada (resultados/ do ponto). Nesta máquina: as repetições encontradas em saidas/. Clique numa linha para escolher o ponto a rodar.</p>`;
}

function ligarTabela() {
  document.querySelectorAll("#tab-pontos tbody tr").forEach((tr) => (tr.onclick = () => { pontoSel = tr.dataset.pasta; desenharExperimento(); }));
}

function grafico(e) {
  const vars = e.variaveis;
  if (!vars.length) return `<h3>Resultado</h3><p class="vazio">Experimento sem variáveis declaradas no cenario.json.</p>`;
  const vx = vars[vars.length - 1];
  const vs = vars.length > 1 ? vars[0] : null;
  const numerico = vx.valores.every((v) => typeof v === "number");
  const series = vs ? vs.valores : [null];
  const dados = series.map((s) => e.pontos.filter((p) => !vs || p.valores[vs.campo] === s)
    .map((p) => ({ x: p.valores[vx.campo], y: valorDoPonto(p).lat?.media, p })).filter((d) => d.y != null));
  const todos = dados.flat();
  if (!todos.length) return `<h3>Resultado</h3><p class="vazio">Ainda não há execuções. Rode uma bateria ao lado.</p>`;
  const W = 640, H = 270, L = 52, R = 16, T = 18, B = 46;
  const ymaxReal = Math.max(...todos.map((d) => d.y));
  const passo = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000].find((s) => ymaxReal / s <= 6) || 1000;
  const ymax = Math.ceil(ymaxReal / passo) * passo;
  const xs = numerico ? vx.valores.slice().sort((a, b) => a - b) : vx.valores;
  const xmin = numerico ? xs[0] : 0, xmax = numerico ? xs[xs.length - 1] : xs.length - 1;
  const px = (x) => { const i = numerico ? x : xs.indexOf(x); return L + (W - L - R) * (xmax === xmin ? 0.5 : (i - xmin) / (xmax - xmin)); };
  const py = (y) => T + (H - T - B) * (1 - y / ymax);
  let g = "";
  for (let t = 0; t <= ymax; t += passo) g += `<line class="grade" x1="${L}" x2="${W - R}" y1="${py(t)}" y2="${py(t)}"/><text x="${L - 6}" y="${py(t) + 4}" text-anchor="end">${num(t, 0)}</text>`;
  xs.forEach((x) => (g += `<text x="${px(x)}" y="${H - B + 18}" text-anchor="middle">${esc(rotuloValor(vx.campo, x))}</text>`));
  g += `<text x="${(L + W - R) / 2}" y="${H - 8}" text-anchor="middle">${esc(vx.rotulo)}</text>`;
  g += `<text x="14" y="${(T + H - B) / 2}" transform="rotate(-90 14 ${(T + H - B) / 2})" text-anchor="middle">latência média do YOLO (ms)</text>`;
  dados.forEach((serie, i) => {
    const cor = corSerie(vs?.campo, series[i], i);
    const ord = serie.slice().sort((a, b) => (numerico ? a.x - b.x : xs.indexOf(a.x) - xs.indexOf(b.x)));
    if (ord.length > 1) g += `<polyline fill="none" stroke="${cor}" stroke-width="2.5" points="${ord.map((d) => `${px(d.x)},${py(d.y)}`).join(" ")}"/>`;
    ord.forEach((d) => {
      const v = valorDoPonto(d.p);
      g += `<circle cx="${px(d.x)}" cy="${py(d.y)}" r="5" fill="${cor}" stroke="var(--card)" stroke-width="2"><title>${esc(d.p.pasta)}: ${num(d.y)} ms ± ${num(v.lat.ic95)} (n = ${v.lat.n}), falha ${num(v.falha?.media)}% · ${v.fonte}</title></circle>`;
    });
  });
  const leg = vs ? `<div class="leg">${series.map((s, i) => `<span><i style="background:${corSerie(vs.campo, s, i)}"></i>${esc(rotuloValor(vs.campo, s))}</span>`).join("")}</div>` : "";
  return `<h3>Resultado</h3>${leg}<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Latência média por ${esc(vx.rotulo)}">${g}</svg>
    <p class="nota">Passe o mouse nos pontos para ver IC95, n e falha.</p>`;
}

function tabelaPontos(e) {
  const vars = e.variaveis;
  const cab = vars.length ? vars.map((v) => `<th>${esc(v.rotulo)}</th>`).join("") : "<th>Ponto</th>";
  const linhas = e.pontos.map((p) => {
    const v = valorDoPonto(p);
    const cel = vars.length ? vars.map((x) => `<td>${esc(rotuloValor(x.campo, p.valores[x.campo]))}</td>`).join("") : `<td>${esc(p.pasta)}</td>`;
    const amostra = p.publicado ? `<span class="st ok" title="amostra oficial, em resultados/">oficial · ${p.publicado.latencia_ms.n}</span>`
      : p.execucoes ? `<span class="st local" title="repetições encontradas em saidas/">nesta máquina · ${p.execucoes}</span>` : `<span class="st nada">nenhuma ainda</span>`;
    return `<tr data-pasta="${esc(p.pasta)}" class="${p.pasta === pontoSel ? "sel" : ""}">${cel}
      <td class="n">${v.lat ? `${num(v.lat.media)} ± ${num(v.lat.ic95)}` : "–"}</td><td class="n">${v.falha ? num(v.falha.media) + "%" : "–"}</td><td>${amostra}</td></tr>`;
  }).join("");
  return `<table id="tab-pontos"><thead><tr>${cab}<th class="n">Latência (ms)</th><th class="n">Falha</th><th>Repetições</th></tr></thead><tbody>${linhas}</tbody></table>`;
}

function figuras(e) {
  const lista = [...e.pontos.filter((p) => p.pasta === pontoSel).flatMap((p) => p.figuras), ...e.figuras_comparativas];
  if (!lista.length) return "";
  return `<section class="card span2"><h3>Figuras</h3><div class="figs">${lista.map((f) =>
    `<a href="/arquivo?caminho=${encodeURIComponent(f)}" target="_blank"><img src="/arquivo?caminho=${encodeURIComponent(f)}" alt="${esc(f)}" loading="lazy"><small>${esc(f.split("/").slice(-1)[0])}</small></a>`).join("")}</div>
    <p class="nota">Figuras geradas pelos scripts de analise/. As do ponto mudam com o ponto escolhido na tabela.</p></section>`;
}


function comandoBateria(pontos, de, ate, deeplog) {
  const alvo = pontos.length === 1 ? pontos[0] : "$p";
  const cmd = deeplog ? `for s in $(seq ${de} ${ate}); do bash execucao/rodar_simulacao.sh ${alvo} $s --deeplog; done`
    : `bash execucao/rodar_experimento.sh ${alvo} ${ate - de + 1} ${de}`;
  return pontos.length === 1 ? cmd : `for p in ${pontos.join(" ")}; do\n  ${cmd}\ndone`;
}

function desenharFormBateria() {
  const p = atual.pontos.find((x) => x.pasta === pontoSel) || atual.pontos[0];
  const prox = p && p.sementes.length ? Math.max(...p.sementes) + 1 : 1;
  const par = Math.min(estado.ambiente.paralelo_max || 2, 10);
  $("#form-bateria").innerHTML = `<h3>Rodar simulações</h3>
    <label>O que rodar</label><select id="b-ponto"><option value="__todos">Todos os ${atual.pontos.length} pontos do experimento</option>
      ${atual.pontos.map((x) => `<option value="${esc(x.pasta)}" ${x.pasta === p?.pasta ? "selected" : ""}>${esc(rotuloPonto(x))}</option>`).join("")}</select>
    <label>Repetições: da semente … até a semente …</label>
    <div class="linha"><input id="b-de" type="number" min="1" value="${prox}"><input id="b-ate" type="number" min="1" value="${prox + 9}"></div>
    <p class="nota">Cada semente é uma repetição independente. 10 já dão uma ideia, e o artigo usa 30.</p>
    <label>Simulações ao mesmo tempo (sugerido: até ${estado.ambiente.paralelo_max} nesta máquina)</label><input id="b-par" type="number" min="1" max="32" value="${par}">
    <div class="chk"><input id="b-deep" type="checkbox"> Guardar o tempo de cada quadro (para percentis; ocupa mais disco)</div>
    <div class="acoes"><button class="btn" id="b-rodar">Rodar</button></div>
    <details><summary>Comando equivalente no terminal</summary><pre id="b-cmd"></pre></details>
    <div id="b-msg"></div>`;
  const ler = () => {
    const v = $("#b-ponto").value;
    return { pontos: v === "__todos" ? atual.pontos.map((x) => x.pasta) : [v], de: +$("#b-de").value, ate: +$("#b-ate").value, paralelo: +$("#b-par").value, deeplog: $("#b-deep").checked };
  };
  const proxima = (pastas) => 1 + Math.max(0, ...atual.pontos.filter((x) => pastas.includes(x.pasta)).flatMap((x) => x.sementes));
  const atualizar = () => {
    const d = ler(), n = Math.max(0, d.ate - d.de + 1) * d.pontos.length;
    $("#b-cmd").textContent = "$ " + comandoBateria(d.pontos, d.de, d.ate, d.deeplog);
    $("#b-rodar").textContent = `Rodar ${n} execuç${n === 1 ? "ão" : "ões"}`;
  };
  ["#b-ponto", "#b-de", "#b-ate", "#b-par", "#b-deep"].forEach((s) => ($(s).oninput = atualizar));
  $("#b-ponto").onchange = () => {
    if ($("#b-ponto").value !== "__todos") { pontoSel = $("#b-ponto").value; desenharExperimento(); return; }
    // Para todos os pontos, começa depois da maior semente já rodada em qualquer um deles.
    const de = proxima(atual.pontos.map((x) => x.pasta)), tam = +$("#b-ate").value - +$("#b-de").value;
    $("#b-de").value = de; $("#b-ate").value = de + Math.max(0, tam);
    atualizar();
  };
  atualizar();
  $("#b-rodar").onclick = async () => {
    const d = ler();
    if (d.paralelo > estado.ambiente.paralelo_max && !confirm(`Mais de ${estado.ambiente.paralelo_max} em paralelo pode deixar a máquina sem memória. Continuar?`)) return;
    try { await api("/api/bateria", d); $("#b-msg").innerHTML = `<div class="msg ok">Bateria iniciada.</div>`; atualizarEstado(); }
    catch (err) { $("#b-msg").innerHTML = `<div class="msg er">${esc(err.message)}</div>`; }
  };
}

function desenharBaterias() {
  const alvo = $("#baterias");
  if (!alvo || !atual) return;
  const prefixo = atual.nome + "/";
  const curto = (p) => p.slice(prefixo.length);
  const minhas = estado.baterias.filter((b) => b.pontos[0].startsWith(prefixo));
  if (!minhas.length) { alvo.innerHTML = `<h3>Baterias</h3><p class="vazio">Nenhuma bateria deste experimento desde que a tela abriu.</p>`; return; }
  alvo.innerHTML = `<h3>Baterias</h3>` + minhas.map((b) => {
    const c = b.contagem, total = b.itens.length, feitas = (c.ok || 0) + (c.falha || 0) + (c.parada || 0);
    const est = b.estimativa_s ? ` · faltam ≈ ${Math.max(1, Math.round(b.estimativa_s / 60))} min` : "";
    const porPasta = Object.fromEntries(atual.pontos.map((x) => [x.pasta, x]));
    const nomeDe = (p) => (porPasta[p] ? rotuloPonto(porPasta[p]) : curto(p));
    const titulo = b.pontos.length === 1 ? nomeDe(b.pontos[0]) : `${b.pontos.length} pontos`;
    const chips = b.pontos.map((p) => {
      const itens = b.itens.filter((x) => x.ponto === p);
      return `${b.pontos.length > 1 ? `<div class="nota" style="margin:6px 0 0">${esc(nomeDe(p))}</div>` : ""}<div class="sementes">${itens.map((s) =>
        `<span class="${s.estado}" title="${esc(`semente ${s.semente}: ${s.estado}${s.decorrido_s ? `, ${Math.round(s.decorrido_s)} s` : ""}${s.msg ? " · " + s.msg : ""}`)}">${s.semente}</span>`).join("")}</div>`;
    }).join("");
    let fim = "";
    if (b.terminada && !b.deeplog && c.ok) {
      const comOk = b.pontos.filter((p) => b.itens.some((x) => x.ponto === p && x.estado === "ok"));
      fim = atual.publicado
        ? `<p class="nota">A amostra oficial dos experimentos publicados só muda pelo terminal:</p><pre>${comOk.map((p) => `$ python3 analise/publicar_manifest.py --ponto ${esc(p)} --lista ${esc(b.listas[p])}`).join("\n")}</pre>`
        : publicacoes[b.id] ? publicacoes[b.id] : `<div class="acoes"><button class="btn sec" data-publicar="${b.id}">Tornar amostra oficial (${comOk.length} ponto${comOk.length > 1 ? "s" : ""})</button></div>
           <p class="nota">Grava o manifesto, as métricas agregadas e as figuras em resultados/ de cada ponto.</p><div data-saida="${b.id}"></div>`;
    }
    return `<div class="bat"><b>${esc(titulo)}</b>${b.deeplog ? ' <span class="st nada">registro por tarefa</span>' : ""}
      <div class="nota">${feitas} de ${total} · ${c.ok || 0} ok · ${c.falha || 0} falha${c.parada ? ` · ${c.parada} parada` : ""}${c.rodando ? ` · ${c.rodando} rodando` : ""}${est}</div>
      <div class="barra"><i style="width:${(100 * feitas) / total}%"></i></div>${chips}
      ${b.terminada ? fim : `<button class="btn perigo" data-parar="${b.id}">Parar</button>`}</div>`;
  }).join("");
  alvo.querySelectorAll("[data-parar]").forEach((x) => (x.onclick = async () => { await api("/api/bateria/parar", { id: x.dataset.parar }); atualizarEstado(); }));
  alvo.querySelectorAll("[data-publicar]").forEach((x) => (x.onclick = async () => {
    const b = estado.baterias.find((y) => y.id === x.dataset.publicar);
    publicacoes[b.id] = `<div class="msg av">Publicando… não feche a tela.</div>`;
    desenharBaterias();
    const saidas = [];
    for (const p of b.pontos.filter((p) => b.itens.some((i) => i.ponto === p && i.estado === "ok"))) {
      try { saidas.push((await api("/api/publicar", { ponto: p, lista: b.listas[p] })).saida); }
      catch (e) {
        saidas.push(e.message);
        publicacoes[b.id] = `<div class="msg er">Falhou em ${esc(p)}</div><pre>${esc(saidas.join("\n\n"))}</pre>`;
        desenharBaterias();
        return;
      }
    }
    publicacoes[b.id] = `<div class="msg ok">Amostra publicada em ${saidas.length} ponto(s).</div><details><summary>Ver o que rodou</summary><pre>${esc(saidas.join("\n\n"))}</pre></details>`;
    await atualizarDados();
  }));
}

// Construtor de cenário: escolhas à esquerda, desenho da topologia à direita. O estado é o
// mesmo objeto gravado em cenario.json; as comparações viram a lista `variar` no envio.

const OPCOES_POLITICA = {
  LOCAL_FIRST: ["Menor tempo estimado", "usa a GPU do próprio ponto de acesso e só manda o quadro ao vizinho quando isso fica mais rápido, mesmo com o atraso da MAN"],
  AUTO: ["Rodízio", "manda cada quadro a uma GPU diferente, em sequência, sem olhar onde a câmera está"],
  LOCAL: ["Só local", "cada ponto de acesso usa só a própria GPU; nunca usa a MAN"],
};
const OPCOES_ATRASO = [[10, "10 ms", "valor do sample_app5 do EdgeCloudSim"], [5, "5 ms", "valor do sample_app4"], [0.25, "0,25 ms", "fibra óptica, cerca de 50 km"]];

function abrirAssistente() {
  vista = "novo";
  pedidoExperimento++;
  assistente = { cen: copia(PADRAO), base: "zero", comparar: compararPadrao(), nomeEditado: false, previa: null };
  desenharLista();
  desenharConstrutor();
}

function compararPadrao() {
  return { politica: { on: true, valores: ["LOCAL", "AUTO", "LOCAL_FIRST"] }, disp: { on: true, valores: [2, 4, 6, 8, 9] },
           gpu: { on: false, valores: [1, 2, 4] }, prop: { on: false, valores: [0.25, 5, 10] } };
}

function slug(t) {
  return t.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40);
}

const stepper = (id, valor, min, max) =>
  `<span class="stepper" data-id="${id}" data-min="${min}" data-max="${max}"><button type="button" data-d="-1" ${valor <= min ? "disabled" : ""}>−</button><b>${valor}</b><button type="button" data-d="1" ${valor >= max ? "disabled" : ""}>+</button></span>`;

const cartao = (grupo, valor, sel, titulo, texto, desabilitado = false) =>
  `<div class="op ${sel ? "sel" : ""} ${desabilitado ? "off" : ""}" data-grupo="${grupo}" data-valor="${esc(valor)}"><b>${titulo}</b>${texto ? `<small>${texto}</small>` : ""}</div>`;

function desenharConstrutor() {
  const a = assistente, c = a.cen, s = c.servidores;
  const porPonto = c.mobilidade === "por_ponto";
  const base = estado.experimentos.filter((e) => e.tem_cenario);
  const pp = c.dispositivos_por_ponto || [];
  const cmp = a.comparar;
  const nomeDisp = porPonto ? "câmeras no ponto de acesso 0" : "dispositivos";
  $("#conteudo").innerHTML = `
  <section class="card span2"><h2>Novo cenário</h2>
    <p class="sub">Monte o que quer simular. O desenho muda enquanto você escolhe.</p>
    <div class="chips" style="margin-top:12px"><span class="sub">Começar de:</span>
      <button class="chip ${a.base === "zero" ? "sel" : ""}" data-base="zero">em branco</button>
      ${base.map((e) => `<button class="chip ${a.base === e.nome ? "sel" : ""}" data-base="${esc(e.nome)}">${esc(e.titulo)}</button>`).join("")}</div>
  </section>
  <div class="construtor span2">
   <div class="formulario">
    <section class="card"><h3>1. Nome</h3>
      <label>Título do experimento</label><input id="c-titulo" type="text" value="${esc(c.titulo)}" placeholder="Ex.: Câmeras em 6 cruzamentos">
      <p class="nota">Pasta: experimentos/<b id="c-pasta">${esc(c.nome || "…")}</b> · <a href="#" id="c-pasta-edita">alterar</a></p>
      <input id="c-nome" type="text" value="${esc(c.nome)}" style="display:none">
      <label>O que você quer descobrir? (opcional)</label><input id="c-pergunta" type="text" value="${esc(c.pergunta)}" placeholder="Ex.: Vale a pena dividir as câmeras entre os cruzamentos?">
    </section>

    <section class="card"><h3>2. Servidores de borda</h3>
      <div class="linha-ctrl"><span>Quantos servidores</span>${stepper("qtd", s.quantidade, 1, 20)}</div>
      <div class="linha-ctrl"><span>Quantos têm GPU (RTX 3050)</span>${stepper("gpu", s.com_gpu, 0, s.quantidade)}</div>
      <p class="nota">Cada servidor fica junto de um ponto de acesso Wi-Fi. As GPUs vão para os primeiros servidores.</p>
      <div class="opcoes" style="margin-top:10px">
        ${cartao("modelo", "tocze", s.modelo === "tocze", "Servidor completo", "8 máquinas virtuais, uma delas com a GPU (Toczé et al., 2020)")}
        ${cartao("modelo", "rodrigues", s.modelo === "rodrigues", "Servidor simples", s.quantidade === 1 ? "1 máquina virtual com a GPU (Rodrigues et al., 2026)" : "só com 1 servidor", s.quantidade !== 1)}
      </div>
    </section>

    <section class="card"><h3>3. Quem usa</h3>
      <div class="opcoes">
        ${cartao("mob", "por_ponto", porPonto, "Câmeras fixas", "cada ponto de acesso com a sua quantidade")}
        ${cartao("mob", "fixa", c.mobilidade === "fixa", "Todos num só lugar", "todos no mesmo ponto de acesso")}
        ${cartao("mob", "nomade", c.mobilidade === "nomade", "Pessoas circulando", "trocam de ponto de acesso com o tempo")}
      </div>
      <div style="margin-top:12px">${porPonto
        ? Array.from({ length: s.quantidade }, (_, i) => `<div class="linha-ctrl"><span>Câmeras no ponto de acesso ${i}</span>${i === 0 && cmp.disp.on
            ? `<small class="sub">varia: ${esc(cmp.disp.valores.join(", "))} (passo 6)</small>` : stepper("pp" + i, pp[i] ?? 0, 0, 30)}</div>`).join("")
        : `<div class="linha-ctrl"><span>Quantos dispositivos</span>${cmp.disp.on ? `<small class="sub">varia: ${esc(cmp.disp.valores.join(", "))} (passo 6)</small>` : stepper("total", c.dispositivos, 1, 60)}</div>
           ${c.mobilidade === "fixa" ? `<div class="linha-ctrl"><span>Em qual ponto de acesso</span>${stepper("fixo", c.ponto_fixo, 0, s.quantidade - 1)}</div>` : ""}`}</div>
      <label style="margin-top:12px">O que os dispositivos rodam</label>
      <div class="opcoes">
        ${cartao("carga", "yolo", c.carga === "yolo", "Só detecção de objetos", "YOLO, 30 quadros por segundo (Rodrigues et al., 2026)")}
        ${cartao("carga", "mista", c.carga === "mista", "Carga mista", "30% YOLO e 70% aplicativos só de CPU (Sonmez et al., 2019)")}
      </div>
    </section>

    <section class="card"><h3>4. Rede entre os servidores (MAN)</h3>
      <div class="opcoes">
        ${cartao("man", "sim", c.man.ligada, "Ligada", "um servidor pode mandar quadros a outro, e cada envio tem o atraso da MAN")}
        ${cartao("man", "nao", !c.man.ligada, "Desligada", "cada servidor só atende o próprio ponto de acesso")}
      </div>
      ${c.man.ligada ? `<label style="margin-top:12px">Atraso de propagação, em cada sentido</label><div class="opcoes">${OPCOES_ATRASO.map(([v, t, d]) => cartao("prop", v, c.man.propagacao_ms == v, t, d)).join("")}</div>` : ""}
    </section>

    <section class="card"><h3>5. Como escolher a GPU de cada quadro</h3>
      ${cmp.politica.on
        ? `<p class="passo-off">Você vai comparar as formas de escolher a GPU (passo 6): cada uma vira uma linha do gráfico.</p>`
        : `<div class="opcoes">${Object.entries(OPCOES_POLITICA).map(([k, [t, d]]) => cartao("pol", k, c.politica === k, t, d)).join("")}</div>`}
    </section>

    <section class="card"><h3>6. O que comparar</h3>
      <p class="sub">Cada valor vira um ponto do experimento. Marque no máximo duas comparações.</p>
      <div class="comparar">
        <label class="chk"><input type="checkbox" data-cmp="politica" ${cmp.politica.on ? "checked" : ""}> As formas de escolher a GPU</label>
        ${cmp.politica.on ? `<div class="sub-op">${Object.entries(OPCOES_POLITICA).map(([k, [t]]) => `<label class="chk"><input type="checkbox" data-pol="${k}" ${cmp.politica.valores.includes(k) ? "checked" : ""}> ${t}</label>`).join("")}</div>` : ""}
        <label class="chk"><input type="checkbox" data-cmp="disp" ${cmp.disp.on ? "checked" : ""}> A quantidade de ${nomeDisp}</label>
        ${cmp.disp.on ? `<div class="sub-op"><input type="text" data-valores="disp" value="${esc(cmp.disp.valores.join(" "))}"><small>valores separados por espaço, ex.: 2 4 6 8</small></div>` : ""}
        <label class="chk"><input type="checkbox" data-cmp="gpu" ${cmp.gpu.on ? "checked" : ""}> Quantos servidores têm GPU</label>
        ${cmp.gpu.on ? `<div class="sub-op"><input type="text" data-valores="gpu" value="${esc(cmp.gpu.valores.join(" "))}"><small>de 0 a ${s.quantidade}</small></div>` : ""}
        ${c.man.ligada ? `<label class="chk"><input type="checkbox" data-cmp="prop" ${cmp.prop.on ? "checked" : ""}> O atraso da MAN (ms)</label>
        ${cmp.prop.on ? `<div class="sub-op"><input type="text" data-valores="prop" value="${esc(cmp.prop.valores.join(" ").replace(/\./g, ","))}"><small>ex.: 0,25 5 10</small></div>` : ""}` : ""}
      </div>
      <details style="margin-top:12px"><summary>Avançado: duração e banda da MAN</summary>
        <div class="linha3"><div><label>Tempo simulado (min)</label><input id="c-dur" type="number" min="1" value="${c.duracao_min}"></div>
        <div><label>Descartar no início (min)</label><input id="c-aq" type="number" min="0" value="${c.aquecimento_min}"></div>
        <div><label>Banda da MAN (Mbps)</label><input id="c-banda" type="number" min="1" value="${c.man.banda_mbps}"></div></div>
      </details>
    </section>
   </div>
   <div class="lado">
    <section class="card fixo"><h3>O que será simulado</h3><div id="c-desenho" class="desenho-rolagem"></div>
      <div id="c-conf"></div>
      <div class="acoes"><button class="btn" id="w-criar" disabled>Criar experimento</button></div>
      <div id="w-res"></div></section>
   </div>
  </div>`;
  ligarConstrutor();
  atualizarDesenho();
}

function ligarConstrutor() {
  const a = assistente, c = a.cen;
  document.querySelectorAll(".chip[data-base]").forEach((b) => (b.onclick = () => copiarBase(b.dataset.base)));
  $("#c-titulo").oninput = (e) => { c.titulo = e.target.value; if (!a.nomeEditado) { c.nome = slug(c.titulo); $("#c-pasta").textContent = c.nome || "…"; } atualizarDesenho(); };
  $("#c-pasta-edita").onclick = (e) => { e.preventDefault(); const n = $("#c-nome"); n.style.display = "block"; n.focus(); };
  $("#c-nome").oninput = (e) => { a.nomeEditado = true; c.nome = slug(e.target.value); $("#c-pasta").textContent = c.nome || "…"; atualizarDesenho(); };
  $("#c-pergunta").oninput = (e) => { c.pergunta = e.target.value; };
  document.querySelectorAll(".stepper").forEach((st) => st.querySelectorAll("button").forEach((b) => (b.onclick = () => {
    const v = Math.min(+st.dataset.max, Math.max(+st.dataset.min, +st.querySelector("b").textContent + +b.dataset.d));
    mudarStepper(st.dataset.id, v);
    desenharConstrutor();
  })));
  document.querySelectorAll(".op[data-grupo]").forEach((o) => (o.onclick = () => {
    if (o.classList.contains("off")) return;
    const v = o.dataset.valor, gr = o.dataset.grupo;
    if (gr === "modelo") c.servidores.modelo = v;
    if (gr === "mob") {
      c.mobilidade = v;
      if (v === "por_ponto" && !c.dispositivos_por_ponto) c.dispositivos_por_ponto = Array.from({ length: c.servidores.quantidade }, (_, i) => (i ? 1 : 4));
    }
    if (gr === "carga") { c.carga = v; c.nuvem = v === "mista" ? "densidade" : "escala"; }
    if (gr === "man") { c.man.ligada = v === "sim"; if (!c.man.ligada) a.comparar.prop.on = false; }
    if (gr === "prop") c.man.propagacao_ms = +v;
    if (gr === "pol") c.politica = v;
    desenharConstrutor();
  }));
  document.querySelectorAll("[data-cmp]").forEach((x) => (x.onchange = () => {
    const ativos = Object.values(a.comparar).filter((v) => v.on).length;
    if (x.checked && ativos >= 2) { x.checked = false; alert("Marque até duas comparações: com mais, o número de pontos cresce rápido."); return; }
    a.comparar[x.dataset.cmp].on = x.checked;
    desenharConstrutor();
  }));
  document.querySelectorAll("[data-pol]").forEach((x) => (x.onchange = () => {
    a.comparar.politica.valores = [...document.querySelectorAll("[data-pol]:checked")].map((y) => y.dataset.pol);
    atualizarDesenho();
  }));
  document.querySelectorAll("[data-valores]").forEach((x) => (x.oninput = () => {
    a.comparar[x.dataset.valores].valores = x.value.trim().split(/\s+/).filter(Boolean).map((t) => Number(t.replace(",", "."))).filter((n) => !isNaN(n));
    atualizarDesenho();
  }));
  [["#c-dur", (v) => (c.duracao_min = v)], ["#c-aq", (v) => (c.aquecimento_min = v)], ["#c-banda", (v) => (c.man.banda_mbps = v)]]
    .forEach(([sel, f]) => ($(sel).oninput = (e) => { f(+e.target.value); atualizarDesenho(); }));
  $("#w-criar").onclick = criarCenario;
}

function mudarStepper(id, v) {
  const c = assistente.cen, s = c.servidores;
  if (id === "qtd") {
    s.quantidade = v;
    s.com_gpu = Math.min(s.com_gpu, v);
    if (v !== 1) s.modelo = "tocze";
    if (c.dispositivos_por_ponto) {
      c.dispositivos_por_ponto = Array.from({ length: v }, (_, i) => c.dispositivos_por_ponto[i] ?? 1);
    }
    c.ponto_fixo = Math.min(c.ponto_fixo, v - 1);
  } else if (id === "gpu") s.com_gpu = v;
  else if (id === "total") c.dispositivos = v;
  else if (id === "fixo") c.ponto_fixo = v;
  else if (id.startsWith("pp")) c.dispositivos_por_ponto[+id.slice(2)] = v;
}

async function copiarBase(nome) {
  const a = assistente;
  a.base = nome;
  if (nome === "zero") { a.cen = copia(PADRAO); a.comparar = compararPadrao(); a.nomeEditado = false; return desenharConstrutor(); }
  const c = await api(`/api/cenario?nome=${encodeURIComponent(nome)}`);
  delete c.gerado_por;
  c.nome = slug(`${nome}-variacao`);
  c.titulo = `${c.titulo} (variação)`;
  if (c.dispositivos_por_ponto) c.mobilidade = "por_ponto";
  const cmp = { politica: { on: false, valores: ["LOCAL", "AUTO", "LOCAL_FIRST"] }, disp: { on: false, valores: [] },
                gpu: { on: false, valores: [] }, prop: { on: false, valores: [] } };
  const chave = { politica: "politica", dispositivos: "disp", "dispositivos_por_ponto.0": "disp", "servidores.com_gpu": "gpu", "man.propagacao_ms": "prop" };
  (c.variar || []).forEach((v) => { if (chave[v.campo]) cmp[chave[v.campo]] = { on: true, valores: v.valores }; });
  ["disp", "gpu", "prop"].forEach((k) => { if (!cmp[k].valores.length) cmp[k].valores = compararPadrao()[k].valores; });
  a.cen = c; a.comparar = cmp; a.nomeEditado = false;
  desenharConstrutor();
}

function cenarioParaEnviar() {
  const a = assistente, c = copia(a.cen), cmp = a.comparar, porPonto = c.mobilidade === "por_ponto";
  const variar = [];
  if (cmp.politica.on && cmp.politica.valores.length) variar.push({ campo: "politica", valores: cmp.politica.valores });
  if (cmp.disp.on && cmp.disp.valores.length) variar.push({ campo: porPonto ? "dispositivos_por_ponto.0" : "dispositivos", valores: cmp.disp.valores });
  if (cmp.gpu.on && cmp.gpu.valores.length) variar.push({ campo: "servidores.com_gpu", valores: cmp.gpu.valores });
  if (c.man.ligada && cmp.prop.on && cmp.prop.valores.length) variar.push({ campo: "man.propagacao_ms", valores: cmp.prop.valores });
  c.variar = variar.map((v) => ({ ...v, rotulo: CAMPOS[v.campo].curto, pasta: CAMPOS[v.campo].pasta }));
  if (!porPonto) c.dispositivos_por_ponto = null;
  else c.dispositivos = c.dispositivos_por_ponto.reduce((x, y) => x + y, 0);
  return c;
}

let esperaConferir = null;
function atualizarDesenho() {
  const c = cenarioParaEnviar();
  $("#c-desenho").innerHTML = desenhoTopologia(c);
  $("#w-criar").disabled = true;
  pedidoConferir++;  // invalida a conferência em andamento
  clearTimeout(esperaConferir);
  esperaConferir = setTimeout(conferir, 350);
}

let pedidoConferir = 0;
async function conferir() {
  const caixa = $("#c-conf");
  if (!caixa) return;
  const meu = ++pedidoConferir;
  const c = cenarioParaEnviar();
  if (!c.nome) { caixa.innerHTML = `<div class="msg av">Dê um título ao experimento para criá-lo.</div>`; return; }
  try {
    const r = await api("/api/cenario/previa", c);
    if (meu !== pedidoConferir) return;  // chegou depois de uma conferência mais nova
    assistente.previa = r;
    const n = r.pontos.length;
    const nomes = c.variar.map((v) => `${CAMPOS[v.campo].curto} (${v.valores.length})`).join(" × ");
    const agrupar = (lista) => {
      // Mensagens iguais a menos dos números (10 clientes…, 12 clientes…) viram uma só, com os
      // números que variam listados na posição deles.
      const grupos = new Map();
      lista.forEach((t) => {
        const corpo = t.replace(/^[^:]+: /, ""), chave = corpo.replace(/\d+/g, "#");
        const nums = corpo.match(/\d+/g) || [];
        if (!grupos.has(chave)) grupos.set(chave, []);
        grupos.get(chave).push(nums);
      });
      return [...grupos].map(([chave, ocorr]) => {
        let i = 0;
        const t = chave.replace(/#/g, () => {
          const vals = [...new Set(ocorr.map((n) => +n[i]))].sort((x, y) => x - y);
          i++;
          return vals.join(", ");
        });
        return ocorr.length > 1 ? `${t} (em ${ocorr.length} pontos)` : t;
      });
    };
    const excl = (c.excluir || []).map((x) => Object.entries(x).map(([k, v]) => `${CAMPOS[k]?.curto || k} = ${rotuloValor(k, v)}`).join(" e "));
    caixa.innerHTML = agrupar(r.erros).map((e) => `<div class="msg er">${esc(e)}</div>`).join("")
      + agrupar(r.avisos).map((e) => `<div class="msg av">${esc(e)}</div>`).join("")
      + (!r.erros.length ? `<div class="msg ok"><b>${n} ponto${n === 1 ? "" : "s"}</b>${nomes ? `: ${esc(nomes)}` : ""}. Depois de criar, cada ponto roda as repetições (sementes) que você escolher.</div>` : "")
      + (excl.length ? `<p class="nota">Combinações excluídas (vindas do experimento copiado): ${esc(excl.join("; "))}.</p>` : "")
      + (r.exemplo ? `<details><summary>Ver a configuração gerada (primeiro ponto)</summary><pre>${esc(r.exemplo)}</pre></details>` : "");
    $("#w-criar").disabled = r.erros.length > 0;
  } catch (e) { if (meu === pedidoConferir) caixa.innerHTML = `<div class="msg er">${esc(e.message)}</div>`; }
}

async function criarCenario() {
  try {
    const r = await api("/api/cenario/criar", cenarioParaEnviar());
    await atualizarEstado();
    await abrirExperimento(r.nome);
  } catch (e) { $("#w-res").innerHTML = `<div class="msg er">${esc(e.message)}</div>`; }
}


$("#btn-novo").onclick = abrirAssistente;
(async () => {
  await atualizarEstado();
  const primeiro = estado.experimentos.find((e) => e.nome === "cameras-fixas") || estado.experimentos[0];
  if (primeiro) abrirExperimento(primeiro.nome);
})();
