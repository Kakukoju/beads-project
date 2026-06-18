import React, { useState, useEffect } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

// Card 組件
interface CardProps {
  children: React.ReactNode;
  className?: string;
}

function Card({ children, className = "" }: CardProps) {
  return (
    <div className={`rounded-lg border border-slate-100 bg-white text-slate-900 shadow-sm ${className}`}>
      {children}
    </div>
  );
}

// Beads IPQC 頁面組件
export default function BeadsIPQCPage() {
  // ===== Tabs：OD / CV 趨勢 =====
  const [activeTab, setActiveTab] = useState("OD");

  // ===== OD 趨勢圖狀態 =====
  const [odYear, setOdYear] = useState(new Date().getFullYear());
  const [odMonth, setOdMonth] = useState<number | null>(new Date().getMonth() + 1);
  const [odWeekly, setOdWeekly] = useState<string | null>(null);
  const [odMarker, setOdMarker] = useState("");
  const [odData, setOdData] = useState([]);
  const [odLoading, setOdLoading] = useState(false);

  // ===== CV 趨勢圖狀態 =====
  const [cvYear, setCvYear] = useState(new Date().getFullYear());
  const [cvMonth, setCvMonth] = useState<number | null>(new Date().getMonth() + 1);
  const [cvWeekly, setCvWeekly] = useState<string | null>(null);
  const [cvMarker, setCvMarker] = useState("");
  const [cvData, setCvData] = useState([]);
  const [cvLoading, setCvLoading] = useState(false);
  const [cvType, setCvType] = useState("OD_CV");

  // ===== 共用下拉選項 =====
  const [availableYears, setAvailableYears] = useState([]);
  const [weeklyList, setWeeklyList] = useState([]);
  const [markerList, setMarkerList] = useState([]);

  // 月份選項
  const monthOptions = [
    { value: null, label: "全部" },
    ...Array.from({ length: 12 }, (_, i) => ({
      value: i + 1,
      label: `${i + 1}月`,
    })),
  ];

 // ===== 初始化：載入年份列表 =====
  useEffect(() => {
    const fetchYears = async () => {
      try {
        const response = await fetch("/api/beads-ipqc/available-years");
        const data = await response.json();

        if (data.ok && data.years.length > 0) {
          setAvailableYears(data.years);
          if (!data.years.includes(odYear)) {
            setOdYear(data.years[0]);
            setCvYear(data.years[0]);
          }
        }
      } catch (err) {
        console.error("載入年份失敗:", err);
      }
    };

    fetchYears();
  }, []);

  // 載入週別列表（依 OD 年份，同步用）
  useEffect(() => {
    const fetchWeeklyList = async () => {
      try {
        const response = await fetch(`/api/beads-ipqc/weekly-list?year=${odYear}`);
        const data = await response.json();

        if (data.ok) {
          setWeeklyList(data.weekly_list || []);
        }
      } catch (err) {
        console.error("載入週別列表失敗:", err);
      }
    };

    if (odYear) {
      fetchWeeklyList();
      setCvYear(odYear); // 同步 CV 年份
    }
  }, [odYear]);

  // 載入 Marker 列表（當年份改變時）
  useEffect(() => {
    const fetchMarkerList = async () => {
      try {
        const response = await fetch(`/api/beads-ipqc/marker-list?year=${odYear}`);
        const data = await response.json();

        if (data.ok && data.marker_list.length > 0) {
          setMarkerList(data.marker_list);
          if (!odMarker) {
            setOdMarker(data.marker_list[0]);
          }
          if (!cvMarker) {
            setCvMarker(data.marker_list[0]);
          }
        }
      } catch (err) {
        console.error("載入 Marker 列表失敗:", err);
      }
    };

    if (odYear) {
      fetchMarkerList();
    }
  }, [odYear]);

  // ===== 載入 OD 趨勢數據 =====
  useEffect(() => {
    const fetchOdData = async () => {
      if (!odMarker) return;

      try {
        setOdLoading(true);

        const params = new URLSearchParams({
          year: odYear.toString(),
          marker: odMarker,
        });

        if (odMonth) {
          params.append("month", odMonth.toString());
        }

        if (odWeekly) {
          params.append("weekly", odWeekly);
        }

        const response = await fetch(`/api/beads-ipqc/od-trend-data?${params}`);
        const data = await response.json();

        if (data.ok) {
          setOdData(data.data || []);
        }
      } catch (err) {
        console.error("載入 OD 趨勢數據失敗:", err);
      } finally {
        setOdLoading(false);
      }
    };

    fetchOdData();
  }, [odYear, odMonth, odWeekly, odMarker]);

  // ===== 載入 CV 趨勢數據（含 SPEC）=====
  useEffect(() => {
    const fetchCvData = async () => {
      if (!cvMarker) return;

      try {
        setCvLoading(true);

        const params = new URLSearchParams({
          year: cvYear.toString(),
          marker: cvMarker,
          cv_type: cvType, // OD_CV 或 Conc_CV
        });

        if (cvMonth) params.append("month", cvMonth.toString());
        if (cvWeekly) params.append("weekly", cvWeekly);

        const response = await fetch(`/api/beads-ipqc/cv-trend-data?${params}`);
        const data = await response.json();

        if (data.ok) {
          const convert = (v: any) =>
            v === null || v === "" || v === undefined || v === " " ? null : Number(v);

          const spec_L1 = convert(data.spec_data?.L1_SPEC);
          const spec_L2 = convert(data.spec_data?.L2_SPEC);

          const fixed = (data.data || []).map((r: any) => ({
            ...r,
            // OD CV
            L1_OD_CV: convert(r.L1_OD_CV),
            L2_OD_CV: convert(r.L2_OD_CV),
            N1_OD_CV: convert(r.N1_OD_CV),
            N3_OD_CV: convert(r.N3_OD_CV),
            // Conc CV
            L1_Conc_CV: convert(r.L1_Conc_CV),
            L2_Conc_CV: convert(r.L2_Conc_CV),
            N1_Conc_CV: convert(r.N1_Conc_CV),
            N3_Conc_CV: convert(r.N3_Conc_CV),
            // SPEC（塞進每一筆）
            L1_SPEC: spec_L1,
            L2_SPEC: spec_L2,
          }));

          setCvData(fixed);
        }
      } catch (err) {
        console.error("載入 CV 趨勢數據失敗:", err);
      } finally {
        setCvLoading(false);
      }
    };

    fetchCvData();
  }, [cvYear, cvMonth, cvWeekly, cvMarker, cvType]);

  // ====== UI 開始 ======
  return (
    <div className="space-y-4"> {/* 縮小垂直間距 */}
      
      {/* Tabs 區域 - 已移除 border-b border-slate-200 (移除白線) */}
      <div>
        <nav className="flex gap-4">
          <button
            type="button"
            onClick={() => setActiveTab("OD")}
            className={`
              py-2 px-4 text-sm font-bold rounded-t-md border transition-all duration-200
              ${
                activeTab === "OD"
                  ? "bg-gray-900 border-blue-500 text-blue-400 border-b-black" // 啟用樣式
                  : "bg-black border-gray-700 text-gray-500 hover:border-gray-500 hover:text-gray-300" // 未啟用樣式
              }
            `}
          >
            OD 趨勢圖
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("CV")}
            className={`
              py-2 px-4 text-sm font-bold rounded-t-md border transition-all duration-200
              ${
                activeTab === "CV"
                  ? "bg-gray-900 border-blue-500 text-blue-400 border-b-black"
                  : "bg-black border-gray-700 text-gray-500 hover:border-gray-500 hover:text-gray-300"
              }
            `}
          >
            CV 趨勢圖
          </button>
        </nav>
      </div>

      {/* ===== Tab 內容：OD 趨勢 ===== */}
      {activeTab === "OD" && (
        <Card className="p-6">
          <h3 className="text-xl font-semibold text-slate-800 mb-4">Beads OD 趨勢圖</h3>

          {/* 過濾器 - 輸入框改為白底黑字 */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
            {/* 年份 */}
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1">年份</label>
              <select
                value={odYear}
                onChange={(e) => setOdYear(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-lg bg-white text-slate-900 border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                {availableYears.map((year) => (
                  <option key={year} value={year}>
                    {year}
                  </option>
                ))}
              </select>
            </div>

            {/* 月份 */}
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1">月份</label>
              <select
                value={odMonth || ""}
                onChange={(e) => setOdMonth(e.target.value ? Number(e.target.value) : null)}
                className="w-full px-3 py-2 rounded-lg bg-white text-slate-900 border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                {monthOptions.map((opt) => (
                  <option key={opt.label} value={opt.value || ""}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            {/* 週別 */}
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1">週別</label>
              <select
                value={odWeekly || ""}
                onChange={(e) => setOdWeekly(e.target.value || null)}
                className="w-full px-3 py-2 rounded-lg bg-white text-slate-900 border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="">全部</option>
                {weeklyList.map((w) => (
                  <option key={w} value={w}>
                    {w}
                  </option>
                ))}
              </select>
            </div>

            {/* Marker */}
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1">Marker</label>
              <select
                value={odMarker}
                onChange={(e) => setOdMarker(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-white text-slate-900 border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                {markerList.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* 當前過濾條件顯示 */}
          <div className="text-sm text-slate-600 mb-4">
            📊 顯示：{odYear} 年
            {odMonth && ` ${odMonth} 月`}
            {odWeekly && ` ${odWeekly}`}
            {odMarker && ` | Marker: ${odMarker}`}
            {odData.length > 0 && ` | 共 ${odData.length} 筆數據`}
          </div>

          {/* 圖表 */}
          {odLoading ? (
            <div className="text-center py-16">
              <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
              <p className="mt-4 text-slate-400">載入中...</p>
            </div>
          ) : odData.length > 0 ? (
            <ResponsiveContainer width="100%" height={400}>
              <LineChart data={odData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis
                  dataKey="batch"
                  tick={{ fontSize: 12 }}
                  stroke="#64748b"
                  angle={-45}
                  textAnchor="end"
                  height={80}
                />
                <YAxis
                  tick={{ fontSize: 12 }}
                  stroke="#64748b"
                  label={{ value: "OD 值", angle: -90, position: "insideLeft" }}
                />
                <Tooltip contentStyle={{ backgroundColor: '#fff', borderColor: '#e2e8f0', borderRadius: '8px' }} />
                <Legend verticalAlign="top" height={36} />
                <Line type="monotone" dataKey="L1_Mean_OD" stroke="#2563eb" strokeWidth={2} name="L1 Mean OD" dot={{ r: 4 }} />
                <Line type="monotone" dataKey="L2_Mean_OD" stroke="#0d9488" strokeWidth={2} name="L2 Mean OD" dot={{ r: 4 }} />
                <Line type="monotone" dataKey="N1_OD" stroke="#ca8a04" strokeWidth={2} name="N1 OD" dot={{ r: 4 }} />
                <Line type="monotone" dataKey="N3_OD" stroke="#7e22ce" strokeWidth={2} name="N3 OD" dot={{ r: 4 }} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-center py-16 text-slate-400">
              <p className="text-lg">📊 暫無 OD 趨勢資料</p>
            </div>
          )}
        </Card>
      )}

      {/* ===== Tab 內容：CV 趨勢 ===== */}
      {activeTab === "CV" && (
        <Card className="p-6">
          <h3 className="text-xl font-semibold text-slate-800 mb-4">Beads CV 趨勢圖</h3>

          {/* 過濾器 - 輸入框改為白底黑字 */}
          <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-6">
            {/* 年份 */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">年份</label>
              <select
                value={cvYear}
                onChange={(e) => setCvYear(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-lg bg-white text-slate-900 border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                {availableYears.map((year) => (
                  <option key={year} value={year}>
                    {year}
                  </option>
                ))}
              </select>
            </div>

            {/* 月份 */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">月份</label>
              <select
                value={cvMonth || ""}
                onChange={(e) => setCvMonth(e.target.value ? Number(e.target.value) : null)}
                className="w-full px-3 py-2 rounded-lg bg-white text-slate-900 border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                {monthOptions.map((opt) => (
                  <option key={opt.label} value={opt.value || ""}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            {/* 週別 */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">週別</label>
              <select
                value={cvWeekly || ""}
                onChange={(e) => setCvWeekly(e.target.value || null)}
                className="w-full px-3 py-2 rounded-lg bg-white text-slate-900 border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="">全部</option>
                {weeklyList.map((w) => (
                  <option key={w} value={w}>
                    {w}
                  </option>
                ))}
              </select>
            </div>

            {/* Marker */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Marker</label>
              <select
                value={cvMarker}
                onChange={(e) => setCvMarker(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-white text-slate-900 border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                {markerList.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>

            {/* CV 類型 */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">CV 類型</label>
              <select
                value={cvType}
                onChange={(e) => setCvType(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-white text-slate-900 border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="OD_CV">OD CV</option>
                <option value="Conc_CV">Conc. CV</option>
              </select>
            </div>
          </div>

          {/* 當前過濾條件顯示 */}
          <div className="text-sm text-slate-600 mb-4">
            📊 顯示：{cvYear} 年
            {cvMonth && ` ${cvMonth} 月`}
            {cvWeekly && ` ${cvWeekly}`}
            {cvMarker && ` | Marker: ${cvMarker}`}
            {` | 模式: ${cvType === "OD_CV" ? "OD CV" : "Conc. CV"}`}
            {cvData.length > 0 && ` | 共 ${cvData.length} 筆數據`}
          </div>

          {/* 圖表 */}
          {cvLoading ? (
            <div className="text-center py-16">
              <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
              <p className="mt-4 text-slate-400">載入中...</p>
            </div>
          ) : cvData.length > 0 ? (
            <ResponsiveContainer width="100%" height={400}>
              <LineChart data={cvData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis
                  dataKey="batch"
                  tick={{ fontSize: 12 }}
                  stroke="#64748b"
                  angle={-45}
                  textAnchor="end"
                  height={80}
                />
                <YAxis
                  tick={{ fontSize: 12 }}
                  stroke="#64748b"
                  label={{ value: "CV 值 (%)", angle: -90, position: "insideLeft" }}
                />
                <Tooltip contentStyle={{ backgroundColor: '#fff', borderColor: '#e2e8f0', borderRadius: '8px' }} />
                <Legend verticalAlign="top" height={36} />

                {cvType === "OD_CV" && (
                  <>
                    <Line type="monotone" dataKey="L1_OD_CV" stroke="#2563eb" strokeWidth={2} name="L1 OD CV" dot={{ r: 4 }} />
                    <Line type="monotone" dataKey="L2_OD_CV" stroke="#0d9488" strokeWidth={2} name="L2 OD CV" dot={{ r: 4 }} />
                    <Line type="monotone" dataKey="N1_OD_CV" stroke="#ca8a04" strokeWidth={2} name="N1 OD CV" dot={{ r: 4 }} />
                    <Line type="monotone" dataKey="N3_OD_CV" stroke="#0ea5e9" strokeWidth={2} name="N3 OD CV" dot={{ r: 4 }} />
                  </>
                )}

                {cvType === "Conc_CV" && (
                  <>
                    <Line type="monotone" dataKey="L1_Conc_CV" stroke="#2563eb" strokeWidth={2} name="L1 Conc CV" dot={{ r: 4 }} />
                    <Line type="monotone" dataKey="L2_Conc_CV" stroke="#0d9488" strokeWidth={2} name="L2 Conc CV" dot={{ r: 4 }} />
                    <Line type="monotone" dataKey="N1_Conc_CV" stroke="#ca8a04" strokeWidth={2} name="N1 Conc CV" dot={{ r: 4 }} />
                    <Line type="monotone" dataKey="N3_Conc_CV" stroke="#0ea5e9" strokeWidth={2} name="N3 Conc CV" dot={{ r: 4 }} />
                  </>
                )}

                <Line type="monotone" dataKey="L1_SPEC" stroke="#dc2626" strokeWidth={2} strokeDasharray="6 6" dot={false} name="L1 SPEC" />
                <Line type="monotone" dataKey="L2_SPEC" stroke="#dc2626" strokeWidth={2} strokeDasharray="6 6" dot={false} name="L2 SPEC" />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-center py-16 text-slate-400">
              <p className="text-lg">📊 暫無 CV 趨勢資料</p>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}