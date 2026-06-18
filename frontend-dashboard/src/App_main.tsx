// src/App.tsx
import { useState, useEffect } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
  ResponsiveContainer,
} from "recharts";
import BeadsIPQCPage from "./BeadsIPQCPage"; // ← Beads IPQC 主頁

// 排程資料類型定義
interface ScheduleRow {
  date: string;
  marker?: string;
  machine: string;
  dryer?: string;
  operator: string;
  rdTime?: string;
  start: string;
  end: string;
  qty?: string;
  pn?: string;
  batch?: string;
  workOrder?: string;
  remark?: string;
}

// 今日統計類型定義
interface TodayStats {
  tasks: number;
  titration_machines: number;
  dryers: number;
  titration_utilization: number;
  dryer_utilization: number;
}

// 稼動率數據類型
interface UtilizationData {
  mode: "day" | "week" | "month";
  period: string;
  titration_utilization: number;
  dryer_utilization: number;
  titration_used: number;
  titration_capacity: number;
  dryer_used: number;
  dryer_capacity: number;
  work_days: number;
}

// 完成率數據類型
interface CompletionData {
  date: string;
  total_orders: number;
  dispensing_rate: number;
  titration_rate: number;
  freeze_drying_rate: number;
  dispensing_completed: number;
  titration_completed: number;
  freeze_drying_completed: number;
}

// 工作分派統計類型
interface WorkloadStats {
  mode: "week" | "month";
  period: string;
  staff_stats: Array<{
    name: string;
    count: number;
    percentage: number;
  }>;
  total_assignments: number;
}

// Progress 組件
interface ProgressProps {
  value?: number;
  max?: number;
  className?: string;
}

function Progress({ value = 0, max = 100, className = "" }: ProgressProps) {
  const percentage = Math.min(Math.max((value / max) * 100, 0), 100);

  return (
    <div
      className={`relative h-2.5 w-full overflow-hidden rounded-full bg-slate-200/80 ${className}`}
    >
      <div
        className="h-full bg-gradient-to-r from-blue-500 via-sky-400 to-emerald-400 transition-all duration-300 ease-in-out"
        style={{ width: `${percentage}%` }}
      />
    </div>
  );
}

// Card 組件
interface CardProps {
  children: React.ReactNode;
  className?: string;
  onClick?: () => void;
}

function Card({ children, className = "", onClick }: CardProps) {
  return (
    <div
      onClick={onClick}
      className={`rounded-2xl border border-slate-200/70 bg-white/80 backdrop-blur-xl shadow-[0_18px_45px_rgba(15,23,42,0.18)] transition-all duration-300 hover:shadow-[0_26px_60px_rgba(15,23,42,0.4)] ${className}`}
    >
      {children}
    </div>
  );
}

// 主要 Dashboard 組件
export default function App() {
  // 排程表資料相關
  const [hoveredRow, setHoveredRow] = useState<number | null>(null);
  const [scheduleData, setScheduleData] = useState<ScheduleRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 視圖切換
  const [currentView, setCurrentView] = useState<string>("Dashboard");

  // 搜尋相關
  const [searchType, setSearchType] = useState<"week" | "date">("week");
  const [searchWeek, setSearchWeek] = useState<string>("");
  const [searchDate, setSearchDate] = useState<string>("");
  const [operatorFilter, setOperatorFilter] = useState<string>("");

  // 編輯相關
  const [isEditing, setIsEditing] = useState(false);
  const [editedData, setEditedData] = useState<ScheduleRow[]>([]);
  const [modifiedRows, setModifiedRows] = useState<Set<number>>(new Set());
  const [isSaving, setIsSaving] = useState(false);

  // 今日統計
  const [todayStats, setTodayStats] = useState<TodayStats>({
    tasks: 0,
    titration_machines: 0,
    dryers: 0,
    titration_utilization: 0,
    dryer_utilization: 0,
  });

  // 稼動率狀態
  const [utilizationMode, setUtilizationMode] = useState<
    "day" | "week" | "month"
  >("day");
  const [utilizationData, setUtilizationData] = useState<UtilizationData>({
    mode: "day",
    period: "",
    titration_utilization: 0,
    dryer_utilization: 0,
    titration_used: 0,
    titration_capacity: 0,
    dryer_used: 0,
    dryer_capacity: 0,
    work_days: 0,
  });

  // 完成率狀態
  const [completionData, setCompletionData] = useState<CompletionData>({
    date: "",
    total_orders: 0,
    dispensing_rate: 0,
    titration_rate: 0,
    freeze_drying_rate: 0,
    dispensing_completed: 0,
    titration_completed: 0,
    freeze_drying_completed: 0,
  });

  // 人員派工狀態
  const [workloadMode, setWorkloadMode] = useState<"week" | "month">("week");
  const [workloadData, setWorkloadData] = useState<WorkloadStats>({
    mode: "week",
    period: "",
    staff_stats: [],
    total_assignments: 0,
  });
  const [workloadLoading, setWorkloadLoading] = useState(false);

  // 初始化預設值
  useEffect(() => {
    const initializeDefaults = async () => {
      try {
        const response = await fetch("/api/schedule/current-week");
        const data = await response.json();

        if (data.ok) {
          setSearchDate(data.date);
          setSearchWeek(data.week);
        }
      } catch (err) {
        console.error("取得預設值失敗:", err);
        const today = new Date();
        setSearchDate(today.toISOString().split("T")[0]);
        setSearchWeek(getISOWeek(today));
      }
    };

    initializeDefaults();
  }, []);

  // 載入稼動率數據
  useEffect(() => {
    const fetchUtilization = async () => {
      try {
        const today = new Date().toISOString().split("T")[0];
        const response = await fetch(
          `/api/schedule/utilization?mode=${utilizationMode}&date=${today}`
        );
        const data = await response.json();

        if (data.ok) {
          setUtilizationData(data);
        }
      } catch (err) {
        console.error("載入稼動率失敗:", err);
      }
    };

    if (currentView === "Dashboard") {
      fetchUtilization();
      const interval = setInterval(fetchUtilization, 60000);
      return () => clearInterval(interval);
    }
  }, [currentView, utilizationMode]);

  // 載入今日統計（在 Dashboard 視圖時）
  useEffect(() => {
    const fetchTodayStats = async () => {
      try {
        const response = await fetch("/api/schedule/today-stats");
        const data = await response.json();

        if (data.ok) {
          setTodayStats({
            tasks: data.tasks,
            titration_machines: data.titration_machines,
            dryers: data.dryers,
            titration_utilization: 0,
            dryer_utilization: 0,
          });
        }
      } catch (err) {
        console.error("載入今日統計失敗:", err);
      }
    };

    if (currentView === "Dashboard") {
      fetchTodayStats();
      const interval = setInterval(fetchTodayStats, 60000);
      return () => clearInterval(interval);
    }
  }, [currentView]);

  // 載入工作分派統計（在「配藥人員派工」頁面時）
  useEffect(() => {
    const fetchWorkloadStats = async () => {
      try {
        setWorkloadLoading(true);
        const today = new Date().toISOString().split("T")[0];
        const response = await fetch(
          `/api/schedule/workload-stats?mode=${workloadMode}&date=${today}`
        );
        const data = await response.json();

        if (data.ok) {
          setWorkloadData(data);
        }
      } catch (err) {
        console.error("載入工作分派統計失敗:", err);
      } finally {
        setWorkloadLoading(false);
      }
    };

    if (currentView === "配藥人員派工") {
      fetchWorkloadStats();
      const interval = setInterval(fetchWorkloadStats, 600000);
      return () => clearInterval(interval);
    }
  }, [currentView, workloadMode]);

  // 載入完成率數據
  useEffect(() => {
    const fetchCompletionRate = async () => {
      try {
        const today = new Date().toISOString().split("T")[0];
        const response = await fetch(
          `/api/schedule/completion-rate?date=${today}`
        );
        const data = await response.json();

        if (data.ok) {
          setCompletionData(data);
        }
      } catch (err) {
        console.error("載入完成率失敗:", err);
      }
    };

    if (currentView === "Dashboard") {
      fetchCompletionRate();
      const interval = setInterval(fetchCompletionRate, 60000);
      return () => clearInterval(interval);
    }
  }, [currentView]);

  // 切換到排程表時自動搜尋
  useEffect(() => {
    if (currentView === "排程表" && (searchWeek || searchDate)) {
      handleSearch();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentView]);

  // 計算 ISO 週數
  const getISOWeek = (date: Date): string => {
    const target = new Date(date.valueOf());
    const dayNr = (date.getDay() + 6) % 7;
    target.setDate(target.getDate() - dayNr + 3);
    const firstThursday = target.valueOf();
    target.setMonth(0, 1);
    if (target.getDay() !== 4) {
      target.setMonth(0, 1 + (((4 - target.getDay()) + 7) % 7));
    }
    const weekNumber =
      1 + Math.ceil((firstThursday - target.valueOf()) / 604800000);
    const year = new Date(firstThursday).getFullYear();
    return `${year}_W${weekNumber.toString().padStart(2, "0")}`;
  };

  // 執行搜尋
  const handleSearch = async () => {
    try {
      setLoading(true);
      setError(null);

      const searchValue = searchType === "week" ? searchWeek : searchDate;

      if (!searchValue) {
        setError("請輸入搜尋條件");
        setLoading(false);
        return;
      }

      let url = `/api/schedule/search?searchType=${searchType}&searchValue=${encodeURIComponent(
        searchValue
      )}`;

      if (operatorFilter.trim()) {
        url += `&operator=${encodeURIComponent(operatorFilter.trim())}`;
      }

      const response = await fetch(url);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      setScheduleData(data);
    } catch (err) {
      console.error("搜尋失敗:", err);
      setError(err instanceof Error ? err.message : "搜尋失敗");
    } finally {
      setLoading(false);
    }
  };

  // 進入編輯模式
  const handleStartEdit = () => {
    setIsEditing(true);
    setEditedData(JSON.parse(JSON.stringify(scheduleData)));
    setModifiedRows(new Set());
  };

  // 取消編輯
  const handleCancelEdit = () => {
    if (modifiedRows.size > 0) {
      if (
        !confirm(`有 ${modifiedRows.size} 筆資料已修改，確定要放棄修改嗎？`)
      ) {
        return;
      }
    }
    setIsEditing(false);
    setEditedData([]);
    setModifiedRows(new Set());
  };

  // 更新單個欄位
  const handleCellChange = (
    rowIndex: number,
    field: keyof ScheduleRow,
    value: string
  ) => {
    const newData = [...editedData];
    newData[rowIndex] = { ...newData[rowIndex], [field]: value };
    setEditedData(newData);

    const newModified = new Set(modifiedRows);
    newModified.add(rowIndex);
    setModifiedRows(newModified);
  };

  // 保存到資料庫
  const handleSaveChanges = async () => {
    if (modifiedRows.size === 0) {
      alert("沒有修改任何資料");
      return;
    }

    if (!confirm(`確定要保存 ${modifiedRows.size} 筆修改嗎？`)) {
      return;
    }

    try {
      setIsSaving(true);

      const dataToSave = Array.from(modifiedRows).map(
        (index) => editedData[index]
      );

      const response = await fetch("/api/schedule/save", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(dataToSave),
      });

      const result = await response.json();

      if (result.ok) {
        alert(result.message || "保存成功！");
        setScheduleData(editedData);
        setIsEditing(false);
        setEditedData([]);
        setModifiedRows(new Set());
      } else {
        alert(`保存失敗：${result.message}`);
      }
    } catch (err) {
      console.error("保存失敗:", err);
      alert(`保存失敗：${err instanceof Error ? err.message : "未知錯誤"}`);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-50 flex font-sans">
      {/* Sidebar */}
      <aside className="relative w-64 bg-slate-950/70 border-r border-slate-800/70 px-5 py-6 flex flex-col shadow-[0_18px_45px_rgba(15,23,42,0.6)]">
        {/* Logo / Title */}
        <div className="flex items-center gap-2 mb-6 px-1">
          <div className="h-9 w-9 rounded-2xl bg-gradient-to-br from-blue-500 via-sky-400 to-emerald-400 flex items-center justify-center shadow-[0_0_25px_rgba(56,189,248,0.6)]">
            <span className="text-xs font-black tracking-tight">BO</span>
          </div>
          <div>
            <div className="text-lg font-semibold tracking-tight text-slate-50">
              BeadsOps
            </div>
            <div className="text-[11px] text-slate-400">
              滴定・凍乾・IPQC 一站式
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav className="space-y-1 flex-1">
          {[
            "Dashboard",
            "Beads 排程作業",
            "滴定凍乾e工單資訊",
            "工單 QR 掃描追蹤",
            "排程表",
            "衝突",
            "配藥人員派工",
            "Beads IPQC資料",
          ].map((item) => {
            const active = currentView === item;
            return (
              <button
                key={item}
                onClick={() => setCurrentView(item)}
                className={`group w-full text-left px-3 py-2 rounded-xl text-sm font-medium flex items-center justify-between transition-all duration-200 ${
                  active
                    ? "bg-gradient-to-r from-blue-600 via-sky-500 to-emerald-400 text-slate-50 shadow-[0_18px_35px_rgba(37,99,235,0.6)] scale-[1.02]"
                    : "text-slate-300 hover:text-slate-50 hover:bg-slate-800/80 hover:translate-x-0.5"
                }`}
              >
                <span>{item}</span>
                <span
                  className={`text-[10px] tracking-widest uppercase ${
                    active ? "text-slate-100" : "text-slate-500 group-hover:text-slate-200"
                  }`}
                >
                  {active ? "ACTIVE" : "OPEN"}
                </span>
              </button>
            );
          })}
        </nav>

        {/* Sidebar footer */}
        <div className="mt-4 pt-4 border-t border-slate-800/70 text-[11px] text-slate-500">
          <div>© Skyla 2025</div>
          <div className="text-slate-600">BeadsOps 生產資訊系統</div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 px-10 py-8 space-y-10 overflow-auto bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950">
        {/* Header */}
        <header className="mb-2 flex items-center justify-between gap-4">
          <div>
            <h2 className="text-3xl font-semibold text-slate-50 tracking-tight">
              Beads Ops — 生產資訊系統
            </h2>
            <p className="text-sm text-slate-400 mt-1">
              排程、IPQC、滴定凍乾 e 工單與 QR 掃描追蹤集中看板
            </p>
          </div>
          <div className="hidden md:flex items-center gap-2 text-xs text-slate-400">
            <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.9)]" />
            <span>Service Status: Online</span>
          </div>
        </header>

        {/* Dashboard 視圖 */}
        {currentView === "Dashboard" && (
          <>
            {/* Top Stats Section - 3 cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* 卡片 1: 今日任務 */}
              <Card className="p-6 hover:scale-[1.02]">
                <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Today • 任務概況
                </div>
                <div className="mt-4 flex items-end justify-between">
                  <div>
                    <div className="text-4xl font-bold text-slate-900">
                      {todayStats.tasks}
                    </div>
                    <div className="mt-1 text-xs text-slate-500">
                      總工單數（含配藥 / 滴定 / 凍乾）
                    </div>
                  </div>
                  <div className="text-right text-xs text-slate-600">
                    <div>
                      滴定機：
                      <span className="font-semibold">
                        {todayStats.titration_machines}
                      </span>
                    </div>
                    <div>
                      凍乾機：
                      <span className="font-semibold">
                        {todayStats.dryers}
                      </span>
                    </div>
                  </div>
                </div>
              </Card>

              {/* 卡片 2: 完成率 */}
              <Card className="p-6 hover:scale-[1.02]">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                    今日完成率
                  </div>
                  <div className="text-[11px] text-slate-400">
                    共 {completionData.total_orders} 筆工單
                  </div>
                </div>

                <div className="mt-4 space-y-3">
                  {/* 配藥 */}
                  <div>
                    <div className="flex justify-between items-center mb-1">
                      <span className="text-xs text-slate-700">配藥</span>
                      <span className="text-sm font-semibold text-slate-800">
                        {completionData.dispensing_rate}%
                      </span>
                    </div>
                    <Progress
                      value={completionData.dispensing_rate}
                      className="h-2"
                    />
                    <div className="text-[11px] text-slate-500 mt-1">
                      {completionData.dispensing_completed} /{" "}
                      {completionData.total_orders}
                    </div>
                  </div>

                  {/* 滴定 */}
                  <div>
                    <div className="flex justify-between items-center mb-1">
                      <span className="text-xs text-slate-700">滴定</span>
                      <span className="text-sm font-semibold text-slate-800">
                        {completionData.titration_rate}%
                      </span>
                    </div>
                    <Progress
                      value={completionData.titration_rate}
                      className="h-2"
                    />
                    <div className="text-[11px] text-slate-500 mt-1">
                      {completionData.titration_completed} /{" "}
                      {completionData.total_orders}
                    </div>
                  </div>

                  {/* 凍乾 */}
                  <div>
                    <div className="flex justify-between items-center mb-1">
                      <span className="text-xs text-slate-700">凍乾</span>
                      <span className="text-sm font-semibold text-slate-800">
                        {completionData.freeze_drying_rate}%
                      </span>
                    </div>
                    <Progress
                      value={completionData.freeze_drying_rate}
                      className="h-2"
                    />
                    <div className="text-[11px] text-slate-500 mt-1">
                      {completionData.freeze_drying_completed} /{" "}
                      {completionData.total_orders}
                    </div>
                  </div>
                </div>
              </Card>

              {/* 卡片 3: 稼動率 */}
              <Card
                className="p-6 cursor-pointer hover:scale-[1.02]"
                onClick={() => {
                  const modes: Array<"day" | "week" | "month"> = [
                    "day",
                    "week",
                    "month",
                  ];
                  const currentIndex = modes.indexOf(utilizationMode);
                  const nextIndex = (currentIndex + 1) % modes.length;
                  setUtilizationMode(modes[nextIndex]);
                }}
              >
                <div className="flex justify-between items-center mb-2">
                  <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                    稼動率
                  </div>
                  <div className="text-[11px] px-2 py-0.5 rounded-full bg-slate-900/5 text-slate-600 border border-slate-200">
                    {utilizationMode === "day" && "日模式"}
                    {utilizationMode === "week" && "周模式"}
                    {utilizationMode === "month" && "月模式"}
                  </div>
                </div>

                <div className="text-[11px] text-slate-500 mb-3">
                  {utilizationData.period}
                  {utilizationMode !== "day" &&
                    utilizationData.work_days > 0 &&
                    `（${utilizationData.work_days} 天）`}
                </div>

                {/* 滴定機稼動率 */}
                <div className="mb-3">
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-xs text-slate-700">滴定機</span>
                    <span className="text-sm font-semibold text-slate-800">
                      {utilizationData.titration_utilization}%
                    </span>
                  </div>
                  <Progress
                    value={utilizationData.titration_utilization}
                    className="h-2"
                  />
                  <div className="text-[11px] text-slate-500 mt-1">
                    {utilizationData.titration_used} /{" "}
                    {utilizationData.titration_capacity}
                  </div>
                </div>

                {/* 凍乾機稼動率 */}
                <div>
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-xs text-slate-700">凍乾機</span>
                    <span className="text-sm font-semibold text-slate-800">
                      {utilizationData.dryer_utilization}%
                    </span>
                  </div>
                  <Progress
                    value={utilizationData.dryer_utilization}
                    className="h-2"
                  />
                  <div className="text-[11px] text-slate-500 mt-1">
                    {utilizationData.dryer_used} /{" "}
                    {utilizationData.dryer_capacity}
                  </div>
                </div>

                <div className="mt-3 text-[11px] text-slate-400 text-right">
                  點擊切換 日 / 週 / 月
                </div>
              </Card>
            </div>

            {/* Middle Section */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* 生產排程概覽 */}
              <div className="lg:col-span-2">
                <Card className="p-6">
                  <h3 className="font-semibold text-lg text-slate-900 mb-2">
                    生產排程概覽
                  </h3>
                  <p className="text-sm text-slate-500 mb-6">
                    未來可以在此顯示滴定、凍乾機台的時間軸與負載狀態。
                  </p>
                  <div className="text-center py-12 text-slate-400 text-sm">
                    排程視覺化開發中...
                  </div>
                </Card>
              </div>

              {/* 即時通知 */}
              <div>
                <Card className="p-6 space-y-4">
                  <h3 className="font-semibold text-lg text-slate-900">
                    即時通知
                  </h3>
                  <div className="text-sm text-slate-700 space-y-1">
                    <p className="font-semibold">GLU-B Port3 可能延遲</p>
                    <p className="text-slate-500">
                      建議調整 Port2 任務時段，或改派人員。
                    </p>
                  </div>
                  <div className="pt-4 border-t border-slate-200">
                    <h4 className="font-semibold mb-3 text-slate-900">
                      今日摘要
                    </h4>
                    <div className="flex items-end space-x-3">
                      <div className="h-20 w-6 rounded-md bg-blue-500/90" />
                      <div className="h-10 w-6 rounded-md bg-amber-400/90" />
                      <div className="h-4 w-6 rounded-md bg-slate-400/90" />
                    </div>
                    <p className="text-[11px] text-slate-500 mt-2">
                      完成 / 進行中 / 其他
                    </p>
                  </div>
                </Card>
              </div>
            </div>
          </>
        )}

        {/* 排程表視圖 */}
        {currentView === "排程表" && (
          <div>
            <Card className="p-6">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4">
                <h3 className="font-semibold text-lg text-slate-900">
                  排程表搜尋
                </h3>

                {/* 編輯/保存/取消按鈕 */}
                {!isEditing ? (
                  <button
                    onClick={handleStartEdit}
                    disabled={scheduleData.length === 0 || loading}
                    className="px-4 py-2 bg-emerald-500 text-white rounded-lg text-sm hover:bg-emerald-600 transition disabled:bg-slate-300 disabled:cursor-not-allowed"
                  >
                    ✏️ 編輯
                  </button>
                ) : (
                  <div className="flex gap-2">
                    <button
                      onClick={handleSaveChanges}
                      disabled={isSaving || modifiedRows.size === 0}
                      className="px-4 py-2 bg-blue-500 text-white rounded-lg text-sm hover:bg-blue-600 transition disabled:bg-slate-300 disabled:cursor-not-allowed"
                    >
                      {isSaving ? "保存中..." : `💾 保存 (${modifiedRows.size})`}
                    </button>
                    <button
                      onClick={handleCancelEdit}
                      disabled={isSaving}
                      className="px-4 py-2 bg-slate-500 text-white rounded-lg text-sm hover:bg-slate-600 transition disabled:bg-slate-300"
                    >
                      ✖️ 取消
                    </button>
                  </div>
                )}
              </div>

              {/* 搜尋介面 */}
              <div className="mb-6 space-y-4">
                {/* 搜尋類型選擇 */}
                <div className="flex flex-wrap gap-4">
                  <label className="flex items-center gap-2 cursor-pointer text-sm text-slate-700">
                    <input
                      type="radio"
                      name="searchType"
                      value="week"
                      checked={searchType === "week"}
                      onChange={(e) =>
                        setSearchType(e.target.value as "week" | "date")
                      }
                      className="w-4 h-4"
                    />
                    <span>按周別搜尋</span>
                  </label>

                  <label className="flex items-center gap-2 cursor-pointer text-sm text-slate-700">
                    <input
                      type="radio"
                      name="searchType"
                      value="date"
                      checked={searchType === "date"}
                      onChange={(e) =>
                        setSearchType(e.target.value as "week" | "date")
                      }
                      className="w-4 h-4"
                    />
                    <span>按日期搜尋</span>
                  </label>
                </div>

                {/* 搜尋輸入框 */}
                <div className="flex flex-col lg:flex-row gap-4 items-end">
                  {searchType === "week" ? (
                    <div className="flex-1">
                      <label className="block text-sm font-medium text-slate-700 mb-1">
                        周別（格式：2025_W46）
                      </label>
                      <input
                        type="text"
                        value={searchWeek}
                        onChange={(e) => setSearchWeek(e.target.value)}
                        placeholder="例如：2025_W46"
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                      />
                    </div>
                  ) : (
                    <div className="flex-1">
                      <label className="block text-sm font-medium text-slate-700 mb-1">
                        日期（格式：yyyy-mm-dd）
                      </label>
                      <input
                        type="date"
                        value={searchDate}
                        onChange={(e) => setSearchDate(e.target.value)}
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                      />
                    </div>
                  )}

                  {/* 人名搜尋 */}
                  <div className="flex-1">
                    <label className="block text-sm font-medium text-slate-700 mb-1">
                      配藥人員（可選）
                    </label>
                    <input
                      type="text"
                      value={operatorFilter}
                      onChange={(e) => setOperatorFilter(e.target.value)}
                      placeholder="例如：angela, suyo"
                      className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                    />
                  </div>

                  {/* 搜尋按鈕 */}
                  <div className="flex gap-2">
                    <button
                      onClick={handleSearch}
                      disabled={loading}
                      className="px-6 py-2 bg-blue-500 text-white rounded-lg text-sm hover:bg-blue-600 transition disabled:bg-slate-300 disabled:cursor-not-allowed"
                    >
                      {loading ? "搜尋中..." : "搜尋"}
                    </button>

                    {operatorFilter && (
                      <button
                        onClick={() => {
                          setOperatorFilter("");
                          handleSearch();
                        }}
                        className="px-4 py-2 bg-slate-400 text-white rounded-lg text-sm hover:bg-slate-500 transition"
                      >
                        清除
                      </button>
                    )}
                  </div>
                </div>

                {operatorFilter && (
                  <div className="text-sm text-slate-600">
                    🔍 正在過濾：配藥人員 ={" "}
                    <span className="font-semibold text-blue-600">
                      {operatorFilter}
                    </span>
                  </div>
                )}
              </div>

              {/* 錯誤訊息 */}
              {error && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg">
                  <p className="text-sm text-red-600">⚠️ {error}</p>
                </div>
              )}

              {/* 表頭 */}
              <div
                className="text-xs md:text-sm text-slate-700 font-medium border-b border-slate-200 pb-2 mb-3"
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(13, minmax(0, 1fr))",
                  gap: "0.5rem",
                }}
              >
                <span>日期</span>
                <span>Marker</span>
                <span>滴定機</span>
                <span>凍乾機</span>
                <span>配藥人員</span>
                <span>RD給藥時間</span>
                <span>預計滴定</span>
                <span>收藥時間</span>
                <span>數量</span>
                <span>料號</span>
                <span>批號</span>
                <span>工單號碼</span>
                <span>備註</span>
              </div>

              {/* 資料列 */}
              {loading ? (
                <div className="space-y-2">
                  {[1, 2, 3, 4].map((i) => (
                    <div
                      key={i}
                      className="rounded-lg p-2 bg-slate-50 animate-pulse"
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(13, minmax(0, 1fr))",
                        gap: "0.5rem",
                      }}
                    >
                      {Array.from({ length: 13 }).map((_, j) => (
                        <div
                          key={j}
                          className="h-4 bg-slate-200 rounded"
                        ></div>
                      ))}
                    </div>
                  ))}
                </div>
              ) : scheduleData.length === 0 ? (
                <div className="text-center py-8 text-slate-400 text-sm">
                  <p>請執行搜尋以顯示排程資料</p>
                </div>
              ) : (
                <>
                  {(isEditing ? editedData : scheduleData).map((row, i) => {
                    const isModified = modifiedRows.has(i);
                    const isHovered = hoveredRow === i;

                    return (
                      <div
                        key={`${row.date}-${row.machine}-${i}`}
                        className={`rounded-lg mb-2 p-2 transition-all duration-200 ${
                          isModified
                            ? "bg-amber-50 border-2 border-amber-300"
                            : isHovered
                            ? "bg-slate-100 scale-[1.01] shadow-sm"
                            : "bg-slate-50"
                        } ${isEditing ? "cursor-auto" : "cursor-pointer"}`}
                        style={{
                          display: "grid",
                          gridTemplateColumns: "repeat(13, minmax(0, 1fr))",
                          gap: "0.5rem",
                        }}
                        onMouseEnter={() => !isEditing && setHoveredRow(i)}
                        onMouseLeave={() => !isEditing && setHoveredRow(null)}
                      >
                        {/* 1. 日期 */}
                        <span className="text-slate-700 px-1 text-xs md:text-sm">
                          {row.date || "-"}
                        </span>

                        {/* 2. Marker */}
                        {isEditing ? (
                          <input
                            type="text"
                            value={row.marker || ""}
                            onChange={(e) =>
                              handleCellChange(i, "marker", e.target.value)
                            }
                            className="w-full px-1 py-0.5 text-xs md:text-sm border border-slate-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
                          />
                        ) : (
                          <span className="text-slate-700 px-1 text-xs md:text-sm">
                            {row.marker || "-"}
                          </span>
                        )}

                        {/* 3. 滴定機 */}
                        <span className="text-slate-700 px-1 font-medium text-xs md:text-sm">
                          {row.machine || "-"}
                        </span>

                        {/* 4. 凍乾機 */}
                        {isEditing ? (
                          <input
                            type="text"
                            value={row.dryer || ""}
                            onChange={(e) =>
                              handleCellChange(i, "dryer", e.target.value)
                            }
                            className="w-full px-1 py-0.5 text-xs md:text-sm border border-slate-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
                          />
                        ) : (
                          <span className="text-slate-700 px-1 text-xs md:text-sm">
                            {row.dryer || "-"}
                          </span>
                        )}

                        {/* 5. 配藥人員 */}
                        {isEditing ? (
                          <input
                            type="text"
                            value={row.operator || ""}
                            onChange={(e) =>
                              handleCellChange(i, "operator", e.target.value)
                            }
                            className="w-full px-1 py-0.5 text-xs md:text-sm border border-slate-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
                          />
                        ) : (
                          <span className="text-slate-700 px-1 text-xs md:text-sm">
                            {row.operator || "-"}
                          </span>
                        )}

                        {/* 6. RD給藥時間 */}
                        {isEditing ? (
                          <input
                            type="time"
                            value={row.rdTime || ""}
                            onChange={(e) =>
                              handleCellChange(i, "rdTime", e.target.value)
                            }
                            className="w-full px-1 py-0.5 text-xs md:text-sm border border-slate-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
                          />
                        ) : (
                          <span className="text-slate-700 px-1 text-xs md:text-sm">
                            {row.rdTime || "-"}
                          </span>
                        )}

                        {/* 7. 預計滴定 */}
                        {isEditing ? (
                          <input
                            type="time"
                            value={row.start || ""}
                            onChange={(e) =>
                              handleCellChange(i, "start", e.target.value)
                            }
                            className="w-full px-1 py-0.5 text-xs md:text-sm border border-slate-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
                          />
                        ) : (
                          <span className="text-slate-700 px-1 text-xs md:text-sm">
                            {row.start || "-"}
                          </span>
                        )}

                        {/* 8. 收藥時間 */}
                        {isEditing ? (
                          <input
                            type="time"
                            value={row.end || ""}
                            onChange={(e) =>
                              handleCellChange(i, "end", e.target.value)
                            }
                            className="w-full px-1 py-0.5 text-xs md:text-sm border border-slate-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
                          />
                        ) : (
                          <span className="text-slate-700 px-1 text-xs md:text-sm">
                            {row.end || "-"}
                          </span>
                        )}

                        {/* 9. 數量 */}
                        {isEditing ? (
                          <input
                            type="text"
                            value={row.qty || ""}
                            onChange={(e) =>
                              handleCellChange(i, "qty", e.target.value)
                            }
                            className="w-full px-1 py-0.5 text-xs md:text-sm border border-slate-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
                          />
                        ) : (
                          <span className="text-slate-700 px-1 text-xs md:text-sm">
                            {row.qty || "-"}
                          </span>
                        )}

                        {/* 10. 料號 */}
                        {isEditing ? (
                          <input
                            type="text"
                            value={row.pn || ""}
                            onChange={(e) =>
                              handleCellChange(i, "pn", e.target.value)
                            }
                            className="w-full px-1 py-0.5 text-xs md:text-sm border border-slate-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
                          />
                        ) : (
                          <span
                            className="text-slate-700 px-1 truncate text-xs md:text-sm"
                            title={row.pn}
                          >
                            {row.pn || "-"}
                          </span>
                        )}

                        {/* 11. 批號 */}
                        {isEditing ? (
                          <input
                            type="text"
                            value={row.batch || ""}
                            onChange={(e) =>
                              handleCellChange(i, "batch", e.target.value)
                            }
                            className="w-full px-1 py-0.5 text-xs md:text-sm border border-slate-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
                          />
                        ) : (
                          <span
                            className="text-slate-700 px-1 truncate text-xs md:text-sm"
                            title={row.batch}
                          >
                            {row.batch || "-"}
                          </span>
                        )}

                        {/* 12. 工單號碼 */}
                        {isEditing ? (
                          <input
                            type="text"
                            value={row.workOrder || ""}
                            onChange={(e) =>
                              handleCellChange(i, "workOrder", e.target.value)
                            }
                            className="w-full px-1 py-0.5 text-xs md:text-sm border border-slate-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
                          />
                        ) : (
                          <span
                            className="text-slate-700 px-1 truncate text-xs md:text-sm"
                            title={row.workOrder}
                          >
                            {row.workOrder || "-"}
                          </span>
                        )}

                        {/* 13. 備註 */}
                        {isEditing ? (
                          <input
                            type="text"
                            value={row.remark || ""}
                            onChange={(e) =>
                              handleCellChange(i, "remark", e.target.value)
                            }
                            placeholder="備註..."
                            className="w-full px-1 py-0.5 text-xs md:text-sm border border-slate-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
                          />
                        ) : (
                          <span
                            className="text-slate-700 px-1 truncate text-xs md:text-sm"
                            title={row.remark}
                          >
                            {row.remark || "-"}
                          </span>
                        )}
                      </div>
                    );
                  })}
                </>
              )}

              {/* 顯示總筆數 */}
              {!loading && scheduleData.length > 0 && (
                <div className="mt-4 pt-3 border-t border-slate-200 text-sm text-slate-500 text-right">
                  共 {scheduleData.length} 筆排程
                  {isEditing && modifiedRows.size > 0 && (
                    <span className="ml-2 text-amber-600 font-medium">
                      （已修改 {modifiedRows.size} 筆）
                    </span>
                  )}
                </div>
              )}
            </Card>
          </div>
        )}

        {/* 人員派工視圖 */}
        {currentView === "配藥人員派工" && (
          <div>
            <Card className="p-6">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4">
                <h3 className="font-semibold text-xl text-slate-900">
                  配藥人員工作分派統計
                </h3>
                <button
                  onClick={() =>
                    setWorkloadMode((prev) =>
                      prev === "week" ? "month" : "week"
                    )
                  }
                  disabled={workloadLoading}
                  className="px-4 py-2 bg-blue-500 text-white rounded-lg text-sm hover:bg-blue-600 transition disabled:bg-slate-300"
                >
                  {workloadMode === "week" ? "切換至月統計" : "切換至周統計"}
                </button>
              </div>

              <div className="mb-4 flex items-center gap-3">
                <div className="text-xs px-3 py-1 bg-blue-100 text-blue-700 rounded-full font-medium">
                  {workloadMode === "week" ? "本周統計" : "本月至本周統計"}
                </div>
                <div className="text-sm text-slate-600">
                  {workloadData.period}
                  {workloadData.total_assignments > 0 && (
                    <span className="ml-2 font-semibold">
                      總工單數：{workloadData.total_assignments}
                    </span>
                  )}
                </div>
              </div>

              {workloadLoading ? (
                <div className="text-center py-16">
                  <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
                  <p className="mt-4 text-slate-400">載入中...</p>
                </div>
              ) : workloadData.staff_stats.length > 0 ? (
                <>
                  <ResponsiveContainer width="100%" height={380}>
                    <BarChart data={workloadData.staff_stats}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                      <XAxis
                        dataKey="name"
                        tick={{ fontSize: 13 }}
                        stroke="#64748b"
                      />
                      <YAxis
                        tick={{ fontSize: 13 }}
                        stroke="#64748b"
                        label={{
                          value: "工單數",
                          angle: -90,
                          position: "insideLeft",
                        }}
                      />
                      <Tooltip
                        content={({ active, payload }) => {
                          if (active && payload && payload.length) {
                            const data = payload[0].payload;
                            return (
                              <div className="bg-white p-4 rounded-lg shadow-lg border border-slate-200">
                                <p className="font-semibold text-slate-800 text-lg">
                                  {data.name}
                                </p>
                                <p className="text-sm text-slate-600 mt-1">
                                  工單數：
                                  <span className="font-semibold">
                                    {data.count}
                                  </span>
                                </p>
                                <p className="text-sm text-slate-600">
                                  佔比：
                                  <span className="font-semibold">
                                    {data.percentage}%
                                  </span>
                                </p>
                                <p className="text-xs text-slate-400 mt-2 border-t pt-2">
                                  {data.count} /{" "}
                                  {workloadData.total_assignments} 筆工單
                                </p>
                              </div>
                            );
                          }
                          return null;
                        }}
                      />
                      <Bar dataKey="count" radius={[8, 8, 0, 0]}>
                        {workloadData.staff_stats.map((_, index) => (
                          <Cell
                            key={`cell-${index}`}
                            fill={[
                              "#3b82f6",
                              "#10b981",
                              "#8b5cf6",
                              "#f59e0b",
                              "#ef4444",
                              "#06b6d4",
                              "#ec4899",
                              "#84cc16",
                            ][index % 8]}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>

                  {/* 詳細數據表格 */}
                  <div className="mt-6 border-t pt-4">
                    <h4 className="font-semibold text-slate-700 mb-3">
                      詳細數據
                    </h4>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                      {workloadData.staff_stats.map((staff, index) => (
                        <div
                          key={index}
                          className="p-3 bg-slate-50 rounded-lg border border-slate-200"
                        >
                          <div className="font-semibold text-slate-800">
                            {staff.name}
                          </div>
                          <div className="text-2xl font-bold text-blue-600 mt-1">
                            {staff.count}
                          </div>
                          <div className="text-xs text-slate-500 mt-1">
                            佔比 {staff.percentage}%
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              ) : (
                <div className="text-center py-16 text-slate-400">
                  <p className="text-lg">📊 暫無工作分派資料</p>
                  <p className="text-sm mt-2">請確認資料庫中有配藥記錄</p>
                </div>
              )}

              <div className="mt-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
                <p className="text-sm text-blue-800">
                  <strong>📌 統計說明：</strong>
                  本統計以「工單號碼 (WorkOrder)」為單位，計算每位配藥人員負責的工單數量。
                  相同的 [工單號碼 + 配藥人員] 組合只計算一次。
                </p>
              </div>
            </Card>
          </div>
        )}

        {/* 衝突視圖 placeholder */}
        {currentView === "衝突" && (
          <Card className="p-10 text-center">
            <h3 className="text-xl font-semibold text-slate-800 mb-2">
              衝突管理功能開發中...
            </h3>
            <p className="text-sm text-slate-500">
              未來可在此顯示機台、配藥人員與時間資源的衝突檢查結果。
            </p>
          </Card>
        )}

          {/* ✅ Beads IPQC 資料視圖 */}
        {currentView === "Beads IPQC資料" && (
          <BeadsIPQCPage />
        )}

        {/* 滴定凍乾 e 工單資訊（8056） */}
        {currentView === "滴定凍乾e工單資訊" && (
          <div className="w-full h-[calc(100vh-140px)]">
              <iframe
                src="http://10.6.182.47:8056"
               className="w-full h-full border-0 rounded-xl shadow bg-transparent"
              />
          </div>
        )}

        {/* Beads 排程作業（8505） */}
        {currentView === "Beads 排程作業" && (
          <div className="w-full h-[calc(100vh-140px)]">
              <iframe
                src="http://10.6.182.47:8505"
                 className="w-full h-full border-0 rounded-xl shadow bg-transparent"
              />
          </div>
        )}

        {/* 工單 QR 掃描追蹤（8502） */}
        {currentView === "工單 QR 掃描追蹤" && (
          <div className="w-full h-[calc(100vh-140px)]">
           
              <iframe
                src="http://10.6.182.47:8502"
                className="w-full h-full border-0 rounded-xl shadow bg-transparent"
              />
          </div>
        )}

        {/* Footer */}
        <footer className="mt-6 pt-4 border-t border-slate-800/60">
          <div className="text-center space-y-1">
            <p className="text-xs text-slate-500 tracking-wide">
              © Skyla 2025 • BeadsOps 生產管理系統
            </p>
            <p className="text-[11px] text-slate-500">
              All Rights Reserved · Version 1.0.0
            </p>
          </div>
        </footer>
      </main>
    </div>
  );
}
