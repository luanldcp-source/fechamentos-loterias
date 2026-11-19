"""Busca os últimos resultados e refaz o JSON do site.

Tenta a API pública da Caixa e, se ela recusar, usa o espelho gratuito
loteriascaixa-api.herokuapp.com. Não precisa de chave.

Uso:
    python scripts/atualizar.py
"""

from __future__ import annotations

import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_data import build  # noqa: E402

PREMIOS = ROOT / "data" / "premios.json"
CAIXA = "https://servicebus2.caixa.gov.br/portaldeloterias/api"
MIRROR = "https://loteriascaixa-api.herokuapp.com/api"
JOGOS = {
    "lotofacil": "lotofacil",
    "diadesorte": "diadesorte",
    "lotomania": "lotomania",
}
HEADERS = {
    "User-Agent": "fechamentos-loterias/1.0 (atualizacao mensal; sem rastreamento)",
    "Accept": "application/json",
    "Referer": "https://loterias.caixa.gov.br/",
}


def get_json(url: str):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_game(game: str) -> tuple[list[dict], str]:
    errors = []
    for base in (CAIXA, MIRROR):
        try:
            latest = get_json(f"{base}/{game}")
            if isinstance(latest, list):
                return [normalize(item) for item in latest], base
            numero = latest.get("numero") or latest.get("concurso")
            rows = [normalize(latest)]
            # A Caixa devolve um concurso por chamada.
            for n in range(numero - 1, numero - 100, -1):
                rows.append(normalize(get_json(f"{base}/{game}/{n}")))
            return rows, base
        except Exception as exc:  # noqa: BLE001 — tenta o espelho
            errors.append(f"{base}: {exc}")
    raise RuntimeError("não consegui baixar os resultados. " + " | ".join(errors))


def normalize(item: dict) -> dict:
    if "premiacoes" in item:
        premios = [
            {
                "descricao": p.get("descricao") or "",
                "ganhadores": p.get("ganhadores") or 0,
                "valor": float(p.get("valorPremio") or 0),
            }
            for p in item["premiacoes"]
        ]
        return {"concurso": int(item["concurso"]), "premios": premios}
    premios = []
    for p in item.get("listaRateioPremio") or []:
        premios.append(
            {
                "descricao": p.get("descricaoFaixa") or "",
                "ganhadores": p.get("numeroDeGanhadores") or 0,
                "valor": float(p.get("valorPremio") or 0),
            }
        )
    return {"concurso": int(item.get("numero") or item.get("concurso")), "premios": premios}


def key_for(descricao: str):
    text = descricao.lower()
    if "mês" in text or "mes" in text:
        return "mes"
    digits = "".join(ch for ch in text if ch.isdigit())
    return int(digits) if digits else descricao


def minimo(rows: list[dict], chave, janela: int):
    ordered = sorted(rows, key=lambda r: r["concurso"], reverse=True)[:janela]
    pagos = []
    for row in ordered:
        for premio in row["premios"]:
            if key_for(premio["descricao"]) == chave and premio["valor"] > 0:
                pagos.append((premio["valor"], row["concurso"]))
    if not pagos:
        return None
    pagos.sort()
    inicio = min(r["concurso"] for r in ordered)
    fim = max(r["concurso"] for r in ordered)
    segundo = pagos[1][0] if len(pagos) > 1 else None
    segundo_concurso = pagos[1][1] if len(pagos) > 1 else None
    return {
        "valor": round(pagos[0][0], 2),
        "concursoDoMinimo": pagos[0][1],
        "pagos": len(pagos),
        "concursos": janela,
        "concursoInicio": inicio,
        "concursoFim": fim,
        "segundoMinimo": round(segundo, 2) if segundo is not None else None,
        "concursoDoSegundo": segundo_concurso,
    }


def atualizar() -> None:
    anterior = json.loads(PREMIOS.read_text(encoding="utf-8"))
    fonte = None
    novo = {
        "atualizadoEm": date.today().isoformat(),
        "fonte": MIRROR,
        "fonteOficial": CAIXA,
        "nota": anterior["nota"],
        "loterias": {},
    }
    for key, slug in JOGOS.items():
        rows, base = fetch_game(slug)
        fonte = base
        print(f"{key}: {len(rows)} concursos via {base}")
        antigo = anterior["loterias"][key]
        faixas = []
        janela_base = antigo["concursoFim"] - antigo["concursoInicio"] + 1
        janela_base = 20
        for faixa in antigo["faixas"]:
            chave = faixa["acertos"]
            janela = 100 if (key == "diadesorte" and chave == 7) else janela_base
            info = minimo(rows, chave, janela)
            if info is None:
                raise RuntimeError(f"sem prêmio pago para {key} {chave}")
            item = {
                "acertos": chave,
                "valor": info["valor"] if not faixa.get("fixo") else faixa["valor"],
                "fixo": faixa.get("fixo", False),
                "concursos": info["concursos"],
                "pagos": info["pagos"],
                "concursoDoMinimo": info["concursoDoMinimo"],
            }
            if chave == "mes":
                item["nome"] = "Mês da Sorte"
                item["valor"] = 2.5
            if info["concursoInicio"] != sorted(rows, key=lambda r: r["concurso"])[-janela:][0]["concurso"]:
                item["concursoInicio"] = info["concursoInicio"]
                item["concursoFim"] = info["concursoFim"]
            if chave == 7:
                item["concursoInicio"] = info["concursoInicio"]
                item["concursoFim"] = info["concursoFim"]
                item["nota"] = (
                    "Nos últimos 20 concursos a faixa de 7 acertos quase não sai. "
                    "Para não exagerar a média, usamos o menor prêmio pago nos últimos 100 concursos."
                )
            if chave == 16 and info["segundoMinimo"] is not None:
                item["segundoMinimo"] = info["segundoMinimo"]
                item["concursoDoSegundo"] = info["concursoDoSegundo"]
            # Faixas fixas continuam com o valor do regulamento, conferido na API.
            if faixa.get("fixo") and abs(info["valor"] - faixa["valor"]) > 0.009:
                print(f"  aviso: {key} {chave} veio {info['valor']} e o regulamento diz {faixa['valor']}")
            faixas.append(item)
        ultimos = sorted(rows, key=lambda r: r["concurso"], reverse=True)[:20]
        novo["loterias"][key] = {
            "concursoInicio": min(r["concurso"] for r in ultimos),
            "concursoFim": max(r["concurso"] for r in ultimos),
            "preco": antigo["preco"],
            "faixas": faixas,
        }
    if fonte:
        novo["fonte"] = fonte
    PREMIOS.write_text(json.dumps(novo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("prêmios atualizados")
    build()


if __name__ == "__main__":
    atualizar()
