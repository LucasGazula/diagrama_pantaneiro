<script lang="ts">
  import { onMount } from "svelte";
  import { getProventos, syncProventos } from "$lib/api/proventos";
  import { listPortfolios } from "$lib/api/portfolios";
  import { portfolioStore } from "$lib/stores/portfolio";
  import { privacyStore } from "$lib/stores/privacy";
  import { formatBrl, formatQty } from "$lib/format";
  import { CLASS_LABELS } from "$lib/classLabels";
  import type { DividendCalendarOut, DividendItemOut, PortfolioOut } from "$lib/types/api";

  const MONTH_NAMES = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
  ];

  const CLASS_ABBR: Record<string, string> = {
    acoes_nacionais: "ACN",
    acoes_internacionais: "ACI",
    fundos_imobiliarios: "FII",
    reits: "REI",
    criptomoedas: "CRY",
    rendafixa: "RF",
    rendafixa_internacional: "RFI",
  };

  const CLASS_COLOR: Record<string, string> = {
    acoes_nacionais: "#e8822c",
    acoes_internacionais: "#b85a1d",
    fundos_imobiliarios: "#d9b86a",
    reits: "#8a6a2e",
    criptomoedas: "#4fa8b8",
    rendafixa: "#7eb360",
    rendafixa_internacional: "#3e6b48",
  };

  const today = new Date();
  let currentYear = $state(today.getFullYear());
  let currentMonth = $state(today.getMonth() + 1);
  let dateMode = $state<"payment" | "ex">("payment");
  let valueMode = $state<"net" | "gross">("net");
  let filterTicker = $state("");
  let filterStatus = $state<"all" | "pago" | "previsto">("all");
  let selectedDay = $state<number | null>(null);

  let portfolios = $state<PortfolioOut[]>([]);
  let showPortfolioMenu = $state(false);
  let activePortfolioId = $derived($portfolioStore.activeId);
  let activePortfolio = $derived(
    portfolios.find((p) => p.id === activePortfolioId) ??
      portfolios.find((p) => p.isDefault) ??
      portfolios[0]
  );

  async function switchPortfolio(id: string) {
    portfolioStore.setActive(id);
    showPortfolioMenu = false;
    selectedDay = null;
    await loadData();
  }

  let calendarData = $state<DividendCalendarOut | null>(null);
  let loading = $state(true);
  let syncing = $state(false);
  let message = $state<string | null>(null);
  let isError = $state(false);

  let masked = $derived($privacyStore);
  let fmtBRL = $derived((v: number) => formatBrl(v, masked));
  let fmtQ = $derived((v: number, digits = 4) => formatQty(v, masked, digits));

  async function loadData() {
    loading = true;
    try {
      calendarData = await getProventos(currentYear, currentMonth, dateMode);
    } catch (e) {
      isError = true;
      message = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }

  async function handleSync() {
    syncing = true;
    message = null;
    isError = false;
    try {
      const res = await syncProventos();
      message = `Sincronizados ${res.syncedTickers} ativos (${res.totalDividendsStored} proventos no histórico).`;
      if (res.failedTickers.length > 0) {
        message += ` Falha em: ${res.failedTickers.join(", ")}`;
      }
      await loadData();
    } catch (e) {
      isError = true;
      message = e instanceof Error ? e.message : "Erro ao sincronizar proventos";
    } finally {
      syncing = false;
    }
  }

  function changeMonth(delta: number) {
    let m = currentMonth + delta;
    let y = currentYear;
    if (m < 1) {
      m = 12;
      y -= 1;
    } else if (m > 12) {
      m = 1;
      y += 1;
    }
    currentMonth = m;
    currentYear = y;
    selectedDay = null;
    loadData();
  }

  function setToday() {
    currentMonth = today.getMonth() + 1;
    currentYear = today.getFullYear();
    selectedDay = today.getDate();
    loadData();
  }

  function toggleDateMode(mode: "payment" | "ex") {
    if (dateMode === mode) return;
    dateMode = mode;
    selectedDay = null;
    loadData();
  }

  onMount(async () => {
    try {
      portfolios = await listPortfolios();
    } catch {
      // non-fatal
    }
    await loadData();
  });

  // Calendar matrix calculation
  let daysInMonth = $derived(new Date(currentYear, currentMonth, 0).getDate());
  let firstDayOfWeek = $derived(new Date(currentYear, currentMonth - 1, 1).getDay()); // 0 = Domingo

  let items = $derived(calendarData?.items ?? []);

  // Items mapped by day of month (1..31)
  let itemsByDay = $derived.by(() => {
    const map: Record<number, DividendItemOut[]> = {};
    for (let d = 1; d <= 31; d++) map[d] = [];
    for (const item of items) {
      const rawDate = dateMode === "ex" ? item.exDate : item.paymentDate;
      if (!rawDate) continue;
      const parts = rawDate.split("-");
      if (parts.length === 3) {
        const itemDay = parseInt(parts[2], 10);
        if (map[itemDay]) {
          map[itemDay].push(item);
        }
      }
    }
    return map;
  });

  // Filtered table items
  let filteredItems = $derived.by(() => {
    return items.filter((item) => {
      if (filterTicker.trim()) {
        if (!item.ticker.toLowerCase().includes(filterTicker.trim().toLowerCase())) {
          return false;
        }
      }
      if (filterStatus !== "all" && item.status !== filterStatus) {
        return false;
      }
      if (selectedDay !== null) {
        const rawDate = dateMode === "ex" ? item.exDate : item.paymentDate;
        if (!rawDate) return false;
        const itemDay = parseInt(rawDate.split("-")[2], 10);
        if (itemDay !== selectedDay) return false;
      }
      return true;
    });
  });

  function formatDatePt(isoDate: string | null): string {
    if (!isoDate) return "—";
    const parts = isoDate.split("-");
    if (parts.length !== 3) return isoDate;
    return `${parts[2]}/${parts[1]}/${parts[0]}`;
  }
</script>

<div class="wrap">
  <!-- TOPBAR -->
  <div class="topbar">
    <div class="brand">
      <span class="prompt">»</span>
      <span class="brand-name">CALENDÁRIO DE PROVENTOS</span>
      {#if activePortfolio}
        <span class="sep">//</span>
        <div class="portfolio-wrap">
          <button
            type="button"
            class="portfolio-btn"
            onclick={() => (showPortfolioMenu = !showPortfolioMenu)}
            aria-haspopup="menu"
            aria-expanded={showPortfolioMenu}
          >
            <span class="portfolio-label">{activePortfolio.name}</span>
            <span class="portfolio-caret">▾</span>
          </button>
          {#if showPortfolioMenu}
            <div class="portfolio-menu" role="menu">
              {#each portfolios as p (p.id)}
                <button
                  type="button"
                  class="portfolio-item"
                  class:active={p.id === activePortfolioId}
                  role="menuitem"
                  onclick={() => switchPortfolio(p.id)}
                >
                  <span class="portfolio-item-mark">
                    {p.id === activePortfolioId ? "›" : " "}
                  </span>
                  <span>{p.name}</span>
                  {#if p.isDefault}<span class="portfolio-item-tag">padrão</span>{/if}
                </button>
              {/each}
              <a
                class="portfolio-item"
                href="/portfolios"
                onclick={() => (showPortfolioMenu = false)}
              >
                <span class="portfolio-item-mark">+</span>
                <span>gerenciar carteiras</span>
              </a>
            </div>
          {/if}
        </div>
      {/if}
      <span class="sep">/</span>
      <span class="ink-dim">{MONTH_NAMES[currentMonth - 1]} {currentYear}</span>
    </div>
    <nav class="nav">
      <button
        type="button"
        onclick={handleSync}
        disabled={syncing}
        class="btn"
        title="Buscar proventos atualizados na API"
      >
        {syncing ? "› sincronizando…" : "› sincronizar proventos"}
      </button>
      <a class="btn" href="/home">› carteira</a>
      <a class="btn" href="/diagram">› diagrama</a>
      <a class="btn" href="/history">› histórico</a>
      <a class="btn btn-accent" href="/aporte">› aporte ▸</a>
    </nav>
  </div>

  {#if message}
    <p class="toast" class:toast-err={isError}>
      <span class="prompt">»</span>
      {message}
    </p>
  {/if}

  <!-- CONTROLS & TOTALS -->
  <section class="panel reveal" style="--delay: 0ms">
    <div class="bracket bracket-tl"></div>
    <div class="bracket bracket-tr"></div>
    <div class="bracket bracket-bl"></div>
    <div class="bracket bracket-br"></div>

    <div class="controls-bar">
      <!-- Month navigation -->
      <div class="month-nav">
        <button class="btn btn-ghost" onclick={() => changeMonth(-1)} title="Mês anterior">‹</button>
        <span class="month-title tab-nums">
          {MONTH_NAMES[currentMonth - 1]} <span class="ink-dim">{currentYear}</span>
        </span>
        <button class="btn btn-ghost" onclick={() => changeMonth(1)} title="Próximo mês">›</button>
        <button class="btn btn-ghost" onclick={setToday}>mês atual</button>
      </div>

      <!-- Date mode toggle -->
      <div class="mode-toggle">
        <span class="mode-label">posicionar por:</span>
        <button
          type="button"
          class="toggle-btn"
          class:active={dateMode === "payment"}
          onclick={() => toggleDateMode("payment")}
        >
          data pagamento
        </button>
        <button
          type="button"
          class="toggle-btn"
          class:active={dateMode === "ex"}
          onclick={() => toggleDateMode("ex")}
        >
          data-com (ex)
        </button>
      </div>

      <!-- Value mode toggle (líquido vs bruto) -->
      <div class="mode-toggle">
        <span class="mode-label">valores:</span>
        <button
          type="button"
          class="toggle-btn"
          class:active={valueMode === "net"}
          onclick={() => (valueMode = "net")}
          title="Valores líquidos após retenção de 15% IRRF no JCP"
        >
          líquido (real)
        </button>
        <button
          type="button"
          class="toggle-btn"
          class:active={valueMode === "gross"}
          onclick={() => (valueMode = "gross")}
          title="Valores brutos declarados sem desconto de imposto"
        >
          bruto
        </button>
      </div>
    </div>

    <!-- Summary cards -->
    <div class="stats-row">
      <div class="stat-card">
        <p class="stat-label">── proventos_recebidos ──</p>
        <p class="stat-value ink-pos tab-nums">
          {fmtBRL(valueMode === "net" ? (calendarData?.totalReceivedNetBrl ?? 0) : (calendarData?.totalReceivedBrl ?? 0))}
        </p>
        <span class="stat-sub ink-dim">
          {#if (calendarData?.totalTaxBrl ?? 0) > 0}
            {valueMode === "net" ? `bruto: ${fmtBRL(calendarData?.totalReceivedBrl ?? 0)}` : `líq: ${fmtBRL(calendarData?.totalReceivedNetBrl ?? 0)}`}
          {:else}
            pagamentos já creditados
          {/if}
        </span>
      </div>

      <div class="stat-card">
        <p class="stat-label">── proventos_previstos ──</p>
        <p class="stat-value ink-dim tab-nums">
          {fmtBRL(valueMode === "net" ? (calendarData?.totalProjectedNetBrl ?? 0) : (calendarData?.totalProjectedBrl ?? 0))}
        </p>
        <span class="stat-sub ink-dim">
          {#if (calendarData?.totalTaxBrl ?? 0) > 0}
            {valueMode === "net" ? `bruto: ${fmtBRL(calendarData?.totalProjectedBrl ?? 0)}` : `líq: ${fmtBRL(calendarData?.totalProjectedNetBrl ?? 0)}`}
          {:else}
            agendados para este mês
          {/if}
        </span>
      </div>

      <div class="stat-card stat-card-highlight">
        <p class="stat-label">── total_do_mês ──</p>
        <p class="stat-value ink tab-nums">
          {fmtBRL(valueMode === "net" ? (calendarData?.totalMonthNetBrl ?? 0) : (calendarData?.totalMonthBrl ?? 0))}
        </p>
        <span class="stat-sub ink-muted">
          {#if (calendarData?.totalTaxBrl ?? 0) > 0}
            {#if valueMode === "net"}
              bruto: {fmtBRL(calendarData?.totalMonthBrl ?? 0)} (-{fmtBRL(calendarData?.totalTaxBrl ?? 0)} IRRF)
            {:else}
              líquido: {fmtBRL(calendarData?.totalMonthNetBrl ?? 0)} (-{fmtBRL(calendarData?.totalTaxBrl ?? 0)} IRRF)
            {/if}
          {:else}
            soma prevista + recebida
          {/if}
        </span>
      </div>

      <div class="stat-card">
        <p class="stat-label">── cotação_usd ──</p>
        <p class="stat-value ink-dim tab-nums">
          R$ {(calendarData?.usdRate ?? 0).toFixed(2)}
        </p>
        <span class="stat-sub ink-dim">câmbio para ativos US</span>
      </div>
    </div>
  </section>

  <!-- CALENDAR GRID -->
  <section class="panel reveal" style="--delay: 120ms">
    <div class="bracket bracket-tl"></div>
    <div class="bracket bracket-tr"></div>
    <div class="bracket bracket-bl"></div>
    <div class="bracket bracket-br"></div>

    <header class="panel-head">
      <h2 class="panel-title">
        ── grade_mensal [{MONTH_NAMES[currentMonth - 1]}/{currentYear}] ──
      </h2>
      {#if selectedDay !== null}
        <span class="panel-sub">
          filtrando dia {selectedDay} ·
          <button class="link-btn" onclick={() => (selectedDay = null)}>limpar filtro dia</button>
        </span>
      {:else}
        <span class="panel-sub ink-dim">clique em um dia para filtrar</span>
      {/if}
    </header>

    <div class="calendar-grid">
      <!-- Weekday headers -->
      {#each ["DOM", "SEG", "TER", "QUA", "QUI", "SEX", "SÁB"] as dayName}
        <div class="cal-weekday">{dayName}</div>
      {/each}

      <!-- Leading empty days -->
      {#each Array(firstDayOfWeek) as _}
        <div class="cal-cell empty"></div>
      {/each}

      <!-- Month days -->
      {#each Array(daysInMonth) as _, idx}
        {@const dayNum = idx + 1}
        {@const dayEvents = itemsByDay[dayNum] ?? []}
        {@const isToday =
          today.getFullYear() === currentYear &&
          today.getMonth() + 1 === currentMonth &&
          today.getDate() === dayNum}
        {@const isSelected = selectedDay === dayNum}

        <div
          class="cal-cell"
          class:is-today={isToday}
          class:is-selected={isSelected}
          class:has-events={dayEvents.length > 0}
          role="button"
          tabindex="0"
          aria-label="{dayNum} de {MONTH_NAMES[currentMonth - 1]}: {dayEvents.length} proventos"
          aria-pressed={isSelected}
          onkeydown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              selectedDay = selectedDay === dayNum ? null : dayNum;
            }
          }}
          onclick={() => (selectedDay = selectedDay === dayNum ? null : dayNum)}
        >
          <div class="cell-head">
            <span class="day-number tab-nums">{dayNum}</span>
            {#if isToday}
              <span class="today-tag">hoje</span>
            {/if}
          </div>

          {#if dayEvents.length > 0}
            <span class="event-count" aria-hidden="true">{dayEvents.length}</span>
            <div class="cell-badges">
              {#each dayEvents as ev (ev.id)}
                {@const evVal = valueMode === "net" ? ev.totalNetBrl : ev.totalBrl}
                <div
                  class="event-badge"
                  class:badge-paid={ev.status === "pago"}
                  class:badge-pending={ev.status === "previsto"}
                  title="{ev.ticker}: {fmtBRL(evVal)} ({ev.dividendType}){ev.isJcp ? ' [-15% IR]' : ''} [{ev.status}]"
                >
                  <span
                    class="badge-dot"
                    style="background: {CLASS_COLOR[ev.assetType] ?? 'var(--accent)'}"
                  ></span>
                  <span class="badge-ticker">{ev.ticker}</span>
                  <span class="badge-amount tab-nums">{fmtBRL(evVal)}</span>
                </div>
              {/each}
            </div>
          {/if}
        </div>
      {/each}
    </div>
  </section>

  <!-- DETAILED TABLE -->
  <section class="panel reveal" style="--delay: 240ms">
    <div class="bracket bracket-tl"></div>
    <div class="bracket bracket-tr"></div>
    <div class="bracket bracket-bl"></div>
    <div class="bracket bracket-br"></div>

    <header class="panel-head flex-between">
      <div>
        <h2 class="panel-title">
          ── detalhamento_proventos [{filteredItems.length}] ──
        </h2>
        {#if selectedDay !== null}
          <span class="panel-sub ink-dim">mostrando eventos do dia {selectedDay}</span>
        {/if}
      </div>

      <!-- Filters -->
      <div class="table-filters">
        <input
          type="text"
          placeholder="filtrar ticker…"
          bind:value={filterTicker}
          class="search-input"
        />

        <div class="status-filters">
          <button
            class="filter-pill"
            class:active={filterStatus === "all"}
            onclick={() => (filterStatus = "all")}
          >
            todos
          </button>
          <button
            class="filter-pill"
            class:active={filterStatus === "pago"}
            onclick={() => (filterStatus = "pago")}
          >
            pagos
          </button>
          <button
            class="filter-pill"
            class:active={filterStatus === "previsto"}
            onclick={() => (filterStatus = "previsto")}
          >
            previstos
          </button>
        </div>
      </div>
    </header>

    {#if loading}
      <p class="loading"><span class="blink">█</span> carregando proventos…</p>
    {:else if filteredItems.length === 0}
      <div class="empty-state">
        <p class="ink-dim">
          nenhum provento encontrado para o período/filtro selecionado.
        </p>
        {#if items.length === 0}
          <p class="ink-muted mt-2">
            dica: clique em <strong>› sincronizar proventos</strong> no topo para buscar dados na API.
          </p>
        {/if}
      </div>
    {:else}
      <!-- svelte-ignore a11y_no_noninteractive_tabindex (Scrollable region needs keyboard focus.) -->
      <div class="table-scroll" role="region" aria-label="Detalhamento de proventos, role para ver todas as colunas" tabindex="0">
      <table class="grid">
        <thead>
          <tr>
            <th class="col-ticker">ativo</th>
            <th class="col-class">classe</th>
            <th class="col-type">tipo</th>
            <th class="col-date">data-com</th>
            <th class="col-date">data pagto</th>
            <th class="col-status">status</th>
            <th class="col-num">cotas</th>
            <th class="col-num">unitário</th>
            <th class="col-num">total {valueMode === "net" ? "líquido" : "bruto"} (r$)</th>
          </tr>
        </thead>
        <tbody>
          {#each filteredItems as item (item.id)}
            <tr>
              <td class="col-ticker">
                <span class="ticker-badge font-bold">{item.ticker}</span>
              </td>
              <td class="col-class">
                <span style="color: {CLASS_COLOR[item.assetType] ?? 'var(--ink-dim)'}">
                  [{CLASS_ABBR[item.assetType] ?? "??"}]
                </span>
                <span class="ink-dim">{CLASS_LABELS[item.assetType] ?? item.assetType}</span>
              </td>
              <td class="col-type ink-muted">
                <span>{item.dividendType}</span>
                {#if item.isJcp}
                  <span class="jcp-tag" title="Retenção de 15% IRRF na fonte">-15% IR</span>
                {/if}
              </td>
              <td class="col-date tab-nums ink-dim">
                {formatDatePt(item.exDate)}
              </td>
              <td class="col-date tab-nums font-semibold">
                {formatDatePt(item.paymentDate)}
              </td>
              <td class="col-status">
                {#if item.status === "pago"}
                  <span class="status-tag status-paid">pago</span>
                {:else}
                  <span class="status-tag status-pending">previsto</span>
                {/if}
              </td>
              <td class="col-num tab-nums">
                {fmtQ(item.amountShares)}
              </td>
              <td class="col-num tab-nums">
                {#if item.currency === "USD"}
                  <span class="ink-dim">US$ {item.rateNative.toFixed(2)}</span>
                  <span class="ink-muted text-xs">({fmtBRL(item.rateBrl)})</span>
                {:else if item.isJcp}
                  <div>{fmtBRL(valueMode === "net" ? item.rateNetBrl : item.rateBrl)}</div>
                  <div class="ink-dim text-xs">
                    {valueMode === "net" ? `bruto: ${fmtBRL(item.rateBrl)}` : `líq: ${fmtBRL(item.rateNetBrl)}`}
                  </div>
                {:else}
                  {fmtBRL(item.rateBrl)}
                {/if}
              </td>
              <td class="col-num tab-nums font-bold" class:ink-pos={item.status === "pago"}>
                <div>{fmtBRL(valueMode === "net" ? item.totalNetBrl : item.totalBrl)}</div>
                {#if item.isJcp}
                  <div class="ink-dim text-xs font-normal">
                    {valueMode === "net" ? `bruto: ${fmtBRL(item.totalBrl)}` : `líq: ${fmtBRL(item.totalNetBrl)}`}
                  </div>
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
      </div>
    {/if}
  </section>
</div>

<style>
  .wrap {
    max-width: 1200px;
    margin: 0 auto;
    padding: 32px 28px 96px;
    color: var(--ink);
  }

  .ink { color: var(--ink); }
  .ink-dim { color: var(--ink-dim); }
  .ink-muted { color: var(--ink-muted); }
  .ink-pos { color: var(--positive); }
  .tab-nums { font-variant-numeric: tabular-nums; }
  .font-bold { font-weight: 700; }
  .font-semibold { font-weight: 600; }
  .text-xs { font-size: 11px; }

  /* ── topbar ── */
  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    row-gap: 10px;
    padding: 10px 14px;
    border: 1px solid var(--hairline);
    background: var(--surface);
    margin-bottom: 20px;
    font-size: 12px;
    letter-spacing: 0.02em;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 10px;
    font-weight: 500;
  }
  .brand-name { color: var(--accent); font-weight: 700; letter-spacing: 0.05em; }
  .prompt { color: var(--accent); font-weight: 700; }
  .sep { color: var(--ink-muted); }

  .portfolio-wrap { position: relative; }
  .portfolio-btn {
    background: transparent;
    border: 1px solid var(--hairline);
    color: var(--accent);
    padding: 3px 8px;
    font: inherit;
    font-size: 12px;
    cursor: pointer;
    letter-spacing: 0.02em;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .portfolio-btn:hover { border-color: var(--accent-dim); background: #14201a; }
  .portfolio-label { font-weight: 700; }
  .portfolio-caret { color: var(--ink-muted); font-size: 10px; }
  .portfolio-menu {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    min-width: 220px;
    background: var(--surface);
    border: 1px solid var(--hairline-strong);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.6);
    z-index: 50;
    display: flex;
    flex-direction: column;
  }
  .portfolio-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: transparent;
    border: none;
    border-bottom: 1px solid var(--hairline);
    color: var(--ink-dim);
    font: inherit;
    font-size: 12px;
    cursor: pointer;
    text-align: left;
    text-decoration: none;
    letter-spacing: 0.02em;
  }
  .portfolio-item:last-child { border-bottom: none; }
  .portfolio-item:hover { color: var(--accent); background: #14201a; }
  .portfolio-item.active { color: var(--accent); }
  .portfolio-item-mark { color: var(--accent); width: 10px; }
  .portfolio-item-tag {
    margin-left: auto;
    padding: 1px 6px;
    font-size: 10px;
    color: var(--bg);
    background: var(--accent-dim);
    letter-spacing: 0.04em;
  }

  .nav { display: flex; gap: 4px; flex-wrap: nowrap; flex-shrink: 0; }

  .btn {
    background: transparent;
    border: 1px solid var(--hairline);
    color: var(--ink-dim);
    padding: 6px 10px;
    font: inherit;
    font-size: 12px;
    cursor: pointer;
    text-decoration: none;
    transition: color 120ms, border-color 120ms, background 120ms;
    letter-spacing: 0.02em;
  }
  .btn:hover:not(:disabled) {
    color: var(--accent);
    border-color: var(--accent-dim);
    background: #14201a;
  }
  .btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .btn-accent {
    color: var(--bg);
    background: var(--accent);
    border-color: var(--accent);
    font-weight: 700;
  }
  .btn-accent:hover { background: #f59640; color: var(--bg); }
  .btn-ghost { border-color: var(--hairline-strong); padding: 4px 8px; }

  .link-btn {
    background: transparent;
    border: none;
    color: var(--accent);
    font: inherit;
    font-size: 12px;
    cursor: pointer;
    text-decoration: underline;
    padding: 0;
  }

  /* ── toast ── */
  .toast {
    margin-bottom: 16px;
    padding: 10px 14px;
    border: 1px solid var(--hairline);
    background: var(--surface);
    color: var(--positive);
    font-size: 12px;
  }
  .toast-err { color: var(--negative); border-color: #3a1a1a; }
  .loading { color: var(--ink-dim); font-size: 13px; padding: 20px 4px; }
  .blink { color: var(--accent); animation: blink 1s steps(1) infinite; }
  @keyframes blink { 50% { opacity: 0; } }

  /* ── brackets & panel ── */
  .panel {
    position: relative;
    background: var(--surface);
    border: 1px solid var(--hairline);
    padding: 24px;
    margin-bottom: 20px;
  }
  .bracket {
    position: absolute;
    width: 14px;
    height: 14px;
    border-color: var(--accent);
    pointer-events: none;
  }
  .bracket-tl { top: -1px; left: -1px; border-top: 2px solid var(--accent); border-left: 2px solid var(--accent); }
  .bracket-tr { top: -1px; right: -1px; border-top: 2px solid var(--accent); border-right: 2px solid var(--accent); }
  .bracket-bl { bottom: -1px; left: -1px; border-bottom: 2px solid var(--accent); border-left: 2px solid var(--accent); }
  .bracket-br { bottom: -1px; right: -1px; border-bottom: 2px solid var(--accent); border-right: 2px solid var(--accent); }

  .panel-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 16px;
    padding-bottom: 10px;
    border-bottom: 1px dashed var(--hairline);
  }
  .panel-title {
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: var(--ink);
  }
  .panel-sub { font-size: 11px; }
  .flex-between { align-items: center; }

  /* ── controls bar ── */
  .controls-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 16px;
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--hairline);
  }
  .month-nav {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .month-title {
    font-size: 16px;
    font-weight: 700;
    min-width: 170px;
    text-align: center;
    letter-spacing: 0.04em;
  }
  .mode-toggle {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .mode-label {
    font-size: 11px;
    color: var(--ink-muted);
    letter-spacing: 0.04em;
    margin-right: 4px;
  }
  .toggle-btn {
    background: transparent;
    border: 1px solid var(--hairline);
    color: var(--ink-dim);
    font: inherit;
    font-size: 11px;
    padding: 4px 8px;
    cursor: pointer;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .toggle-btn.active {
    background: #14201a;
    border-color: var(--accent);
    color: var(--accent);
    font-weight: 700;
  }

  /* ── summary stats ── */
  .stats-row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
  }
  .stat-card {
    padding: 14px 16px;
    background: rgba(0, 0, 0, 0.2);
    border: 1px solid var(--hairline);
  }
  .stat-card-highlight {
    border-color: var(--accent-dim);
    background: #14201a;
  }
  .stat-label {
    font-size: 10px;
    color: var(--ink-muted);
    letter-spacing: 0.1em;
    margin-bottom: 6px;
  }
  .stat-value {
    font-size: 22px;
    font-weight: 700;
    letter-spacing: -0.01em;
    line-height: 1.1;
    margin-bottom: 4px;
  }
  .stat-sub {
    font-size: 11px;
  }

  /* ── calendar grid ── */
  .calendar-grid {
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
    gap: 6px;
  }
  .cal-weekday {
    text-align: center;
    font-size: 11px;
    font-weight: 700;
    color: var(--ink-muted);
    letter-spacing: 0.08em;
    padding: 6px 0;
    border-bottom: 1px solid var(--hairline);
  }
  .cal-cell {
    min-width: 0;
    min-height: 96px;
    padding: 6px 8px;
    background: rgba(0, 0, 0, 0.15);
    border: 1px solid var(--hairline);
    display: flex;
    flex-direction: column;
    cursor: pointer;
    transition: background 120ms, border-color 120ms;
  }
  .cal-cell.empty {
    background: transparent;
    border: none;
    cursor: default;
  }
  .cal-cell:hover:not(.empty) {
    background: rgba(255, 255, 255, 0.03);
    border-color: var(--hairline-strong);
  }
  .cal-cell.is-today {
    border-color: var(--accent);
  }
  .cal-cell.is-selected {
    background: #14201a;
    border-color: var(--accent);
  }
  .cell-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 4px;
  }
  .day-number {
    font-size: 12px;
    font-weight: 600;
    color: var(--ink-dim);
  }
  .cal-cell.is-today .day-number {
    color: var(--accent);
    font-weight: 700;
  }
  .today-tag {
    font-size: 9px;
    padding: 1px 4px;
    background: var(--accent);
    color: var(--bg);
    font-weight: 700;
    letter-spacing: 0.04em;
  }
  .cell-badges {
    display: flex;
    flex-direction: column;
    gap: 3px;
    overflow-y: auto;
    max-height: 80px;
  }
  .event-badge {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 10px;
    padding: 2px 4px;
    background: rgba(0, 0, 0, 0.4);
    border: 1px solid var(--hairline);
  }
  .badge-paid {
    border-left: 2px solid var(--positive);
  }
  .badge-pending {
    border-left: 2px solid var(--accent);
  }
  .badge-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .badge-ticker {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    font-weight: 700;
    color: var(--ink);
  }
  .badge-amount {
    margin-left: auto;
    color: var(--ink-dim);
  }
  .event-count { display: none; }
  .cal-cell:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }

  @media (max-width: 860px) {
    .brand, .nav, .table-filters { flex-wrap: wrap; min-width: 0; }
    .badge-amount { display: none; }
  }
  @media (max-width: 640px) {
    .wrap { padding: 16px 12px 48px; }
    .topbar { align-items: stretch; gap: 16px; padding: 12px; }
    .panel { padding: 20px 12px; }
    .panel-title { overflow-wrap: anywhere; }
    .controls-bar { align-items: stretch; gap: 12px; }
    .month-nav { width: 100%; justify-content: space-between; gap: 4px; }
    .month-title { min-width: 0; font-size: 14px; }
    .month-nav .btn, .toggle-btn, .filter-pill, .link-btn { min-height: 44px; }
    .mode-toggle { flex-wrap: wrap; }
    .stats-row { grid-template-columns: minmax(0, 1fr); gap: 12px; }
    .stat-value, .stat-sub { overflow-wrap: anywhere; }
    .calendar-grid { gap: 3px; }
    .cal-weekday { font-size: 10px; letter-spacing: 0; }
    .cal-cell { min-height: 64px; padding: 6px 2px; align-items: center; }
    .cell-head { justify-content: center; margin-bottom: 6px; }
    .today-tag, .cell-badges { display: none; }
    .event-count {
      display: block;
      color: var(--accent);
      font-size: 10px;
      border-bottom: 2px solid var(--accent);
    }
    .table-filters { width: 100%; gap: 8px; }
    .search-input { width: 100%; min-height: 44px; }
    .status-filters { width: 100%; }
    .filter-pill { flex: 1; }
  }

  /* ── table & filters ── */
  .table-filters {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .search-input {
    background: rgba(0, 0, 0, 0.3);
    border: 1px solid var(--hairline);
    color: var(--ink);
    font: inherit;
    font-size: 11px;
    padding: 4px 8px;
    letter-spacing: 0.02em;
    outline: none;
  }
  .search-input:focus { border-color: var(--accent); }
  .status-filters {
    display: flex;
    gap: 3px;
  }
  .filter-pill {
    background: transparent;
    border: 1px solid var(--hairline);
    color: var(--ink-dim);
    font: inherit;
    font-size: 10px;
    padding: 2px 6px;
    cursor: pointer;
    text-transform: uppercase;
  }
  .filter-pill.active {
    background: #14201a;
    border-color: var(--accent);
    color: var(--accent);
    font-weight: 700;
  }

  .grid {
    display: table;
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }
  .grid th {
    text-align: left;
    padding: 8px 10px;
    border-bottom: 1px solid var(--hairline-strong);
    color: var(--ink-muted);
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .grid td {
    padding: 8px 10px;
    border-bottom: 1px solid var(--hairline);
  }
  .grid tr:hover td {
    background: rgba(255, 255, 255, 0.02);
  }
  .col-ticker { width: 90px; }
  .col-class { width: 150px; }
  .col-type { width: 110px; }
  .col-date { width: 100px; }
  .col-status { width: 80px; }
  .col-num { text-align: right; }
  .grid th.col-num { text-align: right; }

  .ticker-badge {
    color: var(--accent);
    letter-spacing: 0.04em;
  }
  .status-tag {
    display: inline-block;
    font-size: 9px;
    padding: 1px 5px;
    text-transform: uppercase;
    font-weight: 700;
    letter-spacing: 0.04em;
  }
  .status-paid {
    background: rgba(50, 180, 100, 0.15);
    color: var(--positive);
    border: 1px solid var(--positive);
  }
  .status-pending {
    background: rgba(230, 130, 40, 0.15);
    color: var(--accent);
    border: 1px solid var(--accent);
  }
  .jcp-tag {
    display: inline-block;
    margin-left: 6px;
    padding: 1px 5px;
    font-size: 9px;
    font-family: var(--font-mono, monospace);
    font-weight: 700;
    border-radius: 2px;
    background: rgba(232, 130, 44, 0.15);
    color: var(--accent);
    border: 1px solid rgba(232, 130, 44, 0.4);
    letter-spacing: 0.04em;
    vertical-align: middle;
  }
  .empty-state {
    padding: 36px 16px;
    text-align: center;
    font-size: 12px;
  }
  .mt-2 { margin-top: 8px; }
</style>
