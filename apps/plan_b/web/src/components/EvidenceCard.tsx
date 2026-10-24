import { useState } from "react";
import type { ReactNode } from "react";

import { pretty } from "../format";

/**
 * Expandable raw JSON for one record. The JSON is rendered only while open, as text
 * (React escapes it), so large evaluations do not slow the board down.
 */
export function EvidenceCard({
  title,
  value,
  id,
  hint,
}: {
  title: ReactNode;
  value: unknown;
  id?: string;
  hint?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <details
      className="evidence"
      id={id}
      tabIndex={id !== undefined ? -1 : undefined}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>
        <span className="evidence-title">{title}</span>
        {hint !== undefined ? <span className="evidence-hint"> {hint}</span> : null}
      </summary>
      {open ? (
        <pre className="evidence-json" tabIndex={0} aria-label="Raw JSON">
          {pretty(value)}
        </pre>
      ) : null}
    </details>
  );
}
