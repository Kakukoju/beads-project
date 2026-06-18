import React, { useEffect, useState, useCallback } from "react";
import { Snowflake, RefreshCw, Timer, AlertCircle, ChevronDown, ChevronUp } from "lucide-react";
// 如果您的型別定義路徑不同，請自行調整，或使用下方的介面定義
import type { FreezerItem } from "@/types/ops"; 

/* =========================
 * 設定
 * ========================= */
const USE_MOCK_DATA = false;

// 預設樣式 (防止後端樣式遺失)
const DEFAULT_STYLE = {
  color: "#94a3b8", // slate-400
  bg: "#1e293b",    // slate-800
};

/* =========================
 * Helper: 時間格式化 (補零)
 * ========================= */
const formatTime = (min?: number) => {
  if (min == null) return "--";
  const h = Math.floor(min / 60);
  const m = min % 60;
  // 讓數字對齊，例如 01h 05m
  const hStr = h > 0 ? `${h}h ` : "";
  const mStr = `${m.toString().padStart(2, "0")}m`;
  return `${hStr}${mStr}`;
};

/* =========================
 * Sub-Component: 單一凍乾機卡片
 * ========================= */
const FreezeDryerItem = ({ item }: { item: FreezerItem }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  // 1. 🔥 緊急狀態判斷：Running 且剩餘時間 < 60 分鐘 (且不是已完成的負數)
  const isUrgent = item.state === "running" && 
                   item.remainMin != null && 
                   item.remainMin < 60 && 
                   item.remainMin > 0;

  // 2. 判斷是否有詳細資料可供展開
  const runningList = item.hover?.running || [];
  const nextSchedule = item.hover?.nextSchedule; 
  const hasDetails = runningList.length > 0 || !!nextSchedule;

  // 3. 安全獲取樣式
  const style = {
    color: item.style?.color || DEFAULT_STYLE.color,
    bg: item.style?.bg || DEFAULT_STYLE.bg,
    // 如果是緊急狀態，強制邊框變紅，否則用 API 給的顏色
    borderColor: isUrgent ? "#ef4444" : (item.style?.color || DEFAULT_STYLE.color),
  };

  const handleToggle = () => {
    // 只有在有資料時才允許展開
    if (hasDetails) {
      setIsExpanded(!isExpanded);
    }
  };

  return (
    <div
      // 動態 className：
      // - hasDetails: 顯示手指游標 (cursor-pointer)
      // - isUrgent: 加上閃爍動畫 (animate-pulse) 與紅色光暈
      className={`
        relative rounded-lg border transition-all duration-200
        ${hasDetails ? "cursor-pointer hover:brightness-110" : "cursor-default"}
        ${isUrgent ? "animate-pulse ring-1 ring-red-500 shadow-[0_0_15px_rgba(239,68,68,0.4)]" : ""}
      `}
      style={style}
      onClick={handleToggle}
    >
      {/* === 卡片主體 === */}
      <div className="p-3">
        {/* Header: 機台 ID 與狀態 */}
        <div className="flex justify-between items-center mb-2">
          <span className="font-bold text-sm tracking-wide flex items-center gap-1">
            {item.id}
            {/* 箭頭指示：若無資料則變淡並顯示紅色以供識別 */}
            <span className={hasDetails ? "opacity-80" : "opacity-30 text-red-400"}>
              {isExpanded ? <ChevronUp size={14}/> : <ChevronDown size={14}/>}
            </span>
          </span>
          <span className="text-[10px] px-2 py-0.5 border rounded font-bold uppercase bg-black/20">
            {item.state}
          </span>
        </div>

        {/* Body: 目前工單 */}
        <div className="text-xs flex flex-col gap-1 mb-1">
          <div className="flex justify-between">
            <span className="opacity-70">目前工單</span>
            <span className="font-mono font-medium truncate max-w-[100px]" title={item.workOrder || ""}>
              {item.workOrder || "N/A"}
            </span>
          </div>
        </div>

        {/* Footer: 剩餘時間 (Running 狀態才顯示) */}
        {item.state === "running" && item.remainMin != null && (
          <div className="mt-2 pt-2 border-t border-white/20 text-xs flex justify-between items-center">
            <span className="flex items-center gap-1 opacity-80">
              <Timer size={12} /> 剩餘
            </span>
            {/* 如果 < 1小時，文字也變紅加強提示 */}
            <span className={`font-mono font-bold ${item.remainMin < 60 ? 'text-red-400' : ''}`}>
              {formatTime(item.remainMin)}
            </span>
          </div>
        )}
      </div>

      {/* === 展開區域 (下拉選單效果) === */}
      {isExpanded && (
        <div className="px-3 pb-3 pt-2 text-xs border-t border-white/20 bg-black/10 rounded-b-lg">
          
          {/* A. 進行中批次 (當 state=running 時顯示同伴) */}
          {runningList.length > 0 && (
            <div className="mb-2">
              <div className="font-bold opacity-80 mb-1 flex items-center gap-1">
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-400"/>
                進行中批次
              </div>
              <ul className="space-y-1 font-mono pl-3 opacity-90 border-l border-white/10 ml-0.5">
                {runningList.map((wo, idx) => (
                  <li key={`${wo}-${idx}`} className="break-all pl-1">• {wo}</li>
                ))}
              </ul>
            </div>
          )}

          {/* B. 下一輪預排 (當 state=idle 時顯示排程) */}
          {nextSchedule && (
            <div>
              <div className="font-bold opacity-80 mb-1 flex items-center gap-1">
                 <div className="w-1.5 h-1.5 rounded-full bg-amber-400"/>
                 預排 ({nextSchedule.date})
              </div>
              <ul className="space-y-1 font-mono pl-3 opacity-90 border-l border-white/10 ml-0.5">
                {nextSchedule.workOrders.map((wo, idx) => (
                  <li key={`${wo}-${idx}`} className="break-all pl-1">• {wo}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

/* =========================
 * Main Component: 凍乾機監控主畫面
 * ========================= */
export default function FreezeDryerCard() {
  const [items, setItems] = useState<FreezerItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchData = useCallback(async () => {
    if (USE_MOCK_DATA) {
      setLoading(false);
      return;
    }

    try {
      const res = await fetch("/api/ops/freeze-status");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data = await res.json();
      const resources: FreezerItem[] = data.resources || [];

      // 排序: 依 ID 排序
      setItems(resources.sort((a, b) => a.id.localeCompare(b.id)));
      setError(false);
      setLastUpdated(new Date());
    } catch (e) {
      console.error("freeze-status error:", e);
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  // 自動刷新: 每 10 秒
  useEffect(() => {
    fetchData();
    const t = setInterval(fetchData, 10000);
    return () => clearInterval(t);
  }, [fetchData]);

  return (
    <div className="bg-slate-900/80 backdrop-blur-xl border border-slate-700/50 rounded-xl p-5 shadow-2xl flex flex-col h-full w-full">
      {/* Header */}
      <div className="flex justify-between items-center mb-4 shrink-0">
        <h3 className="text-slate-100 text-lg font-bold flex items-center gap-2">
          <Snowflake className="text-blue-400" size={20} />
          凍乾機狀態監控
        </h3>

        <div className="flex items-center gap-3">
          {error && (
            <div className="flex items-center gap-1 text-red-400 text-xs animate-pulse">
              <AlertCircle size={12} />
              <span>連線異常</span>
            </div>
          )}
          
          <button 
            onClick={fetchData} 
            className="text-slate-500 hover:text-white transition-colors p-1 rounded-full hover:bg-slate-800"
            title={lastUpdated ? `最後更新: ${lastUpdated.toLocaleTimeString()}` : "更新"}
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
          
          <span className={`text-[10px] font-mono border px-1.5 py-0.5 rounded ${
              error ? "text-red-400 border-red-900/50 bg-red-900/20" : "text-emerald-400 border-emerald-900/50 bg-emerald-900/20"
            }`}>
            {error ? "OFFLINE" : "ONLINE"}
          </span>
        </div>
      </div>

      {/* Grid Content */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 flex-1 overflow-y-auto pr-1 custom-scrollbar">
        {items.length === 0 && !loading && !error && (
            <div className="col-span-full text-center text-slate-500 py-10">
                無機台資料
            </div>
        )}
        
        {items.map((item) => (
          <FreezeDryerItem key={item.id} item={item} />
        ))}
      </div>
    </div>
  );
}