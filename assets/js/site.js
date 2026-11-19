const root = document.body.dataset.root || "./";
const page = document.body.dataset.page || "home";

const money = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

function pct(value) {
  const digits = value < 0.1 ? 2 : 1;
  return (value * 100).toLocaleString("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }) + "%";
}

function pad(n, loteria) {
  return String(n).padStart(2, "0");
}

function parseSpend(raw) {
  if (!raw) return null;
  const cleaned = raw.replace(/r\$/gi, "").replace(/\s/g, "").replace(/\./g, "").replace(",", ".");
  const value = Number(cleaned);
  return Number.isFinite(value) ? value : null;
}

function gridClass(id) {
  if (id === "lotofacil") return "lf";
  if (id === "diadesorte") return "ds";
  return "lm";
}

function universe(id) {
  if (id === "lotofacil") return [1, 25];
  if (id === "diadesorte") return [1, 31];
  return [0, 99];
}

function monthText(code, versao) {
  if (versao === "mesmo-mes") return "O mês que você escolher";
  if (code === "A") return "Mês A";
  if (code === "B") return "Mês B";
  return code;
}

function copyText(opcao, loteria) {
  return opcao.volantes.map((jogo, i) => {
    const nums = jogo.map((n) => pad(n)).join(" ");
    const mes = opcao.meses ? ` (${monthText(opcao.meses[i], opcao.versao)})` : "";
    return `Jogo ${i + 1}${mes}: ${nums}`;
  }).join("\n");
}

async function copy(text, button) {
  try {
    await navigator.clipboard.writeText(text);
  } catch (err) {
    const area = document.createElement("textarea");
    area.value = text;
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }
  const old = button.textContent;
  button.textContent = "Copiado";
  setTimeout(() => { button.textContent = old; }, 1600);
}

function stat(value, label, main) {
  const el = document.createElement("div");
  el.className = "stat" + (main ? " main" : "");
  el.innerHTML = `<b></b><span></span>`;
  el.querySelector("b").textContent = value;
  el.querySelector("span").textContent = label;
  return el;
}

function renderGame(jogo, index, opcao, loteria) {
  const box = document.createElement("div");
  const head = document.createElement("div");
  head.className = "game-head";
  const title = document.createElement("strong");
  title.textContent = `Jogo ${index + 1}`;
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "Copiar";
  button.addEventListener("click", () => copy(copyText({ ...opcao, volantes: [jogo], meses: opcao.meses ? [opcao.meses[index]] : null }, loteria).replace("Jogo 1", `Jogo ${index + 1}`), button));
  head.append(title, button);
  box.append(head);
  if (opcao.meses) {
    const month = document.createElement("div");
    month.className = "month";
    month.textContent = monthText(opcao.meses[index], opcao.versao);
    box.append(month);
  }
  const [start, end] = universe(loteria.id);
  const selected = new Set(jogo);
  const grid = document.createElement("div");
  grid.className = "grid " + gridClass(loteria.id);
  for (let n = start; n <= end; n += 1) {
    const cell = document.createElement("div");
    cell.className = "cell" + (selected.has(n) ? " on" : "");
    cell.textContent = pad(n);
    grid.append(cell);
  }
  box.append(grid);
  return box;
}

function renderOption(opcao, loteria) {
  const card = document.createElement("article");
  card.className = "option";
  const head = document.createElement("header");
  const title = document.createElement("h2");
  title.textContent = `${money.format(opcao.custo)} · ${opcao.jogos} ${opcao.jogos === 1 ? "jogo" : "jogos"}`;
  const badges = document.createElement("div");
  badges.className = "badges";
  const version = document.createElement("span");
  version.className = "badge quiet";
  version.textContent = opcao.versaoLabel;
  badges.append(version);
  if (opcao.recomendado) {
    const rec = document.createElement("span");
    rec.className = "badge";
    rec.textContent = "Melhor para recuperar metade";
    badges.append(rec);
  }
  if (opcao.versao === "mesmo-mes") {
    const rec = document.createElement("span");
    rec.className = "badge";
    rec.textContent = "Melhor para recuperar tudo";
    badges.append(rec);
  }
  head.append(title, badges);
  card.append(head);

  const desc = document.createElement("p");
  desc.textContent = opcao.descricao;
  card.append(desc);

  const half = document.createElement("p");
  half.className = "meta";
  half.textContent = `Metade de ${money.format(opcao.custo)} é ${money.format(opcao.metaMetade)}. Cada dezena aparece ${opcao.frequenciaMin === opcao.frequenciaMax ? opcao.frequenciaMin + " vez" : "de " + opcao.frequenciaMin + " a " + opcao.frequenciaMax + " vezes"}.`;
  card.append(half);

  const stats = document.createElement("div");
  stats.className = "stats";
  stats.append(
    stat(pct(opcao.recuperarMetade), "de chance de recuperar pelo menos metade", true),
    stat(pct(opcao.qualquerPremio), "de chance de qualquer prêmio"),
    stat(money.format(opcao.retornoEsperado), `de volta, em média (${pct(opcao.retornoEsperado / opcao.custo)} do gasto)`),
    stat(pct(opcao.recuperarTudo), "de chance de recuperar tudo"),
  );
  card.append(stats);

  if (opcao.extra) {
    const note = document.createElement("p");
    note.textContent = `Se 16 acertos pagar ${money.format(opcao.extra.valor)} — o menor valor nos outros concursos da janela — a chance de recuperar metade vai para ${pct(opcao.extra.recuperarMetade)}.`;
    card.append(note);
  }

  const games = document.createElement("div");
  games.className = "games";
  opcao.volantes.forEach((jogo, i) => games.append(renderGame(jogo, i, opcao, loteria)));
  card.append(games);

  const copyAll = document.createElement("button");
  copyAll.type = "button";
  copyAll.className = "primary";
  copyAll.textContent = "Copiar todos os jogos";
  copyAll.addEventListener("click", () => copy(copyText(opcao, loteria), copyAll));
  card.append(copyAll);
  return card;
}

function fillHome(data) {
  const host = document.querySelector("#conteudo");
  const lf = data.loterias.find((l) => l.id === "lotofacil");
  const ds = data.loterias.find((l) => l.id === "diadesorte");
  const lm = data.loterias.find((l) => l.id === "lotomania");
  const best = (lot, pred) => lot.opcoes.filter(pred).sort((a, b) => b.recuperarMetade - a.recuperarMetade)[0];
  const lfBest = best(lf, (o) => o.recomendado);
  const dsBest = best(ds, (o) => o.recomendado);
  const lmBest = best(lm, (o) => o.recomendado);
  const dsTudo = ds.opcoes.find((o) => o.versao === "mesmo-mes" && o.jogos === dsBest.jogos);

  host.innerHTML = "";
  const banner = document.createElement("p");
  banner.className = "banner";
  banner.textContent = data.aviso;
  const h = document.createElement("h1");
  h.textContent = "A chance de receber metade de volta";
  const lead = document.createElement("p");
  lead.className = "lead";
  lead.textContent = `A Lotofácil é, de longe, a melhor para isso. Com ${lfBest.jogos} jogos (${money.format(lfBest.custo)}), a chance de recuperar metade é ${pct(lfBest.recuperarMetade)}. Um prêmio da Lotofácil sai cerca de 1 vez a cada ${data.umJogo.lotofacil.sorteiosPorPremio.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} sorteios. Na Lotomania, cerca de 1 vez a cada ${Math.round(data.umJogo.lotomania.sorteiosPorPremio)}.`;
  const note = document.createElement("p");
  note.className = "muted";
  note.textContent = "O retorno médio é sempre menor que o valor apostado. Estes fechamentos não prometem prêmio: mostram a conta.";
  host.append(banner, h, lead, note);

  const cards = document.createElement("div");
  cards.className = "cards";
  const items = [
    [lf, `${pct(lfBest.recuperarMetade)} de chance de recuperar metade com ${money.format(lfBest.custo)}.`],
    [ds, `${pct(dsBest.recuperarMetade)} de chance de recuperar metade com ${dsBest.jogos} jogos divididos em dois meses. No mesmo mês, a chance de recuperar tudo fica em ${pct(dsTudo.recuperarTudo)}.`],
    [lm, `${pct(lmBest.recuperarMetade)} de chance de recuperar metade com ${money.format(lmBest.custo)}. Um jogo sozinho premia cerca de 1 vez a cada ${Math.round(lm.umJogo.sorteiosPorPremio)} sorteios.`],
  ];
  for (const [lot, line] of items) {
    const card = document.createElement("article");
    card.className = "card";
    const title = document.createElement("h2");
    title.textContent = lot.nome;
    const price = document.createElement("p");
    price.className = "meta";
    price.textContent = `${money.format(lot.preco)} por jogo · concursos ${lot.concursoInicio}–${lot.concursoFim}`;
    const body = document.createElement("p");
    body.textContent = line;
    const link = document.createElement("a");
    link.className = "block";
    link.href = root + lot.href;
    link.textContent = "Ver os fechamentos";
    card.append(title, price, body, link);
    cards.append(card);
  }
  host.append(cards);

  const how = document.createElement("h2");
  how.textContent = "Como ler";
  const list = document.createElement("div");
  list.innerHTML = "<p><strong>Qualquer prêmio</strong> é a chance de pelo menos um jogo ser premiado.</p><p><strong>Recuperar metade</strong> é a chance de o dinheiro dos prêmios somar pelo menos a metade do que você gastou naquele fechamento.</p><p><strong>Média de volta</strong> é o que voltaria, em média, se fosse possível jogar todos os resultados. Não é uma promessa.</p>";
  host.append(how, list);
}

function renderLottery(data) {
  const loteria = data.loterias.find((l) => l.id === page);
  const host = document.querySelector("#conteudo");
  host.innerHTML = "";
  const banner = document.createElement("p");
  banner.className = "banner";
  banner.textContent = data.aviso;
  const h = document.createElement("h1");
  h.textContent = loteria.nome;
  const intro = document.createElement("p");
  intro.className = "lead";
  intro.textContent = `${money.format(loteria.preco)} por jogo. Números atualizados com os concursos ${loteria.concursoInicio} a ${loteria.concursoFim}. Última atualização: ${data.atualizadoEmLabel}.`;
  host.append(banner, h, intro);

  if (page === "diadesorte") {
    const tip = document.createElement("p");
    tip.textContent = "Mês A e mês B são dois meses diferentes, os que você quiser. Metade dos jogos fica em cada um. Na versão de um mês só, escolha qualquer mês e repita em todos os jogos.";
    host.append(tip);
  }
  if (page === "lotomania") {
    const tip = document.createElement("p");
    tip.textContent = "Os prêmios abaixo são os menores de cada faixa nessa janela de concursos. Por isso a chance de recuperar metade é uma conta cautelosa, não a média dos concursos.";
    host.append(tip);
  }

  const prizes = document.createElement("table");
  prizes.className = "table";
  prizes.innerHTML = "<thead><tr><th>Faixa</th><th>Valor usado</th><th>Tipo</th></tr></thead>";
  const body = document.createElement("tbody");
  for (const faixa of loteria.faixas) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td></td><td></td><td></td>`;
    const cells = tr.querySelectorAll("td");
    cells[0].textContent = faixa.nome;
    cells[1].textContent = money.format(faixa.valor);
    cells[2].textContent = faixa.tipo === "fixo" ? "Fixo" : `Menor · ${faixa.concursos}`;
    body.append(tr);
  }
  prizes.append(body);
  host.append(prizes);

  const label = document.createElement("label");
  label.htmlFor = "gasto";
  label.textContent = "Quanto você quer gastar, no máximo?";
  const input = document.createElement("input");
  input.id = "gasto";
  input.type = "text";
  input.inputMode = "decimal";
  input.autocomplete = "off";
  input.placeholder = "Por exemplo, 30";
  const chips = document.createElement("div");
  chips.className = "chips";
  const costs = [...new Set(loteria.opcoes.map((o) => o.custo))].sort((a, b) => a - b);
  for (const cost of costs) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.textContent = money.format(cost);
    chip.addEventListener("click", () => {
      input.value = String(cost).replace(".", ",");
      chips.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", "false"));
      chip.setAttribute("aria-pressed", "true");
      draw();
    });
    chips.append(chip);
  }
  const field = document.createElement("div");
  field.className = "spend";
  field.append(label, input, chips);
  host.append(field);

  const list = document.createElement("div");
  list.className = "cards";
  host.append(list);

  const details = document.createElement("details");
  const summary = document.createElement("summary");
  summary.textContent = "Como esta conta foi feita";
  details.append(summary);
  for (const paragraph of loteria.metodo) {
    const p = document.createElement("p");
    p.textContent = paragraph;
    details.append(p);
  }
  const sim = loteria.opcoes[0].simulacao;
  const check = document.createElement("p");
  check.textContent = `Cada chance foi conferida com ${sim.n.toLocaleString("pt-BR")} sorteios aleatórios.`;
  details.append(check);
  host.append(details);

  function draw() {
    const spend = parseSpend(input.value);
    let options = loteria.opcoes.slice();
    if (spend !== null) {
      options = options.filter((o) => o.custo <= spend + 0.001);
    }
    options.sort((a, b) => a.custo - b.custo || Number(b.recomendado) - Number(a.recomendado));
    list.innerHTML = "";
    if (!options.length) {
      const cheapest = loteria.opcoes.slice().sort((a, b) => a.custo - b.custo)[0];
      const empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent = `Com ${money.format(spend)} não cabe nenhum fechamento pronto. O mais barato é ${money.format(cheapest.custo)} (${cheapest.jogos} jogos).`;
      list.append(empty);
      return;
    }
    if (spend === null) {
      const hint = document.createElement("p");
      hint.className = "muted";
      hint.textContent = "Mostrando todos os fechamentos prontos, do mais barato ao mais caro.";
      list.append(hint);
    }
    for (const opcao of options) list.append(renderOption(opcao, loteria));
  }

  input.addEventListener("input", () => {
    chips.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", "false"));
    draw();
  });
  draw();
}

async function main() {
  const host = document.querySelector("#conteudo");
  host.innerHTML = '<p class="status">Carregando os números…</p>';
  try {
    const response = await fetch(root + "assets/data/fechamentos.json");
    if (!response.ok) throw new Error("sem json");
    const data = await response.json();
    document.querySelectorAll("[data-atualizacao]").forEach((el) => {
      el.textContent = data.atualizadoEmLabel;
    });
    if (page === "home") fillHome(data);
    else renderLottery(data);
  } catch (err) {
    host.innerHTML = '<p class="status">Não consegui carregar os números. Atualize a página. Se você abriu o arquivo direto, use um servidor local, como está no README.</p>';
  }
}

main();
