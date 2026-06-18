// src/main.tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom"; // ✅ 加入 Router
import "./index.css";
import App from "@/App"; // ✅ 路徑別名

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {/* ✅ 外層包 BrowserRouter，讓 useNavigate()、Routes、Route 都能運作 */}
    <BrowserRouter basename="/wo">
      <App />
    </BrowserRouter>
  </StrictMode>
);
