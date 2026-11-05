// As paradas da viagem. Cada texto é montado a partir dos JSON; as frases que
// dependem de um resultado (acima/abaixo, "mais que o dobro") são condicionais.
import { linhas, media as mediaDe, achar, comparavel, porInf, porPct, pct, int, rotulo, esc, NOME_UF, naUF } from "./dados.js";
import { floresta, horas, dispersao, mapa, cem, colunasMes, duasContas, legendaComparacao } from "./graficos.js";

const MESES_LONGOS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
  "setembro", "outubro", "novembro", "dezembro"];
const curto = (s, n = 46) => (s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s);
const alternador = (rotulo = "Contar entre") => `
  <div class="segmentado" role="group" aria-label="${rotulo}">
    <button type="button" data-modo="todos" aria-pressed="true">Todos os acidentes</button>
    <button type="button" data-modo="vitima" aria-pressed="false">Só com vítima</button>
  </div>`;

function cabecalho(n, nome) {
  return `<p class="kicker"><span class="placa">${String(n).padStart(2, "0")}</span>${nome}</p>`;
}
const numero = (valor, legenda) => `<div class="numero"><strong>${valor}</strong><span>${legenda}</span></div>`;

/** Liga um alternador "todos / com vítima" ao redesenho de um gráfico. */
function ligarModo(raiz, desenhar) {
  const botoes = raiz.querySelectorAll("[data-modo]");
  desenhar("todos");
  botoes.forEach((b) => b.addEventListener("click", () => {
    botoes.forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    desenhar(b.dataset.modo);
  }));
}

export function paradas(d) {
  const R = d.recortes, S = d.resumo, nMin = S.n_min;
  const M = S.media;
  const lista = [];

  // ---------- 01 partida ----------
  const em100 = Math.round(M * 100);
  lista.push({
    id: "partida", nome: "Partida",
    html: `
      <div class="parada-texto">
        ${cabecalho(1, "Partida")}
        <h2>De cada 100 acidentes, ${em100} são graves</h2>
        <p>Grave, aqui, é o acidente com pelo menos um morto ou um ferido grave. De ${S.anos[0]} a ${S.anos[1]}, a PRF registrou <strong>${int(S.ocorrencias)}</strong> acidentes nas rodovias federais. <strong>${int(S.graves)}</strong> foram graves, e <strong>${int(S.mortos)}</strong> pessoas morreram.</p>
        <p>Essa média, <strong>${pct(M)}</strong>, é a linha de referência da viagem. Cada parada mostra o que puxa a proporção de graves para cima ou para baixo.</p>
      </div>
      <div class="parada-grafico estreito">
        <div class="grafico quadrado" data-g="cem"></div>
        <div class="legenda"><span><i class="chave grave"></i>grave</span><span><i class="chave leve"></i>sem morto nem ferido grave</span></div>
      </div>`,
    montar(el) {
      el.querySelector('[data-g="cem"]').innerHTML = cem(em100, `${em100} de cada 100 acidentes foram graves`);
    },
  });

  // ---------- 02 como ler ----------
  const brs = linhas(R.br).filter(comparavel);
  const porGraves = [...brs].sort((a, b) => b.graves - a.graves);
  const grandesAltas = brs.filter((l) => l.n >= 5000).sort((a, b) => b.pct - a.pct);
  const b1 = porGraves[0], b2 = porGraves[1], bAlta = grandesAltas[0];
  const lado = (l) => (l.pct < R.br.media ? "abaixo" : "acima");
  lista.push({
    id: "leitura", nome: "Como ler",
    html: `
      <div class="parada-texto">
        ${cabecalho(2, "Antes de sair")}
        <h2>Muito acidente não quer dizer acidente grave</h2>
        <p>A fonte não traz o volume de tráfego, então os dados não dizem onde é mais arriscado dirigir. Eles respondem a uma pergunta mais estreita: <strong>dado que houve um acidente, qual a chance de ele ter sido grave?</strong></p>
        <p>A ${b1.valor} tem o maior número de graves, ${int(b1.graves)}, e a ${b2.valor} vem em seguida, com ${int(b2.graves)}. As duas ficam ${lado(b1) === lado(b2) ? `${lado(b1)} da média na proporção` : "em lados diferentes da média"}: ${pct(b1.pct)} e ${pct(b2.pct)}. Entre as rodovias com mais de ${int(5000)} acidentes, a maior proporção é a da ${bAlta.valor}, ${pct(bAlta.pct)}.</p>
        <p class="nota">Cada valor tem um intervalo de 95%. Só conta como acima ou abaixo da média quando o intervalo inteiro fica de um lado. Com menos de ${int(nMin)} acidentes, fica fora da comparação.</p>
      </div>
      <div class="parada-grafico">
        <p class="subtitulo">Rodovias com ${int(nMin)} acidentes ou mais: número de acidentes e proporção de graves</p>
        <div class="grafico" data-g="br"></div>
        ${legendaComparacao()}
      </div>`,
    montar(el) {
      el.querySelector('[data-g="br"]').innerHTML = dispersao(brs, {
        media: R.br.media, titulo: "Cada ponto é uma BR: número de acidentes contra proporção de graves",
        nomes: [b1.valor, b2.valor, bAlta.valor],
      });
    },
  });

  // ---------- 03 o lugar ----------
  const ufs = linhas(R.uf).filter(comparavel).sort(porInf);
  const ufTopo = ufs[0];
  const ufBaixa = [...ufs].sort((a, b) => a.sup - b.sup)[0];
  const ru = S.resumo_recortes.uf;
  const fora = ru.acima + ru.abaixo;
  lista.push({
    id: "lugar", nome: "O lugar", largo: true,
    html: `
      <div class="parada-texto">
        ${cabecalho(3, "O lugar")}
        <h2>Onde você está muda a chance</h2>
        ${numero(pct(ufTopo.pct), `dos acidentes ${naUF(ufTopo.valor)} foram graves, a maior proporção entre as UFs`)}
        <p>${ru.acima} UFs ficam acima da média, ${ru.abaixo} abaixo e ${ru.indistinguiveis} são indistinguíveis. No outro extremo está ${NOME_UF[ufBaixa.valor]}, com ${pct(ufBaixa.pct)}.</p>
        <p>Entre os acidentes com vítima, das ${fora} UFs fora da média, ${ru.mesmo_lado_com_vitima} ficam do mesmo lado.${ru.mesmo_lado_com_vitima / fora >= 0.9 ? " A diferença regional não vem só de um registro menor de acidentes leves." : ""}</p>
      </div>
      <div class="parada-grafico dupla">
        <figure>
          <p class="subtitulo">Proporção de graves em quadrados de ${String(d.mapa.passo).replace(".", ",")}°</p>
          <div class="grafico" data-g="mapa"></div>
        </figure>
        <figure>
          <div class="grafico-topo"><p class="subtitulo">Por UF</p>${alternador()}</div>
          <div class="grafico" data-g="uf"></div>
        </figure>
        <div class="span2">${legendaComparacao(nMin)}</div>
      </div>`,
    montar(el) {
      el.querySelector('[data-g="mapa"]').innerHTML = mapa(d.mapa, { titulo: "Mapa da proporção de graves", nMin });
      ligarModo(el, (modo) => {
        const ls = linhas(R.uf, modo).filter(comparavel).sort(porInf);
        el.querySelector('[data-g="uf"]').innerHTML = floresta(ls.map((l) => ({ rotulo: NOME_UF[l.valor], l })), {
          media: mediaDe(R.uf, modo), titulo: "Proporção de graves por UF", largura: 440, alturaLinha: 16, rotuloLarg: 132,
          destaque: [0, ls.length - 1],
        });
      });
    },
  });

  // ---------- 04 a estrada ----------
  const simples = achar(R.tipo_pista, "Simples"), dupla = achar(R.tipo_pista, "Dupla"), multipla = achar(R.tipo_pista, "Múltipla");
  lista.push({
    id: "estrada", nome: "A estrada",
    html: `
      <div class="parada-texto">
        ${cabecalho(4, "A estrada")}
        <h2>Uma pista para cada sentido</h2>
        ${numero(pct(simples.pct), "dos acidentes em pista simples foram graves")}
        <p>Na pista dupla, ${pct(dupla.pct)}; na múltipla, ${pct(multipla.pct)}. A pista simples concentra ${pct(simples.n / S.ocorrencias)} dos acidentes.</p>
        <p>Uma explicação plausível, que a análise não testa: sem separação física, uma invasão da contramão vira colisão frontal.</p>
      </div>
      <div class="parada-grafico">
        <div class="grafico-topo"><p class="subtitulo">Proporção de graves por tipo de pista</p>${alternador()}</div>
        <div class="grafico" data-g="pista"></div>
        ${legendaComparacao()}
      </div>`,
    montar(el) {
      ligarModo(el, (modo) => {
        const ls = linhas(R.tipo_pista, modo).sort((a, b) => b.pct - a.pct);
        el.querySelector('[data-g="pista"]').innerHTML = floresta(ls.map((l) => ({ rotulo: `Pista ${l.valor.toLowerCase()}`, l })), {
          media: mediaDe(R.tipo_pista, modo), titulo: "Proporção de graves por tipo de pista", largura: 520, alturaLinha: 70, rotuloLarg: 130,
          destaque: [0, 1, 2]
        });
      });
    },
  });

  // ---------- 05 a hora ----------
  const hs = linhas(R.hora);
  const hMax = [...hs].sort((a, b) => b.pct - a.pct)[0], hMin = [...hs].sort((a, b) => a.pct - b.pct)[0];
  const hsV = linhas(R.hora, "vitima"), hMaxV = [...hsV].sort((a, b) => b.pct - a.pct)[0];
  const nHA = hs.filter((l) => l.comp === "a").length, nHB = hs.filter((l) => l.comp === "b").length;
  const dom = achar(R.dia_semana, "domingo"), sab = achar(R.dia_semana, "sábado");
  const ORDEM_DIAS = ["domingo", "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado"];
  lista.push({
    id: "hora", nome: "A hora", largo: true, noite: true,
    html: `
      <div class="parada-texto">
        ${cabecalho(5, "A hora")}
        <h2>Quando escurece, a proporção sobe</h2>
        ${numero(pct(hMax.pct), `dos acidentes às ${rotulo("hora", hMax.valor)} foram graves, o maior valor do dia`)}
        <p>Das 24 horas, ${nHA} ficam acima da média e ${nHB} abaixo. O menor valor é às ${rotulo("hora", hMin.valor)}, com ${pct(hMin.pct)}. Entre os acidentes com vítima, o pico vai para as ${rotulo("hora", hMaxV.valor)}: ${pct(hMaxV.pct)}.</p>
        <p>No fim de semana também: ${pct(dom.pct)} no domingo e ${pct(sab.pct)} no sábado.</p>
      </div>
      <div class="parada-grafico dupla larga-esq">
        <figure>
          <div class="grafico-topo"><p class="subtitulo">Proporção de graves por hora</p>${alternador()}</div>
          <div class="grafico" data-g="hora"></div>
        </figure>
        <figure>
          <p class="subtitulo">Por dia da semana</p>
          <div class="grafico" data-g="dia"></div>
        </figure>
        <div class="span2">${legendaComparacao()}</div>
      </div>`,
    montar(el) {
      ligarModo(el, (modo) => {
        const ls = linhas(R.hora, modo).sort((a, b) => Number(a.valor) - Number(b.valor));
        const mx = [...ls].sort((a, b) => b.pct - a.pct)[0], mn = [...ls].sort((a, b) => a.pct - b.pct)[0];
        el.querySelector('[data-g="hora"]').innerHTML = horas(ls, {
          media: mediaDe(R.hora, modo), titulo: "Proporção de graves por hora do dia",
          destaque: [Number(mx.valor), Number(mn.valor)],
        });
        const ds = linhas(R.dia_semana, modo).sort((a, b) => ORDEM_DIAS.indexOf(a.valor) - ORDEM_DIAS.indexOf(b.valor));
        el.querySelector('[data-g="dia"]').innerHTML = floresta(ds.map((l) => ({ rotulo: l.valor, l })), {
          media: mediaDe(R.dia_semana, modo), titulo: "Proporção de graves por dia da semana",
          largura: 400, rotuloLarg: 112, alturaLinha: 46,
        });
      });
    },
  });

  // ---------- 06 o tempo ----------
  const chuva = achar(R.condicao_meteorologica, "Chuva"), claro = achar(R.condicao_meteorologica, "Céu Claro");
  lista.push({
    id: "tempo", nome: "O tempo", noite: true, chuva: true,
    html: `
      <div class="parada-texto">
        ${cabecalho(6, "O tempo")}
        <h2>A chuva não aparece onde se espera</h2>
        ${numero(pct(chuva.pct), `dos acidentes com chuva foram graves, contra ${pct(claro.pct)} com céu claro`)}
        <p>Isso não quer dizer que a chuva deixa a estrada mais segura. Sem saber quantos carros rodam na chuva, não dá para comparar risco.</p>
        <p>Quer dizer que os acidentes na chuva são, em proporção, ${chuva.pct < claro.pct ? "menos" : "mais"} graves. Talvez porque se anda mais devagar; a hipótese não foi verificada.</p>
      </div>
      <div class="parada-grafico">
        <div class="grafico-topo"><p class="subtitulo">Proporção de graves por condição do tempo</p>${alternador()}</div>
        <div class="grafico" data-g="tempo"></div>
        ${legendaComparacao(nMin)}
      </div>`,
    montar(el) {
      ligarModo(el, (modo) => {
        const ls = linhas(R.condicao_meteorologica, modo).sort(porPct);
        const ix = ls.map((l, k) => (l.valor === "Chuva" || l.valor === "Céu Claro" ? k : -1)).filter((k) => k >= 0);
        el.querySelector('[data-g="tempo"]').innerHTML = floresta(ls.map((l) => ({ rotulo: l.valor, l })), {
          media: mediaDe(R.condicao_meteorologica, modo), titulo: "Proporção de graves por condição do tempo",
          alturaLinha: 30, rotuloLarg: 150, destaque: ix,
        });
      });
    },
  });

  // ---------- 07 a causa ----------
  const t = d.transicao.causa_acidente;
  const iTroca = t.lista_antiga.findIndex((v, i) => i > 0 && v === 0 && t.lista_antiga[i - 1] > 0);
  const [anoTroca, mesTroca] = t.mes[iTroca].split("-");
  const contramao = achar(R.causa_acidente, "Transitar na contramão");
  const rc = S.resumo_recortes.causa_acidente;
  lista.push({
    id: "causa", nome: "A causa", largo: true, noite: true, contramao: true,
    html: `
      <div class="parada-texto">
        ${cabecalho(7, "A causa")}
        <h2>Um carro invade a contramão</h2>
        ${numero(pct(contramao.pct), `dos acidentes causados por transitar na contramão foram graves, em ${int(contramao.n)} acidentes`)}
        <p>No topo estão as causas com pedestres e a contramão. A causa é a que o policial registra, uma por acidente.</p>
        <p>A lista mudou em ${MESES_LONGOS[Number(mesTroca) - 1]} de ${anoTroca}, sem correspondência um para um com a antiga, então a comparação usa só ${anoTroca} em diante: ${int(rc.ocorrencias_comparaveis)} acidentes, com média de ${pct(R.causa_acidente.media)}.</p>
      </div>
      <div class="parada-grafico">
        <div class="grafico-topo"><p class="subtitulo">As 12 causas mais graves (${anoTroca} em diante)</p>${alternador()}</div>
        <div class="grafico" data-g="causa"></div>
        ${legendaComparacao()}
        <figure class="mini">
          <p class="subtitulo">Acidentes por mês com causa que só existe na lista antiga</p>
          <div class="grafico" data-g="troca"></div>
        </figure>
      </div>`,
    montar(el) {
      el.querySelector('[data-g="troca"]').innerHTML = colunasMes(t, { titulo: "Acidentes por mês com causa da lista antiga" });
      ligarModo(el, (modo) => {
        const ls = linhas(R.causa_acidente, modo).filter(comparavel).sort(porInf).slice(0, 12);
        const ix = ls.findIndex((l) => l.valor === contramao.valor);
        el.querySelector('[data-g="causa"]').innerHTML = floresta(ls.map((l) => ({ rotulo: curto(l.valor, 40), completo: l.valor, l })), {
          media: mediaDe(R.causa_acidente, modo), titulo: "Causas com maior proporção de graves",
          largura: 640, rotuloLarg: 262, alturaLinha: 26, destaque: ix >= 0 ? [ix] : [],
        });
      });
    },
  });

  // ---------- 08 o impacto ----------
  const tipos = linhas(R.tipo_acidente);
  const tiposComp = tipos.filter(comparavel).sort((a, b) => b.pct - a.pct);
  const frontal = achar(R.tipo_acidente, "Colisão frontal");
  const acimaDaFrontal = tiposComp.filter((l) => l.pct > frontal.pct);
  const maisMortos = [...tipos].sort((a, b) => b.mortos - a.mortos)[0];
  const t1 = tiposComp[0];
  lista.push({
    id: "impacto", nome: "O impacto", noite: true, impacto: true,
    html: `
      <div class="parada-texto">
        ${cabecalho(8, "O impacto")}
        <h2>Colisão frontal</h2>
        ${numero(pct(frontal.pct), "das colisões frontais foram graves")}
        <p>${acimaDaFrontal.length === 0 ? "É o tipo de acidente com a maior proporção de graves." : `Só ${acimaDaFrontal.map((l) => l.valor.toLowerCase()).join(", ")} tem proporção maior: ${acimaDaFrontal.map((l) => pct(l.pct)).join(", ")}.`}${frontal.pct > 2 * M ? ` Fica acima do dobro da média, ${pct(M)}.` : ""}</p>
        ${maisMortos.valor === frontal.valor
          ? `<p>É também o tipo com mais mortos em números absolutos: <strong>${int(frontal.mortos)}</strong> de ${S.anos[0]} a ${S.anos[1]}.</p>`
          : `<p>O tipo com mais mortos em números absolutos é ${esc(maisMortos.valor.toLowerCase())}, com ${int(maisMortos.mortos)}; a colisão frontal soma ${int(frontal.mortos)}.</p>`}
      </div>
      <div class="parada-grafico">
        <div class="grafico-topo"><p class="subtitulo">Proporção de graves por tipo de acidente</p>${alternador()}</div>
        <div class="grafico" data-g="tipo"></div>
        ${legendaComparacao(nMin)}
      </div>`,
    montar(el) {
      ligarModo(el, (modo) => {
        const ls = linhas(R.tipo_acidente, modo).sort(porPct);
        el.querySelector('[data-g="tipo"]').innerHTML = floresta(ls.map((l) => ({ rotulo: curto(l.valor, 30), completo: l.valor, l })), {
          media: mediaDe(R.tipo_acidente, modo), titulo: "Proporção de graves por tipo de acidente",
          rotuloLarg: 210, alturaLinha: 20, destaque: [ls.findIndex((l) => l.valor === t1.valor), ls.findIndex((l) => l.valor === frontal.valor)],
        });
      });
    },
  });

  // ---------- 09 a segunda conta ----------
  const alcool = "Ingestão de álcool pelo condutor";
  const aT = achar(R.causa_acidente, alcool), aV = achar(R.causa_acidente, alcool, "vitima");
  const nome = (c) => ({ a: "acima da", b: "abaixo da", i: "indistinguível da" })[c];
  lista.push({
    id: "conta", nome: "A outra conta", noite: true,
    html: `
      <div class="parada-texto">
        ${cabecalho(9, "Depois")}
        <h2>Quando a conta muda a conclusão</h2>
        <p>Um lugar que registra menos acidentes sem vítima tem uma proporção de graves maior sem que os seus acidentes sejam mais graves. Por isso toda comparação foi refeita só entre os acidentes com vítima.</p>
        <p>Na ingestão de álcool pelo condutor, as duas contas discordam. Entre todos os acidentes, ${pct(aT.pct)} foram graves, ${nome(aT.comp)} média. Entre os com vítima, ${pct(aV.pct)}, ${nome(aV.comp)} média. Muitos acidentes com condutor alcoolizado são registrados sem vítima.</p>
      </div>
      <div class="parada-grafico">
        <p class="subtitulo">Ingestão de álcool pelo condutor, nas duas contas</p>
        <div class="grafico" data-g="alcool"></div>
        ${legendaComparacao()}
      </div>`,
    montar(el) {
      el.querySelector('[data-g="alcool"]').innerHTML = duasContas([
        { rotulo: "Todos os acidentes", curto: "Todos", l: aT, media: R.causa_acidente.media },
        { rotulo: "Só com vítima", curto: "Com vítima", l: aV, media: R.causa_acidente.media_com_vitima },
      ], { titulo: "Álcool do condutor: proporção de graves em cada conta, com a média de cada uma" });
    },
  });

  // ---------- 10 o que não dá para dizer ----------
  const rt = S.resumo_recortes.trecho_10km;
  lista.push({
    id: "limites", nome: "Limites", noite: true, largo: true,
    html: `
      <div class="parada-texto largo-texto">
        ${cabecalho(10, "Fim da viagem")}
        <h2>O que estes dados não dizem</h2>
        <p>A viagem mostrou em que situações um acidente, quando acontece, costuma ser mais grave. Quatro perguntas ficam sem resposta:</p>
        <ol class="lista limites">
          <li><strong>Onde é mais perigoso dirigir.</strong> A base não diz quantos carros passam em cada estrada, e uma rodovia movimentada tem muitos acidentes só por ter muito carro. Por isso a medida aqui é outra: de cada 100 acidentes, quantos foram graves.</li>
          <li><strong>Qual fator pesa mais.</strong> Cada parada olhou uma coisa de cada vez, mas noite, fim de semana, pista simples e a região Nordeste costumam aparecer juntos. Parte do que a hora mostra pode vir da estrada, e o contrário também. Separar os efeitos fica para um modelo estatístico, a próxima etapa do projeto.</li>
          <li><strong>Se um trecho específico é perigoso.</strong> Foram comparados ${int(rt.comparaveis)} trechos de 10 km, e com tantos trechos alguns ficam acima da média por acaso. A lista do explorador mostra onde olhar com mais atenção; ela não é um veredito sobre cada trecho.</li>
          <li><strong>O que ficou fora do registro.</strong> A base tem só os acidentes registrados pela PRF, nas rodovias federais. Estradas estaduais e municipais não entram.</li>
        </ol>
        <a class="botao" href="#explorar">Explorar todos os recortes</a>
      </div>`,
    montar() {},
  });

  return lista;
}
