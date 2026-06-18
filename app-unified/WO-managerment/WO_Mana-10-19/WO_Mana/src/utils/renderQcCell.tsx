// src/utils/renderQcCell.tsx
import React from "react";
import type { WorkOrderData } from "@/types";

/**
 * 共用：QC 單一儲存格渲染
 * - 顯示 ✅ / ❌ / ⚠️ 與數值
 * - 若無 QC，僅顯示 ⚠️ 與數值（或 -）
 */
export const renderQcCell = (
  data: WorkOrderData,
  label: string,
  key: keyof WorkOrderData["qcCheckResult"],
  value: number | undefined,
  digits = 4
) => {
  const qc = data.qcCheckResult?.[key];
  const pass = qc?.pass;
  const range = qc?.qc_range ?? null;
  const color =
    pass === true ? "green" : pass === false ? "red" : "gray";
  const symbol = pass === true ? "✅" : pass === false ? "❌" : "⚠️";

  const n =
    typeof value === "number" && Number.isFinite(value)
      ? value.toFixed(digits)
      : "-";

  return (
    <td
      key={key}
      style={{
        color,
        fontWeight: 500,
        textAlign: "center",
        padding: "4px 6px",
      }}
    >
      {symbol} {n}
      {range && (
        <div style={{ fontSize: "11px", color: "#666" }}>({range})</div>
      )}
    </td>
  );
};
