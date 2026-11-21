import { formatDateTime, formatRelative, formatUtc } from "../../utils/format";
import { TONES } from "../../utils/status";

export function Badge({ tone = "slate", children, title }) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${TONES[tone] ?? TONES.slate}`}
    >
      {children}
    </span>
  );
}

export function Card({ title, actions, children, className = "" }) {
  return (
    <section className={`rounded-xl bg-white shadow-sm ring-1 ring-slate-200 ${className}`}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-800">{title}</h2>
          {actions}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

const BUTTON = {
  primary: "bg-sky-600 text-white hover:bg-sky-700 disabled:bg-sky-300",
  secondary: "bg-white text-slate-700 ring-1 ring-slate-300 hover:bg-slate-50 disabled:text-slate-400",
  danger: "bg-red-600 text-white hover:bg-red-700 disabled:bg-red-300",
};

export function Button({ variant = "primary", className = "", ...props }) {
  return (
    <button
      type="button"
      className={`inline-flex items-center justify-center gap-1 rounded-lg px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed ${BUTTON[variant]} ${className}`}
      {...props}
    />
  );
}

export function Field({ label, hint, children }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium text-slate-700">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}

const INPUT =
  "w-full rounded-lg border-0 bg-white px-3 py-1.5 text-sm ring-1 ring-slate-300 focus:ring-2 focus:ring-sky-500 focus:outline-none";

export function Input(props) {
  return <input className={INPUT} {...props} />;
}

export function Select({ children, ...props }) {
  return (
    <select className={INPUT} {...props}>
      {children}
    </select>
  );
}

export function ErrorBox({ error }) {
  if (!error) return null;
  return (
    <div role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800 ring-1 ring-red-200">
      {error.message ?? String(error)}
    </div>
  );
}

export function Spinner({ label = "Cargando…" }) {
  return (
    <div className="flex items-center gap-2 text-sm text-slate-500">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-sky-600" />
      {label}
    </div>
  );
}

export function Empty({ children }) {
  return <p className="py-6 text-center text-sm text-slate-500">{children}</p>;
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
        {subtitle && <p className="text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions}
    </div>
  );
}

/** Fecha local con la hora UTC exacta en el tooltip; opcionalmente "hace X". */
export function TimeText({ iso, now, relative = false }) {
  if (!iso) return <span className="text-slate-400">—</span>;
  return (
    <time dateTime={iso} title={formatUtc(iso)}>
      {relative ? formatRelative(iso, now) : formatDateTime(iso)}
    </time>
  );
}
