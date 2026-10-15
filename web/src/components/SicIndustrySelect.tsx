import { useEffect, useId, useMemo, useRef, useState } from "react";
import {
  formatSicIndustry,
  industryMatchesSearch,
  sicSelectSummary,
  toggleSicIndustry,
} from "../lib/screener";

interface Props {
  industries: string[];
  selected: string[];
  disabled: boolean;
  allLabel: string;
  onChange: (selected: string[]) => void;
}

export function SicIndustrySelect({ industries, selected, disabled, allLabel, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const listId = useId();
  const labelId = useId();

  const visible = useMemo(
    () => industries.filter((label) => industryMatchesSearch(label, search)),
    [industries, search],
  );

  useEffect(() => {
    if (!open) return;
    searchRef.current?.focus();
    const onDoc = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  useEffect(() => {
    if (!open) setSearch("");
  }, [open]);

  const summary = sicSelectSummary(selected, allLabel);
  const count = selected.length;

  return (
    <div className="field sic-select" ref={rootRef}>
      <label id={labelId} htmlFor="sic-industry">
        SEC SIC industry{count ? ` (${count})` : ""}
      </label>
      <button
        id="sic-industry"
        type="button"
        className="sic-select-trigger"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-labelledby={labelId}
        onClick={() => setOpen((v) => !v)}
      >
        <span className={`sic-select-value ${count ? "" : "placeholder"}`}>{summary}</span>
        <span className="sic-select-caret" aria-hidden="true" />
      </button>
      {open && (
        <div className="sic-select-panel" id={listId} role="listbox" aria-multiselectable="true" aria-labelledby={labelId}>
          <div className="sic-select-toolbar">
            <input
              ref={searchRef}
              type="search"
              className="sic-select-search"
              placeholder="Search name or SIC code"
              value={search}
              autoComplete="off"
              spellCheck={false}
              aria-label="Search SEC SIC industries"
              onChange={(e) => setSearch(e.target.value)}
            />
            {count > 0 && (
              <button type="button" className="btn btn-link sic-select-clear" onClick={() => onChange([])}>
                Clear all
              </button>
            )}
          </div>
          <div className="sic-select-list">
            {visible.length === 0 && <p className="sic-select-empty muted">No matching industries</p>}
            {visible.map((label) => {
              const checked = selected.includes(label);
              return (
                <label key={label} className={`sic-select-opt ${checked ? "on" : ""}`}>
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => onChange(toggleSicIndustry(selected, label))}
                  />
                  <span>{formatSicIndustry(label)}</span>
                </label>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
