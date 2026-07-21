import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// 빌드 모드의 프런트엔드 환경을 로드하고 배포 가능한 모드의 API URL을 검증한다.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  if (["test", "production"].includes(mode) && !env.VITE_BACKEND_BASE_URL) {
    throw new Error(`VITE_BACKEND_BASE_URL is required for the ${mode} frontend build`);
  }
  return {
    plugins: [react()],
    server: {
      port: 5173,
    },
  };
});
