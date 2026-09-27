/** Presentation helpers only: formatting and styling. No evaluation logic. */

export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return dateFormatter.format(new Date(iso));
}

/** Scores arrive from the API already computed (0-100); this only formats them. */
export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${value.toFixed(digits)}%`;
}

export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return "—";
  return Number.isInteger(value) ? String(value) : value.toFixed(digits);
}

export const inputClass =
  "block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm " +
  "placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200 " +
  "aria-[invalid=true]:border-red-400";

export const labelClass = "mb-1 block text-sm font-medium text-slate-700";

export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "Something went wrong";
}

export type Tone = "neutral" | "info" | "success" | "warning" | "danger";

export const statusTone: Record<string, Tone> = {
  DRAFT: "neutral",
  READY: "info",
  PENDING: "info",
  RUNNING: "warning",
  COMPLETED: "success",
  FAILED: "danger",
};
