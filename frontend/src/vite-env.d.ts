/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Browser-visible API base URL. Never put secrets in VITE_* variables. */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
