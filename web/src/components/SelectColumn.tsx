import { useEffect, useRef } from "react";
import type { HeaderCheckState } from "../lib/layer3";

export function SelectHeader({
  state,
  filteredCount,
  disabled,
  onToggle,
}: {
  state: HeaderCheckState;
  filteredCount: number;
  disabled?: boolean;
  onToggle: () => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = state === "some";
  }, [state]);

  const label =
    filteredCount === 0
      ? "No filtered companies to select"
      : `Select all ${filteredCount} currently filtered companies, including other pages`;

  return (
    <th className="select-col" scope="col">
      <label className="row-select">
        <input
          ref={ref}
          type="checkbox"
          checked={state === "all"}
          disabled={disabled || filteredCount === 0}
          onChange={onToggle}
          aria-label={label}
        />
      </label>
    </th>
  );
}

export function SelectCell({
  ticker,
  checked,
  saved,
  onChange,
}: {
  ticker: string;
  checked: boolean;
  saved: boolean;
  onChange: (ticker: string, checked: boolean) => void;
}) {
  return (
    <td className="select-col" onClick={(e) => e.stopPropagation()}>
      <label className="row-select">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(ticker, e.target.checked)}
          aria-label={saved ? `Select ${ticker} (already in Layer 3)` : `Select ${ticker} for Layer 3`}
        />
      </label>
      {saved && (
        <span className="in-layer3" title="Already saved on the Layer 3 research list">
          In L3
        </span>
      )}
    </td>
  );
}
