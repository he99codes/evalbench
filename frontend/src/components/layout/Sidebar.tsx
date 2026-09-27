import { NavLink } from "react-router";

import { cn } from "../../lib/utils.ts";

const links = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/evaluations/new", label: "New evaluation" },
  { to: "/criteria", label: "Criteria" },
  { to: "/settings", label: "Settings" },
];

export function Sidebar() {
  return (
    <nav aria-label="Main" className="border-b border-slate-200 bg-slate-50 md:w-56 md:border-r md:border-b-0">
      <div className="px-5 py-4">
        <NavLink to="/dashboard" className="text-lg font-semibold text-slate-900">
          EvalBench
        </NavLink>
        <p className="text-xs text-slate-500">Response evaluation workbench</p>
      </div>
      <ul className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-col md:pb-0">
        {links.map((link) => (
          <li key={link.to}>
            <NavLink
              to={link.to}
              end={link.to === "/evaluations/new"}
              className={({ isActive }) =>
                cn(
                  "block whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium",
                  "focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500",
                  isActive ? "bg-indigo-100 text-indigo-900" : "text-slate-700 hover:bg-slate-100",
                )
              }
            >
              {link.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
