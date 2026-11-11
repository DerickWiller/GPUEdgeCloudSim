// Desenho da topologia de um cenário (servidores, GPUs, MAN, pontos de acesso e dispositivos),
// gerado a partir do mesmo objeto que vai para o cenario.json. Usado no construtor de cenário
// e na página do experimento.
"use strict";

// Limites físicos: valores de experimentos/gerar_cenario.py, que o servidor envia em /api/estado
// (definirLimites); os daqui só valem até a primeira resposta.
let LIMITES = { clientes_por_ap: 480 / 48.24, vram: 6144, vram_por_cliente: 416, mem_por_quadro: 20,
                fracao_yolo: { yolo: 1, mista: 0.3 }, max_clientes_yolo: 14 };
function definirLimites(l) { if (l) LIMITES = l; }

// Arredondamento com empate para o par, como o round do Python, para o desenho e o gerador
// contarem os mesmos clientes YOLO.
function _arredondar(x) {
  const f = Math.floor(x), d = x - f;
  if (Math.abs(d - 0.5) < 1e-9) return f % 2 === 0 ? f : f + 1;
  return Math.round(x);
}
const _nYolo = (k, carga) => _arredondar(k * (LIMITES.fracao_yolo[carga] ?? 1));

function _esc(t) {
  return String(t ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function _faixa(valores) {
  if (!valores || !valores.length) return "";
  const v = [...valores].sort((a, b) => a - b);
  const f = (x) => String(x).replace(".", ",");
  return v.length > 2 ? `${f(v[0])} a ${f(v[v.length - 1])}` : v.map(f).join(" e ");
}

// Valores do cenário para o desenho: a variável, quando há, aparece pela faixa de valores.
function _resumo(cen) {
  const vars = Object.fromEntries((cen.variar || []).filter((v) => v.campo && v.valores?.length).map((v) => [v.campo, v.valores]));
  const n = Math.max(1, cen.servidores?.quantidade || 1);
  const porPonto = cen.mobilidade === "por_ponto" && cen.dispositivos_por_ponto ? [...cen.dispositivos_por_ponto] : null;
  if (porPonto && vars["dispositivos_por_ponto.0"]) porPonto[0] = Math.max(...vars["dispositivos_por_ponto.0"]);
  const total = porPonto ? porPonto.reduce((a, b) => a + b, 0)
    : (vars.dispositivos ? Math.max(...vars.dispositivos) : cen.dispositivos || 0);
  const comGpu = vars["servidores.com_gpu"] ? Math.max(...vars["servidores.com_gpu"]) : cen.servidores?.com_gpu ?? n;
  return { vars, n, porPonto, total, comGpu, yolo: _nYolo(total, cen.carga) };
}

function _camera(x, y, cor) {
  return `<g transform="translate(${x},${y})"><rect x="-7" y="-5" width="11" height="10" rx="2" fill="${cor}"/>` +
    `<path d="M4 -3 L9 -6 L9 6 L4 3 Z" fill="${cor}"/><circle cx="-1.5" cy="0" r="2.4" fill="var(--card)"/></g>`;
}

function _celular(x, y, cor) {
  return `<g transform="translate(${x},${y})"><rect x="-5" y="-8" width="10" height="16" rx="2.5" fill="${cor}"/>` +
    `<rect x="-3" y="-5.5" width="6" height="9" rx="1" fill="var(--card)"/></g>`;
}

function _antena(x, y, cor) {
  return `<g transform="translate(${x},${y})" fill="none" stroke="${cor}" stroke-width="2" stroke-linecap="round">` +
    `<line x1="0" y1="-2" x2="0" y2="16"/><path d="M-6 -6 A9 9 0 0 1 6 -6"/><path d="M-11 -11 A16 16 0 0 1 11 -11"/>` +
    `<circle cx="0" cy="-2" r="2" fill="${cor}" stroke="none"/></g>`;
}

function _dispositivos(x, y, qtd, icone, cor, largura) {
  // Até 12 ícones desenhados; o resto aparece como +N.
  const mostrar = Math.min(qtd, 12), porLinha = Math.max(3, Math.floor(largura / 22));
  let g = "";
  for (let i = 0; i < mostrar; i++) {
    const col = i % porLinha, lin = Math.floor(i / porLinha);
    const linhaQtd = Math.min(porLinha, mostrar - lin * porLinha);
    g += icone(x + (col - (linhaQtd - 1) / 2) * 22, y + lin * 24, cor);
  }
  if (qtd > mostrar) g += `<text x="${x}" y="${y + Math.ceil(mostrar / porLinha) * 24 + 4}" text-anchor="middle" class="d-sub">+${qtd - mostrar}</text>`;
  return g;
}

function desenhoTopologia(cenOriginal) {
  // Como no gerador: lista por ponto implica câmeras fixas; com um só ponto de acesso, quem
  // "circula" fica sempre nele.
  const cen = JSON.parse(JSON.stringify(cenOriginal));
  if (cen.dispositivos_por_ponto && cen.dispositivos_por_ponto.length) cen.mobilidade = "por_ponto";
  if ((cen.servidores?.quantidade || 1) === 1 && cen.mobilidade === "nomade") { cen.mobilidade = "fixa"; cen.ponto_fixo = 0; }
  const r = _resumo(cen);
  const n = r.n;
  const passo = n <= 4 ? 180 : n <= 6 ? 140 : n <= 8 ? 112 : 78;
  const compacto = passo < 100;
  const L = 40, W = Math.max(720, L * 2 + passo * n);
  const xs = Array.from({ length: n }, (_, i) => W / 2 + (i - (n - 1) / 2) * passo);
  const caixa = Math.min(140, passo - 18);
  const memoria = LIMITES.vram - r.yolo * LIMITES.vram_por_cliente;
  const semMemoria = memoria < LIMITES.mem_por_quadro;
  const yolo = (k) => _nYolo(k, cen.carga);
  const icone = cen.mobilidade === "por_ponto" ? _camera : _celular;
  const nomeDisp = cen.mobilidade === "por_ponto" ? ["câmera", "câmeras"] : ["dispositivo", "dispositivos"];
  const plural = (k) => `${k} ${k === 1 ? nomeDisp[0] : nomeDisp[1]}`;
  let g = "";

  // Nuvem: existe no EdgeCloudSim, mas o modelo de rede com GPU não tem WAN.
  {
    const cx = W / 2;
    g += `<g opacity="0.55"><path d="M${cx - 46} 52 a18 18 0 0 1 8 -32 a24 24 0 0 1 44 -6 a18 18 0 0 1 30 14 a16 16 0 0 1 -6 24 Z" fill="none" stroke="var(--ink2)" stroke-width="1.6" stroke-dasharray="5 4"/>` +
      `<text x="${cx}" y="42" text-anchor="middle" class="d-sub">nuvem</text></g>` +
      `<text x="${cx + 80}" y="30" class="d-nota">fora do modelo com GPU (sem WAN)</text>` +
      `<line x1="${cx}" y1="54" x2="${cx}" y2="96" stroke="var(--ink2)" stroke-width="1.4" stroke-dasharray="3 4" opacity="0.5"/>`;
  }

  // MAN entre os servidores.
  const yMan = 104;
  if (cen.man?.ligada && n > 1) {
    g += `<line x1="${xs[0]}" y1="${yMan}" x2="${xs[n - 1]}" y2="${yMan}" stroke="var(--verde)" stroke-width="4" stroke-linecap="round"/>`;
    const prop = r.vars["man.propagacao_ms"] ? `${_faixa(r.vars["man.propagacao_ms"])} ms` : `${String(cen.man.propagacao_ms).replace(".", ",")} ms`;
    g += `<text x="${xs[0]}" y="${yMan - 10}" class="d-rot" fill="var(--verde)">MAN · ${cen.man.banda_mbps} Mbps · ${prop} por sentido</text>`;
  } else if (n > 1) {
    g += `<text x="${xs[0]}" y="${yMan - 10}" class="d-nota">sem MAN: cada servidor só atende o próprio ponto de acesso</text>`;
  }

  // Servidores, pontos de acesso e dispositivos.
  const yS = 124, hS = 78, yAp = yS + hS + 30, yD = yAp + 52;
  let yFim = yD + 40;
  xs.forEach((x, i) => {
    const temGpu = i < r.comGpu;
    if (cen.man?.ligada && n > 1) g += `<line x1="${x}" y1="${yMan}" x2="${x}" y2="${yS}" stroke="var(--verde)" stroke-width="2.5"/>`;
    g += `<rect x="${x - caixa / 2}" y="${yS}" width="${caixa}" height="${hS}" rx="10" fill="var(--card)" stroke="${temGpu ? "var(--azul)" : "var(--line)"}" stroke-width="${temGpu ? 2.5 : 1.5}"/>`;
    g += `<text x="${x}" y="${yS + 20}" text-anchor="middle" class="d-rot">${compacto ? "S" : "Servidor "}${i}</text>`;
    g += `<text x="${x}" y="${yS + 37}" text-anchor="middle" class="d-sub">${cen.servidores?.modelo === "rodrigues" ? "1 VM" : "8 VMs"}</text>`;
    if (temGpu) {
      const lg = compacto ? 46 : 74;
      g += `<rect x="${x - lg / 2}" y="${yS + 46}" width="${lg}" height="22" rx="4" fill="${semMemoria ? "var(--er-bg)" : "var(--soft)"}" stroke="${semMemoria ? "var(--alerta)" : "var(--azul)"}"/>` +
        `<text x="${x}" y="${yS + 61}" text-anchor="middle" class="d-gpu" fill="${semMemoria ? "var(--alerta)" : "var(--azul)"}">${compacto ? "GPU" : "RTX 3050"}</text>`;
    } else {
      g += `<text x="${x}" y="${yS + 61}" text-anchor="middle" class="d-sub">sem GPU</text>`;
    }
    g += `<line x1="${x}" y1="${yS + hS}" x2="${x}" y2="${yAp - 14}" stroke="var(--line)" stroke-width="2"/>`;

    // Dispositivos neste ponto de acesso.
    let qtd = 0, rotulo = "";
    if (r.porPonto) {
      qtd = r.porPonto[i] || 0;
      rotulo = i === 0 && r.vars["dispositivos_por_ponto.0"] ? `${_faixa(r.vars["dispositivos_por_ponto.0"])} ${nomeDisp[1]} (varia)` : plural(qtd);
    } else if (cen.mobilidade === "fixa" && i === (cen.ponto_fixo || 0)) {
      qtd = r.total;
      rotulo = r.vars.dispositivos ? `${_faixa(r.vars.dispositivos)} ${nomeDisp[1]} (varia)` : plural(qtd);
    }
    const satura = yolo(qtd) > LIMITES.clientes_por_ap;
    const corAp = satura ? "var(--alerta)" : "var(--ink2)";
    g += _antena(x, yAp - 6, corAp);
    g += `<text x="${x}" y="${yAp + 24}" text-anchor="middle" class="d-sub">${compacto ? "AP" : "ponto de acesso"} ${i}</text>`;
    if (qtd) {
      g += _dispositivos(x, yD, qtd, icone, satura ? "var(--alerta)" : "var(--lar)", caixa);
      const linhas = Math.ceil(Math.min(qtd, 12) / Math.max(3, Math.floor(caixa / 22)));
      const yRot = yD + linhas * 24 + (qtd > 12 ? 26 : 4);
      g += `<text x="${x}" y="${yRot}" text-anchor="middle" class="d-rot" fill="${satura ? "var(--alerta)" : "var(--ink)"}">${_esc(rotulo)}</text>`;
      if (satura) g += `<text x="${x}" y="${yRot + 16}" text-anchor="middle" class="d-alerta">WLAN satura com mais de 9</text>`;
      yFim = Math.max(yFim, yRot + (satura ? 16 : 0));
    }
  });

  // Dispositivos circulando entre os pontos de acesso.
  let altura = Math.max(yD + 110, yFim + 48);
  if (cen.mobilidade === "nomade") {
    const yN = yD + 6;
    g += `<rect x="${xs[0] - caixa / 2}" y="${yN - 20}" width="${xs[n - 1] - xs[0] + caixa}" height="74" rx="12" fill="none" stroke="var(--lar)" stroke-dasharray="6 5"/>`;
    g += _dispositivos(W / 2, yN, r.total, _celular, "var(--lar)", Math.min(W - 120, 26 * 12));
    const rot = r.vars.dispositivos ? `${_faixa(r.vars.dispositivos)} dispositivos (varia)` : `${r.total} dispositivo${r.total === 1 ? "" : "s"}`;
    g += `<text x="${W / 2}" y="${yN + 44}" text-anchor="middle" class="d-rot">${_esc(rot)} circulando entre os pontos de acesso</text>`;
  }

  // Legenda e alertas gerais.
  const avisos = [];
  if (semMemoria) avisos.push(`memória da GPU insuficiente: cada GPU guarda o modelo de todos os ${r.yolo} clientes YOLO (${LIMITES.vram_por_cliente} MB cada); cabem no máximo ${LIMITES.max_clientes_yolo}`);
  if (r.comGpu === 0 && r.yolo > 0) avisos.push("há clientes YOLO, mas nenhum servidor tem GPU");
  // Legenda em sequência; a largura de cada texto é estimada em 7 px por caractere.
  const yLeg = altura - 26;
  const itens = [
    [icone(6, 0, "var(--lar)"), cen.carga === "mista" ? "dispositivo (30% rodam YOLO)" : "cliente YOLO, 30 quadros/s"],
    [`<rect x="0" y="-7" width="16" height="14" rx="3" fill="var(--soft)" stroke="var(--azul)"/>`, "GPU RTX 3050"],
    [`<line x1="0" y1="0" x2="20" y2="0" stroke="var(--verde)" stroke-width="4"/>`, "MAN"],
    ["", "VM = máquina virtual"],
  ];
  let xl = L;
  itens.forEach(([simbolo, texto]) => {
    g += `<g transform="translate(${xl},${yLeg})">${simbolo}<text x="${simbolo ? 24 : 0}" y="4" class="d-sub">${_esc(texto)}</text></g>`;
    xl += (simbolo ? 24 : 0) + texto.length * 7 + 22;
  });
  if (r.vars["servidores.com_gpu"]) {
    g += `<text x="${L}" y="${altura - 4}" class="d-nota">servidores com GPU: ${_esc(r.vars["servidores.com_gpu"].join(", "))} (varia; desenhado com ${r.comGpu})</text>`;
    altura += 18;
  }
  avisos.forEach((a, i) => (g += `<text x="${L}" y="${altura + i * 18}" class="d-alerta">${_esc(a)}</text>`));
  altura += avisos.length * 18 + 6;
  // Largura máxima igual à do desenho, para que o texto tenha o mesmo tamanho com 1 ou 8 servidores.
  return `<svg class="topologia" viewBox="0 0 ${W} ${altura}" style="max-width:${W}px" role="img" aria-label="Topologia do cenário">${g}</svg>`;
}
