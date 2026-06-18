import React, { useState, useEffect } from "react";
import { Loader2 } from "lucide-react";
import { Card } from "./ui/Card";
import { CircleProgress } from "./CircleProgress";
import LowYieldModal from "./LowYieldModal";
import { normalizePercent } from "./utils/percent";

/* =======================
 * 型別定義
 * ======================= */

// 用於 UI 列表渲染的項目
interface YieldItem {
  label: string;
  value: number; // 百分比數值 (0-100)
  total?: number; // 批數 (可選，新 API 若未回傳則不顯示)
  color: string;
}

// 後端 /api/wip/yield-period-stats 回傳的資料結構
interface YieldPeriodData {
  ref_date: string;
  weekly_yield: number;
  monthly_yield: number;
  quarterly_yield: number;
}

// 左側列表的狀態
interface YieldListState {
  ok: boolean;
  items: YieldItem[];
  refDate?: string; // 新增：基準日
  has_low_yield_alert?: boolean;
}

/** 右側圓環專用 */
interface OverallWipYield {
  percent: number;
  baseDate: string | null;
}

/* =======================
 * Component
 * ======================= */

const BeadsYield: React.FC = () => {
  /** 左側列表 (周/月/季 量產良率) */
  const [stats, setStats] = useState<YieldListState>({
    ok: true,
    items: [],
  });

  /** 右側圓環 (入庫總良率) */
  const [overall, setOverall] = useState<OverallWipYield>({
    percent: 0,
    baseDate: null,
  });

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  /** ⭐ 同步狀態（關鍵） */
  const [syncing, setSyncing] = useState(false);

  /* =======================
   * 左側：取得 周/月/季 量產良率
   * API: /api/wip/yield-period-stats
   * ======================= */
  const fetchStats = async () => {
    try {
      // 修改：呼叫新的 API
      const res = await fetch("/api/wip/yield-period-stats");
      const json = await res.json();

      if (json?.success) {
        const data = json.data as YieldPeriodData;
        
        // 將後端數據轉換為 UI 列表格式
        const mappedItems: YieldItem[] = [
          {
            label: "周良率 (7天)",
            value: data.weekly_yield * 100,
            color: "bg-blue-500",
          },
          {
            label: "月良率 (4周)",
            value: data.monthly_yield * 100,
            color: "bg-emerald-500",
          },
          {
            label: "季良率 (12周)",
            value: data.quarterly_yield * 100,
            color: "bg-violet-500",
          }
        ];

        setStats({
          ok: true,
          items: mappedItems,
          refDate: data.ref_date,
          // 如果新 API 沒回傳 alert 狀態，這裡暫設 false 或保留擴充
          has_low_yield_alert: false, 
        });
      } else {
        // 若 API 失敗但不影響整體，僅記錄錯誤
        console.warn("取得量產良率失敗:", json?.error);
        setStats(prev => ({ ...prev, ok: false }));
      }
    } catch (err) {
      console.error("連線後端失敗", err);
      setError("連線後端失敗");
    }
  };

  /* =======================
   * 右側：整體 WIP Yield (圓環)
   * API: /api/wip/yield-overall-tmr
   * ======================= */
  const fetchOverall = async () => {
    try {
      const res = await fetch("/api/wip/yield-overall-tmr");
      const data = await res.json();

      if (data?.success) {
        setOverall({
          percent: normalizePercent(data.overall_yield),
          baseDate: data.base_date ?? null,
        });
      }
    } catch (err) {
      console.error("fetch overall wip yield failed", err);
    }
  };

  /* =======================
   * ⭐ 手動同步
   * ======================= */
  const handleManualSync = async () => {
    if (syncing) return;

    try {
      setSyncing(true);

      const res = await fetch("/api/wip/sync", {
        method: "POST",
      });
      const data = await res.json();

      if (!res.ok || data?.status !== "success") {
        console.error("manual sync failed", data);
        return;
      }

      // 同步完成後刷新兩邊數據
      await Promise.all([fetchStats(), fetchOverall()]);
    } catch (err) {
      console.error("manual sync error", err);
    } finally {
      setSyncing(false);
    }
  };

  /* =======================
   * 初始 & 定時刷新
   * ======================= */
  useEffect(() => {
    setLoading(true);

    Promise.all([fetchStats(), fetchOverall()])
      .catch(() => setError("載入資料失敗"))
      .finally(() => setLoading(false));

    // 每 2 小時刷新一次
    const interval = setInterval(() => {
      fetchStats();
      fetchOverall();
    }, 7200000);

    return () => clearInterval(interval);
  }, []);

  /* =======================
   * Render
   * ======================= */

  return (
    <Card
      title={
        <div className="flex items-center justify-between w-full">
          <span>Beads 量產良率趨勢</span>

          {/* ⭐ 手動同步按鈕 */}
          <button
            onClick={handleManualSync}
            disabled={syncing}
            className={`text-xs px-2 py-1 rounded border transition
              ${
                syncing
                  ? "border-slate-600 text-slate-500 cursor-not-allowed"
                  : "border-slate-500 text-slate-300 hover:bg-slate-700"
              }`}
          >
            {syncing ? "同步中…" : "立即同步"}
          </button>
        </div>
      }
      className="h-64 relative"
    >
      {loading ? (
        <div className="flex flex-col items-center justify-center h-full text-slate-400">
          <Loader2 className="animate-spin h-6 w-6 mb-2" />
          載入中...
        </div>
      ) : error ? (
        <div className="text-red-400 text-center py-10">{error}</div>
      ) : (
        <div className="flex items-center gap-4 h-full">
          {/* 左側：周/月/季 良率列表 */}
          <div className="flex-1 space-y-4">
             {/* 顯示基準日提示 */}
             {stats.refDate && (
                <div className="text-[10px] text-slate-500 text-right mb-[-8px]">
                  基準日: {stats.refDate} (往前推7天)
                </div>
             )}

            {stats.items.map((item, idx) => (
              <div key={idx}>
                <div className="flex justify-between text-xs text-slate-400 mb-1">
                  <span>
                    {item.label}
                    {/* 只有當 total 存在且大於 0 時才顯示批數 */}
                    {item.total !== undefined && item.total > 0 && (
                      <span className="text-[10px] text-slate-500 ml-1">
                        (共 {item.total} 批)
                      </span>
                    )}
                  </span>
                  <span className={`font-semibold ${
                      item.value < 90 ? "text-red-400" : "text-emerald-400"
                  }`}>
                    {item.value.toFixed(2)}%
                  </span>
                </div>

                <div className="w-full bg-slate-700/50 rounded-full h-3">
                  <div
                    className={`h-3 rounded-full transition-all duration-1000 ${
                      item.color || "bg-teal-500"
                    }`}
                    style={{ width: `${Math.min(item.value, 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>

          {/* =========================
           * 右側：整體 WIP Yield（⭐ 旋轉效果）
           * 保持不變，顯示總計數良率
           * ========================= */}
          <div
            className={`flex flex-col items-center ${
              syncing ? "animate-spin-slow" : ""
            }`}
          >
            <CircleProgress
              percentage={overall.percent}
              size={80}
              color={
                overall.percent < 90
                  ? "#ef4444"
                  : overall.percent < 95
                  ? "#f59e0b"
                  : "#10b981"
              }
              trackColor="#334155"
              strokeWidth={8}
              textParams={{
                value: `${overall.percent.toFixed(1)}%`,
                sub: overall.baseDate
                  ? `${overall.baseDate}`
                  : "無數據",
              }}
            />

            {stats.has_low_yield_alert && (
              <div className="mt-4">
                <LowYieldModal onUpdate={fetchStats} />
              </div>
            )}
          </div>
        </div>
      )}
    </Card>
  );
};

export default BeadsYield;