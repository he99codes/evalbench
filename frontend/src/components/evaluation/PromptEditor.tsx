import type { UseFormRegisterReturn } from "react-hook-form";

import { cn, inputClass, labelClass } from "../../lib/utils.ts";

export function PromptEditor({
  registration,
  error,
  length,
}: {
  registration: UseFormRegisterReturn;
  error?: string;
  length?: number;
}) {
  const id = "prompt-editor";
  return (
    <div>
      <label htmlFor={id} className={labelClass}>
        Prompt
      </label>
      <p id={`${id}-hint`} className="mb-2 text-xs text-slate-500">
        The instruction both responses were written for. Requests and constraints are extracted from it.
      </p>
      <textarea
        id={id}
        rows={6}
        aria-invalid={Boolean(error)}
        aria-describedby={cn(`${id}-hint`, error && `${id}-error`)}
        className={cn(inputClass, "font-mono")}
        {...registration}
      />
      <div className="mt-1 flex justify-between text-xs">
        <span id={`${id}-error`} className="text-red-700">
          {error}
        </span>
        {length !== undefined && <span className="text-slate-400">{length} characters</span>}
      </div>
    </div>
  );
}
