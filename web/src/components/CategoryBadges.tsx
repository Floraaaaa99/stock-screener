import type { Layer2Badge } from "../types";

export function CategoryBadges({ badges, showBlocked = false }: { badges: Layer2Badge[]; showBlocked?: boolean }) {
  const shown = badges.filter((b) => b.applied || (showBlocked && b.blockedByThreshold));
  if (shown.length === 0) return <span className="muted">—</span>;
  return (
    <span className="badge-list">
      {shown.map((b) => (
        <span
          key={b.id}
          className={`cat-badge ${b.applied ? "on" : "blocked"} ${b.id}`}
          title={b.tooltip}
        >
          {b.applied ? b.label : `${b.label}: Threshold not configured`}
        </span>
      ))}
    </span>
  );
}
