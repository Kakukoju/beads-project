// src/pages/PrintView.tsx
import React, { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { InterfaceView } from "@/components/InterfaceView";
import type { WorkOrderData } from "@/types";

export const PrintView: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const data = location.state as WorkOrderData | undefined;

  useEffect(() => {
    if (!data) return;
    // ✅ 小延遲，確保內容渲染完成再列印
    const t = setTimeout(() => {
      window.print();
      // ✅ 列印結束後返回首頁
      setTimeout(() => navigate(-1), 800);
    }, 800);
    return () => clearTimeout(t);
  }, [data, navigate]);

  if (!data)
    return (
      <div style={{ textAlign: "center", marginTop: "40vh" }}>
        ❌ 沒有可列印資料
      </div>
    );

  return (
    <div
      style={{
        background: "white",       // ✅ 改白底
        width: "210mm",            // ✅ 固定 A4 寬度
        margin: "0 auto",
        padding: 0,                // ✅ 移除外層 padding，避免超高
        display: "block",
        overflow: "hidden",
      }}
    >
      <InterfaceView data={data} />
    </div>
  );
};
