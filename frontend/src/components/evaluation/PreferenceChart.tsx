import type { ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ProjectAnalytics } from "../../types/project.ts";

function ChartCard({ title, summary, children }: { title: string; summary: string; children: ReactNode }) {
  return (
    <figure className="rounded-lg border border-slate-200 p-4">
      <figcaption className="mb-1 text-sm font-semibold text-slate-700">{title}</figcaption>
      <p className="sr-only">{summary}</p>
      <div aria-hidden="true" className="h-64">
        {children}
      </div>
    </figure>
  );
}

/** A vs B (vs tie) preferences per completion day, stacked. */
export function PreferenceOverTimeChart({ analytics }: { analytics: ProjectAnalytics }) {
  const data = analytics.preference_over_time;
  const summary = data.map((d) => `${d.date}: A ${d.A}, B ${d.B}, tie ${d.TIE}`).join("; ");
  return (
    <ChartCard title="Preference over time" summary={summary || "No completed evaluations yet."}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="date" tick={{ fontSize: 12 }} />
          <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
          <Tooltip />
          <Legend />
          <Bar dataKey="A" name="Response A" stackId="p" fill="#6366f1" />
          <Bar dataKey="B" name="Response B" stackId="p" fill="#14b8a6" />
          <Bar dataKey="TIE" name="Tie" stackId="p" fill="#94a3b8" />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

/** Pass rate per criterion across all scored responses (latest run of each evaluation). */
export function CriterionPassRateChart({ analytics }: { analytics: ProjectAnalytics }) {
  const data = analytics.criteria.map((c) => ({ name: c.name, pass_rate: c.pass_rate }));
  const summary = data.map((d) => `${d.name}: ${d.pass_rate}% pass`).join("; ");
  return (
    <ChartCard title="Criterion pass rate" summary={summary || "No scored criteria yet."}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 8, right: 16, left: 40, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis type="number" domain={[0, 100]} unit="%" tick={{ fontSize: 12 }} />
          <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 12 }} />
          <Tooltip formatter={(v) => `${v}%`} />
          <Bar dataKey="pass_rate" name="Pass rate" fill="#6366f1" />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
