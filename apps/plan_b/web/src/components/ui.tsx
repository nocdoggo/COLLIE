import type { ReactNode } from "react";

import type { StatusLabel, Tone } from "../format";

/** Status as icon + text (never color alone). The icon is decorative. */
export function StatusBadge({ label, extra }: { label: StatusLabel; extra?: string }) {
  return (
    <span className={`badge tone-${label.tone}`}>
      <span className="badge-icon" aria-hidden="true">
        {label.icon}
      </span>
      {label.text}
      {extra !== undefined ? <span className="badge-extra"> {extra}</span> : null}
    </span>
  );
}

export function Tag({ tone = "neutral", icon, children }: { tone?: Tone; icon?: string; children: ReactNode }) {
  return (
    <span className={`tag tone-${tone}`}>
      {icon !== undefined ? (
        <span className="badge-icon" aria-hidden="true">
          {icon}
        </span>
      ) : null}
      {children}
    </span>
  );
}

export function Section({
  id,
  title,
  subtitle,
  children,
  className,
}: {
  id: string;
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className={`card ${className ?? ""}`}>
      <h2 id={`${id}-title`} className="card-title">
        {title}
      </h2>
      {subtitle !== undefined ? <p className="card-subtitle">{subtitle}</p> : null}
      {children}
    </section>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>;
}

/**
 * Moves focus to another element on the board. Plain #fragment links would collide with the
 * hash router, so this is a button that scrolls and focuses the target.
 */
export function JumpButton({ targetId, children }: { targetId: string; children: ReactNode }) {
  return (
    <button
      type="button"
      className="link-button"
      onClick={() => {
        const target = document.getElementById(targetId);
        if (target === null) return;
        if (target instanceof HTMLDetailsElement) target.open = true;
        target.scrollIntoView({ block: "center" });
        target.focus({ preventScroll: true });
      }}
    >
      {children}
    </button>
  );
}

/** A scenario time in the event zone, with the exact UTC instant as machine-readable value. */
export function When({ iso, text }: { iso: string | null | undefined; text: string }) {
  if (iso === null || iso === undefined) return <span>{text}</span>;
  return (
    <time dateTime={iso} title={iso}>
      {text}
    </time>
  );
}

export function Code({ children }: { children: ReactNode }) {
  return <code className="code">{children}</code>;
}

export function domId(prefix: string, id: string): string {
  return `${prefix}-${id.replace(/[^A-Za-z0-9_-]/g, "_")}`;
}
