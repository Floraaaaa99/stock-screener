import type { Layer2Rate } from "../types";

export function QoqChart({ rates, width = 120, height = 36 }: { rates: Layer2Rate[]; width?: number; height?: number }) {
  const nums = rates.map((r) => r.rate);
  const known = nums.filter((n): n is number => n !== null && Number.isFinite(n));
  if (known.length === 0) return <span className="muted">N/A</span>;
  const lo = Math.min(0, ...known);
  const hi = Math.max(0, ...known);
  const span = hi - lo || 1;
  const pad = 2;
  const innerW = width - pad * 2;
  const innerH = height - pad * 2;
  const pts = nums.map((n, i) => {
    const x = pad + (i * innerW) / Math.max(1, nums.length - 1);
    if (n === null || !Number.isFinite(n)) return null;
    const y = pad + innerH - ((n - lo) / span) * innerH;
    return { x, y, n };
  });
  const line = pts.filter((p): p is { x: number; y: number; n: number } => p !== null);
  const zeroY = pad + innerH - ((0 - lo) / span) * innerH;
  const d = line.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  return (
    <svg className="qoq-chart" width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
      <line x1={pad} x2={width - pad} y1={zeroY} y2={zeroY} className="qoq-zero" />
      {d && <path d={d} className="qoq-line" />}
      {pts.map((p, i) =>
        p ? <circle key={i} cx={p.x} cy={p.y} r={2.2} className={p.n < 0 ? "qoq-neg" : "qoq-pos"} /> : null,
      )}
    </svg>
  );
}
