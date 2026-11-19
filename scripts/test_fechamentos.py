"""Conferências da conta. Rode depois de scripts/build_data.py."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_data import (  # noqa: E402
    cents,
    faixa_map,
    load_json,
    lotomania_exact,
    segundo_16,
    single_chance_lotofacil,
    single_chance_lotomania,
)

DATA = ROOT / "assets" / "data" / "fechamentos.json"
VOLANTES = ROOT / "data" / "volantes.json"
PREMIOS = ROOT / "data" / "premios.json"


def has_three(nums) -> bool:
    run = 1
    last = None
    for n in sorted(nums):
        if last is not None and n == last + 1:
            run += 1
            if run >= 3:
                return True
        else:
            run = 1
        last = n
    return False


def fail(msg: str) -> None:
    raise SystemExit(msg)


def main() -> None:
    lf = single_chance_lotofacil()
    lm = single_chance_lotomania()
    if abs(lf["sorteiosPorPremio"] - 9.4438) > 0.01:
        fail(f"Lotofácil 1 jogo deveria ser ~9,44 sorteios, veio {lf['sorteiosPorPremio']}")
    if abs(lm["sorteiosPorPremio"] - 87.58) > 0.05:
        fail(f"Lotomania 1 jogo deveria ser ~87,6 sorteios, veio {lm['sorteiosPorPremio']}")
    if math.comb(25, 15) != 3_268_760 or math.comb(31, 7) != 2_629_575:
        fail("totais de sorteios inesperados")

    premios = load_json(PREMIOS)
    table = [0] * 21
    for hits, value in faixa_map(premios["loterias"]["lotomania"]).items():
        table[hits] = value
    # Um jogo qualquer de 50 dezenas tem de devolver cerca de R$ 0,42 com estes mínimos.
    jogo = list(range(50))
    um = lotomania_exact([jogo], table, 300, cents(segundo_16(premios["loterias"]["lotomania"])))
    if abs(um["retornoEsperado"] - 0.4222) > 0.005:
        fail(f"média de um jogo da Lotomania: {um['retornoEsperado']}")
    if abs(um["qualquerPremio"] - lm["chance"]) > 1e-12:
        fail("chance de um jogo não bate com a fórmula")

    if not DATA.exists():
        fail("rode python scripts/build_data.py antes dos testes")
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    volantes = json.loads(VOLANTES.read_text(encoding="utf-8"))

    for item in volantes:
        width = {"lotofacil": 25, "diadesorte": 31, "lotomania": 100}[item["loteria"]]
        freq = [0] * width
        for jogo in item["jogos"]:
            if has_three(jogo):
                fail(f"3 seguidos em {item['loteria']} {item['versao']} {item['custo']}")
            esperado = {"lotofacil": 15, "diadesorte": 7, "lotomania": 50}[item["loteria"]]
            if len(set(jogo)) != esperado:
                fail("volante com tamanho errado")
            for n in jogo:
                freq[n if item["loteria"] == "lotomania" else n - 1] += 1
        slack = 2 if item["loteria"] == "diadesorte" and item["versao"] == "concentrada" and len(item["jogos"]) == 4 else 1
        if max(freq) - min(freq) > slack:
            fail(f"frequência desigual em {item['loteria']} {item['versao']} {item['custo']}: {min(freq)}-{max(freq)}")

    by_id = {}
    for loteria in doc["loterias"]:
        if loteria["preco"] <= 0:
            fail("preço")
        for opcao in loteria["opcoes"]:
            by_id[opcao["id"]] = opcao
            if opcao["retornoEsperado"] >= opcao["custo"] - 1e-9:
                fail(f"média não ficou abaixo do gasto em {opcao['id']}: {opcao['retornoEsperado']}")
            if not opcao["simulacao"]["ok"]:
                fail(f"simulação fora da conta exata em {opcao['id']}")
            if not 0 <= opcao["recuperarMetade"] <= opcao["qualquerPremio"] + 1e-9:
                # Metade pode passar de "qualquer prêmio"? Não: recuperar metade exige prêmio,
                # exceto se um prêmio de mês pequeno não conta como metade mas conta como prêmio.
                # Então metade <= qualquer. Se a simulação passou, a conta exata deve respeitar isso.
                fail(f"metade maior que qualquer prêmio em {opcao['id']}")

    lf4 = by_id["lotofacil-4-espalhada"]
    if abs(lf4["recuperarMetade"] - 0.4045) > 0.004:
        fail(f"Lotofácil 4 jogos: {lf4['recuperarMetade']}")
    if abs(lf4["qualquerPremio"] - lf4["recuperarMetade"]) > 1e-9:
        fail("em 4 jogos da Lotofácil, qualquer prêmio já é metade")

    lf12c = by_id["lotofacil-12-concentrada"]
    if abs(lf12c["recuperarMetade"] - 0.248) > 0.01:
        fail(f"Lotofácil 12 concentrada: {lf12c['recuperarMetade']}")

    ds4 = by_id["diadesorte-4-espalhada"]
    # 2/12 + 10/12 * 4 * P(4 ou mais), com jogos disjuntos.
    p4 = 76805 / 2_629_575
    esperado = 2 / 12 + (10 / 12) * 4 * p4
    if abs(ds4["recuperarMetade"] - esperado) > 1e-6:
        fail(f"Dia de Sorte 4 espalhada {ds4['recuperarMetade']} != {esperado}")
    tudo = by_id["diadesorte-4-mesmo-mes"]["recuperarTudo"]
    if not 0.085 <= tudo <= 0.095:
        fail(f"mesmo mês deveria recuperar tudo perto de 9%, veio {tudo}")
    if tudo <= ds4["recuperarTudo"]:
        fail("o mesmo mês deveria recuperar tudo com mais facilidade do que dois meses")

    lm4 = by_id["lotomania-4-espalhada"]
    lm4m = by_id["lotomania-4-espelho"]
    if abs(lm4["qualquerPremio"] - lm4["recuperarMetade"]) > 1e-12:
        fail("Lotomania R$ 12: qualquer prêmio já cobre a metade")
    if not 0.044 <= lm4["qualquerPremio"] <= 0.047:
        fail(f"Lotomania espalhada R$ 12: {lm4['qualquerPremio']}")
    if not 0.044 <= lm4m["qualquerPremio"] <= 0.047:
        fail(f"Lotomania espelho R$ 12: {lm4m['qualquerPremio']}")
    if abs(lm4["retornoEsperado"] - 1.6889) > 0.01:
        fail(f"média de 4 jogos: {lm4['retornoEsperado']}")

    print("ok")
    for loteria in doc["loterias"]:
        print(loteria["nome"])
        for opcao in loteria["opcoes"]:
            print(
                f"  {opcao['id']}: qualquer {opcao['qualquerPremio']*100:.2f}%  "
                f"metade {opcao['recuperarMetade']*100:.2f}%  "
                f"tudo {opcao['recuperarTudo']*100:.2f}%  "
                f"média {opcao['retornoEsperado']:.2f}"
            )


if __name__ == "__main__":
    main()
