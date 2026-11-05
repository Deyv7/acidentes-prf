"""Fase 0: perfil dos arquivos de acidentes da PRF antes de qualquer pipeline.

Lê os ZIPs direto (sem extrair), só com a biblioteca padrão, e grava em
resultados/ tudo o que é citado em docs/validacao-fonte.md.

Uso:
    python -I src/validar_fonte.py --dados C:/caminho/dados-prf/bruto --saida resultados

A pasta de dados deve ter subpastas ocorrencia_<ano>/ocorrencia_<ano>.zip e,
opcionalmente, pessoa_<ano>/pessoa_<ano>.zip.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

# Com -I o Python não põe a pasta do projeto no sys.path; o projeto é confiável,
# os dados não (por isso -I).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.regras import (CONTAGENS, LAT_MAX, LAT_MIN, LON_MAX, LON_MIN,  # noqa: E402
                        NORONHA, dentro_do_brasil)

NULOS = {"", "NA"}

CATEGORICAS = [
    "dia_semana", "uf", "br", "causa_acidente", "tipo_acidente",
    "classificacao_acidente", "fase_dia", "sentido_via",
    "condicao_metereologica", "tipo_pista", "tracado_via", "uso_solo",
    "regional",
]

RE_INT = re.compile(r"^-?\d+$")
RE_DEC = re.compile(r"^-?\d+(,\d+)?$")
RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RE_DATA_BR = re.compile(r"^\d{2}/\d{2}/\d{2,4}$")
RE_HORA = re.compile(r"^\d{2}:\d{2}:\d{2}$")


def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def detectar_codificacao(dados: bytes) -> dict:
    """UTF-8 válido? Se não, há bytes 0x80-0x9F (só existem como texto em cp1252)?"""
    try:
        dados.decode("utf-8")
        utf8 = True
    except UnicodeDecodeError:
        utf8 = False
    faixa_c1 = sum(1 for b in dados if 0x80 <= b <= 0x9F)
    if utf8:
        cod = "utf-8"
    elif faixa_c1 == 0:
        cod = "latin-1"  # equivalente a cp1252 quando não há bytes 0x80-0x9F
    else:
        cod = "cp1252"
    return {"utf8_valido": utf8, "bytes_0x80_0x9f": faixa_c1,
            "bom_utf8": dados.startswith(b"\xef\xbb\xbf"), "codificacao": cod}


def tipo_inferido(valores: list[str]) -> str:
    vs = [v for v in valores if v not in NULOS]
    if not vs:
        return "vazio"
    for nome, rx in [("inteiro", RE_INT), ("decimal_virgula", RE_DEC),
                     ("data_iso", RE_DATA), ("data_br", RE_DATA_BR),
                     ("hora", RE_HORA)]:
        if all(rx.match(v) for v in vs):
            return nome
    return "texto"


def num(v: str) -> float | None:
    if v in NULOS:
        return None
    try:
        return float(v.replace(",", "."))
    except ValueError:
        return None


def ler_csv(zip_path: Path) -> tuple[dict, list[str], list[dict]]:
    with zipfile.ZipFile(zip_path) as z:
        membros = [i for i in z.infolist() if not i.is_dir()]
        assert len(membros) == 1, f"esperava 1 arquivo em {zip_path}"
        info = membros[0]
        dados = z.read(info)
    cod = detectar_codificacao(dados)
    texto = dados.decode(cod["codificacao"])
    primeira = texto.split("\n", 1)[0]
    sep = max([";", ",", "\t", "|"], key=primeira.count)
    fim_linha = "CRLF" if "\r\n" in texto[:10000] else "LF"
    leitor = csv.reader(io.StringIO(texto, newline=""), delimiter=sep, quotechar='"')
    cab = next(leitor)
    linhas, largura_errada = [], 0
    for reg in leitor:
        if not reg:
            continue
        if len(reg) != len(cab):
            largura_errada += 1
            continue
        linhas.append(dict(zip(cab, reg)))
    meta = {
        "arquivo_zip": zip_path.name,
        "sha256_zip": sha256(zip_path),
        "bytes_zip": zip_path.stat().st_size,
        "arquivo_csv": info.filename,
        "bytes_csv": info.file_size,
        "data_no_zip": "%04d-%02d-%02d" % info.date_time[:3],
        **cod,
        "separador": sep,
        "fim_de_linha": fim_linha,
        "n_colunas": len(cab),
        "n_linhas": len(linhas),
        "linhas_com_largura_errada": largura_errada,
    }
    return meta, cab, linhas


def perfil_colunas(cab: list[str], linhas: list[dict]) -> list[dict]:
    saida = []
    for c in cab:
        vals = [r[c] for r in linhas]
        cont = Counter(vals)
        nao_nulos = [v for v in vals if v not in NULOS]
        saida.append({
            "coluna": c,
            "tipo_inferido": tipo_inferido(vals),
            "vazios": cont.get("", 0),
            "na": cont.get("NA", 0),
            "pct_nulo": round(100 * (len(vals) - len(nao_nulos)) / len(vals), 3),
            "distintos": len(set(nao_nulos)),
            "exemplos": " | ".join(v for v, _ in Counter(nao_nulos).most_common(3)),
        })
    return saida


def checar_qualidade(linhas: list[dict], ano: int) -> tuple[list[dict], dict]:
    """Prévia dos testes de qualidade pedidos. Conta linhas reprovadas."""
    n = len(linhas)
    ids = [r["id"] for r in linhas]
    cont_id = Counter(ids)
    id_nulo = sum(1 for i in ids if i in NULOS)
    id_dup_linhas = sum(c for i, c in cont_id.items() if c > 1 and i not in NULOS)
    # Achado na primeira execução da silver: ids redondos em notação científica.
    id_nao_inteiro = [i for i in ids if i not in NULOS and not RE_INT.match(i)]

    lat = [num(r["latitude"]) for r in linhas]
    lon = [num(r["longitude"]) for r in linhas]
    coord_nula = sum(1 for a, o in zip(lat, lon) if a is None or o is None)
    fora_br = [(a, o) for a, o in zip(lat, lon)
               if a is not None and o is not None and not dentro_do_brasil(a, o)]
    zero_zero = sum(1 for a, o in zip(lat, lon) if a == 0 and o == 0)
    trocadas = sum(1 for a, o in fora_br
                   if LAT_MIN <= o <= LAT_MAX and LON_MIN <= a <= LON_MAX)
    magnitude = sum(1 for a, o in fora_br if abs(a) > 90 or abs(o) > 180)

    datas = [r["data_inversa"] for r in linhas]
    data_invalida = sum(1 for d in datas if not RE_DATA.match(d))
    fora_ano = sum(1 for d in datas if RE_DATA.match(d) and int(d[:4]) != ano)
    hora_invalida = sum(1 for r in linhas if not RE_HORA.match(r["horario"]))

    neg = {c: sum(1 for r in linhas if (num(r[c]) or 0) < 0) for c in CONTAGENS}
    cont_nula = {c: sum(1 for r in linhas if r[c] in NULOS) for c in CONTAGENS}

    def i(r, c):
        v = num(r[c])
        return int(v) if v is not None else 0

    cl = lambda r: r["classificacao_acidente"]
    fatal_sem_morto = sum(1 for r in linhas if cl(r) == "Com Vítimas Fatais" and i(r, "mortos") == 0)
    morto_nao_fatal = sum(1 for r in linhas if i(r, "mortos") > 0 and cl(r) != "Com Vítimas Fatais")
    morto_class_nula = sum(1 for r in linhas if i(r, "mortos") > 0 and cl(r) in NULOS)
    morto_class_outra = morto_nao_fatal - morto_class_nula
    feridas_sem_ferido = sum(1 for r in linhas if cl(r) == "Com Vítimas Feridas" and i(r, "feridos") == 0)
    feridas_com_morto = sum(1 for r in linhas if cl(r) == "Com Vítimas Feridas" and i(r, "mortos") > 0)
    sem_vitimas_com_vitima = sum(1 for r in linhas if cl(r) == "Sem Vítimas"
                                 and (i(r, "mortos") > 0 or i(r, "feridos") > 0))
    class_nula = sum(1 for r in linhas if cl(r) in NULOS)
    feridos_soma = sum(1 for r in linhas
                       if i(r, "feridos") != i(r, "feridos_leves") + i(r, "feridos_graves"))
    soma_estado = lambda r: i(r, "mortos") + i(r, "feridos") + i(r, "ilesos") + i(r, "ignorados")
    pessoas_soma = sum(1 for r in linhas if i(r, "pessoas") != soma_estado(r))
    pessoas_menor = sum(1 for r in linhas if i(r, "pessoas") < soma_estado(r))
    pessoas_maior = sum(1 for r in linhas if i(r, "pessoas") > soma_estado(r))

    testes = [
        ("id_nulo", id_nulo),
        ("id_duplicado_linhas", id_dup_linhas),
        ("id_nao_inteiro", len(id_nao_inteiro)),
        ("coordenada_nula_ou_invalida", coord_nula),
        ("coordenada_fora_do_brasil", len(fora_br)),
        ("data_invalida", data_invalida),
        ("data_fora_do_ano_do_arquivo", fora_ano),
        ("horario_invalido", hora_invalida),
        *[(f"{c}_negativo", v) for c, v in neg.items()],
        *[(f"{c}_nulo", v) for c, v in cont_nula.items()],
        ("classif_fatal_com_mortos_0", fatal_sem_morto),
        ("mortos_maior_0_e_classif_nula", morto_class_nula),
        ("mortos_maior_0_e_classif_nao_fatal_preenchida", morto_class_outra),
        ("classif_feridas_com_feridos_0", feridas_sem_ferido),
        ("classif_feridas_com_mortos_maior_0", feridas_com_morto),
        ("classif_sem_vitimas_com_morto_ou_ferido", sem_vitimas_com_vitima),
        ("classificacao_nula", class_nula),
        ("feridos_diferente_de_leves_mais_graves", feridos_soma),
        ("pessoas_diferente_da_soma_por_estado", pessoas_soma),
        ("pessoas_menor_que_soma_por_estado", pessoas_menor),
        ("pessoas_maior_que_soma_por_estado", pessoas_maior),
    ]
    tab = [{"teste": t, "linhas_reprovadas": v,
            "pct_das_linhas": round(100 * v / n, 3)} for t, v in testes]
    extra = {
        "id_nao_inteiro_valores": id_nao_inteiro,
        "coordenada_fora_do_brasil_detalhe": {
            "lat_lon_zero": zero_zero,
            "possivelmente_trocadas": trocadas,
            "magnitude_absurda": magnitude,
            "exemplos": [list(p) for p in fora_br[:10]],
        },
        "data_min": min(d for d in datas if RE_DATA.match(d)),
        "data_max": max(d for d in datas if RE_DATA.match(d)),
    }
    return tab, extra


def coord_por_uf(linhas: list[dict]) -> list[dict]:
    """Percentis 1 e 99 de lat/lon por UF: deixa visível ponto muito longe da UF."""
    por_uf = defaultdict(list)
    for r in linhas:
        a, o = num(r["latitude"]), num(r["longitude"])
        if a is not None and o is not None:
            por_uf[r["uf"]].append((a, o))

    def pct(xs, p):
        xs = sorted(xs)
        return round(xs[min(len(xs) - 1, int(p * len(xs)))], 4)

    saida = []
    for uf in sorted(por_uf):
        pts = por_uf[uf]
        la, lo = [p[0] for p in pts], [p[1] for p in pts]
        saida.append({"uf": uf, "n": len(pts),
                      "lat_min": round(min(la), 4), "lat_p01": pct(la, .01),
                      "lat_p99": pct(la, .99), "lat_max": round(max(la), 4),
                      "lon_min": round(min(lo), 4), "lon_p01": pct(lo, .01),
                      "lon_p99": pct(lo, .99), "lon_max": round(max(lo), 4)})
    return saida


def tabela_grave(linhas: list[dict]) -> list[dict]:
    """Cruza a definição proposta de grave com a classificação da PRF."""
    def i(r, c):
        v = num(r[c])
        return int(v) if v is not None else 0
    cont = Counter()
    for r in linhas:
        cl = r["classificacao_acidente"] if r["classificacao_acidente"] not in NULOS else "(nulo)"
        tem_morto = i(r, "mortos") > 0
        tem_grave = i(r, "feridos_graves") > 0
        cont[(cl, tem_morto, tem_grave, tem_morto or tem_grave)] += 1
    return [{"classificacao_acidente": k[0], "mortos_maior_0": k[1],
             "feridos_graves_maior_0": k[2], "grave_proposto": k[3], "ocorrencias": v}
            for k, v in sorted(cont.items())]


def comparar_pessoa(ocorr: list[dict], pessoas: list[dict]) -> dict:
    """Soma as contagens do arquivo por pessoa e compara com o por ocorrência."""
    def i(r, c):
        v = num(r[c])
        return int(v) if v is not None else 0
    soma = defaultdict(Counter)
    estados = Counter()
    for p in pessoas:
        for c in ["mortos", "feridos_graves", "feridos_leves", "ilesos"]:
            soma[p["id"]][c] += i(p, c)
        soma[p["id"]]["linhas"] += 1
        estados[p["estado_fisico"]] += 1
    ids_o = {r["id"] for r in ocorr}
    ids_p = set(soma)
    diverg = Counter()
    exemplos = defaultdict(list)
    for r in ocorr:
        s = soma.get(r["id"])
        if s is None:
            continue
        for c in ["mortos", "feridos_graves", "feridos_leves", "ilesos"]:
            if s[c] != i(r, c):
                diverg[c] += 1
                if len(exemplos[c]) < 5:
                    exemplos[c].append({"id": r["id"], "ocorrencia": i(r, c), "pessoa": s[c]})
    # Fatais com classificação nula: a classificação também falta no arquivo por pessoa?
    nula_o = {r["id"] for r in ocorr if r["classificacao_acidente"] in NULOS}
    class_p = defaultdict(set)
    for p in pessoas:
        class_p[p["id"]].add(p["classificacao_acidente"])
    nula_preenchida_em_pessoa = sum(1 for x in nula_o if class_p.get(x, {"NA"}) - NULOS)
    # Quantas linhas por pessoa cada ocorrência tem, comparado com as colunas
    # pessoas e mortos + feridos + ilesos + ignorados do arquivo por ocorrência.
    est = defaultdict(Counter)
    for p in pessoas:
        est[p["id"]][p["estado_fisico"]] += 1
    soma_estado = lambda r: i(r, "mortos") + i(r, "feridos") + i(r, "ilesos") + i(r, "ignorados")
    linhas_igual_pessoas = sum(1 for r in ocorr if soma[r["id"]]["linhas"] == i(r, "pessoas"))
    linhas_igual_soma = sum(1 for r in ocorr if soma[r["id"]]["linhas"] == soma_estado(r))
    ign_igual_sem_estado = sum(1 for r in ocorr if i(r, "ignorados")
                               == est[r["id"]]["NA"] + est[r["id"]]["Não Informado"])
    return {
        "ocorrencias_onde_linhas_pessoa_igual_coluna_pessoas": linhas_igual_pessoas,
        "ocorrencias_onde_linhas_pessoa_igual_mortos_feridos_ilesos_ignorados": linhas_igual_soma,
        "ocorrencias_onde_ignorados_igual_estado_NA_ou_nao_informado": ign_igual_sem_estado,
        "ids_ocorrencia": len(ids_o), "ids_pessoa": len(ids_p),
        "ids_so_em_ocorrencia": len(ids_o - ids_p),
        "ids_so_em_pessoa": len(ids_p - ids_o),
        "linhas_pessoa": len(pessoas),
        "estado_fisico": dict(estados.most_common()),
        "ocorrencias_com_contagem_divergente": dict(diverg),
        "exemplos_divergencia": dict(exemplos),
        "classif_nula_na_ocorrencia_mas_preenchida_em_pessoa": nula_preenchida_em_pessoa,
    }


def gravar_csv(caminho: Path, linhas: list[dict]) -> None:
    with caminho.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(linhas)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dados", type=Path, required=True)
    ap.add_argument("--saida", type=Path, default=Path("resultados"))
    args = ap.parse_args()
    args.saida.mkdir(parents=True, exist_ok=True)

    layout, ocorr_por_ano = {}, {}
    for zp in sorted(args.dados.glob("ocorrencia_*/ocorrencia_*.zip")):
        ano = int(zp.stem.split("_")[1])
        meta, cab, linhas = ler_csv(zp)
        ocorr_por_ano[ano] = linhas
        layout[ano] = cab
        qual, extra = checar_qualidade(linhas, ano)
        dominios = {c: dict(Counter(r[c] for r in linhas).most_common())
                    for c in CATEGORICAS if c in cab}
        # tracado_via pode trazer vários valores separados por ';'
        multi = sum(1 for r in linhas if ";" in r.get("tracado_via", ""))
        decimal = {c: sum(1 for r in linhas if "," in r[c]) for c in ["km", "latitude", "longitude"]}
        perfil = {**meta, "colunas": cab, **extra,
                  "linhas_tracado_via_multivalor": multi,
                  "valores_com_virgula_decimal": decimal,
                  "dominios": dominios}
        (args.saida / f"fase0_perfil_{ano}.json").write_text(
            json.dumps(perfil, ensure_ascii=False, indent=2), encoding="utf-8")
        gravar_csv(args.saida / f"fase0_colunas_{ano}.csv", perfil_colunas(cab, linhas))
        gravar_csv(args.saida / f"fase0_qualidade_{ano}.csv", qual)
        gravar_csv(args.saida / f"fase0_coord_por_uf_{ano}.csv", coord_por_uf(linhas))
        gravar_csv(args.saida / f"fase0_grave_x_classificacao_{ano}.csv", tabela_grave(linhas))
        print(f"{ano}: {meta['n_linhas']} linhas, {meta['codificacao']}, sep '{meta['separador']}'")

    resumo = []
    for ano, linhas in sorted(ocorr_por_ano.items()):
        grave = sum(1 for r in linhas if (num(r["mortos"]) or 0) > 0 or (num(r["feridos_graves"]) or 0) > 0)
        com_morto = sum(1 for r in linhas if (num(r["mortos"]) or 0) > 0)
        sem_vit = sum(1 for r in linhas if r["classificacao_acidente"] == "Sem Vítimas")
        resumo.append({"ano": ano, "ocorrencias": len(linhas),
                       "graves": grave, "pct_graves": round(100 * grave / len(linhas), 2),
                       "com_morto": com_morto, "sem_vitimas": sem_vit,
                       "pct_sem_vitimas": round(100 * sem_vit / len(linhas), 2),
                       "data_min": min(r["data_inversa"] for r in linhas),
                       "data_max": max(r["data_inversa"] for r in linhas)})
    gravar_csv(args.saida / "fase0_resumo_por_ano.csv", resumo)

    # Pontos a leste da costa continental (-34,78) e até Noronha, aceitos ou não.
    # Serve para conferir que só os do arquipélago passam no teste.
    leste = []
    for ano, linhas in sorted(ocorr_por_ano.items()):
        for r in linhas:
            a, o = num(r["latitude"]), num(r["longitude"])
            if a is not None and o is not None and LON_MAX < o <= NORONHA[3] and LAT_MIN <= a <= LAT_MAX:
                leste.append({"ano": ano, "id": r["id"], "uf": r["uf"], "br": r["br"], "km": r["km"],
                              "municipio": r["municipio"], "latitude": a, "longitude": o,
                              "aceito": dentro_do_brasil(a, o)})
    gravar_csv(args.saida / "fase0_coord_leste_da_costa.csv", leste or [{"ano": "", "id": ""}])

    # Série mensal da proporção de "Sem Vítimas", para localizar a quebra.
    mensal = []
    for ano, linhas in sorted(ocorr_por_ano.items()):
        por_mes = defaultdict(Counter)
        for r in linhas:
            m = r["data_inversa"][:7]
            por_mes[m]["total"] += 1
            por_mes[m]["sem_vitimas"] += r["classificacao_acidente"] == "Sem Vítimas"
            por_mes[m]["com_morto"] += (num(r["mortos"]) or 0) > 0
        for m in sorted(por_mes):
            c = por_mes[m]
            mensal.append({"mes": m, "ocorrencias": c["total"], "sem_vitimas": c["sem_vitimas"],
                           "pct_sem_vitimas": round(100 * c["sem_vitimas"] / c["total"], 2),
                           "com_morto": c["com_morto"]})
    gravar_csv(args.saida / "fase0_sem_vitimas_por_mes.csv", mensal)

    anos = sorted(layout)
    todas = sorted({c for cab in layout.values() for c in cab}, key=lambda c: (layout[anos[-1]] + [c]).index(c))
    gravar_csv(args.saida / "fase0_layout_por_ano.csv",
               [{"coluna": c, **{str(a): (layout[a].index(c) + 1 if c in layout[a] else "") for a in anos}}
                for c in todas])

    for zp in sorted(args.dados.glob("pessoa_*/pessoa_*.zip")):
        ano = int(zp.stem.split("_")[1])
        meta, cab, linhas = ler_csv(zp)
        comp = comparar_pessoa(ocorr_por_ano.get(ano, []), linhas)
        (args.saida / f"fase0_pessoa_vs_ocorrencia_{ano}.json").write_text(
            json.dumps({**meta, "colunas": cab, **comp}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"pessoa {ano}: {meta['n_linhas']} linhas")


if __name__ == "__main__":
    main()
