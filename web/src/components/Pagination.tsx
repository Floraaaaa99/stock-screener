import { formatCount } from "../lib/format";
import { PAGE_SIZE } from "../lib/screener";

interface Props {
  page: number;
  pages: number;
  total: number;
  onPage: (page: number) => void;
}

function pageList(page: number, pages: number): (number | "…")[] {
  const out: (number | "…")[] = [];
  const add = (p: number) => {
    if (p >= 1 && p <= pages && !out.includes(p)) out.push(p);
  };
  add(1);
  if (page - 2 > 2) out.push("…");
  for (let p = page - 2; p <= page + 2; p++) add(p);
  if (page + 2 < pages - 1) out.push("…");
  add(pages);
  return out;
}

export function Pagination({ page, pages, total, onPage }: Props) {
  const from = (page - 1) * PAGE_SIZE + 1;
  const to = Math.min(page * PAGE_SIZE, total);
  return (
    <nav className="pagination" aria-label="Pagination">
      <span className="muted">
        Showing {formatCount(from)}–{formatCount(to)} of {formatCount(total)}
      </span>
      <div className="pages">
        <button type="button" className="btn btn-small" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          ‹ Prev
        </button>
        {pageList(page, pages).map((p, i) =>
          p === "…" ? (
            <span key={`gap-${i}`} className="gap">
              …
            </span>
          ) : (
            <button
              key={p}
              type="button"
              className={`btn btn-small ${p === page ? "current" : ""}`}
              aria-current={p === page ? "page" : undefined}
              onClick={() => onPage(p)}
            >
              {p}
            </button>
          ),
        )}
        <button type="button" className="btn btn-small" disabled={page >= pages} onClick={() => onPage(page + 1)}>
          Next ›
        </button>
      </div>
    </nav>
  );
}
