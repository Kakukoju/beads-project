// src/config.ts
// 🧩 全域設定檔 — 定義 Flask API 伺服器位置

const LOCAL_IP = "10.6.182.47"; // ⚠️ ← Flask 主機的 IPv4
const LOCAL_PORT = 5012;

// ✅ 固定使用區網位址（讓別台裝置能連）
export const API_BASE = `http://${LOCAL_IP}:${LOCAL_PORT}/api`;

export const DEFAULT_HEADERS = {
  "Content-Type": "application/json",
};
