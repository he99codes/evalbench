import { createBrowserRouter, Navigate } from "react-router";

import { EmptyState } from "../components/common/EmptyState.tsx";
import Criteria from "../pages/Criteria.tsx";
import Dashboard from "../pages/Dashboard.tsx";
import EvaluationDetail from "../pages/EvaluationDetail.tsx";
import NewEvaluation from "../pages/NewEvaluation.tsx";
import Settings from "../pages/Settings.tsx";
import { App } from "./App.tsx";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      { path: "dashboard", element: <Dashboard /> },
      { path: "evaluations/new", element: <NewEvaluation /> },
      { path: "evaluations/:id", element: <EvaluationDetail /> },
      { path: "projects/:id", element: <Criteria /> },
      { path: "criteria", element: <Criteria /> },
      { path: "settings", element: <Settings /> },
      { path: "*", element: <EmptyState title="Page not found" /> },
    ],
  },
]);
