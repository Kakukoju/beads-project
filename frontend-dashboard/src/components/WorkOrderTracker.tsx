import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  Search,
  Package,
  Camera,
  X,
  ChevronDown,
  ChevronUp,
  Loader2,
  BarChart3,
  ClipboardList,
  Filter,
} from "lucide-react";

// ==========================================
// Types
// ==========================================

interface StationData {
  name: string;
  time: string | null;
  photos: string[];
  uploader: string | null;
}

interface WorkOrder {
  workOrder: string;
  quantity: number | null;
  beadName: string;
  marker: string;
  date: string | null;
  stations: StationData[];
  progress: number; // 0~7
  progressPercent: number; // 0~100
  currentStation: string;
}

interface TrackingResponse {
  success: boolean;
  data: WorkOrder[];
  total: number;
}

interface HeatmapCell {
  beadName: string;
  period: string;
  count: number;
}

interface StatsResponse {
  success: boolean;
  periods: string[];
  beads: string[];
  cells: HeatmapCell[];
}

const STATION_NAMES = [
  "收藥",
  "滴定準備",
  "滴定開始",
  "滴定結束",
  "凍乾準備",
  "凍乾開始",
  "凍乾結束",
];

const S3_BASE = "https://beads-photos-harry.s3.ap-northeast-1.amazonaws.com/workorder_photo";

// ==========================================
// Helpers
// ==========================================

function formatTime(ts: string | null): string {
  if (!ts) return "--:--";
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return "--:--";
    return d.toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit", hour12: false });
  } catch {
    return "--:--";
  }
}

function formatDate(ts: string | null): string {
  if (!ts) return "";
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return "";
    return d.toLocaleDateString("zh-TW");
  } catch {
    return "";
  }
}

function getDefaultDateRange(): [string, string] {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - 7);
  const fmt = (d: Date) => d.toISOString().split("T")[0];
  return [fmt(start), fmt(end)];
}

/** Color scale for heatmap: 0 → transparent, max → deep red */
function heatColor(value: number, max: number): string {
  if (value === 0) return "transparent";
  const ratio = Math.min(value / max, 1);
  // YlOrRd inspired
  if (ratio < 0.25) return "rgba(254,217,118,0.7)";
  if (ratio < 0.5) return "rgba(253,141,60,0.8)";
  if (ratio < 0.75) return "rgba(227,26,28,0.85)";
  return "rgba(128,0,38,0.95)";
}

function heatTextColor(value: number, max: number): string {
  if (value === 0) return "transparent";
  const ratio = Math.min(value / max, 1);
  return ratio > 0.5 ? "#fff" : "#1e293b";
}

// ==========================================
// Sub-components
// ==========================================

/** Photo lightbox modal */
const PhotoModal: React.FC<{
  src: string;
  caption: string;
  onClose: () => void;
}> = ({ src, caption, onClose }) => (
  <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4" onClick={onClose}>
    <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" />
    <div
      className="relative bg-slate-900 border border-slate-700 rounded-xl shadow-2xl max-w-3xl max-h-[90vh] flex flex-col overflow-hidden"
      onClick={(e) => e.stopPropagation()}
    >
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700 bg-slate-800">
        <span className="text-sm text-slate-300 truncate">{caption}</span>
        <button onClick={onClose} className="p-1 text-slate-400 hover:text-white hover:bg-red-600 rounded transition-colors">
          <X size={18} />
        </button>
      </div>
      <div className="flex-1 overflow-auto p-2 flex items-center justify-center bg-slate-950">
        <img src={src} alt={caption} className="max-w-full max-h-[75vh] object-contain rounded" />
      </div>
    </div>
  </div>
);

/** Single station column within a work order row */
const StationCell: React.FC<{
  station: StationData;
  workOrder: string;
  index: number;
  onPhotoClick: (src: string, caption: string) => void;
}> = ({ station, workOrder, index, onPhotoClick }) => {
  const hasTime = !!station.time;
  const timeShort = formatTime(station.time);
  const uploader = station.uploader || "";

  return (
    <div className={`flex flex-col items-center text-center min-w-0 ${hasTime ? "" : "opacity-30"}`}>
      {/* Station header */}
      <div className="text-[11px] font-bold text-slate-200 truncate w-full">{station.name}</div>
      <div className="text-[10px] text-slate-400 font-mono">{timeShort}</div>
      {hasTime && uploader && (
        <div className="text-[9px] text-slate-500 truncate w-full">{uploader}</div>
      )}

      {/* Photo grid */}
      {station.photos.length > 0 && (
        <div className={`mt-1 grid gap-1 w-full ${station.photos.length === 1 ? "grid-cols-1" : "grid-cols-2"}`}>
          {station.photos.slice(0, 4).map((photo, pi) => {
            const src = `${S3_BASE}/${photo}`;
            const caption = `${station.name} - ${formatTime(station.time)} (${uploader})`;
            return (
              <div key={`${workOrder}-${index}-${pi}`} className="relative group cursor-pointer" onClick={() => onPhotoClick(src, caption)}>
                <img
                  src={src}
                  alt={`${station.name} ${pi + 1}`}
                  className="w-full aspect-square object-cover rounded-t-md border border-slate-700"
                  loading="lazy"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = "none";
                  }}
                />
                <div className="w-full bg-slate-800 border border-t-0 border-slate-700 rounded-b-md text-[9px] text-slate-400 text-center py-0.5 group-hover:bg-slate-700 group-hover:text-white transition-colors">
                  🔍
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

/** Single work order card */
const WorkOrderCard: React.FC<{
  wo: WorkOrder;
  onPhotoClick: (src: string, caption: string) => void;
}> = ({ wo, onPhotoClick }) => {
  const [expanded, setExpanded] = useState(false);

  // Auto-hide photos if completed > 1 hour ago
  const lastStation = wo.stations[wo.stations.length - 1];
  const autoHide =
    lastStation.time && Date.now() - new Date(lastStation.time).getTime() > 3600000;

  const showStations = expanded || !autoHide;

  return (
    <div className="bg-slate-800/60 border border-slate-700/50 rounded-xl p-4 space-y-3">
      {/* Header row */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => setExpanded(!expanded)}
          className="p-1 text-slate-400 hover:text-white transition-colors rounded"
          title={expanded ? "收合" : "展開"}
        >
          {showStations ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>

        <div className="flex items-center gap-2 flex-1 min-w-0">
          <Package size={16} className="text-blue-400 shrink-0" />
          <span className="font-bold text-white text-base font-mono truncate">{wo.workOrder}</span>
          <span className="text-xs text-slate-400 shrink-0 flex items-center gap-1">
            {wo.beadName && <span className="bg-slate-700 px-2 py-0.5 rounded text-slate-300">{wo.beadName}</span>}
            {wo.marker && <span className="bg-amber-900/40 text-amber-300 border border-amber-700/40 px-2 py-0.5 rounded">{wo.marker}</span>}
            {wo.quantity != null && <span>數量: {wo.quantity}</span>}
          </span>
        </div>

        <span className="text-xs text-slate-500 shrink-0">{formatDate(wo.date)}</span>
        <span className={`text-[10px] px-2 py-0.5 rounded font-bold shrink-0 ${
          wo.progressPercent === 100
            ? "bg-emerald-900/40 text-emerald-400 border border-emerald-700/50"
            : wo.progressPercent > 0
            ? "bg-blue-900/40 text-blue-400 border border-blue-700/50"
            : "bg-slate-700/40 text-slate-400 border border-slate-600/50"
        }`}>
          {wo.currentStation}
        </span>
      </div>

      {/* Progress bar */}
      <div className="w-full bg-slate-700/50 rounded-full h-2 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            wo.progressPercent === 100 ? "bg-emerald-500" : "bg-blue-500"
          }`}
          style={{ width: `${wo.progressPercent}%` }}
        />
      </div>

      {/* Station details */}
      {showStations && (
        <div className="grid grid-cols-7 gap-2 pt-2 border-t border-slate-700/30">
          {wo.stations.map((s, i) => (
            <StationCell
              key={`${wo.workOrder}-st-${i}`}
              station={s}
              workOrder={wo.workOrder}
              index={i}
              onPhotoClick={onPhotoClick}
            />
          ))}
        </div>
      )}
    </div>
  );
};

/** Production heatmap (Top 24 beads) */
const ProductionHeatmap: React.FC<{ period: string }> = ({ period }) => {
  const [data, setData] = useState<StatsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`/api/workorder/qr-stats?period=${period}`)
      .then((r) => r.json())
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [period]);

  const maxVal = useMemo(() => {
    if (!data?.cells) return 1;
    return Math.max(1, ...data.cells.map((c) => c.count));
  }, [data]);

  const periodLabels: Record<string, string> = {
    week: "週統計",
    month: "月統計",
    quarter: "季統計",
    year: "年統計",
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-slate-400">
        <Loader2 className="animate-spin mr-2" size={20} />
        載入統計資料中...
      </div>
    );
  }

  if (!data?.success || !data.beads.length) {
    return <div className="text-center py-16 text-slate-500">無足夠資料繪製熱力圖</div>;
  }

  // Build lookup map
  const cellMap = new Map<string, number>();
  data.cells.forEach((c) => cellMap.set(`${c.beadName}|${c.period}`, c.count));

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h3 className="text-lg font-bold text-slate-200">📊 生產統計分析</h3>
        <span className="text-xs bg-blue-500/20 text-blue-300 px-3 py-1 rounded-full border border-blue-500/30">
          {periodLabels[period] || period} — Top 24 Beads
        </span>
      </div>

      <div className="overflow-auto max-h-[70vh] border border-slate-700/50 rounded-lg">
        <table className="text-[10px] border-collapse w-full">
          <thead className="sticky top-0 z-10 bg-slate-800">
            <tr>
              <th className="p-2 text-left text-slate-300 font-bold border-b border-slate-700 bg-slate-800 sticky left-0 z-20 min-w-[140px]">
                Bead Name
              </th>
              {data.periods.map((p) => (
                <th key={p} className="p-2 text-center text-slate-400 font-medium border-b border-slate-700 bg-slate-800 whitespace-nowrap">
                  {p}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.beads.map((bead) => (
              <tr key={bead} className="hover:bg-slate-800/50">
                <td className="p-2 text-slate-300 font-mono border-b border-slate-800/50 sticky left-0 bg-slate-900 z-10 truncate max-w-[180px]" title={bead}>
                  {bead}
                </td>
                {data.periods.map((p) => {
                  const val = cellMap.get(`${bead}|${p}`) || 0;
                  return (
                    <td
                      key={`${bead}-${p}`}
                      className="p-2 text-center font-bold border-b border-slate-800/30"
                      style={{
                        backgroundColor: heatColor(val, maxVal),
                        color: heatTextColor(val, maxVal),
                      }}
                    >
                      {val > 0 ? val : ""}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

// ==========================================
// Main Component
// ==========================================

export default function WorkOrderTracker() {
  // View mode
  const [mode, setMode] = useState<"tracking" | "statistics">("tracking");
  const [statPeriod, setStatPeriod] = useState("week");

  // Filters
  const [dateRange, setDateRange] = useState(getDefaultDateRange);
  const [woFilter, setWoFilter] = useState("");
  const [beadFilter, setBeadFilter] = useState("");
  const [incompleteOnly, setIncompleteOnly] = useState(false);
  const [showFilters, setShowFilters] = useState(true);

  // Data
  const [orders, setOrders] = useState<WorkOrder[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  // Photo modal
  const [modalPhoto, setModalPhoto] = useState<{ src: string; caption: string } | null>(null);

  // Fetch work orders
  const fetchOrders = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("start", dateRange[0]);
      params.set("end", dateRange[1]);
      if (woFilter.trim()) params.set("workOrder", woFilter.trim());
      if (beadFilter.trim()) params.set("beadName", beadFilter.trim());
      if (incompleteOnly) params.set("incompleteOnly", "1");

      const res = await fetch(`/api/workorder/qr-tracking?${params}`);
      const data: TrackingResponse = await res.json();
      if (data.success) {
        setOrders(data.data);
        setTotal(data.total);
      }
    } catch (err) {
      console.error("載入工單追蹤資料失敗:", err);
    } finally {
      setLoading(false);
    }
  }, [dateRange, woFilter, beadFilter, incompleteOnly]);

  useEffect(() => {
    if (mode === "tracking") {
      fetchOrders();
      const interval = setInterval(fetchOrders, 60000);
      return () => clearInterval(interval);
    }
  }, [mode, fetchOrders]);

  return (
    <div className="w-full h-full flex flex-col animate-in fade-in duration-500">
      {/* Toolbar */}
      <div className="shrink-0 bg-slate-800/80 backdrop-blur border-b border-slate-700/50 px-5 py-3 flex items-center gap-4 flex-wrap">
        {/* Mode toggle */}
        <div className="flex gap-1 bg-slate-900 rounded-lg p-1">
          <button
            onClick={() => setMode("tracking")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              mode === "tracking" ? "bg-blue-600 text-white" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <ClipboardList size={14} /> 工單追蹤
          </button>
          <button
            onClick={() => setMode("statistics")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
              mode === "statistics" ? "bg-blue-600 text-white" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <BarChart3 size={14} /> 統計
          </button>
        </div>

        {/* Statistics period selector */}
        {mode === "statistics" && (
          <select
            value={statPeriod}
            onChange={(e) => setStatPeriod(e.target.value)}
            className="text-xs bg-slate-700 border border-slate-600 text-slate-200 rounded-md px-2 py-1.5"
          >
            <option value="week">週統計</option>
            <option value="month">月統計</option>
            <option value="quarter">季統計</option>
            <option value="year">年統計</option>
          </select>
        )}

        {/* Tracking filters */}
        {mode === "tracking" && (
          <>
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`flex items-center gap-1 text-xs px-2 py-1.5 rounded-md border transition-colors ${
                showFilters ? "border-blue-500/50 text-blue-400 bg-blue-500/10" : "border-slate-600 text-slate-400"
              }`}
            >
              <Filter size={13} /> 篩選
            </button>

            <span className="text-xs text-slate-500 ml-auto">
              共 {total} 筆工單
            </span>
          </>
        )}
      </div>

      {/* Filter bar */}
      {mode === "tracking" && showFilters && (
        <div className="shrink-0 bg-slate-850 border-b border-slate-700/30 px-5 py-3 flex items-end gap-4 flex-wrap">
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-slate-500">開始日期</label>
            <input
              type="date"
              value={dateRange[0]}
              onChange={(e) => setDateRange([e.target.value, dateRange[1]])}
              className="text-xs bg-slate-700 border border-slate-600 text-slate-200 rounded-md px-2 py-1.5"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-slate-500">結束日期</label>
            <input
              type="date"
              value={dateRange[1]}
              onChange={(e) => setDateRange([dateRange[0], e.target.value])}
              className="text-xs bg-slate-700 border border-slate-600 text-slate-200 rounded-md px-2 py-1.5"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-slate-500">工單號</label>
            <div className="relative">
              <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                type="text"
                value={woFilter}
                onChange={(e) => setWoFilter(e.target.value)}
                placeholder="搜尋工單號..."
                className="text-xs bg-slate-700 border border-slate-600 text-slate-200 rounded-md pl-7 pr-2 py-1.5 w-40"
              />
            </div>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-slate-500">Bead / Marker</label>
            <input
              type="text"
              value={beadFilter}
              onChange={(e) => setBeadFilter(e.target.value)}
              placeholder="Bead 或 Marker..."
              className="text-xs bg-slate-700 border border-slate-600 text-slate-200 rounded-md px-2 py-1.5 w-36"
            />
          </div>
          <label className="flex items-center gap-2 text-xs text-slate-400 cursor-pointer pb-1">
            <input
              type="checkbox"
              checked={incompleteOnly}
              onChange={(e) => setIncompleteOnly(e.target.checked)}
              className="rounded border-slate-600"
            />
            只顯示未完成
          </label>
        </div>
      )}

      {/* Content area */}
      <div className="flex-1 overflow-auto p-5">
        {mode === "statistics" ? (
          <ProductionHeatmap period={statPeriod} />
        ) : loading ? (
          <div className="flex items-center justify-center py-20 text-slate-400">
            <Loader2 className="animate-spin mr-2" size={20} />
            載入工單資料中...
          </div>
        ) : orders.length === 0 ? (
          <div className="text-center py-20 text-slate-500">
            <Package size={48} className="mx-auto mb-4 opacity-20" />
            <p className="text-lg">無符合條件的工單</p>
          </div>
        ) : (
          <div className="space-y-4">
            {orders.map((wo) => (
              <WorkOrderCard key={wo.workOrder} wo={wo} onPhotoClick={(src, caption) => setModalPhoto({ src, caption })} />
            ))}
          </div>
        )}
      </div>

      {/* Photo modal */}
      {modalPhoto && (
        <PhotoModal src={modalPhoto.src} caption={modalPhoto.caption} onClose={() => setModalPhoto(null)} />
      )}
    </div>
  );
}
