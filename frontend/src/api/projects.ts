import type { Project, ProjectAnalytics, ProjectInput } from "../types/project.ts";
import { apiRequest } from "./client.ts";

export const projectsApi = {
  list: () => apiRequest<Project[]>("/projects"),
  get: (id: string) => apiRequest<Project>(`/projects/${id}`),
  create: (input: ProjectInput) => apiRequest<Project>("/projects", { method: "POST", body: input }),
  update: (id: string, input: Partial<ProjectInput>) =>
    apiRequest<Project>(`/projects/${id}`, { method: "PATCH", body: input }),
  remove: (id: string) => apiRequest<void>(`/projects/${id}`, { method: "DELETE" }),
  analytics: (id: string) => apiRequest<ProjectAnalytics>(`/projects/${id}/analytics`),
};
