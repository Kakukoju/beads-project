// utils/percent.ts
export function normalizePercent(v: unknown): number {
  if (v === null || v === undefined) return 0;

  // number
  if (typeof v === "number" && Number.isFinite(v)) {
    // 後端回傳 0~1
    if (v <= 1) return v * 100;
    return v;
  }

  // string
  if (typeof v === "string") {
    const s = v.replace("%", "").trim();
    const n = Number(s);
    if (!Number.isFinite(n)) return 0;

    // "0.9945" or "0.9945%"
    if (n <= 1) return n * 100;

    return n;
  }

  return 0;
}
