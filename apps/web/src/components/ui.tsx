"use client";

import Link from "next/link";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { ApiError } from "@/lib/api";
import { hasKey, useI18n } from "@/lib/i18n";
import type { Criterion, SkillStateName } from "@/lib/types";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

/* ------------------------------------------------------------------ buttons */
type Variant = "primary" | "secondary" | "ghost" | "danger";
const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-accent-contrast hover:bg-accent-strong border-transparent",
  secondary: "bg-surface-2 text-text border-border hover:bg-surface-3 hover:border-border-strong",
  ghost: "bg-transparent text-muted border-transparent hover:text-text hover:bg-surface-2",
  danger: "bg-danger-soft text-danger border-transparent hover:bg-danger hover:text-accent-contrast",
};
const BUTTON_BASE =
  "inline-flex items-center justify-center gap-1.5 rounded-md border font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 whitespace-nowrap";
const SIZES = { sm: "h-7 px-2.5 text-sm", md: "h-8 px-3 text-sm" } as const;

export function Button({
  variant = "secondary",
  size = "md",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: keyof typeof SIZES }) {
  return <button type="button" className={cx(BUTTON_BASE, SIZES[size], VARIANTS[variant], className)} {...props} />;
}

export function ButtonLink({
  href,
  variant = "secondary",
  size = "md",
  className,
  children,
}: {
  href: string;
  variant?: Variant;
  size?: keyof typeof SIZES;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Link href={href} className={cx(BUTTON_BASE, SIZES[size], VARIANTS[variant], className)}>
      {children}
    </Link>
  );
}

/* ------------------------------------------------------------------ layout */
export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 max-w-2xl text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

export function Panel({
  title,
  actions,
  children,
  className,
  padded = true,
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return (
    <section className={cx("rounded-lg border border-border bg-surface", className)}>
      {(title || actions) && (
        <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-2.5">
          {title && <h2 className="text-sm font-semibold">{title}</h2>}
          {actions}
        </div>
      )}
      <div className={padded ? "p-4" : undefined}>{children}</div>
    </section>
  );
}

/* ------------------------------------------------------------------ status */
const STATE_STYLE: Record<SkillStateName, string> = {
  planned: "text-subtle bg-surface-2",
  locked: "text-subtle bg-surface-2",
  available: "text-accent bg-accent-soft",
  in_progress: "text-warning bg-warning-soft",
  mastered: "text-success bg-success-soft",
  needs_review: "text-warning bg-warning-soft",
};

export function StateBadge({ state }: { state: SkillStateName }) {
  const { t } = useI18n();
  return (
    <span className={cx("inline-flex items-center rounded-sm px-1.5 py-0.5 text-xs font-medium", STATE_STYLE[state])}>
      {t(`state.${state}`)}
    </span>
  );
}

export function Tag({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "success" | "danger" | "warning" | "accent" }) {
  const tones = {
    neutral: "text-muted bg-surface-2",
    success: "text-success bg-success-soft",
    danger: "text-danger bg-danger-soft",
    warning: "text-warning bg-warning-soft",
    accent: "text-accent bg-accent-soft",
  };
  return <span className={cx("inline-flex items-center rounded-sm px-1.5 py-0.5 text-xs", tones[tone])}>{children}</span>;
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-muted" role="status">
      <span className="size-3.5 animate-spin rounded-full border-2 border-border-strong border-t-accent" aria-hidden />
      {label}
    </span>
  );
}

export function LoadingBlock() {
  const { t } = useI18n();
  return (
    <div className="flex min-h-40 items-center justify-center">
      <Spinner label={t("common.loading")} />
    </div>
  );
}

export function errorText(t: ReturnType<typeof useI18n>["t"], error: ApiError): string {
  const key = `error.${error.code}`;
  return hasKey(key) ? t(key) : t("error.generic", { message: error.message });
}

export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  const { t } = useI18n();
  return (
    <div role="alert" className="rounded-lg border border-danger/40 bg-danger-soft p-4">
      <p className="text-sm font-semibold text-danger">{t("error.title")}</p>
      <p className="mt-1 text-sm">{errorText(t, error)}</p>
      {error.requestId && <p className="mt-1 font-mono text-xs text-subtle">request_id: {error.requestId}</p>}
      {onRetry && (
        <Button className="mt-3" size="sm" onClick={onRetry}>
          {t("common.retry")}
        </Button>
      )}
    </div>
  );
}

export function InlineNotice({ tone = "neutral", children }: { tone?: "neutral" | "warning" | "danger" | "success" | "accent"; children: ReactNode }) {
  const tones = {
    neutral: "border-border bg-surface-2 text-muted",
    warning: "border-warning/30 bg-warning-soft text-text",
    danger: "border-danger/30 bg-danger-soft text-text",
    success: "border-success/30 bg-success-soft text-text",
    accent: "border-accent/30 bg-accent-soft text-text",
  };
  return <div className={cx("rounded-md border px-3 py-2 text-sm", tones[tone])}>{children}</div>;
}

/* ------------------------------------------------------------------ content */
export function Markdown({ children, className }: { children: string; className?: string }) {
  // react-markdown does not render raw HTML: content and learner text cannot inject markup.
  return (
    <div className={cx("prose-forge", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{ a: ({ href, children: c }) => <a href={href} target="_blank" rel="noreferrer noopener">{c}</a> }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}

export function CodeBlock({ code, label }: { code: string; label?: string }) {
  return (
    <figure className="overflow-hidden rounded-md border border-border bg-code">
      {label && <figcaption className="border-b border-border px-3 py-1 text-xs text-subtle">{label}</figcaption>}
      <pre className="overflow-x-auto px-3 py-2.5 font-mono text-sm leading-relaxed">
        <code>{code.replace(/\n$/, "")}</code>
      </pre>
    </figure>
  );
}

export function CriteriaList({ criteria }: { criteria: Criterion[] }) {
  const { t, tk } = useI18n();
  return (
    <ul className="space-y-1.5">
      {criteria.map((c) => (
        <li key={c.id} className="flex items-start gap-2 text-sm">
          <span
            aria-hidden
            className={cx(
              "mt-0.5 inline-flex size-4 shrink-0 items-center justify-center rounded-full text-[10px] font-bold",
              c.met ? "bg-success-soft text-success" : "border border-dashed border-border-strong text-subtle",
            )}
          >
            {c.met ? "✓" : ""}
          </span>
          <span className={c.met ? "text-text" : "text-muted"}>
            {tk(`criterion.${c.id}`, c.id)}
            <span className="ml-1.5 font-mono text-xs text-subtle">{t("common.of", { a: c.current, b: c.required })}</span>
            {c.note && <span className="ml-1.5 text-xs text-warning">· {tk(`criterion.note.${c.note}`, c.note)}</span>}
          </span>
          <span className="sr-only">{c.met ? t("common.yes") : t("common.no")}</span>
        </li>
      ))}
    </ul>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="min-w-0">
      <dt className="truncate text-xs text-muted">{label}</dt>
      <dd className="mt-0.5 text-lg font-semibold tabular-nums">{value}</dd>
      {hint && <p className="text-xs text-subtle">{hint}</p>}
    </div>
  );
}

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
  label,
  className,
}: {
  tabs: { id: T; label: ReactNode }[];
  value: T;
  onChange: (v: T) => void;
  label: string;
  className?: string;
}) {
  return (
    <div role="tablist" aria-label={label} className={cx("flex gap-0.5 overflow-x-auto", className)}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          id={`tab-${tab.id}`}
          aria-selected={value === tab.id}
          aria-controls={`panel-${tab.id}`}
          tabIndex={value === tab.id ? 0 : -1}
          onClick={() => onChange(tab.id)}
          onKeyDown={(e) => {
            if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
            const i = tabs.findIndex((x) => x.id === value);
            const next = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
            if (next) {
              onChange(next.id);
              document.getElementById(`tab-${next.id}`)?.focus();
            }
          }}
          className={cx(
            "h-8 shrink-0 rounded-md px-2.5 text-sm transition-colors",
            value === tab.id ? "bg-surface-3 font-medium text-text" : "text-muted hover:bg-surface-2 hover:text-text",
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
