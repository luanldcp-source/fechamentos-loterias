# Fechamentos de Loterias

Site estático, em português, para o Luan e os amigos. A meta não é o prêmio máximo. É uma chance honesta de recuperar pelo menos metade do que se gasta na Lotofácil, no Dia de Sorte e na Lotomania.

Nenhum prêmio é garantido. A média do que volta é sempre menor do que o valor apostado.

Não tem anúncio, cadastro, pagamento nem rastreador.

## Ver no computador

É preciso ter Python 3.11 ou mais novo.

```bash
pip install -r requirements.txt
python scripts/build_data.py
python -m http.server 43123
```

Abra `http://127.0.0.1:43123`.

O comando `build_data.py` só refaz as contas com os volantes e os prêmios que já estão no repositório. Para baixar resultados novos, use o comando de atualização abaixo.

## O que cada página faz

A pessoa diz o máximo que quer gastar. A página mostra os fechamentos que cabem: os jogos num quadro, um botão para copiar, a chance de qualquer prêmio, a chance de recuperar metade e a média do que volta.

Os números saem de uma conta exata, feita antes, e conferida com uma simulação de sorteios aleatórios.

- **Lotofácil:** R$ 3,50, 15 dezenas de 25. Opções de R$ 14, R$ 28, R$ 42 e R$ 49 (14 jogos, cabe em R$ 50).
- **Dia de Sorte:** R$ 2,50, 7 dezenas de 31, mais o Mês da Sorte. Três versões: espalhada, concentrada e o mesmo mês em todos os jogos. Dois meses divididos meio a meio são melhores para recuperar metade. O mesmo mês é melhor para tentar recuperar tudo, porque o mês sozinho devolve a aposta, com 1 chance em 12.
- **Lotomania:** R$ 3,00, 50 dezenas de 00 a 99. Versão espalhada e pares espelho. Os prêmios usados são os menores de cada faixa nos últimos 20 concursos.

## Atualizar os prêmios

Uma vez por mês, ou quando quiser:

```bash
python scripts/atualizar.py
```

O script tenta a API pública da Caixa (`https://servicebus2.caixa.gov.br/portaldeloterias/api/<jogo>/<concurso>`). Se a Caixa recusar, usa o espelho gratuito `https://loteriascaixa-api.herokuapp.com/api/<jogo>`. Não precisa de chave.

Ele recalcula o menor prêmio de cada faixa, refaz as chances e grava `data/premios.json` e `assets/data/fechamentos.json`.

Para conferir:

```bash
python scripts/test_fechamentos.py
```

## Publicar de graça

O site é só HTML, CSS e JavaScript. A pasta inteira do projeto pode ir para o ar.

### GitHub Pages

1. Envie este projeto para um repositório seu no GitHub.
2. Em Settings → Pages, escolha a branch `main` e a pasta raiz (`/`).
3. O endereço fica `https://seu-usuario.github.io/nome-do-repositorio/`.

O arquivo `.github/workflows/atualizar.yml` roda no dia 1 de cada mês, baixa os resultados e grava a atualização no repositório. No GitHub, o workflow precisa de permissão para escrever na branch (Settings → Actions → General → Workflow permissions → Read and write).

### Vercel

1. Crie um projeto novo e aponte para o repositório.
2. Não precisa de comando de build. A pasta de saída é a raiz.
3. Cada `git push` publica de novo.

### Netlify

1. New site from Git.
2. Build command: deixe vazio.
3. Publish directory: `.` (a raiz).

Se a hospedagem não tiver agendamento, rode `python scripts/atualizar.py` uma vez por mês no seu computador e envie os arquivos.

## Como a conta é feita

- **Lotofácil:** os 3.268.760 sorteios possíveis são todos examinados.
- **Dia de Sorte:** os 2.629.575 sorteios de números, vezes os 12 meses.
- **Lotomania:** são cerca de 535 sextilhões de sorteios. As dezenas que entram nos mesmos jogos formam grupos, e a conta — com números inteiros — diz quantos sorteios caem em cada grupo. A soma fecha com o total oficial de combinações.

Em todo fechamento, cada dezena aparece quase o mesmo número de vezes, os jogos da versão espalhada se cruzam pouco e nenhum jogo tem três números seguidos.

Os prêmios que mudam de concurso usam o menor valor pago na janela. Concurso sem ganhador não entra, porque zero significa que ninguém levou.
