import type { UseFormRegisterReturn } from "react-hook-form";

import { cn, inputClass, labelClass } from "../../lib/utils.ts";

export function ResponseEditor({
  label,
  registration,
  error,
}: {
  label: "A" | "B";
  registration: UseFormRegisterReturn;
  error?: string;
}) {
  const id = `response-${label.toLowerCase()}-editor`;
  return (
    <div>
      <label htmlFor={id} className={labelClass}>
        Response {label}
      </label>
      <textarea
        id={id}
        rows={12}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? `${id}-error` : undefined}
        className={cn(inputClass, "font-mono")}
        {...registration}
      />
      {error && (
        <p id={`${id}-error`} className="mt-1 text-xs text-red-700">
          {error}
        </p>
      )}
    </div>
  );
}
