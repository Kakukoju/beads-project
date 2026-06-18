import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],

  // 🟦 讓 Recharts 正確預編譯以避免 HMR 慢 / 圖表壞掉
  optimizeDeps: {
    include: ['recharts']
  },

  server: {
    host: true,         // 🟢 允許網內其他裝置存取
    port: 5174,         // 🟢 固定使用 5174
    strictPort: true,   // 🟢 port 被占用時會報錯，避免自動跳轉
    allowedHosts: ['tons-stating-modular-attempting.trycloudflare.com'],
    cors: true,         // 🟢 開啟 CORS 以利 iframe 嵌入

    proxy: {
      // === 1. Ops / Abnormal / Mobile (5100) ===
      "/api/ops": { target: "http://127.0.0.1:5100", changeOrigin: true },
      "/api/latest_abnormal": { target: "http://127.0.0.1:5100", changeOrigin: true },
      "/api/today_abnormals": { target: "http://127.0.0.1:5100", changeOrigin: true },
      "/api/resolve_abnormal": { target: "http://127.0.0.1:5100", changeOrigin: true },
      "/api/abnormal_record": { target: "http://127.0.0.1:5100", changeOrigin: true },
      "/api/abnormal_top5": { target: "http://127.0.0.1:5100", changeOrigin: true },
      "/api/mobile": { target: "http://127.0.0.1:5100", changeOrigin: true },
      "/photos": { target: "http://127.0.0.1:5100", changeOrigin: true },
      "/api/titration": { target: "http://127.0.0.1:5100", changeOrigin: true },

      // === 2. Droplet / Titration Condition (5011) python "D:\OneDrive - 天亮醫療器材股份有限公司\.vscode\Beads配藥\app_unified128.py" ===
      "/api/droplet-records": { target: "http://127.0.0.1:5011", changeOrigin: true },
      "OPTIONS /api/update_571_table": { target: "http://127.0.0.1:5011", changeOrigin: true },

      // === 3. Schedule / UI / WIP (8505): python "D:\OneDrive - 天亮醫療器材股份有限公司\.vscode\Bead_auto_update_schedule\beads_unified_server_V14.py"===
      // 統一改用 127.0.0.1 確保 Windows 解析正確
      "/api/schedule": { target: "http://127.0.0.1:8505", changeOrigin: true },
      "/api/forms": { target: "http://127.0.0.1:8505", changeOrigin: true },
      "/api/run": { target: "http://127.0.0.1:8505", changeOrigin: true },
      "/api/cancel": { target: "http://127.0.0.1:8505", changeOrigin: true },
      "/api/test": { target: "http://127.0.0.1:8505", changeOrigin: true },
      "/api/health": { target: "http://127.0.0.1:8505", changeOrigin: true },
      "/api/open-file": { target: "http://127.0.0.1:8505", changeOrigin: true },
      "/api/excel-deeplink": { target: "http://127.0.0.1:8505", changeOrigin: true },
      "/api/pick-file": { target: "http://127.0.0.1:8505", changeOrigin: true },
      "/api/vba-sync": { target: "http://127.0.0.1:8505", changeOrigin: true },
      "/api/workorder": { target: "http://127.0.0.1:8505", changeOrigin: true },
      "/api/beads-ipqc": { target: "http://127.0.0.1:8505", changeOrigin: true },
      "/api/dashboard": { target: "http://127.0.0.1:8505", changeOrigin: true },
      "/api/years": { target: "http://127.0.0.1:8505", changeOrigin: true },
      "/api/options": { target: "http://127.0.0.1:8505", changeOrigin: true },
      "/api/qc_table": { target: "http://127.0.0.1:8505", changeOrigin: true },
      "/api/wip": { target: "http://127.0.0.1:8505", changeOrigin: true },
      "/wip": { target: "http://127.0.0.1:8505", changeOrigin: true }
    },
  },
});