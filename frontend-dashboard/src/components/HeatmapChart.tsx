import React, { useEffect, useState } from "react";
import { ResponsiveHeatMapCanvas } from "@nivo/heatmap";
import { Loader2 } from 'lucide-react';

// Heatmap API 回傳格式
interface HeatmapResponse {
  markers: string[];
  buckets: string[];
  matrix: number[][];
  mode: string;
}

// Nivo heatmap row 格式
interface HeatmapRow {
  id: string;
  data: { x: string; y: number }[];
}

interface Props {
  mode?: "week" | "month" | "quarter";
}

// ✅ 根據背景色計算文字顏色（提高對比度）
const getContrastColor = (hexColor: string): string => {
  // 將 hex 轉為 RGB
  const rgb = hexColor.match(/^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i);
  if (!rgb) return "#ffffff";
  
  const r = parseInt(rgb[1], 16);
  const g = parseInt(rgb[2], 16);
  const b = parseInt(rgb[3], 16);
  
  // 計算亮度 (YIQ formula)
  const brightness = (r * 299 + g * 587 + b * 114) / 1000;
  
  // 亮度 > 128 用深色，否則用白色
  return brightness > 128 ? "#1e293b" : "#ffffff";
};

const HeatmapChart: React.FC<Props> = ({ mode = "week" }) => {
  // ✅ API 加上 top=24 參數
  const API_BASE = import.meta.env.VITE_API_BASE ?? "";
  const API = `${API_BASE}/api/heatmap_usage?mode=${mode}&top=24`;

  const [data, setData] = useState<HeatmapRow[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);

    fetch(API)
      .then((res) => {
        if (!res.ok) {
          throw new Error(`HTTP error! status: ${res.status}`);
        }
        return res.json();
      })
      .then((res: HeatmapResponse) => {
        const { markers, buckets, matrix } = res;

        const formatted: HeatmapRow[] = markers.map(
          (marker: string, i: number) => ({
            id: marker,
            data: buckets.map((bucket: string, j: number) => ({
              x: bucket,
              y: matrix[i]?.[j] ?? 0,
            })),
          })
        );

        setData(formatted);
        setError(null);
      })
      .catch((err) => {
        console.error("Heatmap API Error:", err);
        setError("無法讀取 heatmap 資料（後端可能離線或 API 路徑設定錯誤）");
      })
      .finally(() => setLoading(false));
  }, [API, mode]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-slate-400">
        <Loader2 className="animate-spin h-12 w-12 text-blue-500 mb-4" />
        <p className="text-lg">載入藥品使用熱圖中...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-16">
        <p className="text-red-400 text-lg">❌ {error}</p>
        <button
          onClick={() => window.location.reload()}
          className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
        >
          重新載入
        </button>
      </div>
    );
  }

  if (!data.length) {
    return (
      <div className="text-center py-16 text-slate-400">
        <p className="text-lg">📊 無藥品使用資料</p>
        <p className="text-sm mt-2">請確認資料庫中有滴定排程記錄</p>
      </div>
    );
  }

  // 計算總使用量
  const totalUsage = data.reduce(
    (sum, row) => sum + row.data.reduce((s, d) => s + d.y, 0),
    0
  );

  return (
    <div className="space-y-6">
      {/* 標題與統計 */}
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-lg font-semibold text-slate-200">
            藥品（Marker）使用情況熱圖
          </h4>
          <p className="text-sm text-slate-400 mt-1">
            {mode === "week" && "按週別統計"}
            {mode === "month" && "按月份統計"}
            {mode === "quarter" && "按季度統計"}
            <span className="ml-2 text-blue-400">
              （顯示 Top {data.length} 種藥品）
            </span>
          </p>
        </div>
        <div className="text-sm text-slate-400">
          總使用次數：<span className="font-bold text-blue-400">{totalUsage}</span>
        </div>
      </div>

      {/* Nivo Heatmap */}
      <div className="bg-slate-900/50 rounded-xl p-4 border border-slate-700">
        {/* ✅ 根據 Marker 數量動態調整高度 */}
        <div style={{ height: Math.max(600, data.length * 30) }}>
          <ResponsiveHeatMapCanvas
            data={data}
            margin={{ top: 60, right: 90, bottom: 80, left: 140 }}
            colors={{
              type: "quantize",
              scheme: "reds",
              steps: 9,
            }}
            axisTop={null}
            axisRight={null}
            // ✅ Y 軸文字用白色
            axisLeft={{
              tickSize: 5,
              tickPadding: 8,
              legend: "藥品（Marker）",
              legendOffset: -100,
              legendPosition: "middle",
              // 🎨 軸文字樣式
              ticksStyle: {
                fill: "#ffffff",
                fontSize: 12,
                fontWeight: 500,
              },
              legendStyle: {
                fill: "#ffffff",
                fontSize: 14,
                fontWeight: 600,
              },
            }}
            // ✅ X 軸文字用白色
            axisBottom={{
              tickSize: 5,
              tickPadding: 8,
              tickRotation: -45,
              legend:
                mode === "week"
                  ? "週別"
                  : mode === "month"
                  ? "月份"
                  : "季度",
              legendOffset: 60,
              legendPosition: "middle",
              // 🎨 軸文字樣式
              ticksStyle: {
                fill: "#ffffff",
                fontSize: 11,
                fontWeight: 500,
              },
              legendStyle: {
                fill: "#ffffff",
                fontSize: 14,
                fontWeight: 600,
              },
            }}
            // ✅ 改進數字對比度
            cellShape={(cell: any) => {
              const textColor = getContrastColor(cell.color);
              
              return (
                <g>
                  <rect
                    x={cell.x}
                    y={cell.y}
                    width={cell.width}
                    height={cell.height}
                    fill={cell.color}
                    stroke="#1e293b"
                    strokeWidth={1.5}
                  />
                  {cell.value > 0 && (
                    <>
                      {/* 🎨 文字描邊（增強對比） */}
                      <text
                        x={cell.x + cell.width / 2}
                        y={cell.y + cell.height / 2}
                        textAnchor="middle"
                        dominantBaseline="central"
                        fill="none"
                        stroke={textColor === "#ffffff" ? "#000000" : "#ffffff"}
                        strokeWidth={3}
                        fontSize={12}
                        fontWeight="bold"
                      >
                        {cell.value}
                      </text>
                      {/* 🎨 主文字（動態顏色） */}
                      <text
                        x={cell.x + cell.width / 2}
                        y={cell.y + cell.height / 2}
                        textAnchor="middle"
                        dominantBaseline="central"
                        fill={textColor}
                        fontSize={12}
                        fontWeight="bold"
                        style={{
                          paintOrder: "stroke",
                          filter: "drop-shadow(0 1px 2px rgba(0,0,0,0.3))",
                        }}
                      >
                        {cell.value}
                      </text>
                    </>
                  )}
                </g>
              );
            }}
            // ✅ 全局主題：確保所有文字預設白色
            theme={{
              text: {
                fill: "#ffffff",
                fontSize: 12,
              },
              axis: {
                domain: {
                  line: {
                    stroke: "#64748b",
                    strokeWidth: 1,
                  },
                },
                ticks: {
                  line: {
                    stroke: "#64748b",
                    strokeWidth: 1,
                  },
                  text: {
                    fill: "#ffffff",
                    fontSize: 12,
                  },
                },
                legend: {
                  text: {
                    fill: "#ffffff",
                    fontSize: 14,
                    fontWeight: 600,
                  },
                },
              },
              tooltip: {
                container: {
                  background: "#1e293b",
                  color: "#ffffff",
                  fontSize: "13px",
                  borderRadius: "8px",
                  boxShadow: "0 4px 12px rgba(0, 0, 0, 0.4)",
                  padding: "12px 16px",
                  border: "1px solid #475569",
                },
              },
            }}
            // 🎯 自定義 Tooltip
            tooltip={({ cell }: any) => {
              const marker = cell.serieId;
              const timePeriod = cell.data.x;
              const count = cell.value;
              
              return (
                <div
                  style={{
                    background: "#1e293b",
                    color: "#ffffff",
                    padding: "12px 16px",
                    borderRadius: "8px",
                    boxShadow: "0 4px 12px rgba(0, 0, 0, 0.5)",
                    border: "1px solid #475569",
                    minWidth: "200px",
                  }}
                >
                  <div style={{ 
                    fontSize: "14px", 
                    fontWeight: "bold", 
                    marginBottom: "8px",
                    color: "#60a5fa",
                    borderBottom: "1px solid #475569",
                    paddingBottom: "6px",
                  }}>
                    📊 使用詳情
                  </div>
                  
                  <div style={{ fontSize: "13px", marginBottom: "6px" }}>
                    <span style={{ color: "#94a3b8" }}>藥品：</span>
                    <span style={{ 
                      color: "#fbbf24", 
                      fontWeight: "600",
                      marginLeft: "8px",
                    }}>
                      {marker}
                    </span>
                  </div>
                  
                  <div style={{ fontSize: "13px", marginBottom: "6px" }}>
                    <span style={{ color: "#94a3b8" }}>
                      {mode === "week" ? "週別：" : mode === "month" ? "月份：" : "季度："}
                    </span>
                    <span style={{ 
                      color: "#a78bfa", 
                      fontWeight: "500",
                      marginLeft: "8px",
                    }}>
                      {timePeriod}
                    </span>
                  </div>
                  
                  <div style={{ fontSize: "13px" }}>
                    <span style={{ color: "#94a3b8" }}>使用次數：</span>
                    <span style={{ 
                      color: count > 10 ? "#f87171" : count > 5 ? "#fb923c" : "#34d399",
                      fontWeight: "bold",
                      fontSize: "15px",
                      marginLeft: "8px",
                    }}>
                      {count}
                    </span>
                    <span style={{ color: "#94a3b8", marginLeft: "4px" }}>次</span>
                  </div>
                  
                  {count === 0 && (
                    <div style={{ 
                      marginTop: "8px", 
                      fontSize: "12px", 
                      color: "#94a3b8",
                      fontStyle: "italic",
                    }}>
                      此時段無使用記錄
                    </div>
                  )}
                </div>
              );
            }}
            layers={["cells", "axes", "legends"]}
            // ✅ 啟用滑鼠互動
            enableGridX={false}
            enableGridY={false}
          />
        </div>
      </div>

      {/* ❌ 已移除：數據說明區塊 */}

      {/* ✅ 使用排行（顯示全部 24 個） */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
        {data.map((row, index) => {
          const total = row.data.reduce((sum, d) => sum + d.y, 0);
          return (
            <div
              key={row.id}
              className="p-4 bg-slate-800/50 rounded-lg border border-slate-700 hover:bg-slate-800 transition-colors"
            >
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xs font-bold text-slate-500">#{index + 1}</span>
                <span className="text-sm font-medium text-slate-300 truncate">
                  {row.id}
                </span>
              </div>
              <div className="text-2xl font-bold text-amber-400">{total}</div>
              <div className="text-xs text-slate-500 mt-1">次使用</div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default HeatmapChart;
