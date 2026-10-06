<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";

  import { listPositions } from "$lib/api/positions";
  import { listTargets } from "$lib/api/targets";
  import { logout as apiLogout } from "$lib/api/auth";
  import { refreshPrices } from "$lib/api/prices";
  import { authStore } from "$lib/stores/auth";
  import { portfolioStore } from "$lib/stores/portfolio";
  import { privacyStore } from "$lib/stores/privacy";
  import { formatBrl, formatBrlCompact, formatQty, formatLastUpdated } from "$lib/format";
  import { CLASS_LABELS } from "$lib/classLabels";
  import EditTargetsModal from "$lib/components/EditTargetsModal.svelte";
  import type { PositionOut, TargetOut } from "$lib/types/api";

  const CLASS_ABBR: Record<string, string> = {
    acoes_nacionais: "ACN",
    acoes_internacionais: "ACI",
    fundos_imobiliarios: "FII",
    reits: "REI",
    criptomoedas: "CRY",
    rendafixa: "RF",
    rendafixa_internacional: "RFI",
  };

  // Paleta pantaneira — do pôr-do-sol ao corixo, passando pelo cerradão
  const CLASS_COLOR: Record<string, string> = {
    acoes_nacionais: "#e8822c",           // pôr-do-sol / bico de tuiuiú
    acoes_internacionais: "#b85a1d",      // argila do barranco
    fundos_imobiliarios: "#d9b86a",       // areia de baía seca
    reits: "#8a6a2e",                     // madeira de aroeira
    criptomoedas: "#4fa8b8",              // água do corixo ao sol
    rendafixa: "#7eb360",                 // pastagem de cerradão
    rendafixa_internacional: "#3e6b48",   // mata ripária densa
  };

  let user = $derived($authStore.user);

  function getCachedPositions(portfolioId: string | null): PositionOut[] {
    if (typeof localStorage === "undefined") return [];
    try {
      const raw = localStorage.getItem(`cached_positions_${portfolioId ?? "default"}`);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  }

  function getCachedTargets(portfolioId: string | null): TargetOut[] {
    if (typeof localStorage === "undefined") return [];
    try {
      const raw = localStorage.getItem(`cached_targets_${portfolioId ?? "default"}`);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  }

  function saveCache(portfolioId: string | null, pos: PositionOut[], tgt: TargetOut[]) {
    if (typeof localStorage === "undefined") return;
    try {
      localStorage.setItem(`cached_positions_${portfolioId ?? "default"}`, JSON.stringify(pos));
      localStorage.setItem(`cached_targets_${portfolioId ?? "default"}`, JSON.stringify(tgt));
    } catch {}
  }

  let showPortfolioMenu = $state(false);
  let portfolios = $state($portfolioStore.all);
  let activePortfolioId = $state($portfolioStore.activeId);
  portfolioStore.subscribe((s) => {
    portfolios = s.all;
    activePortfolioId = s.activeId;
  });
  let activePortfolio = $derived(
    portfolios.find((p) => p.id === activePortfolioId) ?? null,
  );

  let initialPos = getCachedPositions(activePortfolioId);
  let initialTgt = getCachedTargets(activePortfolioId);

  let positions = $state<PositionOut[]>(initialPos);
  let targets = $state<TargetOut[]>(initialTgt);
  let loading = $state(initialPos.length === 0);
  let error = $state<string | null>(null);

  let lastUpdatedAt = $derived.by<string | null>(() => {
    if (!positions || positions.length === 0) return null;
    let latest: number | null = null;
    for (const p of positions) {
      if (p.updatedAt) {
        const t = new Date(p.updatedAt).getTime();
        if (!isNaN(t) && (latest === null || t > latest)) {
          latest = t;
        }
      }
    }
    return latest ? new Date(latest).toISOString() : null;
  });

  let refreshing = $state(false);
  let backgroundSyncing = $state(false);
  let refreshMessage = $state<string | null>(null);
  let refreshFailed = $state(false);

  let showTargetsModal = $state(false);
  let hoveredClass = $state<string | null>(null);

  // ── ordenação clicável da tabela de posições ──
  type SortKey = "nome" | "classe" | "quantidade" | "preco" | "valor" | "participacao" | "forca";
  let sortKey = $state<SortKey>("valor");
  let sortDesc = $state(true);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      sortDesc = !sortDesc;
    } else {
      sortKey = key;
      // padrão: numéricos começam desc, texto começa asc
      sortDesc = key !== "nome" && key !== "classe";
    }
  }

  function sortIndicator(key: SortKey): string {
    if (sortKey !== key) return "·";
    return sortDesc ? "▼" : "▲";
  }

  async function switchPortfolio(id: string) {
    if (id === activePortfolioId) {
      showPortfolioMenu = false;
      return;
    }
    portfolioStore.setActive(id);
    showPortfolioMenu = false;
    const cachedP = getCachedPositions(id);
    const cachedT = getCachedTargets(id);
    if (cachedP.length > 0) {
      positions = cachedP;
      targets = cachedT;
      loading = false;
    } else {
      loading = true;
    }
    error = null;
    try {
      const [freshPos, freshTgt] = await Promise.all([listPositions(), listTargets()]);
      positions = freshPos;
      targets = freshTgt;
      saveCache(id, freshPos, freshTgt);
    } catch (e) {
      if (positions.length === 0) {
        error = e instanceof Error ? e.message : String(e);
      }
    } finally {
      loading = false;
    }
  }

  async function handleRefresh() {
    refreshing = true;
    refreshMessage = null;
    refreshFailed = false;
    try {
      const result = await refreshPrices("all");
      const parts: string[] = [];
      parts.push(`${result.refreshed} posição(ões) atualizada(s)`);
      if (result.skippedManual > 0) parts.push(`${result.skippedManual} manual (RF) ignorada(s)`);
      if (result.stale?.length) {
        parts.push(`${result.stale.length} cotação(ões) antiga(s); confira data antes de aportar`);
      }
      if (result.failed.length > 0) {
        parts.push(`${result.failed.length} falharam: ${result.failed.map((f) => f.name).join(", ")}`);
        refreshFailed = true;
      }
      refreshMessage = parts.join(" · ");
      [positions, targets] = await Promise.all([listPositions(), listTargets()]);
      saveCache(activePortfolioId, positions, targets);
    } catch (e) {
      refreshMessage = `Erro: ${e instanceof Error ? e.message : String(e)}`;
      refreshFailed = true;
    } finally {
      refreshing = false;
    }
  }

  onMount(async () => {
    // 1. Initial quick load from API
    try {
      const [freshPos, freshTgt] = await Promise.all([listPositions(), listTargets()]);
      positions = freshPos;
      targets = freshTgt;
      saveCache(activePortfolioId, freshPos, freshTgt);
    } catch (e) {
      if (positions.length === 0) {
        error = e instanceof Error ? e.message : String(e);
      }
    } finally {
      loading = false;
    }

    // 2. Background price refresh
    try {
      backgroundSyncing = true;
      await refreshPrices("all", false);
      const updated = await listPositions();
      positions = updated;
      saveCache(activePortfolioId, updated, targets);
    } catch {
      // Non-fatal: background auto-refresh does not disrupt view
    } finally {
      backgroundSyncing = false;
    }
  });

  let totalValue = $derived(positions.reduce((s, p) => s + p.currentValueBrl, 0));

  let classCurrentPct = $derived.by(() => {
    const byType: Record<string, number> = {};
    for (const p of positions) byType[p.assetType] = (byType[p.assetType] ?? 0) + p.currentValueBrl;
    const out: Record<string, number> = {};
    for (const [t, v] of Object.entries(byType)) out[t] = totalValue > 0 ? (v / totalValue) * 100 : 0;
    return out;
  });

  // Donut segment builder — SVG arcs drawn on a 100×100 viewBox, stroke-based
  type Segment = { assetType: string; label: string; pct: number; value: number; color: string; offset: number };

  let donutSegments = $derived.by<Segment[]>(() => {
    const entries = Object.entries(classCurrentPct)
      .filter(([, pct]) => pct > 0.01)
      .sort((a, b) => b[1] - a[1]);
    const segs: Segment[] = [];
    let cursor = 0;
    for (const [assetType, pct] of entries) {
      const value = positions
        .filter((p) => p.assetType === assetType)
        .reduce((s, p) => s + p.currentValueBrl, 0);
      segs.push({
        assetType,
        label: CLASS_ABBR[assetType] ?? assetType.slice(0, 3).toUpperCase(),
        pct,
        value,
        color: CLASS_COLOR[assetType] ?? "#6b7480",
        offset: cursor,
      });
      cursor += pct;
    }
    return segs;
  });

  // Strength heat-strip: strength can be negative — map to 10 cells via sign-symmetric scheme
  function strengthCells(s: number): { filled: boolean; tone: "pos" | "neg" | "zero" }[] {
    const cells = Array.from({ length: 10 }, () => ({ filled: false, tone: "zero" as const }));
    if (s === 0) return cells;
    const magnitude = Math.min(Math.abs(s), 10);
    const tone = s > 0 ? "pos" : "neg";
    for (let i = 0; i < magnitude; i++) cells[i] = { filled: true, tone } as any;
    return cells;
  }

  let masked = $derived($privacyStore);
  let fmtBRL = $derived((v: number) => formatBrl(v, masked));
  let fmtBRLCompact = $derived((v: number) => formatBrlCompact(v, masked));
  let fmtQty = $derived((v: number, digits = 6) => formatQty(v, masked, digits));

  async function handleLogout() {
    try {
      await apiLogout();
    } catch {
      // ignore
    }
    authStore.logout();
    portfolioStore.reset();
    await goto("/login");
  }

  // Donut geometry constants
  const RADIUS = 38;
  const CIRCUMFERENCE = 2 * Math.PI * RADIUS;
</script>

<section class="wrap">
  <!-- Top bar -->
  <div class="topbar">
    <div class="brand">
      <img src="/logo.png" alt="diagrama_pantaneiro" class="brand-logo" />
      <span class="prompt">$</span>
      <span class="brand-name">diagrama_pantaneiro</span>
      <span class="sep">//</span>
      <span class="user">{user?.email ?? "…"}</span>
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
      {#if backgroundSyncing || refreshing}
        <span class="sep">//</span>
        <span class="sync-indicator">
          <span class="spin">⟳</span> atualizando…
        </span>
      {/if}
    </div>
    <nav class="nav">
      <button type="button" onclick={handleRefresh} disabled={refreshing || backgroundSyncing} class="btn">
        › atualizar
      </button>
      <a class="btn" href="/home/new">› adicionar</a>
      <a class="btn" href="/diagram">› diagrama</a>
      <a class="btn" href="/history">› histórico</a>
      <a class="btn" href="/proventos">› proventos</a>
      <a class="btn btn-accent" href="/aporte">› aporte ▸</a>
      <button class="btn" onclick={handleLogout}>› sair</button>
    </nav>
  </div>

  {#if refreshMessage}
    <p class="toast" class:toast-err={refreshFailed}>
      <span class="prompt">»</span>
      {refreshMessage}
    </p>
  {/if}

  {#if loading && positions.length === 0}
    <p class="loading"><span class="blink">█</span> carregando carteira</p>
  {:else if error && positions.length === 0}
    <p class="toast toast-err"><span class="prompt">!</span> {error}</p>
  {:else}
    <!-- HERO: total + donut -->
    <section class="hero reveal" style="--delay: 0ms">
      <div class="bracket bracket-tl"></div>
      <div class="bracket bracket-tr"></div>
      <div class="bracket bracket-bl"></div>
      <div class="bracket bracket-br"></div>

      <div class="hero-left">
        <p class="label">── patrimônio_total ──</p>
        <p class="total">{fmtBRL(totalValue)}</p>
        <p class="sub">
          <span class="ink-dim">posições:</span>
          <span class="ink">{positions.length}</span>
          <span class="ink-muted">·</span>
          <span class="ink-dim">classes:</span>
          <span class="ink">{donutSegments.length}</span>
          {#if lastUpdatedAt}
            <span class="ink-muted">·</span>
            <span class="ink-dim">atualizado:</span>
            <span class="ink">{formatLastUpdated(lastUpdatedAt)}</span>
          {/if}
        </p>
        <div class="ascii-hr">
          ┼───────────────────────────────────
        </div>
        <ul class="legend">
          {#each donutSegments as s (s.assetType)}
            <li
              class="legend-row"
              class:is-hover={hoveredClass === s.assetType}
              onmouseenter={() => (hoveredClass = s.assetType)}
              onmouseleave={() => (hoveredClass = null)}
              role="listitem"
            >
              <span class="swatch" style="background: {s.color}"></span>
              <span class="legend-abbr">{s.label}</span>
              <span class="legend-name ink-dim">{CLASS_LABELS[s.assetType] ?? s.assetType}</span>
              <span class="legend-pct tab-nums">{s.pct.toFixed(1)}%</span>
              <span class="legend-val tab-nums ink-dim">{fmtBRLCompact(s.value)}</span>
            </li>
          {/each}
        </ul>
      </div>

      <div class="hero-right">
        <svg viewBox="0 0 100 100" class="donut" aria-label="Allocation donut">
          <!-- base ring -->
          <circle cx="50" cy="50" r={RADIUS} fill="none" stroke="var(--hairline)" stroke-width="1" />
          {#each donutSegments as s, i (s.assetType)}
            {@const len = (s.pct / 100) * CIRCUMFERENCE}
            {@const dashOffset = -((s.offset / 100) * CIRCUMFERENCE)}
            <circle
              cx="50"
              cy="50"
              r={RADIUS}
              fill="none"
              stroke={s.color}
              stroke-width={hoveredClass === s.assetType ? 14 : 12}
              stroke-dasharray="{len} {CIRCUMFERENCE - len}"
              stroke-dashoffset={dashOffset}
              transform="rotate(-90 50 50)"
              class="donut-seg"
              style="--draw-delay: {i * 70}ms; --draw-len: {len}; --draw-total: {CIRCUMFERENCE};"
              opacity={hoveredClass && hoveredClass !== s.assetType ? 0.25 : 1}
              role="img"
              aria-label="{s.label} {s.pct.toFixed(1)}%"
              onmouseenter={() => (hoveredClass = s.assetType)}
              onmouseleave={() => (hoveredClass = null)}
            />
          {/each}
          <!-- inner hairline -->
          <circle cx="50" cy="50" r={RADIUS - 7} fill="none" stroke="var(--hairline)" stroke-width="0.5" />
          <text x="50" y="47" text-anchor="middle" class="donut-label-sm">alocação</text>
          <text x="50" y="56" text-anchor="middle" class="donut-label-lg">
            {donutSegments.length > 0 ? `${donutSegments[0].label}` : "—"}
          </text>
          <text x="50" y="63" text-anchor="middle" class="donut-label-sm ink-dim">
            {donutSegments.length > 0 ? `${donutSegments[0].pct.toFixed(0)}%` : ""}
          </text>
        </svg>
      </div>
    </section>

    <!-- TARGETS -->
    <section class="panel reveal" style="--delay: 120ms">
      <div class="bracket bracket-tl"></div>
      <div class="bracket bracket-tr"></div>
      <div class="bracket bracket-bl"></div>
      <div class="bracket bracket-br"></div>

      <header class="panel-head">
        <h2 class="panel-title">── meta_vs_atual ──</h2>
        <button type="button" class="btn btn-ghost" onclick={() => (showTargetsModal = true)}>
          › editar_metas
        </button>
      </header>

      <div class="targets">
        {#each targets as t, idx (t.id)}
          {@const current = classCurrentPct[t.assetType] ?? 0}
          {@const target = t.targetPercentage}
          {@const diff = current - target}
          {@const max = Math.max(current, target, 20)}
          <div class="target-row" style="--row-delay: {idx * 40}ms">
            <div class="target-head">
              <span class="target-abbr" style="color: {CLASS_COLOR[t.assetType] ?? 'var(--ink)'}">
                [{CLASS_ABBR[t.assetType] ?? "??"}]
              </span>
              <span class="target-name">{CLASS_LABELS[t.assetType] ?? t.assetType}</span>
              <span class="target-stats tab-nums">
                <span class="ink">{current.toFixed(1)}%</span>
                <span class="ink-muted">/</span>
                <span class="ink-dim">meta {target.toFixed(0)}%</span>
                {#if Math.abs(diff) > 0.5}
                  <span class="diff" class:diff-over={diff > 0} class:diff-under={diff < 0}>
                    [{diff > 0 ? "+" : ""}{diff.toFixed(1)}]
                  </span>
                {/if}
              </span>
            </div>
            <div class="bar-track">
              <!-- tick marks every 10% of rendered width -->
              {#each Array(10) as _, i}
                {#if (i + 1) * 10 < max}
                  <span class="tick" style="left: {((i + 1) * 10 / max) * 100}%"></span>
                {/if}
              {/each}
              <!-- fill -->
              <div
                class="bar-fill"
                class:over={diff > 0.5}
                class:under={diff < -0.5}
                class:match={Math.abs(diff) <= 0.5}
                style="clip-path: inset(0 {100 - (current / max) * 100}% 0 0)"
              ></div>
              <!-- target marker -->
              <span class="target-marker" style="left: {(target / max) * 100}%">▼</span>
            </div>
          </div>
        {/each}
      </div>
    </section>

    <!-- POSITIONS -->
    <section class="panel reveal" style="--delay: 240ms">
      <div class="bracket bracket-tl"></div>
      <div class="bracket bracket-tr"></div>
      <div class="bracket bracket-bl"></div>
      <div class="bracket bracket-br"></div>

      <header class="panel-head">
        <h2 class="panel-title">── posições [{positions.length}] ──</h2>
        <div class="panel-meta">
          {#if lastUpdatedAt}
            <span class="panel-sub ink-dim">atualizado: <span class="ink">{formatLastUpdated(lastUpdatedAt)}</span></span>
            <span class="panel-sub ink-muted">·</span>
          {/if}
          <span class="panel-sub ink-dim">ordenar_por={sortKey} {sortDesc ? "desc" : "asc"}</span>
        </div>
      </header>

      <!-- svelte-ignore a11y_no_noninteractive_tabindex (Scrollable region needs keyboard focus.) -->
      <div class="table-scroll" role="region" aria-label="Posições da carteira, role para ver todas as colunas" tabindex="0">
      <table class="grid">
        <thead>
          <tr>
            <th class="col-name sortable" class:is-active={sortKey === "nome"} onclick={() => toggleSort("nome")} onkeydown={(e) => e.key === "Enter" && toggleSort("nome")} tabindex="0">
              nome <span class="sort-ind">{sortIndicator("nome")}</span>
            </th>
            <th class="col-class sortable" class:is-active={sortKey === "classe"} onclick={() => toggleSort("classe")} onkeydown={(e) => e.key === "Enter" && toggleSort("classe")} tabindex="0">
              classe <span class="sort-ind">{sortIndicator("classe")}</span>
            </th>
            <th class="col-num sortable" class:is-active={sortKey === "quantidade"} onclick={() => toggleSort("quantidade")} onkeydown={(e) => e.key === "Enter" && toggleSort("quantidade")} tabindex="0">
              quantidade / saldo <span class="sort-ind">{sortIndicator("quantidade")}</span>
            </th>
            <th class="col-num sortable" class:is-active={sortKey === "preco"} onclick={() => toggleSort("preco")} onkeydown={(e) => e.key === "Enter" && toggleSort("preco")} tabindex="0">
              preço <span class="sort-ind">{sortIndicator("preco")}</span>
            </th>
            <th class="col-num sortable" class:is-active={sortKey === "valor"} onclick={() => toggleSort("valor")} onkeydown={(e) => e.key === "Enter" && toggleSort("valor")} tabindex="0">
              valor <span class="sort-ind">{sortIndicator("valor")}</span>
            </th>
            <th class="col-share sortable" class:is-active={sortKey === "participacao"} onclick={() => toggleSort("participacao")} onkeydown={(e) => e.key === "Enter" && toggleSort("participacao")} tabindex="0">
              participação <span class="sort-ind">{sortIndicator("participacao")}</span>
            </th>
            <th class="col-strength sortable" class:is-active={sortKey === "forca"} onclick={() => toggleSort("forca")} onkeydown={(e) => e.key === "Enter" && toggleSort("forca")} tabindex="0">
              força <span class="sort-ind">{sortIndicator("forca")}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {#each [...positions].sort((a, b) => {
            const dir = sortDesc ? -1 : 1;
            const classLabel = (p: PositionOut) => CLASS_LABELS[p.assetType] ?? p.assetType;
            const share = (p: PositionOut) => totalValue > 0 ? p.currentValueBrl / totalValue : 0;
            switch (sortKey) {
              case "nome": return a.name.localeCompare(b.name, "pt-BR") * dir;
              case "classe": return classLabel(a).localeCompare(classLabel(b), "pt-BR") * dir;
              case "quantidade": return (a.amount - b.amount) * dir;
              case "preco": return ((a.currentPrice ?? 0) - (b.currentPrice ?? 0)) * dir;
              case "valor": return (a.currentValueBrl - b.currentValueBrl) * dir;
              case "participacao": return (share(a) - share(b)) * dir;
              case "forca": return (a.strength - b.strength) * dir;
              default: return 0;
            }
          }) as p, i (p.id)}
            {@const share = totalValue > 0 ? (p.currentValueBrl / totalValue) * 100 : 0}
            {@const cells = strengthCells(p.strength)}
            <tr style="--row-delay: {i * 20}ms">
              <td class="col-name">
                <a href="/home/{p.id}">{p.name}</a>
              </td>
              <td class="col-class">
                <span style="color: {CLASS_COLOR[p.assetType] ?? 'var(--ink-dim)'}">
                  [{CLASS_ABBR[p.assetType] ?? "??"}]
                </span>
                <span class="ink-dim">{CLASS_LABELS[p.assetType] ?? p.assetType}</span>
              </td>
              <td class="col-num tab-nums">
                {p.trackingMode === "balance" ? fmtBRL(p.amount) : fmtQty(p.amount)}
              </td>
              <td class="col-num tab-nums ink-dim">
                {p.currentPrice != null ? fmtBRL(p.currentPrice) : "—"}
                {#if p.quoteAsOf}
                  <span class="block text-xs text-slate-500">{p.quoteStale ? "Cotação antiga:" : "Cotação:"} {new Date(p.quoteAsOf).toLocaleDateString("pt-BR", { timeZone: "UTC" })}</span>
                {/if}
              </td>
              <td class="col-num tab-nums val">{fmtBRL(p.currentValueBrl)}</td>
              <td class="col-share">
                <div class="mini-bar">
                  <div
                    class="mini-bar-fill"
                    style="width: {share}%; background: {CLASS_COLOR[p.assetType] ?? 'var(--accent)'}"
                  ></div>
                  <span class="mini-bar-label tab-nums">{share.toFixed(1)}%</span>
                </div>
              </td>
              <td class="col-strength">
                <div class="heat">
                  {#each cells as c}
                    <span class="heat-cell" class:hc-filled={c.filled} class:hc-pos={c.tone === "pos"} class:hc-neg={c.tone === "neg"}></span>
                  {/each}
                  <span
                    class="heat-num tab-nums"
                    class:ink-pos={p.strength > 0}
                    class:ink-neg={p.strength < 0}
                  >
                    {p.strength > 0 ? "+" : ""}{p.strength}
                  </span>
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
      </div>
    </section>
  {/if}

  {#if showTargetsModal}
    <EditTargetsModal
      initialTargets={targets}
      onsaved={(updated) => {
        targets = updated;
        showTargetsModal = false;
      }}
      onclose={() => (showTargetsModal = false)}
    />
  {/if}
</section>

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
  .ink-neg { color: var(--negative); }

  /* ── topbar ─────────────────────────────── */
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
  .brand-logo { height: 56px; width: auto; display: block; }
  .brand-name { color: var(--accent); font-weight: 700; letter-spacing: 0.05em; }
  .prompt { color: var(--accent); font-weight: 700; }
  .sep { color: var(--ink-muted); }
  .user { color: var(--ink-dim); }

  .sync-indicator {
    color: var(--accent);
    font-size: 11px;
    letter-spacing: 0.04em;
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }
  .spin {
    display: inline-block;
    animation: spin 1s linear infinite;
  }
  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

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
  .btn-ghost { border-color: var(--hairline-strong); }

  /* ── toast ──────────────────────────────── */
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

  /* ── brackets decoration ─────────────────── */
  .panel, .hero {
    position: relative;
    background: var(--surface);
    border: 1px solid var(--hairline);
    padding: 28px 24px;
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

  /* ── hero ───────────────────────────────── */
  .hero {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 320px;
    gap: 40px;
    align-items: center;
  }
  .hero-left .label {
    font-size: 11px;
    color: var(--ink-muted);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin-bottom: 8px;
  }
  .total {
    font-size: 44px;
    font-weight: 800;
    letter-spacing: -0.02em;
    line-height: 1;
    font-variant-numeric: tabular-nums;
    color: var(--ink);
  }
  .sub { margin-top: 10px; font-size: 12px; display: flex; gap: 8px; }
  .ascii-hr { margin: 18px 0 14px; color: var(--hairline-strong); font-size: 12px; overflow: hidden; white-space: nowrap; }

  .legend { list-style: none; padding: 0; margin: 0; display: grid; gap: 4px; }
  .legend-row {
    display: grid;
    grid-template-columns: 14px 38px 1fr auto auto;
    align-items: center;
    gap: 10px;
    font-size: 12px;
    padding: 4px 6px;
    border: 1px solid transparent;
    cursor: default;
  }
  .legend-row.is-hover { border-color: var(--hairline-strong); background: var(--surface-raised); }
  .swatch { width: 10px; height: 10px; display: inline-block; }
  .legend-abbr { color: var(--ink); font-weight: 700; letter-spacing: 0.05em; }
  .legend-name { font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .legend-pct { color: var(--ink); font-weight: 500; }
  .legend-val { font-size: 11px; }

  .donut { width: 100%; max-width: 300px; aspect-ratio: 1; }
  .donut-seg {
    transition: stroke-width 160ms, opacity 160ms;
    cursor: pointer;
    animation: draw-seg 900ms ease-out backwards;
    animation-delay: var(--draw-delay, 0ms);
  }
  @keyframes draw-seg {
    from {
      stroke-dasharray: 0 var(--draw-total);
    }
  }
  .donut-label-sm {
    font-size: 4px;
    fill: var(--ink-muted);
    letter-spacing: 0.1em;
    text-transform: uppercase;
    font-family: "JetBrains Mono", monospace;
  }
  .donut-label-lg {
    font-size: 10px;
    fill: var(--accent);
    font-weight: 800;
    letter-spacing: 0.05em;
    font-family: "JetBrains Mono", monospace;
  }

  /* ── panel head ─────────────────────────── */
  .panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 18px;
  }
  .panel-title { font-size: 12px; font-weight: 700; letter-spacing: 0.1em; color: var(--ink-dim); }
  .panel-meta { display: flex; align-items: center; gap: 8px; }
  .panel-sub { font-size: 11px; letter-spacing: 0.05em; }

  /* ── targets ────────────────────────────── */
  .targets { display: grid; gap: 14px; }
  .target-row { animation: fade-up 500ms ease-out backwards; animation-delay: var(--row-delay); }
  .target-head {
    display: grid;
    grid-template-columns: 50px 1fr auto;
    gap: 10px;
    align-items: baseline;
    margin-bottom: 6px;
    font-size: 12px;
  }
  .target-abbr { font-weight: 700; letter-spacing: 0.05em; }
  .target-name { color: var(--ink); font-weight: 500; }
  .target-stats { font-size: 12px; display: flex; gap: 6px; }
  .diff-over { color: var(--negative); font-weight: 700; }
  .diff-under { color: var(--info); font-weight: 700; }

  .bar-track {
    position: relative;
    height: 14px;
    background: #0d0f12;
    border: 1px solid var(--hairline);
    overflow: visible;
  }
  .tick { position: absolute; top: 0; bottom: 0; width: 1px; background: var(--hairline-strong); pointer-events: none; }
  .bar-fill {
    width: 100%;
    height: 100%;
    transition: clip-path 600ms cubic-bezier(0.2, 0.9, 0.3, 1);
    background: repeating-linear-gradient(
      90deg,
      var(--fill) 0 6px,
      color-mix(in srgb, var(--fill) 75%, #000) 6px 8px
    );
    --fill: var(--positive);
  }
  .bar-fill.over { --fill: var(--negative); }
  .bar-fill.under { --fill: var(--info); }
  .bar-fill.match { --fill: var(--positive); }
  .target-marker {
    position: absolute;
    top: -10px;
    transform: translateX(-50%);
    color: var(--accent);
    font-size: 10px;
    line-height: 1;
    pointer-events: none;
    text-shadow: 0 0 6px var(--accent);
  }

  /* ── grid (positions) ───────────────────── */
  .grid {
    display: table;
    width: 100%;
    min-width: 980px;
    border-collapse: collapse;
    font-size: 12px;
    table-layout: fixed;
  }
  .grid thead { display: table-header-group; }
  .grid tbody { display: table-row-group; }
  .grid tr { display: table-row; }
  .grid th, .grid td { display: table-cell; }
  /* larguras explícitas — garante alinhamento thead↔tbody sem depender do auto-layout */
  .grid .col-name { width: 20%; word-break: break-word; }
  .grid .col-class { width: 18%; }
  .grid .col-num { width: 10%; }
  .grid .col-share { width: 18%; }
  .grid .col-strength { width: 14%; }
  .grid thead th {
    text-align: left;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    font-size: 10px;
    color: var(--ink-muted);
    padding: 8px 10px;
    border-bottom: 1px solid var(--hairline-strong);
  }
  .grid thead th.col-num,
  .grid thead th.col-strength { text-align: right !important; }
  .sortable { cursor: pointer; user-select: none; transition: color 120ms, background 120ms; }
  .sortable:hover { color: var(--accent); background: var(--surface-raised); }
  .sortable:focus-visible { outline: 1px solid var(--accent); outline-offset: -1px; }
  .sortable.is-active { color: var(--accent); }
  .sort-ind { font-size: 9px; opacity: 0.7; margin-left: 4px; }
  .sortable.is-active .sort-ind { opacity: 1; }
  .grid tbody tr {
    animation: fade-up 400ms ease-out backwards;
    animation-delay: var(--row-delay);
  }
  .grid tbody td {
    padding: 10px;
    border-bottom: 1px solid var(--hairline);
    vertical-align: middle;
  }
  .grid tbody tr:hover td { background: var(--surface-raised); }
  .col-num { text-align: right; }
  .col-strength { text-align: right; }
  .val { color: var(--ink); font-weight: 700; }
  .col-name a { color: var(--ink); text-decoration: none; border-bottom: 1px dotted var(--hairline-strong); }
  .col-name a:hover { color: var(--accent); border-bottom-color: var(--accent); }

  /* mini horizontal share bar */
  .mini-bar {
    position: relative;
    width: 120px;
    height: 12px;
    background: #0d0f12;
    border: 1px solid var(--hairline);
  }
  .mini-bar-fill { height: 100%; }
  .mini-bar-label {
    position: absolute;
    right: 4px;
    top: 50%;
    transform: translateY(-50%);
    font-size: 10px;
    color: var(--ink);
    mix-blend-mode: difference;
  }

  /* strength heat-strip */
  .heat { display: flex; gap: 2px; align-items: center; justify-content: flex-end; }
  .heat-cell {
    width: 6px;
    height: 12px;
    background: var(--hairline);
    display: inline-block;
  }
  .hc-filled.hc-pos { background: var(--positive); box-shadow: 0 0 4px color-mix(in srgb, var(--positive) 60%, transparent); }
  .hc-filled.hc-neg { background: var(--negative); box-shadow: 0 0 4px color-mix(in srgb, var(--negative) 60%, transparent); }
  .heat-num { margin-left: 8px; min-width: 28px; text-align: right; font-weight: 700; }

  /* ── reveal animation ───────────────────── */
  .reveal { animation: fade-up 600ms cubic-bezier(0.2, 0.9, 0.3, 1) backwards; animation-delay: var(--delay, 0ms); }
  @keyframes fade-up {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
  }

  @media (max-width: 860px) {
    .hero { grid-template-columns: 1fr; }
    .hero-right { justify-self: center; width: min(100%, 300px); }
    .nav { justify-content: flex-start; flex-wrap: wrap; }
    .brand { flex-wrap: wrap; min-width: 0; }
    .panel-head, .panel-meta { flex-wrap: wrap; gap: 10px; }
    .sub { flex-wrap: wrap; }
  }
  @media (max-width: 640px) {
    .wrap { padding: 16px 12px 48px; }
    .topbar { align-items: stretch; gap: 16px; padding: 12px; }
    .brand-logo { height: 36px; }
    .brand-name { font-size: 11px; }
    .panel, .hero { padding: 20px 12px; }
    .hero { gap: 24px; }
    .total { font-size: clamp(24px, 7vw, 36px); overflow-wrap: anywhere; }
    .legend-row { grid-template-columns: 10px 32px minmax(0, 1fr) auto; gap: 6px; }
    .legend-val { grid-column: 3 / -1; justify-self: end; }
    .target-head { grid-template-columns: 38px minmax(0, 1fr); gap: 6px; }
    .target-stats { grid-column: 2; flex-wrap: wrap; }
    .panel-title { overflow-wrap: anywhere; }
    .panel-head .btn { min-height: 44px; }
  }
</style>
