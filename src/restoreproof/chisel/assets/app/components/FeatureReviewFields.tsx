"use client";

import { useId, type ReactNode } from "react";

const inputStyle = "w-full rounded-xl border border-outline-variant bg-background/60 px-3.5 py-3 text-sm leading-6 text-on-surface placeholder:text-on-surface-variant/60 transition-colors hover:border-outline focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20";

interface ReviewFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  multiline?: boolean;
  hint?: string;
  rows?: number;
  onBlur?: () => void;
}

export const ReviewField = ({ label, value, onChange, multiline, hint, rows = 3, onBlur }: ReviewFieldProps) => {
  const id = useId();
  const shared = {
    id,
    value,
    onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => onChange(event.target.value),
    onBlur,
    "aria-describedby": hint ? `${id}-hint` : undefined,
    className: inputStyle,
  };

  return (
    <div className="space-y-2">
      <label htmlFor={id} className="block text-sm font-medium text-on-surface">{label}</label>
      {multiline ? <textarea {...shared} rows={rows} className={`${inputStyle} min-h-24 resize-y`} /> : <input {...shared} type="text" />}
      {hint && <p id={`${id}-hint`} className="text-xs leading-5 text-on-surface-variant">{hint}</p>}
    </div>
  );
};

export const ReviewListField = ({ label, values, onChange, hint }: {
  label: string;
  values: string[];
  onChange: (values: string[]) => void;
  hint?: string;
}) => (
  <ReviewField
    label={label}
    value={values.join("\n")}
    onChange={(value) => onChange(value.split("\n"))}
    onBlur={() => {
      const normalized = values.map((value) => value.trim()).filter(Boolean);
      if (JSON.stringify(normalized) !== JSON.stringify(values)) onChange(normalized);
    }}
    multiline
    rows={Math.min(8, Math.max(3, values.length + 1))}
    hint={hint ?? "One item per line. Leave blank if there are no items."}
  />
);

export const ReviewSection = ({ title, description, children, action }: {
  title: string;
  description: string;
  children: ReactNode;
  action?: ReactNode;
}) => (
  <section className="rounded-2xl border border-outline-variant bg-surface-container p-5 sm:p-7">
    <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h3 className="text-lg font-semibold tracking-tight text-on-surface">{title}</h3>
        <p className="mt-1 max-w-2xl text-sm leading-6 text-on-surface-variant">{description}</p>
      </div>
      {action}
    </div>
    {children}
  </section>
);

export const ReviewButton = ({ children, onClick, label }: {
  children: ReactNode;
  onClick: () => void;
  label?: string;
}) => (
  <button
    type="button"
    onClick={onClick}
    aria-label={label}
    className="min-h-10 rounded-lg border border-outline-variant px-3 py-2 text-sm font-medium text-primary transition-colors hover:border-primary/50 hover:bg-primary/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
  >
    {children}
  </button>
);
