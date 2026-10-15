import { formatCount } from "../lib/format";
import type { AddToLayer3Result } from "../lib/layer3";

interface Props {
  selectedCount: number;
  alreadySavedCount: number;
  filteredCount: number;
  lastResult: AddToLayer3Result | null;
  storageNotice: string | null;
  onClear: () => void;
  onAdd: () => void;
  onOpenLayer3: () => void;
}

export function SelectionBar({
  selectedCount,
  alreadySavedCount,
  filteredCount,
  lastResult,
  storageNotice,
  onClear,
  onAdd,
  onOpenLayer3,
}: Props) {
  return (
    <div className="selection-bar panel">
      <div className="selection-bar-main">
        <p className="selection-count">
          <strong>{formatCount(selectedCount)}</strong> selected
          {alreadySavedCount > 0 && (
            <span className="muted"> · {formatCount(alreadySavedCount)} already in Layer 3</span>
          )}
        </p>
        <p className="selection-scope muted">
          Header checkbox selects all <strong>{formatCount(filteredCount)}</strong> companies on this
          filtered list, including other pages. While select-all is on, adding or removing a
          category keeps the new list fully selected. Checking a row does not add it until you
          click Add to Layer 3.
        </p>
      </div>
      <div className="selection-actions">
        <button type="button" className="btn" disabled={selectedCount === 0} onClick={onClear}>
          Clear selection
        </button>
        <button type="button" className="btn current" disabled={selectedCount === 0} onClick={onAdd}>
          Add {selectedCount > 0 ? formatCount(selectedCount) : "0"} to Layer 3
        </button>
        <button type="button" className="btn btn-link" onClick={onOpenLayer3}>
          View Layer 3
        </button>
      </div>
      {lastResult && (
        <p className="selection-result" role="status">
          {lastResult.added > 0
            ? `Added ${formatCount(lastResult.added)} ${lastResult.added === 1 ? "issuer" : "issuers"} to Layer 3.`
            : "No new issuers added."}
          {lastResult.alreadySaved > 0 &&
            ` ${formatCount(lastResult.alreadySaved)} already on the list were left unchanged.`}
        </p>
      )}
      {storageNotice && (
        <p className="selection-storage" role="status">
          {storageNotice}
        </p>
      )}
    </div>
  );
}
