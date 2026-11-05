// Leitura dos JSON gerados por src/exportar_web.py e formatação de números.
// Nenhum número da página é escrito à mão: tudo sai daqui.

export async function carregar() {
  const nomes = ["resumo", "recortes", "transicao", "mapa"];
  const respostas = await Promise.all(
    nomes.map((n) => fetch(`./dados/${n}.json`).then((r) => {
      if (!r.ok) throw new Error(`${n}.json: ${r.status}`);
      return r.json();
    })),
  );
  return Object.fromEntries(nomes.map((n, i) => [n, respostas[i]]));
}

const fmtInt = new Intl.NumberFormat("pt-BR");
const fmtPct = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

export const int = (x) => fmtInt.format(x);
export const pct = (x) => (x == null ? "–" : `${fmtPct.format(x * 100)}%`);
export const pctNum = (x) => fmtPct.format(x * 100);

// Modo "todos os acidentes" ou "só com vítima": mesmos campos, nomes diferentes no JSON.
export const CAMPOS = {
  todos: { n: "n", pct: "pct", inf: "inf", sup: "sup", comp: "comp", media: "media" },
  vitima: { n: "n_vitima", pct: "pct_vitima", inf: "inf_vitima", sup: "sup_vitima", comp: "comp_vitima", media: "media_com_vitima" },
};

/** Linhas de um recorte como objetos, no modo pedido. */
export function linhas(recorte, modo = "todos") {
  const c = CAMPOS[modo];
  return recorte.valor.map((valor, i) => ({
    i,
    valor,
    n: recorte[c.n][i],
    graves: recorte.graves[i],
    pct: recorte[c.pct][i],
    inf: recorte[c.inf][i],
    sup: recorte[c.sup][i],
    comp: recorte[c.comp][i],
    pos: recorte.pos[i],
    mortos: recorte.mortos[i],
    n_todos: recorte.n[i],
  }));
}

/** Comparáveis primeiro, depois por % de graves. */
export const porPct = (a, b) => (comparavel(b) - comparavel(a)) || (b.pct - a.pct);

const PREP_UF = { BA: "na", PB: "na", AL: "em", GO: "em", MT: "em", MS: "em", MG: "em", PE: "em", RO: "em", RR: "em", SC: "em", SP: "em", SE: "em" };
/** "no Maranhão", "na Bahia", "em São Paulo". */
export const naUF = (uf) => `${PREP_UF[uf] ?? "no"} ${NOME_UF[uf]}`;

export const media = (recorte, modo = "todos") => recorte[CAMPOS[modo].media];
export const comparavel = (l) => l.comp === "a" || l.comp === "b" || l.comp === "i";

export function achar(recorte, valor, modo = "todos") {
  const l = linhas(recorte, modo).find((x) => x.valor === valor);
  if (!l) throw new Error(`valor ausente: ${valor}`);
  return l;
}

/** Ordena pelo limite inferior do IC (a mesma regra da análise). */
export const porInf = (a, b) => b.inf - a.inf;

export const COMPARACAO = {
  a: "acima da média",
  b: "abaixo da média",
  i: "indistinguível",
  p: "amostra pequena",
  f: "fora da comparação",
};

export const NOME_RECORTE = {
  uf: "UF",
  br: "Rodovia (BR)",
  trecho_10km: "Trecho de 10 km",
  municipio: "Município",
  hora: "Hora",
  dia_semana: "Dia da semana",
  fase_dia: "Fase do dia",
  mes: "Mês",
  ano: "Ano",
  condicao_meteorologica: "Condição do tempo",
  tipo_pista: "Tipo de pista",
  tipo_acidente: "Tipo de acidente",
  causa_acidente: "Causa (2021 em diante)",
};

export const NOME_UF = {
  AC: "Acre", AL: "Alagoas", AP: "Amapá", AM: "Amazonas", BA: "Bahia", CE: "Ceará",
  DF: "Distrito Federal", ES: "Espírito Santo", GO: "Goiás", MA: "Maranhão", MT: "Mato Grosso",
  MS: "Mato Grosso do Sul", MG: "Minas Gerais", PA: "Pará", PB: "Paraíba", PR: "Paraná",
  PE: "Pernambuco", PI: "Piauí", RJ: "Rio de Janeiro", RN: "Rio Grande do Norte",
  RS: "Rio Grande do Sul", RO: "Rondônia", RR: "Roraima", SC: "Santa Catarina",
  SP: "São Paulo", SE: "Sergipe", TO: "Tocantins",
};

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

/** Rótulo legível de um valor de recorte. */
export function rotulo(recorte, valor) {
  if (recorte === "hora") return `${Number(valor)}h`;
  if (recorte === "mes") return MESES[Number(valor) - 1];
  if (recorte === "uf") return NOME_UF[valor] ?? valor;
  return valor;
}

export const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
