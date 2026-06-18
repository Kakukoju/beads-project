// src/components/BufferBaseTable.tsx
// ✅ 最小改動版本：只添加 printMode 支援
import React from "react";
import type { BufferBaseInfo, QcRanges, QcCheckResult } from "@/types";

type Props = {
  data?: BufferBaseInfo;
  qcRanges?: QcRanges;
  qcCheckResult?: QcCheckResult;
  digits?: number;
  printMode?: boolean; // ✅ 添加此行
};

export const BufferBaseTable: React.FC<Props> = ({
  data,
  qcRanges,
  qcCheckResult,
  digits = 4,
  printMode = false, // ✅ 添加此行（默認為 false）
}) => {
  if (!data)
    return (
      <p className="text-gray-500 text-sm italic mt-2">
        無 Buffer/Base 資料
      </p>
    );

  /** ✅ 數值格式化 */
  const fmt = (v?: string | number | null) => {
    const n =
      typeof v === "string"
        ? parseFloat(v)
        : typeof v === "number"
        ? v
        : NaN;
    return !isNaN(n) && Number.isFinite(n) ? n.toFixed(digits) : "-";
  };

  /** ✅ 欄位配置 (key 與 Flask 一致) */
  const fields = [
    { label: "L1 反應 OD", key: "L1OD", qcKey: "L1-OD" },
    { label: "L2 反應 OD", key: "L2OD", qcKey: "L2-OD" },
    { label: "L1 起始 OD", key: "L1StartOD", qcKey: "L1-起始OD" },
    { label: "L2 起始 OD", key: "L2StartOD", qcKey: "L2-起始OD" },
  ] as const;

  /** ✅ 與 InterfaceView 完全同步的 QC 格式顯示 */
  const renderQcCell = (
    key: keyof QcCheckResult,
    value: number
  ) => {
    const qc = qcCheckResult?.[key];
    const pass = qc?.pass;

    const color =
      pass === true ? "green" : pass === false ? "red" : "gray";
    const symbol =
      pass === true ? "✅" : pass === false ? "❌" : "⚠️";

    // ✅ 根據 printMode 使用不同樣式
    if (printMode) {
      return (
        <td
          key={String(key)}
          style={{
            border: "1px solid #333",
            padding: "4px 6px",
            textAlign: "center",
            color,
            fontWeight: 500,
          }}
        >
          {symbol} {fmt(value)}
        </td>
      );
    }

    return (
      <td
        key={String(key)}
        className="border px-4 py-2 text-center font-mono"
        style={{ color, fontWeight: 500 }}
      >
        {symbol} {fmt(value)}
      </td>
    );
  };

  /** ✅ 判定是否有不通過 */
  const hasQcFail =
    qcCheckResult &&
    Object.values(qcCheckResult).some((r) => r.pass === false);

  /** ✅ QC 範圍說明文字 */
  const rangeLine = [
    `L1-OD: ${qcRanges?.["L1-OD"] ?? "—"}`,
    `L2-OD: ${qcRanges?.["L2-OD"] ?? "—"}`,
    `L1-起始OD: ${qcRanges?.["L1-起始OD"] ?? "—"}`,
    `L2-起始OD: ${qcRanges?.["L2-起始OD"] ?? "—"}`,
  ].join("　");

  // ✅ 列印模式使用簡化樣式
  if (printMode) {
    return (
      <div className="w-full">
        {/* QC 範圍說明 */}
        <p style={{ fontSize: "11px", color: "#666", margin: "4px 0" }}>
          QC 標準範圍：{rangeLine}
        </p>

        {/* 主表格 - 使用與工單一致的樣式 */}
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            margin: "6px 0",
            fontSize: "13px",
          }}
        >
          <thead>
            <tr>
              {fields.map((f) => (
                <th
                  key={f.key}
                  style={{
                    border: "1px solid #333",
                    padding: "4px 6px",
                    textAlign: "center",
                    backgroundColor: "#f8f8f8",
                    fontWeight: "bold",
                  }}
                >
                  {f.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              {fields.map((f) =>
                renderQcCell(
                  f.key as keyof QcCheckResult,
                  data[f.key as keyof BufferBaseInfo] as number
                )
              )}
            </tr>
          </tbody>
        </table>

        {/* ⚠️ 警示訊息 */}
        {hasQcFail && (
          <p
            style={{
              marginTop: "8px",
              color: "red",
              fontWeight: "bold",
              fontSize: "12px",
            }}
          >
            ⚠️ OD 超出 QC 範圍，請複查！
          </p>
        )}
      </div>
    );
  }

  // ✅ 正常顯示模式（原有的 Tailwind 樣式）
  return (
    <div className="w-full mt-8">
      <h3 className="text-lg font-semibold mb-2 text-gray-800">
        試劑 OD
      </h3>

      {/* ✅ 顯示 QC 標準範圍 */}
      <p className="text-sm text-gray-600 mb-2">
        QC 標準範圍：{rangeLine}
      </p>

      {/* ✅ 主表格 */}
      <div className="overflow-x-auto border rounded-lg shadow bg-white">
        <table className="min-w-full border-collapse text-sm text-gray-800">
          <thead className="bg-gray-100">
            <tr>
              {fields.map((f) => (
                <th
                  key={f.key}
                  className="border px-4 py-2 text-center font-semibold"
                >
                  {f.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr className="even:bg-gray-50 text-center">
              {fields.map((f) =>
                renderQcCell(
                  f.key as keyof QcCheckResult,
                  data[f.key as keyof BufferBaseInfo] as number
                )
              )}
            </tr>
          </tbody>
        </table>
      </div>

      {/* ⚠️ 警示訊息 */}
      {hasQcFail && (
        <p className="mt-3 text-red-600 font-semibold text-sm flex items-center gap-1">
          ⚠️ OD 超出 QC 範圍，請複查！
        </p>
      )}
    </div>
  );
};
