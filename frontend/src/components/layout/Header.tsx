import { useQuery } from "@tanstack/react-query";

import { getHealth } from "../../api/client.ts";
import { cn } from "../../lib/utils.ts";

/** Top bar: shows live backend/database health reported by GET /health. */
export function Header() {
  const health = useQuery({ queryKey: ["health"], queryFn: getHealth, refetchInterval: 30_000 });

  let label = "Checking backend…";
  let dot = "bg-slate-400";
  if (health.isError) {
    label = "Backend unreachable";
    dot = "bg-red-500";
  } else if (health.data) {
    const ok = health.data.status === "ok";
    label = ok ? "Backend healthy · database connected" : `Database ${health.data.database}`;
    dot = ok ? "bg-emerald-500" : "bg-amber-500";
  }

  return (
    <header className="flex items-center justify-end gap-4 border-b border-slate-200 bg-white px-6 py-3">
      {health.data?.llm_provider && (
        <span className="text-xs text-slate-500">
          Evaluator: <span className="font-mono">{health.data.llm_provider}</span>
          {health.data.llm_model && <span className="font-mono"> / {health.data.llm_model}</span>}
        </span>
      )}
      <span role="status" aria-live="polite" className="flex items-center gap-2 text-xs text-slate-600">
        <span aria-hidden="true" className={cn("h-2 w-2 rounded-full", dot)} />
        {label}
      </span>
    </header>
  );
}
