const MASK = "••••";

export function formatBrl(v: number, masked = false): string {
  if (masked) return `R$ ${MASK}`;
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function formatBrlCompact(v: number, masked = false): string {
  if (masked) return `R$ ${MASK}`;
  if (v >= 1_000_000) return `R$ ${(v / 1_000_000).toFixed(2)}M`;
  if (v >= 1_000) return `R$ ${(v / 1_000).toFixed(1)}k`;
  return formatBrl(v);
}

export function formatQty(
  v: number,
  masked = false,
  maxDigits = 6,
): string {
  if (masked) return MASK;
  return v.toLocaleString("pt-BR", { maximumFractionDigits: maxDigits });
}

export function formatLastUpdated(iso: string | Date | null | undefined): string {
  if (!iso) return "—";
  const d = typeof iso === "string" ? new Date(iso) : iso;
  if (isNaN(d.getTime())) return "—";

  const now = new Date();
  const timeStr = d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });

  const isToday =
    d.getDate() === now.getDate() &&
    d.getMonth() === now.getMonth() &&
    d.getFullYear() === now.getFullYear();

  if (isToday) {
    return `hoje às ${timeStr}`;
  }

  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  const isYesterday =
    d.getDate() === yesterday.getDate() &&
    d.getMonth() === yesterday.getMonth() &&
    d.getFullYear() === yesterday.getFullYear();

  if (isYesterday) {
    return `ontem às ${timeStr}`;
  }

  const dateStr = d.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: d.getFullYear() !== now.getFullYear() ? "numeric" : undefined,
  });
  return `${dateStr} às ${timeStr}`;
}
