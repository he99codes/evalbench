import { Outlet } from "react-router";

import { AppShell } from "../components/layout/AppShell.tsx";

/** Root layout: every page renders inside the AppShell (sidebar + header). */
export function App() {
  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}
