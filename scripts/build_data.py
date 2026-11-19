"""Calcula as chances exatas dos fechamentos e grava o JSON do site.

As probabilidades da Lotofácil e do Dia de Sorte saem da lista completa de
sorteios. As da Lotomania saem de uma contagem inteira: as dezenas que
entram nos mesmos jogos formam um grupo, e a gente conta de quantas
formas dá para tirar 20 dezenas desses grupos.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import date
from itertools import combinations
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
VOLANTES = ROOT / "data" / "volantes.json"
PREMIOS = ROOT / "data" / "premios.json"
OUT = ROOT / "assets" / "data" / "fechamentos.json"

POP = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)
MC_N = 200_000
MC_SEED = 20261119


def cents(value: float) -> int:
    return int(round(value * 100))


def hit_rows(draw_masks: np.ndarray, game_mask: int) -> np.ndarray:
    x = draw_masks & np.uint32(game_mask)
    return (
        POP[x & 255]
        + POP[(x >> 8) & 255]
        + POP[(x >> 16) & 255]
        + POP[(x >> 24) & 255]
    ).astype(np.uint16)


def draw_masks(universe: int, drawn: int) -> np.ndarray:
    combos = np.array(list(combinations(range(universe), drawn)), dtype=np.uint16)
    masks = np.zeros(len(combos), dtype=np.uint32)
    for col in range(drawn):
        masks |= np.uint32(1) << combos[:, col].astype(np.uint32)
    return masks


def game_mask(nums: list[int], one_based: bool) -> int:
    mask = 0
    for n in nums:
        mask |= 1 << (n - 1 if one_based else n)
    return mask


def summarize(returns: np.ndarray, any_mask: np.ndarray, stake_cents: int) -> dict:
    half = stake_cents / 2
    return {
        "qualquerPremio": float(any_mask.mean()),
        "recuperarMetade": float((returns >= half).mean()),
        "recuperarTudo": float((returns >= stake_cents).mean()),
        "retornoEsperado": float(returns.mean()) / 100.0,
    }


def monte_carlo_mask(universe: int, drawn: int, n: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    scores = rng.random((n, universe))
    pick = np.argpartition(scores, drawn, axis=1)[:, :drawn]
    masks = np.zeros(n, dtype=np.uint32)
    for col in range(drawn):
        masks |= np.uint32(1) << pick[:, col].astype(np.uint32)
    return masks


def within_sampling_error(exact: float, sim: float, n: int, sigmas: float = 4.0) -> bool:
    se = math.sqrt(max(exact, 0.0) * (1.0 - max(exact, 0.0)) / n)
    return abs(exact - sim) <= sigmas * se + 1.0 / n


def lotofacil_stats(jogos: list[list[int]], faixas: dict[int, int], stake_cents: int, draws: np.ndarray) -> dict:
    table = np.zeros(16, dtype=np.float64)
    for hits, value in faixas.items():
        table[hits] = value
    hit = np.stack([hit_rows(draws, game_mask(g, True)) for g in jogos], axis=1)
    returns = table[hit].sum(axis=1)
    any_mask = returns > 0
    return summarize(returns, any_mask, stake_cents)


def lotofacil_mc(jogos: list[list[int]], faixas: dict[int, int], stake_cents: int, n: int, seed: int) -> dict:
    masks = monte_carlo_mask(25, 15, n, seed)
    return lotofacil_stats(jogos, faixas, stake_cents, masks)


def diadesorte_number_returns(jogos: list[list[int]], faixas: dict[int, int], draws: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    table = np.zeros(8, dtype=np.float64)
    for hits, value in faixas.items():
        if isinstance(hits, int):
            table[hits] = value
    hit = np.stack([hit_rows(draws, game_mask(g, True)) for g in jogos], axis=1)
    returns = table[hit].sum(axis=1)
    any_num = (hit >= 4).any(axis=1)
    return returns, any_num


def diadesorte_stats(jogos, meses, faixas, mes_cents: int, stake_cents: int, draws: np.ndarray) -> dict:
    num, any_num = diadesorte_number_returns(jogos, faixas, draws)
    counts = Counter(meses)
    n_labels = len(counts)
    if n_labels > 12:
        raise RuntimeError("mais de 12 meses")
    total_months = 12
    acc = {k: 0.0 for k in ("qualquerPremio", "recuperarMetade", "recuperarTudo", "retornoEsperado")}
    n = len(num)
    half = stake_cents / 2

    def fold(bonus: float, weight: int) -> None:
        total = num + bonus
        any_mask = any_num | (bonus > 0)
        acc["qualquerPremio"] += float(any_mask.sum()) * weight
        acc["recuperarMetade"] += float((total >= half).sum()) * weight
        acc["recuperarTudo"] += float((total >= stake_cents).sum()) * weight
        acc["retornoEsperado"] += float(total.sum()) * weight

    for _label, count in counts.items():
        fold(mes_cents * count, 1)
    fold(0.0, total_months - n_labels)
    denom = n * total_months
    return {
        "qualquerPremio": acc["qualquerPremio"] / denom,
        "recuperarMetade": acc["recuperarMetade"] / denom,
        "recuperarTudo": acc["recuperarTudo"] / denom,
        "retornoEsperado": acc["retornoEsperado"] / denom / 100.0,
    }


def diadesorte_mc(jogos, meses, faixas, mes_cents, stake_cents, n, seed) -> dict:
    rng = np.random.default_rng(seed)
    masks = monte_carlo_mask(31, 7, n, seed)
    num, any_num = diadesorte_number_returns(jogos, faixas, masks)
    labels = list(dict.fromkeys(meses))
    # Um mês sorteado entre 12. Rótulos diferentes são meses diferentes.
    drawn = rng.integers(0, 12, size=n)
    bonus = np.zeros(n, dtype=np.float64)
    for i, label in enumerate(labels):
        bonus[drawn == i] = mes_cents * meses.count(label)
    total = num + bonus
    any_mask = any_num | (bonus > 0)
    return summarize(total, any_mask, stake_cents)


def lotomania_groups(jogos: list[list[int]]) -> tuple[list[int], list[int]]:
    sig = [0] * 100
    for gi, jogo in enumerate(jogos):
        if len(set(jogo)) != 50:
            raise RuntimeError("jogo da Lotomania sem 50 dezenas")
        for n in jogo:
            sig[n] |= 1 << gi
    counts = Counter(sig)
    if sum(counts.values()) != 100:
        raise RuntimeError("assinaturas não cobrem 100 dezenas")
    masks = list(counts.keys())
    sizes = [counts[m] for m in masks]
    return sizes, masks


def lotomania_exact(jogos, prize_table: list[int], stake_cents: int, alt16: int | None) -> dict:
    sizes, masks = lotomania_groups(jogos)
    if len(sizes) > 12:
        raise RuntimeError(f"demasiados grupos ({len(sizes)}) para a contagem exata")
    games = len(jogos)
    cap = 20
    combs = [[math.comb(sz, k) if k <= sz else 0 for k in range(cap + 1)] for sz in sizes]
    hits = [0] * games
    total = 0
    any_c = 0
    half_c = 0
    full_c = 0
    half_alt = 0
    ev = 0
    ev_alt = 0
    half = stake_cents / 2
    alt_table = prize_table[:]
    if alt16 is not None:
        alt_table[16] = alt16

    def add(game_mask: int, k: int, sign: int) -> None:
        if k == 0:
            return
        g = 0
        mm = game_mask
        while mm:
            if mm & 1:
                hits[g] += sign * k
            mm >>= 1
            g += 1

    def walk(idx: int, remaining: int, ways: int) -> None:
        nonlocal total, any_c, half_c, full_c, half_alt, ev, ev_alt
        if idx == len(sizes) - 1:
            k = remaining
            if k > sizes[idx]:
                return
            w = ways * combs[idx][k]
            if w == 0:
                return
            add(masks[idx], k, 1)
            p = 0
            pa = 0
            won = False
            for h in hits:
                value = prize_table[h]
                alt = alt_table[h]
                if value:
                    won = True
                    p += value
                if alt:
                    pa += alt
            add(masks[idx], k, -1)
            total += w
            if won:
                any_c += w
            if p >= half:
                half_c += w
            if p >= stake_cents:
                full_c += w
            if pa >= half:
                half_alt += w
            ev += p * w
            ev_alt += pa * w
            return
        max_k = min(sizes[idx], remaining)
        row = combs[idx]
        gmask = masks[idx]
        for k in range(max_k + 1):
            add(gmask, k, 1)
            walk(idx + 1, remaining - k, ways * row[k])
            add(gmask, k, -1)

    walk(0, 20, 1)
    universe = math.comb(100, 20)
    if total != universe:
        raise RuntimeError(f"contagem {total} != C(100,20) {universe}")
    return {
        "qualquerPremio": any_c / total,
        "recuperarMetade": half_c / total,
        "recuperarTudo": full_c / total,
        "retornoEsperado": (ev / total) / 100.0,
        "recuperarMetadeAlternativa": half_alt / total,
        "retornoAlternativo": (ev_alt / total) / 100.0,
    }


def lotomania_mc(jogos, prize_table: list[int], stake_cents: int, alt16: int, n: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    scores = rng.random((n, 100))
    pick = np.argpartition(scores, 20, axis=1)[:, :20]
    membership = np.zeros((len(jogos), 100), dtype=np.uint8)
    for gi, jogo in enumerate(jogos):
        membership[gi, jogo] = 1
    # hits[trial, game]
    chosen = membership[:, pick]  # (G, n, 20) — big but 6*2e5*20 = 24e6
    hits = chosen.sum(axis=2).T
    table = np.array(prize_table, dtype=np.int64)
    alt = table.copy()
    alt[16] = alt16
    prizes = table[hits].sum(axis=1)
    prizes_alt = alt[hits].sum(axis=1)
    half = stake_cents / 2
    return {
        "qualquerPremio": float((prizes > 0).mean()),
        "recuperarMetade": float((prizes >= half).mean()),
        "recuperarMetadeAlternativa": float((prizes_alt >= half).mean()),
    }


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def faixa_map(premios_lot: dict, skip_mes: bool = False) -> dict:
    out = {}
    for faixa in premios_lot["faixas"]:
        if skip_mes and faixa["acertos"] == "mes":
            continue
        if faixa["acertos"] == "mes":
            continue
        out[faixa["acertos"]] = cents(faixa["valor"])
    return out


def mes_valor(premios_lot: dict) -> int:
    for faixa in premios_lot["faixas"]:
        if faixa["acertos"] == "mes":
            return cents(faixa["valor"])
    raise RuntimeError("sem Mês da Sorte")


def segundo_16(premios_lot: dict) -> float:
    for faixa in premios_lot["faixas"]:
        if faixa["acertos"] == 16:
            return faixa["segundoMinimo"]
    raise RuntimeError("sem faixa 16")


def br_date(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{d}/{m}/{y}"


def money_br(value: float) -> str:
    whole, frac = f"{value:.2f}".split(".")
    groups = []
    while whole:
        groups.append(whole[-3:])
        whole = whole[:-3]
    return "R$ " + ".".join(reversed(groups)) + "," + frac


def option_payload(base: dict, stats: dict, sim: dict, extra: dict | None = None) -> dict:
    ok = within_sampling_error(stats["qualquerPremio"], sim["qualquerPremio"], MC_N) and within_sampling_error(
        stats["recuperarMetade"], sim["recuperarMetade"], MC_N
    )
    if "recuperarMetadeAlternativa" in sim:
        ok = ok and within_sampling_error(
            stats["recuperarMetadeAlternativa"], sim["recuperarMetadeAlternativa"], MC_N
        )
    freq = [0] * (25 if base["loteria"] == "lotofacil" else 31 if base["loteria"] == "diadesorte" else 100)
    for jogo in base["jogos"]:
        for n in jogo:
            freq[n if base["loteria"] == "lotomania" else n - 1] += 1
    payload = {
        "id": f"{base['loteria']}-{len(base['jogos'])}-{base['versao']}",
        "versao": base["versao"],
        "jogos": len(base["jogos"]),
        "custo": base["custo"],
        "volantes": base["jogos"],
        "meses": base.get("meses"),
        "frequenciaMin": min(freq),
        "frequenciaMax": max(freq),
        "qualquerPremio": stats["qualquerPremio"],
        "recuperarMetade": stats["recuperarMetade"],
        "recuperarTudo": stats["recuperarTudo"],
        "retornoEsperado": stats["retornoEsperado"],
        "metaMetade": round(base["custo"] / 2, 2),
        "simulacao": {
            "n": MC_N,
            "qualquerPremio": sim["qualquerPremio"],
            "recuperarMetade": sim["recuperarMetade"],
            "ok": ok,
        },
    }
    if extra:
        payload["extra"] = extra
    if not ok:
        payload["simulacao"]["ok"] = False
    return payload


LABEL = {
    "espalhada": "Espalhada",
    "concentrada": "Concentrada",
    "mesmo-mes": "Mesmo mês",
    "espelho": "Pares espelho",
}

DESCRICAO = {
    ("lotofacil", "espalhada"): "Os jogos se cruzam pouco. Cada dezena aparece quase o mesmo número de vezes, e nenhum jogo tem três números seguidos.",
    ("lotofacil", "concentrada"): "Os jogos se repetem mais. Quando acerta, costuma acertar mais de um — a chance de algum prêmio cai, e a de juntar meia aposta pode subir.",
    ("diadesorte", "espalhada"): "Números espalhados e dois meses, metade dos jogos em cada um. É o melhor jeito de tentar recuperar metade.",
    ("diadesorte", "concentrada"): "Números mais repetidos, ainda com dois meses. Acertar um jogo puxa os outros, mas a chance de acertar algum diminui.",
    ("diadesorte", "mesmo-mes"): "Os mesmos números espalhados, todos no mesmo mês. O mês sozinho devolve a aposta inteira se sair: 1 chance em 12, e um pouco mais por causa dos números.",
    ("lotomania", "espalhada"): "Cada dezena entra em quase a mesma quantidade de jogos, os jogos se cruzam pouco e nenhum tem três números seguidos.",
    ("lotomania", "espelho"): "Cada jogo entra junto com o seu complemento: as 50 dezenas que ficaram de fora. Se um faz 0, o outro faz 20.",
}


def build() -> dict:
    volantes = load_json(VOLANTES)
    premios = load_json(PREMIOS)
    print("sorteios da Lotofácil e do Dia de Sorte...")
    lf_draws = draw_masks(25, 15)
    ds_draws = draw_masks(31, 7)
    lf_preco = premios["loterias"]["lotofacil"]
    ds_preco = premios["loterias"]["diadesorte"]
    lm_preco = premios["loterias"]["lotomania"]
    lf_faixas = faixa_map(lf_preco)
    ds_faixas = faixa_map(ds_preco)
    mes = mes_valor(ds_preco)
    lm_table = [0] * 21
    for hits, value in faixa_map(lm_preco).items():
        lm_table[hits] = value
    alt16 = cents(segundo_16(lm_preco))

    grouped: dict[str, list] = {"lotofacil": [], "diadesorte": [], "lotomania": []}
    for index, item in enumerate(volantes):
        lot = item["loteria"]
        stake_cents = cents(item["custo"])
        print(f"  {lot} {item['versao']} R$ {item['custo']:.2f}")
        if lot == "lotofacil":
            stats = lotofacil_stats(item["jogos"], lf_faixas, stake_cents, lf_draws)
            sim = lotofacil_mc(item["jogos"], lf_faixas, stake_cents, MC_N, MC_SEED + index)
            extra = None
        elif lot == "diadesorte":
            stats = diadesorte_stats(item["jogos"], item["meses"], ds_faixas, mes, stake_cents, ds_draws)
            sim = diadesorte_mc(item["jogos"], item["meses"], ds_faixas, mes, stake_cents, MC_N, MC_SEED + index)
            extra = None
        else:
            stats = lotomania_exact(item["jogos"], lm_table, stake_cents, alt16)
            sim = lotomania_mc(item["jogos"], lm_table, stake_cents, alt16, MC_N, MC_SEED + index)
            extra = {
                "acertos": 16,
                "valor": segundo_16(lm_preco),
                "recuperarMetade": stats["recuperarMetadeAlternativa"],
                "simulacao": sim["recuperarMetadeAlternativa"],
            }
        payload = option_payload(item, stats, sim, extra)
        payload["descricao"] = DESCRICAO[(lot, item["versao"])]
        payload["versaoLabel"] = LABEL[item["versao"]]
        grouped[lot].append(payload)
        print(
            f"    qualquer {payload['qualquerPremio']*100:.2f}%  "
            f"metade {payload['recuperarMetade']*100:.2f}%  "
            f"média R$ {payload['retornoEsperado']:.2f}  "
            f"simulação {'ok' if payload['simulacao']['ok'] else 'FORA'}"
        )

    def best_half(options: list[dict]) -> dict:
        return max(options, key=lambda o: (o["recuperarMetade"], -o["custo"]))

    lf_best = best_half(grouped["lotofacil"])
    ds_best = best_half([o for o in grouped["diadesorte"] if o["versao"] != "mesmo-mes"])
    lm_best = best_half(grouped["lotomania"])
    for opt in grouped["lotofacil"]:
        opt["recomendado"] = opt["id"] == lf_best["id"]
    for opt in grouped["diadesorte"]:
        opt["recomendado"] = opt["id"] == ds_best["id"]
        opt["destaqueTudo"] = opt["versao"] == "mesmo-mes" and opt["jogos"] == ds_best["jogos"]
    for opt in grouped["lotomania"]:
        opt["recomendado"] = opt["id"] == lm_best["id"]

    single_lf = single_chance_lotofacil()
    single_lm = single_chance_lotomania()
    doc = {
        "atualizadoEm": premios["atualizadoEm"],
        "atualizadoEmLabel": br_date(premios["atualizadoEm"]),
        "aviso": "Nenhum prêmio é garantido. A média do que volta é sempre menor do que o valor gasto.",
        "objetivo": "Recuperar pelo menos metade do que foi apostado. O prêmio máximo não é a meta.",
        "umJogo": {
            "lotofacil": single_lf,
            "lotomania": single_lm,
        },
        "loterias": [
            lottery_block("lotofacil", "Lotofácil", "lotofacil/", lf_preco, grouped["lotofacil"], single_lf),
            lottery_block("diadesorte", "Dia de Sorte", "dia-de-sorte/", ds_preco, grouped["diadesorte"], None),
            lottery_block("lotomania", "Lotomania", "lotomania/", lm_preco, grouped["lotomania"], single_lm),
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print("gravei", OUT)
    return doc


def single_chance_lotofacil() -> dict:
    total = math.comb(25, 15)
    wins = sum(math.comb(15, k) * math.comb(10, 15 - k) for k in range(11, 16))
    return {"chance": wins / total, "sorteiosPorPremio": total / wins, "total": total}


def single_chance_lotomania() -> dict:
    total = math.comb(100, 20)
    wins = sum(math.comb(50, k) * math.comb(50, 20 - k) for k in (0, 15, 16, 17, 18, 19, 20))
    return {"chance": wins / total, "sorteiosPorPremio": total / wins, "total": total}


def lottery_block(key, nome, href, prem, options, single) -> dict:
    method = {
        "lotofacil": [
            "A Lotofácil sorteia 15 números de 1 a 25. Existem 3.268.760 resultados possíveis, e a conta olha todos.",
            "Para cada resultado, somamos o prêmio dos jogos do fechamento. Daí sai a chance de ganhar qualquer coisa, a chance de receber de volta pelo menos metade do gasto, e a média do dinheiro que volta.",
            "11, 12 e 13 acertos têm prêmio fixo. 14 e 15 mudam de concurso para concurso. Usamos o menor valor pago na faixa, para não prometer um cenário bonito.",
            "Pelo regulamento, cerca de 43,79% do dinheiro apostado vai para os prêmios. O resto não volta. A média calculada aqui fica ainda mais baixa, porque usa os menores prêmios recentes.",
            "Uma simulação de sorteios aleatórios confere se a conta exata está no lugar. Os dois números precisam ficar perto.",
        ],
        "diadesorte": [
            "O Dia de Sorte tira 7 números de 1 a 31 e um mês. São 2.629.575 sorteios de números, vezes 12 meses. A conta percorre todos.",
            "4 acertos pagam R$ 5, 5 acertos pagam R$ 25 e o Mês da Sorte paga R$ 2,50 em cada jogo que marcou o mês certo. Esse valor se soma ao prêmio dos números. 6 e 7 acertos mudam: usamos o menor valor recente.",
            "Se todos os jogos usam o mesmo mês, o mês sozinho devolve a aposta inteira — e ele sai 1 vez em 12. Os números empurram essa chance um pouco para cima.",
            "Se os jogos se dividem em dois meses, metade em cada, um desses meses devolve exatamente metade da aposta. A chance disso é 2 em 12, fora o que os números acrescentam. Por isso dois meses são melhores para recuperar metade, e um mês só é melhor para tentar recuperar tudo.",
            "Nenhum fechamento garante prêmio. A média continua abaixo do que se gasta.",
        ],
        "lotomania": [
            "A Lotomania sorteia 20 números de 00 a 99. São cerca de 535 sextilhões de resultados. Não dá para listar um por um.",
            "Dá para agrupar as dezenas que entram nos mesmos jogos. A conta, feita com números inteiros, diz de quantas formas a sorte pode cair em cada grupo. A soma tem de bater com o total oficial de combinações — e bate.",
            "Não há prêmio fixo. Usamos o menor valor de cada faixa nos concursos indicados. Concurso sem ganhador não entra, porque zero quer dizer que ninguém levou.",
            "Com 4 jogos (R$ 12), qualquer prêmio já devolve pelo menos metade: o menor prêmio considerado passa de R$ 6. Com R$ 30 ou R$ 60, um prêmio de 15 ou de 16 acertos no valor mais baixo não cobre a metade.",
            "Em um concurso, 16 acertos pagou bem menos que nos outros. Mostramos também a chance de recuperar metade se 16 acertos pagar o menor valor dos outros 19 concursos.",
            "Na média destes prêmios baixos, um jogo de R$ 3,00 devolve cerca de R$ 0,42. A simulação aleatória confere a conta.",
        ],
    }[key]
    faixa_txt = []
    for faixa in prem["faixas"]:
        nome_faixa = "Mês da Sorte" if faixa["acertos"] == "mes" else f"{faixa['acertos']} acertos"
        fixo = "fixo" if faixa.get("fixo") else "menor recente"
        extra = ""
        if faixa.get("nota"):
            extra = " " + faixa["nota"]
        if faixa["acertos"] == 16 and faixa.get("segundoMinimo"):
            extra += (
                " Nos outros concursos da janela, o menor foi "
                f"{money_br(faixa['segundoMinimo'])}."
            )
        inicio = faixa.get("concursoInicio", prem["concursoInicio"])
        fim = faixa.get("concursoFim", prem["concursoFim"])
        faixa_txt.append(
            {
                "nome": nome_faixa,
                "valor": faixa["valor"],
                "tipo": fixo,
                "concursos": f"{inicio}–{fim}",
                "nota": extra.strip(),
            }
        )
    return {
        "id": key,
        "nome": nome,
        "href": href,
        "preco": prem["preco"],
        "concursoInicio": prem["concursoInicio"],
        "concursoFim": prem["concursoFim"],
        "faixas": faixa_txt,
        "metodo": method,
        "umJogo": single,
        "opcoes": options,
    }


if __name__ == "__main__":
    build()
