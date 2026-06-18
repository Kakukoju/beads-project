// vite.config.ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  base: "/wo/",
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'), // ✅ 這行是讓 @ 指向 src
    },
  },
   server: {
    host: "0.0.0.0",  // 可改成 "0.0.0.0" 讓區網其他裝置也能訪問
    port: 8056,         // 🔧 固定 port，不再隨機
    open: true,         // 啟動時自動開啟瀏覽器
  },
});

