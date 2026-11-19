"""Busca fechamentos balanceados e grava data/volantes.json.

A busca usa simulação para escolher os volantes. As probabilidades
publicadas são calculadas depois, por enumeração exata, em build_data.py.
"""

from __future__ import annotations

import json
import random
import time
from itertools import combinations
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "volantes.json"


def has_three(nums: list[int]) -> bool:
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


def lotofacil_catalog() -> list[int]:
    out: list[int] = []

    def rec(pos: int, ones: int, run: int, cur: int) -> None:
        if pos == 25:
            if ones == 0:
                out.append(cur)
            return
        rec(pos + 1, ones, 0, cur)
        if ones and run < 2:
            rec(pos + 1, ones - 1, run + 1, cur | (1 << pos))

    rec(0, 15, 0, 0)
    return out


def mask_nums(mask: int, width: int, one_based: bool = True) -> list[int]:
    shift = 1 if one_based else 0
    return [i + shift for i in range(width) if (mask >> i) & 1]


def prepare_draws(universe: int, draw: int):
    combos = np.array(list(combinations(range(universe), draw)), dtype=np.uint8)
    masks = np.zeros(len(combos), dtype=np.uint32)
    for col in range(draw):
        masks |= np.uint32(1) << combos[:, col].astype(np.uint32)
    return masks


def sample_idx(n: int, size: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.choice(n, size=size, replace=False)


POP = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)


def hit_rows(draw_masks: np.ndarray, game_mask: int) -> np.ndarray:
    x = draw_masks & np.uint32(game_mask)
    return (
        POP[x & 255]
        + POP[(x >> 8) & 255]
        + POP[(x >> 16) & 255]
        + POP[(x >> 24) & 255]
    ).astype(np.uint8)


class LotofacilSearch:
    def __init__(self) -> None:
        print("preparando sorteios da Lotofácil...")
        t = time.time()
        self.draws = prepare_draws(25, 15)
        self.catalog = lotofacil_catalog()
        self.cache: dict[int, np.ndarray] = {}
        self._sample_cache: dict[int, np.ndarray] = {}
        self.sample = sample_idx(len(self.draws), 120_000, 11)
        self.sample_draws = self.draws[self.sample]
        print(f"  {len(self.draws)} sorteios, {len(self.catalog)} volantes válidos, {time.time()-t:.1f}s")

    def hits(self, mask: int, sample: bool) -> np.ndarray:
        key = (mask, sample)
        # separate caches
        store = self._sample_cache if sample else self.cache
        if mask not in store:
            base = self.sample_draws if sample else self.draws
            store[mask] = hit_rows(base, mask)
        return store[mask]

    def prize_return(self, games: list[int], sample: bool) -> np.ndarray:
        prizes = np.array(
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 7, 14, 35, 1033.24, 408185.03],
            dtype=np.float64,
        )
        hit = np.stack([self.hits(m, sample) for m in games], axis=1)
        return prizes[hit].sum(axis=1)

    def mc_stats(self, games: list[int], stake: float) -> tuple[float, float]:
        ret = self.prize_return(games, True)
        any_p = float((ret > 0).mean())
        half = float((ret >= stake * 0.5 - 1e-6).mean())
        return any_p, half

    def exact_stats(self, games: list[int], stake: float) -> dict:
        ret = self.prize_return(games, False)
        return {
            "any": float((ret > 0).mean()),
            "half": float((ret >= stake * 0.5 - 1e-6).mean()),
            "full": float((ret >= stake - 1e-6).mean()),
            "ev": float(ret.mean()),
        }


def freq_of(games: list[int], width: int = 25) -> list[int]:
    freq = [0] * width
    for m in games:
        mm = m
        while mm:
            b = (mm & -mm).bit_length() - 1
            freq[b] += 1
            mm &= mm - 1
    return freq


def intersections(games: list[int]) -> list[int]:
    out = []
    for i in range(len(games)):
        for j in range(i + 1, len(games)):
            out.append((games[i] & games[j]).bit_count())
    return out


def balanced(games: list[int], width: int = 25) -> bool:
    freq = freq_of(games, width)
    return max(freq) - min(freq) <= 1 and min(freq) >= 1


def repair(catalog: list[int], k: int, rng: random.Random, steps: int = 20000) -> list[int] | None:
    games = [rng.choice(catalog) for _ in range(k)]
    for _ in range(steps):
        freq = freq_of(games)
        if max(freq) - min(freq) <= 1 and min(freq) >= 1:
            return games
        hi = rng.choice([n for n, f in enumerate(freq) if f == max(freq)])
        lo = rng.choice([n for n, f in enumerate(freq) if f == min(freq)])
        order = list(range(k))
        rng.shuffle(order)
        for i in order:
            if (games[i] >> hi) & 1 and not ((games[i] >> lo) & 1):
                new = games[i] ^ (1 << hi) ^ (1 << lo)
                if new.bit_count() == 15 and not has_three(mask_nums(new, 25, False)):
                    games[i] = new
                    break
    freq = freq_of(games)
    if max(freq) - min(freq) <= 1 and min(freq) >= 1:
        return games
    return None


def polish(games: list[int], rng: random.Random, mode: str, steps: int = 4000) -> list[int]:
    games = games[:]
    k = len(games)

    def score(gs: list[int]) -> tuple:
        inter = intersections(gs)
        freq = freq_of(gs)
        bal = 0 if max(freq) - min(freq) <= 1 else 1
        if mode == "spread":
            return (bal, max(inter) - min(inter), max(inter), -min(inter))
        # concentrated: high overlap spread, still balanced
        var = sum((x - (sum(inter) / len(inter))) ** 2 for x in inter)
        return (bal, -var, -max(inter))

    best = score(games)
    for _ in range(steps):
        freq = freq_of(games)
        i = rng.randrange(k)
        hi = rng.choice([n for n in range(25) if (games[i] >> n) & 1])
        opts = []
        for n in range(25):
            if (games[i] >> n) & 1:
                continue
            freq[hi] -= 1
            freq[n] += 1
            if max(freq) - min(freq) <= 1:
                opts.append(n)
            freq[n] -= 1
            freq[hi] += 1
        if not opts:
            continue
        rng.shuffle(opts)
        improved = False
        for n in opts[:8]:
            new = games[i] ^ (1 << hi) ^ (1 << n)
            if has_three(mask_nums(new, 25, False)):
                continue
            old = games[i]
            games[i] = new
            sc = score(games)
            if sc < best:
                best = sc
                improved = True
                break
            games[i] = old
        if not improved:
            continue
    return games


def search_lotofacil(engine: LotofacilSearch) -> list[dict]:
    specs = [
        (4, 14.0, "espalhada", "spread", 40),
        (8, 28.0, "espalhada", "spread", 30),
        (12, 42.0, "espalhada", "spread", 24),
        (12, 42.0, "concentrada", "concentrated", 24),
        (14, 49.0, "espalhada", "spread", 18),
    ]
    chosen = []
    for k, stake, label, mode, restarts in specs:
        print(f"Lotofácil {k} jogos {label}")
        t = time.time()
        pool = []
        for s in range(restarts):
            rng = random.Random(1000 + k * 50 + s * 17 + (0 if mode == "spread" else 9))
            repaired = repair(engine.catalog, k, rng)
            if not repaired:
                continue
            games = polish(repaired, rng, mode, steps=2500 if k <= 8 else 3500)
            if not balanced(games):
                continue
            any_p, half = engine.mc_stats(games, stake)
            inter = intersections(games)
            # Espalhada: maior chance de algum prêmio. Concentrada: maior chance de recuperar metade.
            key = (any_p, half, -(max(inter) - min(inter))) if mode == "spread" else (half, any_p)
            pool.append((key, games, any_p, half, min(inter), max(inter)))
        assert pool, f"nenhum fechamento balanceado para {k} {label}"
        pool.sort(key=lambda row: row[0], reverse=True)
        best_exact = None
        best_pack = None
        for row in pool[:3]:
            exact = engine.exact_stats(row[1], stake)
            rank = (exact["any"], exact["half"]) if mode == "spread" else (exact["half"], exact["any"])
            if best_exact is None or rank > best_exact:
                best_exact = rank
                best_pack = (row, exact)
        row, exact = best_pack
        games = row[1]
        freq = freq_of(games)
        print(
            f"  MC any {row[2]*100:.2f} half {row[3]*100:.2f} | "
            f"exato any {exact['any']*100:.2f} half {exact['half']*100:.2f} "
            f"inter {row[4]}-{row[5]} freq {min(freq)}-{max(freq)} em {time.time()-t:.0f}s"
        )
        chosen.append(
            {
                "loteria": "lotofacil",
                "versao": label,
                "jogos": [mask_nums(m, 25, True) for m in games],
                "custo": stake,
                "meses": None,
            }
        )
    return chosen


def _freq(games: list[set[int]], universe: int = 31) -> list[int]:
    freq = [0] * universe
    for g in games:
        for n in g:
            freq[n] += 1
    return freq


def _overlap_sum(games: list[set[int]]) -> int:
    total = 0
    for i in range(len(games)):
        for j in range(i + 1, len(games)):
            total += len(games[i] & games[j])
    return total


def dia_repair(k: int, rng: random.Random, mode: str, slack: int = 1) -> list[list[int]]:
    universe = 31
    size = 7

    def rand_ticket() -> set[int]:
        while True:
            nums = sorted(rng.sample(range(universe), size))
            if not has_three(nums):
                return set(nums)

    games = [rand_ticket() for _ in range(k)]
    for _ in range(15000):
        freq = _freq(games)
        if max(freq) - min(freq) <= slack:
            break
        hi = rng.choice([n for n, f in enumerate(freq) if f == max(freq)])
        lo = rng.choice([n for n, f in enumerate(freq) if f == min(freq)])
        order = list(range(k))
        rng.shuffle(order)
        for i in order:
            if hi in games[i] and lo not in games[i]:
                new = set(games[i])
                new.remove(hi)
                new.add(lo)
                if not has_three(new):
                    games[i] = new
                    break
    # Ajusta a sobreposição sem estragar o equilíbrio.
    best_overlap = _overlap_sum(games)
    for _ in range(6000):
        freq = _freq(games)
        i = rng.randrange(k)
        hi = rng.choice(tuple(games[i]))
        opts = [n for n in range(universe) if n not in games[i]]
        rng.shuffle(opts)
        for n in opts[:10]:
            freq[hi] -= 1
            freq[n] += 1
            ok_freq = max(freq) - min(freq) <= slack
            freq[n] -= 1
            freq[hi] += 1
            if not ok_freq:
                continue
            new = set(games[i])
            new.remove(hi)
            new.add(n)
            if has_three(new):
                continue
            old = games[i]
            games[i] = new
            overlap = _overlap_sum(games)
            improved = overlap < best_overlap if mode == "spread" else overlap > best_overlap
            if improved:
                best_overlap = overlap
                break
            games[i] = old
    freq = _freq(games)
    if max(freq) - min(freq) > slack:
        raise RuntimeError(f"Dia de Sorte {k} {mode} não ficou balanceado {min(freq)}-{max(freq)}")
    for g in games:
        if has_three(g) or len(g) != 7:
            raise RuntimeError("volante inválido")
    return [sorted(n + 1 for n in g) for g in games]


def search_dia() -> list[dict]:
    out = []
    # 4 espalhados: progressão disjunta, sem 3 seguidos.
    spread4 = [
        [1, 5, 9, 13, 17, 21, 25],
        [2, 6, 10, 14, 18, 22, 26],
        [3, 7, 11, 15, 19, 23, 27],
        [4, 8, 12, 16, 20, 24, 28],
    ]
    for g in spread4:
        assert not has_three(g)
    plans = {
        "espalhada": ["A", "A", "B", "B"],
        "concentrada": None,  # filled below
        "mesmo-mes": ["M", "M", "M", "M"],
    }
    # Com 4 jogos cabe no máximo uma dezena por número. A versão concentrada
    # abre um pouco essa regra (diferença de até 2) para os jogos se repetirem.
    conc4 = dia_repair(4, random.Random(42), "concentrated", slack=2)
    built = {
        4: {"espalhada": spread4, "concentrada": conc4, "mesmo-mes": spread4},
    }
    for k, seed in ((20, 7), (40, 9)):
        espalhada = dia_repair(k, random.Random(seed), "spread", slack=1)
        built[k] = {
            "espalhada": espalhada,
            "concentrada": dia_repair(k, random.Random(seed + 100), "concentrated", slack=1),
            "mesmo-mes": espalhada,
        }
    price = 2.5
    for k, versions in built.items():
        for versao, jogos in versions.items():
            if versao == "mesmo-mes":
                meses = ["M"] * k
            else:
                meses = ["A"] * (k // 2) + ["B"] * (k - k // 2)
            out.append(
                {
                    "loteria": "diadesorte",
                    "versao": versao,
                    "jogos": jogos,
                    "custo": round(price * k, 2),
                    "meses": meses,
                }
            )
            freq = [0] * 31
            for g in jogos:
                assert not has_three(g)
                for n in g:
                    freq[n - 1] += 1
            print(f"Dia de Sorte {k} {versao}: freq {min(freq)}-{max(freq)}")
    return out


def class_games_from_rows(rows: list[tuple[int, ...]]) -> list[int]:
    masks = []
    for gi, bits in enumerate(rows):
        m = 0
        for b in bits:
            m |= 1 << b
        masks.append(m)
    return masks


def label_classes(game_classes: list[tuple[int, ...]], class_sizes: list[int], seed: int) -> list[int]:
    """Assign each number 0..99 to a class. Returns class id per number."""
    nclass = len(class_sizes)
    cg = [0] * nclass
    for gi, bits in enumerate(game_classes):
        for c in bits:
            cg[c] |= 1 << gi
    rng = random.Random(seed)
    for trial in range(5000):
        quota = class_sizes[:]
        assign = [-1] * 100
        rr = random.Random(seed * 1009 + trial * 17)
        ok = True
        for pos in range(100):
            hot = 0
            if pos >= 2:
                hot = cg[assign[pos - 1]] & cg[assign[pos - 2]]
            # also avoid a triple that wraps? checked later linearly is enough
            cands = [c for c in range(nclass) if quota[c] > 0 and (cg[c] & hot) == 0]
            if not cands:
                ok = False
                break
            w = [quota[c] for c in cands]
            c = rr.choices(cands, weights=w, k=1)[0]
            assign[pos] = c
            quota[c] -= 1
        if ok and all(q == 0 for q in quota):
            return assign
    raise RuntimeError(f"não achei numeração sem 3 seguidos (seed {seed})")


def games_from_assignment(assign: list[int], game_classes: list[tuple[int, ...]]) -> list[list[int]]:
    jogos = []
    for bits in game_classes:
        wanted = set(bits)
        nums = [n for n, c in enumerate(assign) if c in wanted]
        if len(nums) != 50:
            raise RuntimeError(f"jogo com {len(nums)} dezenas")
        if has_three(nums):
            raise RuntimeError("3 consecutivos")
        jogos.append(nums)
    return jogos


def circulant(offs: tuple[int, ...], n: int = 10) -> list[tuple[int, ...]]:
    return [tuple(sorted((o + s) % n for o in offs)) for s in range(n)]


def search_lotomania() -> list[dict]:
    out = []
    # 4 espalhados: 6 classes, tamanhos que fecham 50 por jogo.
    # ordem a,b,c,d,e,f = interseções 01,02,03,12,13,23
    sizes4 = [16, 17, 17, 17, 17, 16]
    classes4 = [(0, 1, 2), (0, 3, 4), (1, 3, 5), (2, 4, 5)]
    assign4 = label_classes(classes4, sizes4, seed=2026)
    jogos4 = games_from_assignment(assign4, classes4)
    out.append({"loteria": "lotomania", "versao": "espalhada", "jogos": jogos4, "custo": 12.0, "meses": None, "classes": classes4, "tamanhos": sizes4})

    # 4 espelho: pares complementares pelo resto módulo 4. 1100 / 0011 e 0110 / 1001.
    classes_m = [(0, 1), (2, 3), (1, 2), (0, 3)]
    sizes_m = [25, 25, 25, 25]
    # Explicit pattern is already valid; build directly so the complement is obvious.
    mirror4 = []
    patterns = [
        {0, 1},
        {2, 3},
        {1, 2},
        {0, 3},
    ]
    for pat in patterns:
        nums = [n for n in range(100) if (n % 4) in pat]
        assert len(nums) == 50 and not has_three(nums)
        mirror4.append(nums)
    out.append({"loteria": "lotomania", "versao": "espelho", "jogos": mirror4, "custo": 12.0, "meses": None, "classes": classes_m, "tamanhos": sizes_m})

    # 10 jogos: circulante que chega perto da referência e tem numeração válida.
    offs10 = (0, 1, 2, 3, 7)
    rows10 = circulant(offs10)
    assign10 = label_classes(rows10, [10] * 10, seed=77)
    jogos10 = games_from_assignment(assign10, rows10)
    out.append({"loteria": "lotomania", "versao": "espalhada", "jogos": jogos10, "custo": 30.0, "meses": None, "classes": rows10, "tamanhos": [10] * 10})

    # 10 espelho: 5 pares complementares de classes.
    primaries = [(0, 1, 2, 4, 7), (0, 1, 3, 5, 8), (0, 1, 3, 6, 8), (0, 1, 4, 5, 8), (0, 2, 3, 5, 8)]
    rows_m10 = []
    for p in primaries:
        comp = tuple(x for x in range(10) if x not in p)
        rows_m10.append(p)
        rows_m10.append(comp)
    assign_m10 = label_classes(rows_m10, [10] * 10, seed=91)
    jogos_m10 = games_from_assignment(assign_m10, rows_m10)
    out.append({"loteria": "lotomania", "versao": "espelho", "jogos": jogos_m10, "custo": 30.0, "meses": None, "classes": rows_m10, "tamanhos": [10] * 10})

    # 20 espalhados: dois circulantes sobre as mesmas classes.
    offs_a = (0, 1, 2, 4, 7)
    offs_b = (0, 1, 3, 6, 8)
    rows20 = circulant(offs_a) + circulant(offs_b)
    # column sum must be 10 and each row weight 5
    col = [0] * 10
    for row in rows20:
        assert len(row) == 5
        for c in row:
            col[c] += 1
    assert col == [10] * 10, col
    assign20 = label_classes(rows20, [10] * 10, seed=1)
    jogos20 = games_from_assignment(assign20, rows20)
    out.append({"loteria": "lotomania", "versao": "espalhada", "jogos": jogos20, "custo": 60.0, "meses": None, "classes": rows20, "tamanhos": [10] * 10})

    # 20 espelho: 10 pares complementares (todos os pares de um conjunto de 10 primários sem colisão).
    # Usa um conjunto fixo de 10 blocos cujo complemento não está na lista, depois acrescenta os complementos.
    prim20 = [
        (0, 1, 3, 6, 7),
        (0, 2, 4, 6, 7),
        (0, 2, 3, 7, 9),
        (0, 1, 2, 6, 8),
        (0, 1, 5, 6, 8),
        (0, 4, 6, 7, 8),
        (0, 2, 4, 6, 9),
        (0, 2, 3, 4, 9),
        (0, 2, 4, 8, 9),
        (0, 2, 4, 5, 9),
    ]
    seen = set()
    rows_m20 = []
    for p in prim20:
        comp = tuple(sorted(x for x in range(10) if x not in set(p)))
        p = tuple(sorted(p))
        if p in seen or comp in seen or p == comp:
            raise RuntimeError(f"par inválido {p}")
        seen.add(p)
        seen.add(comp)
        rows_m20.append(p)
        rows_m20.append(comp)
    col = [0] * 10
    for row in rows_m20:
        for c in row:
            col[c] += 1
    assert col == [10] * 10, col
    assign_m20 = label_classes(rows_m20, [10] * 10, seed=1)
    jogos_m20 = games_from_assignment(assign_m20, rows_m20)
    out.append({"loteria": "lotomania", "versao": "espelho", "jogos": jogos_m20, "custo": 60.0, "meses": None, "classes": rows_m20, "tamanhos": [10] * 10})

    for item in out:
        if item["custo"] == 12.0 and item["versao"] == "espelho":
            continue
        print(f"Lotomania R${item['custo']:.0f} {item['versao']}: {len(item['jogos'])} jogos ok")
    print("Lotomania R$12 espelho: 4 jogos ok")
    return out


def main() -> None:
    engine = LotofacilSearch()
    volantes = []
    volantes.extend(search_lotofacil(engine))
    volantes.extend(search_dia())
    volantes.extend(search_lotomania())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(volantes, ensure_ascii=False, indent=2), encoding="utf-8")
    print("gravei", OUT)


if __name__ == "__main__":
    main()
