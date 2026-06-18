import React, { useEffect, useState } from "react";
import { Snowflake } from "lucide-react";

// 1. Type 定義
type FreezerItem = {
  id: string;
  state: "idle" | "preparing" | "running" | "finished";
  workOrder?: string;
  remainMin?: number;
};

export default function FreezeDryerCard() {
  const [items, setItems] = useState<FreezerItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // 2. 定義抓取資料的函式 (獨立出來以便重複呼叫)
    const fetchData = () => {
      fetch("/api/ops/freeze-status")
        .then(res => res.json())
        .then(data => {
          if (data?.resources) setItems(data.resources);
        })
        .catch(err => console.error("API Error:", err))
        .finally(() => setLoading(false));
    };

    // 3. 初次渲染時立即執行一次
    fetchData();

    // 4. 設定定時器：每 10000 毫秒 (10秒) 自動執行一次
    const intervalId = setInterval(fetchData, 10000);

    // 5. 重要：清理函式 (Cleanup)
    // 當使用者離開此頁面或元件被移除時，必須清除定時器，否則會在背景一直跑，導致效能問題
    return () => clearInterval(intervalId);
  }, []);

  const statusColor = (s: string) => {
    switch (s) {
      case "running": return "text-indigo-400";
      case "preparing": return "text-amber-400";
      case "finished": return "text-emerald-400";
      default: return "text-slate-400";
    }
  };

  return (
    <div className="bg-slate-800/50 backdrop-blur-md border border-slate-700/50 rounded-xl p-5 shadow-lg">
      <h3 className="text-slate-300 text-lg font-medium mb-4 flex items-center gap-2">
        <Snowflake className="text-indigo-400" size={18} />
        凍乾機狀態
        {/* 可以加一個小小的指示器，讓使用者知道它是即時的 (選用) */}
        <span className="flex h-2 w-2 relative ml-auto">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
          <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
        </span>
      </h3>

      {loading ? (
        <div className="text-slate-400 text-sm">載入中...</div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {items.map((f, index) => (
            <div
              key={f.id || index}
              className="border border-slate-700 rounded-lg p-3 bg-slate-900/40"
            >
              <div className="flex justify-between items-center">
                <span className="text-sm text-slate-200">{f.id}</span>
                <span className={`text-xs ${statusColor(f.state)}`}>
                  {f.state}
                </span>
              </div>

              <div className="text-xs text-slate-400 mt-1">
                {f.workOrder ? `工單 ${f.workOrder}` : "無工單"}
              </div>

              {f.state === "running" && f.remainMin !== undefined && f.remainMin !== null && (
                <div className="text-xs text-indigo-300 mt-1">
                  剩餘 {(f.remainMin / 60).toFixed(1)} hr
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}