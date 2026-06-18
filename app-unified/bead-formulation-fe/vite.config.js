// vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: [
            // 先匹配更長的 "@/components"、"@/lib"
            { find: "@/components", replacement: path.resolve(__dirname, "components") },
            { find: "@/lib", replacement: path.resolve(__dirname, "lib") },
            // 最後才放 "@"
            { find: "@", replacement: path.resolve(__dirname, "src") },
        ],
    },
    server: {
        host: true, // 允許同網段裝置存取
        port: 5173, // 想改埠號可改這裡
        proxy: {
            "/api": {
                target: "http://localhost:8055", //  Flask 位址
                changeOrigin: true,
            },
        },
    },
});
