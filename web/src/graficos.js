// Gráficos em SVG escrito à mão. Cor só pela comparação com a média
// (acima / abaixo / indistinguível); texto sempre nas cores de texto.
import { pct, pctNum, int, esc, COMPARACAO } from "./dados.js";

// ---------- dicas (tooltip) ----------
const registro = new Map();
let proximoId = 0;

/** Guarda o HTML das dicas de um gráfico; os elementos levam data-dica="id:i". */
export function registrar(conteudos) {
  const id = `g${proximoId++}`;
  registro.set(id, conteudos);
  return id;
}

export function dicaHtml(chave) {
  const [id, i] = chave.split(":");
  return registro.get(id)?.[Number(i)] ?? "";
}

export function htmlDica(titulo, l, media) {
  const linha = (k, v) => `<span class="linha-dica"><span>${k}</span><span>${v}</span></span>`;
  return `<b>${esc(titulo)}</b>` +
    linha("Acidentes", int(l.n)) +
    linha("% graves", pct(l.pct)) +
    (l.inf != null ? linha("IC 95%", `${pctNum(l.inf)} a ${pct(l.sup)}`) : "") +
    linha("Média", pct(media)) +
    `<span class="selo ${l.comp}">${COMPARACAO[l.comp]}</span>`;
}

// ---------- utilidades ----------
// Em tela estreita o gráfico é desenhado na largura real, para o texto não encolher.
const estreito = () => matchMedia("(max-width: 699px)").matches;
const larguraTela = () => Math.max(280, Math.min(600, innerWidth - 92));
const cortar = (s, max) => (s.length > max ? `${s.slice(0, max - 1).trimEnd()}…` : s);
const escala = (d0, d1, r0, r1) => (v) => r0 + ((v - d0) / (d1 - d0)) * (r1 - r0);
const cor = (comp) => ({ a: "var(--acima)", b: "var(--abaixo)", i: "var(--neutro)" })[comp] ?? "var(--neutro)";
const f = (x) => Math.round(x * 10) / 10;

function dominio(ls, media, folga = 0.02) {
  const lo = Math.min(media, ...ls.map((l) => l.inf ?? l.pct));
  const hi = Math.max(media, ...ls.map((l) => l.sup ?? l.pct));
  return [Math.max(0, Math.floor((lo - folga) * 20) / 20), Math.min(1, Math.ceil((hi + folga) * 20) / 20)];
}

function marcas(d0, d1, px = Infinity) {
  let passo = d1 - d0 > 0.35 ? 0.1 : 0.05;
  while (((d1 - d0) / passo) * 36 > px) passo *= 2; // rótulos com pelo menos 36px entre si
  const out = [];
  for (let v = Math.ceil(d0 / passo - 1e-9) * passo; v <= d1 + 1e-9; v += passo) out.push(Math.round(v * 100) / 100 + 0);
  return out;
}

const svg = (w, h, rotuloAria, corpo) =>
  `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${esc(rotuloAria)}">${corpo}</svg>`;

// ---------- intervalo por linha (forest plot) ----------
/**
 * rows: [{rotulo, l}] já ordenadas. Ponto = % graves; traço = IC 95%; linha = média.
 * destaque: índices das linhas que recebem o valor escrito.
 */
export function floresta(rows, { media, titulo, largura = 560, alturaLinha = 22, rotuloLarg = 168, destaque = [], dominioX } = {}) {
  const topo = 30, base = 26, dir = 56;
  if (estreito()) {
    largura = larguraTela();
    rotuloLarg = Math.min(rotuloLarg, Math.round(largura * 0.4));
    alturaLinha = Math.min(Math.max(alturaLinha, 20), 34);
  }
  const maxChars = Math.floor((rotuloLarg - 14) / 6.4);
  const h = topo + rows.length * alturaLinha + base;
  const [d0, d1] = dominioX ?? dominio(rows.map((r) => r.l), media);
  const x = escala(d0, d1, rotuloLarg, largura - dir);
  const id = registrar(rows.map((r) => htmlDica(r.completo ?? r.rotulo, r.l, media)));
  let s = "";
  for (const t of marcas(d0, d1, x(d1) - x(d0))) {
    s += `<line class="linha-grade" x1="${f(x(t))}" x2="${f(x(t))}" y1="${topo - 6}" y2="${h - base}"/>`;
    s += `<text class="eixo-texto" x="${f(x(t))}" y="${h - base + 16}" text-anchor="middle">${pctNum(t).replace(",0", "")}%</text>`;
  }
  s += `<line class="linha-media" x1="${f(x(media))}" x2="${f(x(media))}" y1="${topo - 10}" y2="${h - base}"/>`;
  s += `<text class="rotulo" x="${f(x(media))}" y="${topo - 14}" text-anchor="middle">média ${pct(media)}</text>`;
  rows.forEach((r, k) => {
    const y = topo + k * alturaLinha + alturaLinha / 2;
    const l = r.l, c = cor(l.comp), oco = !(l.comp in { a: 1, b: 1, i: 1 });
    const forte = destaque.includes(k);
    s += `<g class="linha-graf" data-dica="${id}:${k}">`;
    s += `<rect class="alvo" x="0" y="${f(y - alturaLinha / 2)}" width="${largura}" height="${alturaLinha}"/>`;
    s += `<text class="${forte ? "rotulo-forte" : "rotulo"}" x="${rotuloLarg - 12}" y="${f(y + 4.5)}" text-anchor="end">${esc(cortar(r.rotulo, maxChars))}</text>`;
    s += `<g class="anim" style="--i:${k}">`;
    if (l.inf != null) s += `<line class="ic" x1="${f(x(l.inf))}" x2="${f(x(l.sup))}" y1="${f(y)}" y2="${f(y)}" stroke="${c}"/>`;
    s += oco
      ? `<circle cx="${f(x(l.pct))}" cy="${f(y)}" r="4.5" fill="var(--cartao)" stroke="${c}" stroke-width="1.5"/>`
      : `<circle class="ponto-dado" cx="${f(x(l.pct))}" cy="${f(y)}" r="5" fill="${c}"/>`;
    if (forte) s += `<text class="valor-texto" x="${f(Math.min(x(l.sup ?? l.pct) + 8, largura - dir + 8))}" y="${f(y + 4.5)}">${pct(l.pct)}</text>`;
    s += `</g></g>`;
  });
  return svg(largura, h, titulo, s);
}

// ---------- hora a hora (colunas de ponto + IC) ----------
export function horas(ls, { media, titulo, destaque = [] }) {
  const curto = estreito();
  const w = curto ? larguraTela() : 520, h = curto ? 300 : 440, esq = 40, dir = 10, topo = 26, base = 28;
  const [d0, d1] = dominio(ls, media);
  const y = escala(d0, d1, h - base, topo);
  const passo = (w - esq - dir) / 24;
  const xc = (hora) => esq + passo * hora + passo / 2;
  const id = registrar(ls.map((l) => htmlDica(`${Number(l.valor)}h`, l, media)));
  let s = "";
  for (const t of marcas(d0, d1)) {
    s += `<line class="linha-grade" x1="${esq}" x2="${w - dir}" y1="${f(y(t))}" y2="${f(y(t))}"/>`;
    s += `<text class="eixo-texto" x="${esq - 8}" y="${f(y(t) + 4)}" text-anchor="end">${pctNum(t).replace(",0", "")}%</text>`;
  }
  s += `<line class="linha-media" x1="${esq}" x2="${w - dir}" y1="${f(y(media))}" y2="${f(y(media))}"/>`;
  s += `<text class="rotulo" x="${w - dir}" y="${f(y(media) - 7)}" text-anchor="end">média ${pct(media)}</text>`;
  ls.forEach((l, k) => {
    const hora = Number(l.valor), cx = xc(hora), c = cor(l.comp);
    s += `<g data-dica="${id}:${k}"><rect class="alvo" x="${f(cx - passo / 2)}" y="${topo}" width="${f(passo)}" height="${h - topo - base}"/>`;
    s += `<g class="anim sobe" style="--i:${hora}">`;
    s += `<line class="ic" x1="${f(cx)}" x2="${f(cx)}" y1="${f(y(l.inf))}" y2="${f(y(l.sup))}" stroke="${c}"/>`;
    s += `<circle class="ponto-dado" cx="${f(cx)}" cy="${f(y(l.pct))}" r="5" fill="${c}"/>`;
    if (destaque.includes(hora)) s += `<text class="valor-texto" x="${f(cx)}" y="${f(y(l.sup) - 9)}" text-anchor="middle">${pct(l.pct)}</text>`;
    s += `</g></g>`;
    if (hora % (curto ? 6 : 3) === 0) s += `<text class="eixo-texto" x="${f(cx)}" y="${h - base + 18}" text-anchor="middle">${hora}h</text>`;
  });
  return svg(w, h, titulo, s);
}

// ---------- dispersão: número de acidentes x % graves ----------
export function dispersao(ls, { media, titulo, nomes = [] }) {
  const w = estreito() ? larguraTela() : 640, h = estreito() ? 320 : 380, esq = 44, dir = 16, topo = 20, base = 34;
  const lx0 = Math.floor(Math.log10(Math.min(...ls.map((l) => l.n)))), lx1 = Math.ceil(Math.log10(Math.max(...ls.map((l) => l.n))));
  const [d0, d1] = dominio(ls.map((l) => ({ inf: l.pct, sup: l.pct })), media, 0.03);
  const x = escala(lx0, lx1, esq, w - dir), y = escala(d0, d1, h - base, topo);
  const id = registrar(ls.map((l) => htmlDica(l.valor, l, media)));
  let s = "";
  for (const t of marcas(d0, d1)) {
    s += `<line class="linha-grade" x1="${esq}" x2="${w - dir}" y1="${f(y(t))}" y2="${f(y(t))}"/>`;
    s += `<text class="eixo-texto" x="${esq - 8}" y="${f(y(t) + 4)}" text-anchor="end">${pctNum(t).replace(",0", "")}%</text>`;
  }
  for (let e = lx0; e <= lx1; e++) {
    s += `<text class="eixo-texto" x="${f(x(e))}" y="${h - base + 18}" text-anchor="${e === lx1 ? "end" : e === lx0 ? "start" : "middle"}">${int(10 ** e)}</text>`;
  }
  s += `<text class="eixo-texto" x="${w - dir}" y="${h - 2}" text-anchor="end">acidentes na rodovia (escala log) →</text>`;
  s += `<line class="linha-media" x1="${esq}" x2="${w - dir}" y1="${f(y(media))}" y2="${f(y(media))}"/>`;
  const usados = [];
  ls.forEach((l, k) => {
    const cx = x(Math.log10(l.n)), cy = y(l.pct);
    s += `<g data-dica="${id}:${k}" class="anim" style="--i:${k % 40}">`;
    s += `<circle class="alvo" cx="${f(cx)}" cy="${f(cy)}" r="10"/>`;
    s += `<circle class="ponto-dado" cx="${f(cx)}" cy="${f(cy)}" r="${l.comp === "p" ? 3.5 : 5}" fill="${l.comp === "p" ? "var(--cartao)" : cor(l.comp)}" stroke="${l.comp === "p" ? "var(--neutro)" : "var(--cartao)"}" stroke-width="1.5"/>`;
    if (nomes.includes(l.valor)) {
      const ancora = cx > w - 120 ? "end" : "start", dx = ancora === "end" ? -10 : 10;
      const perto = usados.some(([ux, uy]) => Math.abs(ux - cx) < 90 && Math.abs(uy - (cy - 8)) < 14);
      const ty = perto ? cy + 18 : cy - 8;
      usados.push([cx, ty]);
      s += `<text class="rotulo-forte" x="${f(cx + dx)}" y="${f(ty)}" text-anchor="${ancora}">${esc(l.valor)}</text>`;
    }
    s += `</g>`;
  });
  // Rótulo da média por cima dos pontos, numa etiqueta com fundo, no lado
  // da linha com menos pontos por perto.
  const texto = `média ${pct(media)}`, lw = texto.length * 7 + 16, lh = 22, ym = y(media);
  const ocupacao = (x0) => ls.filter((l) => { const cx = x(Math.log10(l.n)), cy = y(l.pct); return cx > x0 - 6 && cx < x0 + lw + 6 && Math.abs(cy - ym) < lh; }).length;
  const xl = ocupacao(esq + 4) <= ocupacao(w - dir - lw - 4) ? esq + 4 : w - dir - lw - 4;
  s += `<g class="media-etiqueta" pointer-events="none"><rect x="${f(xl)}" y="${f(ym - lh / 2)}" width="${lw}" height="${lh}" rx="${lh / 2}"/>`;
  s += `<text x="${f(xl + lw / 2)}" y="${f(ym + 4.5)}" text-anchor="middle">${texto}</text></g>`;
  return svg(w, h, titulo, s);
}

// ---------- mapa em grade ----------
export function mapa(m, { titulo, nMin }) {
  const lon0 = -74.5, lon1 = -32, lat0 = -34.5, lat1 = 6;
  const k = 12, cosLat = Math.cos((15 * Math.PI) / 180);
  const w = (lon1 - lon0) * k * cosLat, h = (lat1 - lat0) * k;
  const px = (lon) => (lon - lon0) * k * cosLat, py = (lat) => (lat1 - lat) * k;
  let s = "";
  for (const c of m.contorno) {
    const d = c.anel.map(([lo, la], i) => `${i ? "L" : "M"}${f(px(lo))} ${f(py(la))}`).join("") + "Z";
    s += `<path class="contorno" d="${d}"/>`;
  }
  const id = registrar(m.lat.map((lat, i) => {
    const l = { n: m.n[i], pct: m.pct[i], inf: m.inf[i], sup: m.sup[i], comp: m.comp[i] };
    const g = (v) => pctNum(v / 100).replace(",0", "");
    const t = `Lat. ${g(lat)}° a ${g(lat + m.passo)}°, long. ${g(m.lon[i])}° a ${g(m.lon[i] + m.passo)}°`;
    return htmlDica(t, l, m.media);
  }));
  const lado = m.passo * k, ladoX = lado * cosLat;
  m.lat.forEach((lat, i) => {
    const comp = m.comp[i];
    const classe = comp === "p" ? "celula pequena" : `celula ${comp}`;
    const x = px(m.lon[i]), y = py(lat + m.passo);
    s += `<rect class="${classe}" data-dica="${id}:${i}" x="${f(x + 0.6)}" y="${f(y + 0.6)}" width="${f(ladoX - 1.2)}" height="${f(lado - 1.2)}" rx="1.2" style="--i:${Math.round((lat1 - lat) / 2)}"${comp === "p" ? "" : ` fill="${cor(comp)}"`}/>`;
  });
  return svg(f(w), f(h), `${titulo}. Quadrados com menos de ${nMin} acidentes aparecem apagados.`, s);
}

// ---------- 100 pontos ----------
export function cem(qtd, titulo, { graves, total } = {}) {
  // Uma faixa de 100 acidentes: os graves à esquerda, o resto à direita,
  // com uma divisória fina a cada acidente.
  const w = estreito() ? larguraTela() : 460, h = 200;
  const y0 = 104, alt = 56, gap = 2;
  const x = (v) => (v / 100) * w;
  const xg = x(qtd);
  let s = "";
  s += `<g class="anim sobe" style="--i:0">
    <text class="cem-num" x="0" y="44">${qtd}</text>
    <text class="cem-rotulo" x="0" y="68">graves</text>
    ${graves != null ? `<text class="eixo-texto" x="0" y="88">${int(graves)} acidentes</text>` : ""}
  </g>
  <g class="anim sobe" style="--i:6">
    <text class="cem-num leve" x="${w}" y="44" text-anchor="end">${100 - qtd}</text>
    <text class="cem-rotulo" x="${w}" y="68" text-anchor="end">sem morto nem ferido grave</text>
    ${graves != null ? `<text class="eixo-texto" x="${w}" y="88" text-anchor="end">${int(total - graves)} acidentes</text>` : ""}
  </g>`;
  s += `<rect class="cem-resto" x="${f(xg + gap / 2)}" y="${y0}" width="${f(w - xg - gap / 2)}" height="${alt}" rx="6"/>`;
  s += `<rect class="cem-graves anim estica" x="0" y="${y0}" width="${f(xg - gap / 2)}" height="${alt}" rx="6"/>`;
  let dg = "", dr = "";
  for (let i = 1; i < 100; i++) {
    if (i === qtd) continue;
    const seg = `M${f(x(i))} ${y0 + 6}V${y0 + alt - 6}`;
    if (i < qtd) dg += seg; else dr += seg;
  }
  s += `<path class="cem-div anim" d="${dg}"/><path class="cem-div resto" d="${dr}"/>`;
  for (let v = 0; v <= 100; v += 10) {
    const xv = Math.min(w - 0.5, Math.max(0.5, x(v)));
    s += `<line class="linha-eixo" x1="${f(xv)}" x2="${f(xv)}" y1="${y0 + alt + 6}" y2="${y0 + alt + (v % 50 ? 10 : 14)}"/>`;
  }
  for (const v of [0, 50, 100]) s += `<text class="eixo-texto" x="${f(x(v))}" y="${y0 + alt + 32}" text-anchor="${v === 0 ? "start" : v === 100 ? "end" : "middle"}">${v === 100 ? "100 acidentes" : v}</text>`;
  return svg(w, h, titulo, s);
}

// ---------- colunas por mês (troca da lista de causas) ----------
export function colunasMes(t, { titulo }) {
  const w = estreito() ? larguraTela() : 640, h = 120, esq = 50, dir = 8, topo = 10, base = 22;
  const max = Math.max(...t.lista_antiga);
  const y = escala(0, max, h - base, topo);
  const passo = (w - esq - dir) / t.mes.length, larg = Math.max(3, passo - 4);
  const id = registrar(t.mes.map((m, i) => `<b>${m}</b><span class="linha-dica"><span>Com causa da lista antiga</span><span>${int(t.lista_antiga[i])}</span></span><span class="linha-dica"><span>Todos os acidentes</span><span>${int(t.ocorrencias[i])}</span></span>`));
  let s = "";
  const topoEixo = Math.ceil(max / 1000) * 1000;
  for (const v of [0, topoEixo / 2, topoEixo]) {
    if (v > max * 1.05) continue;
    s += `<line class="linha-grade" x1="${esq}" x2="${w - dir}" y1="${f(y(v))}" y2="${f(y(v))}"/>`;
    s += `<text class="eixo-texto" x="${esq - 8}" y="${f(y(v) + 4)}" text-anchor="end">${int(v)}</text>`;
  }
  t.mes.forEach((m, i) => {
    const x = esq + passo * i + (passo - larg) / 2, v = t.lista_antiga[i];
    const alto = y(0) - y(v);
    s += `<g data-dica="${id}:${i}"><rect class="alvo" x="${f(esq + passo * i)}" y="${topo}" width="${f(passo)}" height="${h - topo - base}"/>`;
    if (v > 0) s += `<path class="anim cresce barra-serie" style="--i:${i}" d="M${f(x)} ${f(y(0))}V${f(y(v) + Math.min(4, alto))}q0 -${f(Math.min(4, alto))} ${f(Math.min(4, alto))} -${f(Math.min(4, alto))}H${f(x + larg - Math.min(4, alto))}q${f(Math.min(4, alto))} 0 ${f(Math.min(4, alto))} ${f(Math.min(4, alto))}V${f(y(0))}Z"/>`;
    s += `</g>`;
    if (m.endsWith("-01")) s += `<text class="eixo-texto" x="${f(x + larg / 2)}" y="${h - base + 17}" text-anchor="start">jan ${m.slice(0, 4)}</text>`;
  });
  s += `<line class="linha-eixo" x1="${esq}" x2="${w - dir}" y1="${f(y(0))}" y2="${f(y(0))}"/>`;
  return svg(w, h, titulo, s);
}

// ---------- duas contas, cada uma com a sua média ----------
export function duasContas(itens, { titulo }) {
  // itens: [{rotulo, l, media}]
  const w = estreito() ? larguraTela() : 560, alt = 96, topo = 10, base = 26, esq = estreito() ? 104 : 150, dir = 60;
  const h = topo + itens.length * alt + base;
  const todos = itens.flatMap((it) => [it.l.inf, it.l.sup, it.media]);
  const d0 = Math.floor((Math.min(...todos) - 0.03) * 20) / 20, d1 = Math.ceil((Math.max(...todos) + 0.03) * 20) / 20;
  const x = escala(d0, d1, esq, w - dir);
  const id = registrar(itens.map((it) => htmlDica(it.rotulo, it.l, it.media)));
  let s = "";
  for (const t of marcas(d0, d1, x(d1) - x(d0))) {
    s += `<line class="linha-grade" x1="${f(x(t))}" x2="${f(x(t))}" y1="${topo}" y2="${h - base}"/>`;
    s += `<text class="eixo-texto" x="${f(x(t))}" y="${h - base + 16}" text-anchor="middle">${pctNum(t).replace(",0", "")}%</text>`;
  }
  itens.forEach((it, k) => {
    const y = topo + k * alt + alt / 2 + 6, c = cor(it.l.comp);
    s += `<g data-dica="${id}:${k}"><rect class="alvo" x="0" y="${topo + k * alt}" width="${w}" height="${alt}"/>`;
    s += `<text class="rotulo-forte" x="${esq - 14}" y="${f(y + 4.5)}" text-anchor="end">${esc(estreito() ? (it.curto ?? it.rotulo) : it.rotulo)}</text>`;
    s += `<line class="linha-media" x1="${f(x(it.media))}" x2="${f(x(it.media))}" y1="${f(y - 16)}" y2="${f(y + 16)}"/>`;
    s += `<text class="rotulo" x="${f(x(it.media))}" y="${f(y - 21)}" text-anchor="middle">média ${pct(it.media)}</text>`;
    s += `<g class="anim" style="--i:${k * 4}"><line class="ic" x1="${f(x(it.l.inf))}" x2="${f(x(it.l.sup))}" y1="${y}" y2="${y}" stroke="${c}"/>`;
    s += `<circle class="ponto-dado" cx="${f(x(it.l.pct))}" cy="${y}" r="6" fill="${c}"/>`;
    s += `<text class="valor-texto" x="${f(x(it.l.sup) + 10)}" y="${f(y + 4.5)}">${pct(it.l.pct)}</text></g></g>`;
  });
  return svg(w, h, titulo, s);
}

export function legendaComparacao(nMin = null) {
  return `<div class="legenda" aria-label="Legenda">
    <span><i class="chave acima"></i>acima da média</span>
    <span><i class="chave neutro"></i>indistinguível</span>
    <span><i class="chave abaixo"></i>abaixo da média</span>
    ${nMin ? `<span><i class="chave pequena"></i>menos de ${int(nMin)} acidentes</span>` : ""}
    <span><i class="chave ic-chave"></i>intervalo de 95%</span>
  </div>`;
}
