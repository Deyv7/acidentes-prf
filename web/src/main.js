import "lenis/dist/lenis.css";
import "./estilo.css";
import { carregar, int, pct, esc } from "./dados.js";
import { paradas } from "./narrativa.js";
import { dicaHtml } from "./graficos.js";
import { montarExplorador } from "./explorador.js";
import { iniciarJornada } from "./jornada.js";
import { criarEstrada } from "./estrada.js";

for (const id of ["estrada-abertura", "estrada-fim"]) criarEstrada(document.getElementById(id));

function montarAbertura(d) {
  const S = d.resumo;
  document.getElementById("ab-kicker").textContent = `Rodovias federais · ${S.anos[0]} a ${S.anos[1]}`;
  document.getElementById("ab-lead").innerHTML =
    `A PRF registrou <strong>${int(S.ocorrencias)}</strong> acidentes nas rodovias federais em ${S.anos[1] - S.anos[0] + 1} anos. ` +
    `Em <strong>${int(S.graves)}</strong> deles alguém morreu ou ficou gravemente ferido. ` +
    `Esta viagem passa pelos lugares, horários e situações em que um acidente, quando acontece, tem mais chance de ser grave.`;
}

function montarParadas(d) {
  const trilho = document.getElementById("trilho");
  const lista = paradas(d);
  trilho.innerHTML = lista.map((p) => `
    <article class="parada${p.largo ? " larga" : ""}${p.estreito ? " estreita" : ""}" id="p-${p.id}" data-id="${p.id}" data-nome="${esc(p.nome)}"
      ${p.noite ? 'data-noite="1"' : ""} ${p.contramao ? 'data-contramao="1"' : ""} ${p.chuva ? 'data-chuva="1"' : ""} ${p.impacto ? 'data-impacto="1"' : ""}>
      <div class="parada-corpo">${p.html}</div>
    </article>`).join("");
  const cards = [...trilho.querySelectorAll(".parada")];
  lista.forEach((p, i) => p.montar(cards[i]));

  const nav = document.getElementById("estacoes");
  nav.innerHTML = lista.map((p, i) =>
    `<button type="button" class="estacao" aria-label="${String(i + 1).padStart(2, "0")} ${esc(p.nome)}"><span>${String(i + 1).padStart(2, "0")}</span><em>${esc(p.nome)}</em></button>`).join("");
  return { cards, estacoes: [...nav.querySelectorAll(".estacao")] };
}

function montarSobre(d) {
  const S = d.resumo;
  const regras = Object.entries(S.qualidade);
  const bloqueantes = regras.filter(([, q]) => q.bloqueante);
  const bloqueantesComFalha = bloqueantes.filter(([, q]) => Object.values(q.por_ano).some((v) => v > 0));
  const tratadas = regras.filter(([, q]) => !q.bloqueante);
  document.getElementById("ex-lead").textContent =
    `Os ${Object.keys(d.recortes).length} recortes da análise, com a proporção de graves, o intervalo de 95% e a comparação com a média. ` +
    `Comece pelos trechos de 10 km ou troque o recorte.`;
  document.getElementById("sobre-conteudo").innerHTML = `
    <div>
      <p class="kicker">Fonte</p>
      <p>Dados abertos da Polícia Rodoviária Federal, acidentes agrupados por ocorrência, ${S.anos[0]} a ${S.anos[1]}. Malha das UFs do IBGE, usada só como contorno do mapa.</p>
    </div>
    <div>
      <p class="kicker">Como foi feito</p>
      <p>Pipeline em camadas bronze, silver e gold com Spark e Delta Lake, rodando no Databricks e conferido com uma execução local. Grave é o acidente com pelo menos um morto ou ferido grave. A média geral é ${pct(S.media)}; entre os acidentes com vítima, ${pct(S.media_com_vitima)}.</p>
    </div>
    <div>
      <p class="kicker">Qualidade</p>
      <p>${regras.length} regras checadas em todos os anos. ${bloqueantes.length} delas bloqueiam o pipeline se uma linha falhar${bloqueantesComFalha.length === 0 ? ", e nenhuma falhou" : `; ${bloqueantesComFalha.length} falharam`}. As outras ${tratadas.length} têm tratamento documentado.</p>
    </div>`;
}

function ligarDicas() {
  const dica = document.getElementById("dica");
  let aberta = null;
  const posicionar = (x, y) => {
    const r = dica.getBoundingClientRect();
    let left = x + 16, top = y + 16;
    if (left + r.width > innerWidth - 8) left = x - r.width - 16;
    if (top + r.height > innerHeight - 8) top = y - r.height - 16;
    dica.style.transform = `translate(${Math.max(8, left)}px, ${Math.max(8, top)}px)`;
  };
  const mostrar = (alvo, x, y) => {
    if (alvo !== aberta) {
      dica.innerHTML = dicaHtml(alvo.dataset.dica);
      aberta?.classList.remove("em-foco");
      alvo.classList.add("em-foco");
      aberta = alvo;
    }
    dica.hidden = false;
    posicionar(x, y);
  };
  const esconder = () => { dica.hidden = true; aberta?.classList.remove("em-foco"); aberta = null; };
  document.addEventListener("pointermove", (e) => {
    const alvo = e.target.closest?.("[data-dica]");
    if (alvo) mostrar(alvo, e.clientX, e.clientY); else if (aberta) esconder();
  }, { passive: true });
  document.addEventListener("pointerdown", (e) => {
    const alvo = e.target.closest?.("[data-dica]");
    if (alvo) mostrar(alvo, e.clientX, e.clientY); else esconder();
  });
  addEventListener("scroll", () => { if (aberta) esconder(); }, { passive: true });
}

async function iniciar() {
  try {
    const d = await carregar();
    montarAbertura(d);
    const { cards, estacoes } = montarParadas(d);
    montarExplorador(document.getElementById("explorador"), d);
    montarSobre(d);
    ligarDicas();
    iniciarJornada({
      secao: document.getElementById("jornada"),
      trilho: document.getElementById("trilho"),
      cena: document.getElementById("cena"),
      cards, estacoes,
    });
  } catch (erro) {
    document.getElementById("ab-lead").textContent = `Não foi possível carregar os dados (${erro.message}).`;
    throw erro;
  }
}

iniciar();
