/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_BACKEND_BASE_URL?: string;
  readonly VITE_USE_MOCK_API?: "true" | "false";
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
