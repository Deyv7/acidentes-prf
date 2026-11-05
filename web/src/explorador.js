// Explorador: qualquer recorte, as duas contas, busca e ordenação.
import { linhas, media as mediaDe, comparavel, pct, int, rotulo, esc, COMPARACAO, NOME_RECORTE } from "./dados.js";

const PAGINA = 25;

export function montarExplorador(raiz, d) {
  const R = d.recortes;
  const estado = { recorte: "trecho_10km", modo: "todos", soComparaveis: true, busca: "", ordem: "inf", desc: true, limite: PAGINA };

  raiz.innerHTML = `
    <div class="controles">
      <label class="campo"><span>Recorte</span>
        <select class="ctl" id="ex-recorte">${Object.entries(NOME_RECORTE).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select>
      </label>
      <div class="campo"><span>Contar entre</span>
        <div class="segmentado" role="group" aria-label="Contar entre">
          <button type="button" data-modo="todos" aria-pressed="true">Todos</button>
          <button type="button" data-modo="vitima" aria-pressed="false">Só com vítima</button>
        </div>
      </div>
      <div class="campo"><span>Mostrar</span>
        <div class="segmentado" role="group" aria-label="Mostrar">
          <button type="button" data-filtro="comp" aria-pressed="true">Comparáveis</button>
          <button type="button" data-filtro="todos" aria-pressed="false">Todos</button>
        </div>
      </div>
      <label class="campo busca"><span>Buscar</span>
        <input class="ctl" id="ex-busca" type="search" placeholder="Ex.: BR-116, Recife, Colisão" autocomplete="off">
      </label>
    </div>
    <p class="ex-resumo" id="ex-resumo" aria-live="polite"></p>
    <div class="tabela-wrap" data-lenis-prevent>
      <table class="tabela">
        <thead><tr>
          <th scope="col">#</th>
          <th scope="col"><button data-ordem="valor">Valor</button></th>
          <th scope="col" class="num"><button data-ordem="n">Acidentes</button></th>
          <th scope="col" class="num"><button data-ordem="graves">Graves</button></th>
          <th scope="col" class="num"><button data-ordem="pct">% graves</button></th>
          <th scope="col"><button data-ordem="inf">Intervalo de 95%</button></th>
          <th scope="col">Comparação</th>
          <th scope="col" class="num"><button data-ordem="mortos">Mortos</button></th>
        </tr></thead>
        <tbody id="ex-corpo"></tbody>
      </table>
    </div>
    <button class="botao secundario mais" id="ex-mais" type="button">Mostrar mais</button>`;

  const $ = (s) => raiz.querySelector(s);
  $("#ex-recorte").value = estado.recorte;

  function desenhar() {
    const r = R[estado.recorte];
    const m = mediaDe(r, estado.modo);
    let ls = linhas(r, estado.modo);
    const total = ls.length;
    if (estado.soComparaveis) ls = ls.filter(comparavel);
    if (estado.busca) {
      const q = estado.busca.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
      ls = ls.filter((l) => `${l.valor} ${rotulo(estado.recorte, l.valor)}`.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().includes(q));
    }
    const k = estado.ordem, sinal = estado.desc ? -1 : 1;
    ls.sort((a, b) => {
      const va = a[k] ?? -Infinity, vb = b[k] ?? -Infinity;
      return (typeof va === "string" ? va.localeCompare(vb, "pt-BR") : va - vb) * sinal;
    });

    // Escala comum para as barrinhas de IC.
    const comIc = ls.filter((l) => l.inf != null);
    const lo = Math.min(m, ...comIc.map((l) => l.inf)), hi = Math.max(m, ...comIc.map((l) => l.sup));
    const x = (v) => ((v - lo) / (hi - lo || 1)) * 100;

    $("#ex-resumo").textContent =
      `${int(ls.length)} de ${int(total)} valores · média do recorte ${pct(m)}` +
      (estado.modo === "vitima" ? " (só acidentes com vítima)" : "");
    $("#ex-corpo").innerHTML = ls.slice(0, estado.limite).map((l, i) => `
      <tr>
        <td class="num mudo">${i + 1}</td>
        <td class="valor">${esc(rotulo(estado.recorte, l.valor))}</td>
        <td class="num">${int(l.n)}</td>
        <td class="num">${int(l.graves)}</td>
        <td class="num">${pct(l.pct)}</td>
        <td class="mini">${l.inf == null ? "" : `<span class="mini-ic" aria-label="de ${pct(l.inf)} a ${pct(l.sup)}">
          <i class="mini-media" style="left:${x(m).toFixed(1)}%"></i>
          <i class="mini-faixa ${l.comp}" style="left:${x(l.inf).toFixed(1)}%;width:${Math.max(0.8, x(l.sup) - x(l.inf)).toFixed(1)}%"></i>
        </span>`}</td>
        <td><span class="selo ${l.comp}">${COMPARACAO[l.comp]}</span></td>
        <td class="num">${int(l.mortos)}</td>
      </tr>`).join("") || `<tr><td colspan="8" class="vazio">Nenhum valor encontrado.</td></tr>`;
    $("#ex-mais").hidden = ls.length <= estado.limite;
    raiz.querySelectorAll("[data-ordem]").forEach((b) => {
      const ativo = b.dataset.ordem === estado.ordem;
      b.closest("th").setAttribute("aria-sort", ativo ? (estado.desc ? "descending" : "ascending") : "none");
      b.dataset.seta = ativo ? (estado.desc ? "↓" : "↑") : "";
    });
  }

  $("#ex-recorte").addEventListener("change", (e) => { estado.recorte = e.target.value; estado.limite = PAGINA; desenhar(); });
  $("#ex-busca").addEventListener("input", (e) => { estado.busca = e.target.value.trim(); estado.limite = PAGINA; desenhar(); });
  $("#ex-mais").addEventListener("click", () => { estado.limite += PAGINA * 2; desenhar(); });
  raiz.querySelectorAll("[data-modo]").forEach((b) => b.addEventListener("click", () => {
    raiz.querySelectorAll("[data-modo]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    estado.modo = b.dataset.modo; desenhar();
  }));
  raiz.querySelectorAll("[data-filtro]").forEach((b) => b.addEventListener("click", () => {
    raiz.querySelectorAll("[data-filtro]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    estado.soComparaveis = b.dataset.filtro === "comp"; estado.limite = PAGINA; desenhar();
  }));
  raiz.querySelectorAll("[data-ordem]").forEach((b) => b.addEventListener("click", () => {
    if (estado.ordem === b.dataset.ordem) estado.desc = !estado.desc;
    else { estado.ordem = b.dataset.ordem; estado.desc = b.dataset.ordem !== "valor"; }
    desenhar();
  }));
  desenhar();
}
