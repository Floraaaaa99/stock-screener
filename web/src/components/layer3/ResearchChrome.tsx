import type { ReactNode } from "react";
import { naReason, flagText } from "../../lib/explain";
import { fiscalLabel, formatDate } from "../../lib/format";
import {
  displayKind,
  displayKindLabel,
  metricProvenance,
  verificationLabel,
  type DisplayKind,
  type MetricKind,
  type ProvenanceFields,
} from "../../lib/layer3Research";

export function QualityChip({ kind, title }: { kind: DisplayKind; title?: string }) {
  return (
    <span className={`l3-chip is-${kind}`} title={title}>
      {displayKindLabel(kind)}
    </span>
  );
}

export function ProvenancePanel({
  fields,
  extra,
}: {
  fields: ProvenanceFields;
  extra?: ReactNode;
}) {
  const flags = fields.qualityFlags ?? [];
  const period =
    fields.fiscalYear && fields.fiscalQuarter
      ? fiscalLabel(fields.fiscalYear, fields.fiscalQuarter)
      : null;
  return (
    <dl className="l3-prov-grid">
      {period && (
        <div>
          <dt>Fiscal period</dt>
          <dd>{period}</dd>
        </div>
      )}
      {(fields.start || fields.end) && (
        <div>
          <dt>Dates</dt>
          <dd>
            {fields.start ? `${fields.start} → ` : ""}
            {fields.end ?? "—"}
            {fields.end ? ` (${formatDate(fields.end)})` : ""}
          </dd>
        </div>
      )}
      {fields.concept && (
        <div>
          <dt>SEC concept</dt>
          <dd className="concept">{fields.concept}</dd>
        </div>
      )}
      {fields.calculationMethod && (
        <div>
          <dt>Calculation</dt>
          <dd>{fields.calculationMethod}</dd>
        </div>
      )}
      {fields.method && (
        <div>
          <dt>Quarter method</dt>
          <dd>{fields.method}</dd>
        </div>
      )}
      {fields.formula && (
        <div>
          <dt>Formula</dt>
          <dd>{fields.formula}</dd>
        </div>
      )}
      <div>
        <dt>Verification</dt>
        <dd>{verificationLabel(fields.verification)}</dd>
      </div>
      {fields.identity && (
        <div>
          <dt>Identity</dt>
          <dd>{fields.identity.replace(/_/g, " ")}</dd>
        </div>
      )}
      {fields.status && (
        <div>
          <dt>Status</dt>
          <dd>{fields.status.replace(/_/g, " ")}</dd>
        </div>
      )}
      {fields.reason && (
        <div>
          <dt>Reason</dt>
          <dd>{naReason(fields.reason)}</dd>
        </div>
      )}
      {flags.length > 0 && (
        <div>
          <dt>Quality flags</dt>
          <dd>{flags.map((f) => flagText(f)).join(" · ")}</dd>
        </div>
      )}
      {fields.qualityNote && (
        <div>
          <dt>Quality note</dt>
          <dd>{fields.qualityNote}</dd>
        </div>
      )}
      {fields.unreliableTtm != null && (
        <div>
          <dt>Suppressed TTM</dt>
          <dd>Stored but not shown as a clean ratio: {fields.unreliableTtm}</dd>
        </div>
      )}
      {fields.unreliableValue != null && (
        <div>
          <dt>Suppressed value</dt>
          <dd>Stored but not shown as a clean ratio: {fields.unreliableValue}</dd>
        </div>
      )}
      {fields.form && (
        <div>
          <dt>Filing</dt>
          <dd>
            {fields.url ? (
              <a href={fields.url} target="_blank" rel="noreferrer">
                {fields.form}
                {fields.accn ? ` · ${fields.accn}` : ""}
              </a>
            ) : (
              fields.form
            )}
            {fields.filed ? ` · filed ${formatDate(fields.filed)}` : ""}
          </dd>
        </div>
      )}
      {fields.unit && (
        <div>
          <dt>Unit</dt>
          <dd>{fields.unit}</dd>
        </div>
      )}
      {extra}
    </dl>
  );
}

export function MetricSource({ metric, label = "Source" }: { metric?: MetricKind | null; label?: string }) {
  if (!metric) return null;
  return (
    <details className="l3-prov">
      <summary>{label}</summary>
      <ProvenancePanel fields={metricProvenance(metric)} />
    </details>
  );
}

export function MetricCard({
  title,
  value,
  period,
  metric,
  hint,
}: {
  title: string;
  value: ReactNode;
  period?: string | null;
  metric?: MetricKind | null;
  hint?: string | null;
}) {
  const kind = displayKind(metric);
  const reason = metric?.reason ? naReason(metric.reason) : hint;
  return (
    <article className="l3-card">
      <header>
        <h3>{title}</h3>
        <QualityChip kind={kind} title={reason ?? undefined} />
      </header>
      <p className={`l3-card-value ${kind === "missing" || kind === "not_applicable" || kind === "suppressed" ? "is-empty" : ""}`}>
        {value}
      </p>
      {period && <p className="muted l3-card-period">{period}</p>}
      {reason && (kind === "missing" || kind === "not_applicable" || kind === "suppressed") && (
        <p className="muted l3-card-reason">{reason}</p>
      )}
      <MetricSource metric={metric} />
    </article>
  );
}

export function ViewToggle<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { id: T; label: string }[];
  onChange: (next: T) => void;
  label: string;
}) {
  return (
    <div className="l3-view-toggle" role="group" aria-label={label}>
      {options.map((opt) => (
        <button
          key={opt.id}
          type="button"
          className={`btn btn-small ${value === opt.id ? "current" : ""}`}
          aria-pressed={value === opt.id}
          onClick={() => onChange(opt.id)}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

export function Unavailable({ reason }: { reason?: string | null }) {
  return (
    <span className="na" title={reason ? naReason(reason) : "Not available — missing values are not replaced with zero"}>
      Unavailable
    </span>
  );
}
