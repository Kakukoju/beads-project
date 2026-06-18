import React, { useState, useEffect } from 'react';
import {
    ComposedChart, // 改用 ComposedChart 以支援雙軸 (Bar + Line)
    Bar,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
    Cell
} from "recharts";
// 🔴 加入 Activity 和 History
import {
    FlaskConical,
    AlertTriangle,
    CheckCircle2,
    Clock,
    Calendar,
    Activity,
    History
} from 'lucide-react';


// 共用 Card 樣式
const Card = ({ children, className = "", title }: { children: React.ReactNode; className?: string; title?: string }) => (
    <div className={`bg-slate-800/50 backdrop-blur-md border border-slate-700/50 rounded-xl p-5 shadow-lg relative overflow-hidden ${className}`}>
        <div className="absolute -top-10 -right-10 w-32 h-32 bg-teal-500/10 rounded-full blur-3xl pointer-events-none"></div>
        {title && <h3 className="text-slate-300 text-lg font-medium mb-4 flex items-center gap-2">{title}</h3>}
        {children}
    </div>
);

const TitrationStatistic = () => {
    const [loading, setLoading] = useState(false);
    const [statsData, setStatsData] = useState<any[]>([]);
    const [kpi, setKpi] = useState({
        total_machines: 13,
        avg_utilization: 0,
        in_use_count: 0,
        daily_batches: 0,
    });

    // 🆕 新增這個狀態來存儲週/月統計
    const [periodStats, setPeriodStats] = useState({
        weekly: {
            active_days: 0,
            ports: { util: 0, idle: 0 },
            ivek: { util: 0, idle: 0 }
        },
        monthly: {
            active_days: 0,
            ports: { util: 0, idle: 0 },
            ivek: { util: 0, idle: 0 }
        }
    });

    // 🔴 修改 1: 移除 dateOptions，改為直接設定預設日期 (預設昨天)
    const [selectedDate, setSelectedDate] = useState(() => {
        const d = new Date();
        d.setDate(d.getDate() - 1);
        // HTML date input 需要 YYYY-MM-DD 格式
        return d.toISOString().split('T')[0];
    });

    // 取得數據
    useEffect(() => {
        if (!selectedDate) return;

        const fetchData = async () => {
            setLoading(true);
            try {
                // 🔴 錯誤原因：原本寫成這樣 (相對路徑)，瀏覽器會去問 localhost:5173
                // const res = await fetch(`/api/titration/stats?date=${selectedDate}`);

                // ✅ 修正：必須加上 "http://10.6.182.47:5001"，瀏覽器才會去問 Python 後端
                const apiUrl = `/api/titration/stats?date=${selectedDate}`;

                console.log("正在從這裡抓資料:", apiUrl);

                const res = await fetch(apiUrl);
                const data = await res.json();

                if (data.ok) {
                    setStatsData(data.data);
                    setKpi(data.kpi);
                }
            } catch (err) {
                console.error("Failed to fetch titration stats", err);
            } finally {
                setLoading(false);
            }
        };

        fetchData();
    }, [selectedDate]);

    useEffect(() => {
        const fetchPeriodStats = async () => {
            try {
                const res = await fetch("/api/titration/period_stats");
                const data = await res.json();
                if (data.ok) {
                    setPeriodStats({
                        weekly: data.weekly,
                        monthly: data.monthly
                    });
                }
            } catch (err) {
                console.error("Failed to fetch period stats", err);
            }
        };
        fetchPeriodStats();
    }, []); // 只需執行一次

    return (
        <div className="space-y-6 animate-in fade-in duration-500 pb-10">

            {/* 控制列：日期選擇 */}
            <div className="flex justify-between items-center bg-slate-800/30 p-4 rounded-lg border border-slate-700">
                <div className="flex items-center gap-2">
                    <h2 className="text-xl font-bold text-slate-200">滴定機稼動統計</h2>
                    {loading && <span className="text-xs text-blue-400 animate-pulse">載入中...</span>}
                </div>
                <div className="flex items-center gap-2">
                    <Calendar size={18} className="text-slate-400" />

                    {/* 🔴 修改 2: 將 select 改為 input type="date" */}
                    <input
                        type="date"
                        value={selectedDate}
                        onChange={(e) => setSelectedDate(e.target.value)}
                        // 加入 [color-scheme:dark] 讓瀏覽器內建的日曆彈窗變成深色風格
                        className="bg-slate-700 text-white border border-slate-600 rounded px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 outline-none [color-scheme:dark] cursor-pointer"
                    />
                </div>
            </div>

            {/* 頂部 KPI 卡片 */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <Card className="bg-gradient-to-br from-slate-800 to-slate-900 border-l-4 border-l-teal-500">
                    <div className="flex items-center gap-4">
                        <div className="p-3 bg-teal-500/10 rounded-full text-teal-400">
                            <FlaskConical size={24} />
                        </div>
                        <div>
                            <div className="text-slate-400 text-xs uppercase tracking-wider">總機台數</div>
                            <div className="text-2xl font-bold text-white font-mono">{kpi.total_machines} <span className="text-sm font-normal text-slate-500">台</span></div>
                        </div>
                    </div>
                </Card>
                <Card className="bg-gradient-to-br from-slate-800 to-slate-900 border-l-4 border-l-green-500">
                    <div className="flex items-center gap-4">
                        <div className="p-3 bg-green-500/10 rounded-full text-green-400">
                            <CheckCircle2 size={24} />
                        </div>
                        <div>
                            <div className="text-slate-400 text-xs uppercase tracking-wider">平均稼動率</div>
                            <div className={`text-2xl font-bold font-mono ${kpi.avg_utilization > 80 ? 'text-green-400' : 'text-amber-400'}`}>
                                {kpi.avg_utilization}%
                            </div>
                        </div>
                    </div>
                </Card>
                <Card className="bg-gradient-to-br from-slate-800 to-slate-900 border-l-4 border-l-blue-500">
                    <div className="flex items-center gap-4">
                        <div className="p-3 bg-blue-500/10 rounded-full text-blue-400">
                            <Clock size={24} />
                        </div>
                        <div>
                            {/* 🔴 修改標題 */}
                            <div className="text-slate-400 text-xs uppercase tracking-wider">當日生產批次</div>
                            {/* 🔴 修改綁定的數據為 kpi.daily_batches */}
                            <div className="text-2xl font-bold text-blue-400 font-mono">
                                {kpi.daily_batches} <span className="text-sm font-normal text-slate-500">批</span>
                            </div>
                        </div>
                    </div>
                </Card>
                {/* 4. 週/月稼動統計 (取代原本的今日使用中) */}
                {/* 卡片 4: 週期平均 (Ports / IVEK 分開顯示) */}
                <Card className="bg-gradient-to-br from-slate-800 to-slate-900 border-l-4 border-l-purple-500">
                    <div className="flex flex-col justify-center h-full gap-3 text-sm">

                        {/* --- 上半部：近 7 日 --- */}
                        <div className="border-b border-slate-700/50 pb-2">
                            <div className="flex items-center gap-2 mb-2">
                                <div className="p-1.5 bg-purple-500/10 rounded text-purple-400">
                                    <Activity size={16} />
                                </div>
                                <span className="text-slate-300 font-bold">近 7 日</span>
                                <span className="text-[10px] text-slate-500 bg-slate-800 px-1.5 rounded">
                                    實動 {periodStats.weekly.active_days} 天
                                </span>
                            </div>

                            {/* Ports 數據 */}
                            <div className="flex justify-between items-center pl-2 mb-1">
                                <span className="text-slate-400 text-xs">Ports (12台)</span>
                                <div>
                                    <span className="text-purple-300 font-bold font-mono">{periodStats.weekly.ports.util}%</span>
                                    <span className="text-[10px] text-slate-500 ml-1">閒 {periodStats.weekly.ports.idle}h</span>
                                </div>
                            </div>
                            {/* IVEK 數據 */}
                            <div className="flex justify-between items-center pl-2">
                                <span className="text-slate-400 text-xs">IVEK (1台)</span>
                                <div>
                                    <span className="text-purple-300 font-bold font-mono">{periodStats.weekly.ivek.util}%</span>
                                    <span className="text-[10px] text-slate-500 ml-1">閒 {periodStats.weekly.ivek.idle}h</span>
                                </div>
                            </div>
                        </div>

                        {/* --- 下半部：近 30 日 --- */}
                        <div className="pt-1">
                            <div className="flex items-center gap-2 mb-2">
                                <div className="p-1.5 bg-indigo-500/10 rounded text-indigo-400">
                                    <History size={16} />
                                </div>
                                <span className="text-slate-300 font-bold">近 30 日</span>
                                <span className="text-[10px] text-slate-500 bg-slate-800 px-1.5 rounded">
                                    實動 {periodStats.monthly.active_days} 天
                                </span>
                            </div>

                            {/* Ports 數據 */}
                            <div className="flex justify-between items-center pl-2 mb-1">
                                <span className="text-slate-400 text-xs">Ports</span>
                                <div>
                                    <span className="text-indigo-300 font-bold font-mono">{periodStats.monthly.ports.util}%</span>
                                    <span className="text-[10px] text-slate-500 ml-1">閒 {periodStats.monthly.ports.idle}h</span>
                                </div>
                            </div>
                            {/* IVEK 數據 */}
                            <div className="flex justify-between items-center pl-2">
                                <span className="text-slate-400 text-xs">IVEK</span>
                                <div>
                                    <span className="text-indigo-300 font-bold font-mono">{periodStats.monthly.ivek.util}%</span>
                                    <span className="text-[10px] text-slate-500 ml-1">閒 {periodStats.monthly.ivek.idle}h</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </Card>
            </div>

            {/* 主要圖表區 */}
            <div className="grid grid-cols-1 gap-6">
                <div className="col-span-1">
                    <Card title={`各機台稼動率與閒置時間統計 (${selectedDate})`} className="h-[500px]">
                        {statsData.length > 0 ? (
                            <ResponsiveContainer width="100%" height="100%">
                                <ComposedChart data={statsData} margin={{ top: 20, right: 30, left: 20, bottom: 40 }}>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />

                                    {/* X軸：機台名稱 */}
                                    <XAxis
                                        dataKey="name"
                                        stroke="#94a3b8"
                                        angle={-45}
                                        textAnchor="end"
                                        height={60}
                                        tick={{ fontSize: 12 }}
                                    />

                                    {/* Y1軸：稼動率 (左) */}
                                    <YAxis
                                        yAxisId="left"
                                        stroke="#2dd4bf"
                                        label={{ value: '稼動率 (%)', angle: -90, position: 'insideLeft', fill: '#2dd4bf' }}
                                        domain={[0, 100]}
                                    />

                                    {/* Y2軸：閒置時間 (右) */}
                                    <YAxis
                                        yAxisId="right"
                                        orientation="right"
                                        stroke="#f43f5e"
                                        label={{ value: '閒置時間 (hrs)', angle: 90, position: 'insideRight', fill: '#f43f5e' }}
                                    />

                                    <Tooltip
                                        contentStyle={{ backgroundColor: '#1e293b', borderColor: '#475569', color: '#f8fafc' }}
                                        formatter={(value: any, name: string) => {
                                            if (name === "稼動率") return [`${value}%`, name];
                                            if (name === "閒置時間") return [`${value} hrs`, name];
                                            return [value, name];
                                        }}
                                    />
                                    <Legend wrapperStyle={{ paddingTop: '10px' }} />

                                    {/* Bar: 稼動率 */}
                                    <Bar yAxisId="left" dataKey="utilization" name="稼動率" barSize={30} radius={[4, 4, 0, 0]}>
                                        {statsData.map((entry, index) => (
                                            <Cell key={`cell-${index}`} fill={entry.status === 'Running' ? '#3b82f6' : '#2dd4bf'} />
                                        ))}
                                    </Bar>

                                    {/* Line: 閒置時間 (紅色線) */}
                                    <Line
                                        yAxisId="right"
                                        type="monotone"
                                        dataKey="idleHours"
                                        name="閒置時間"
                                        stroke="#f43f5e"
                                        strokeWidth={3}
                                        dot={{ r: 4, fill: '#f43f5e' }}
                                    />
                                </ComposedChart>
                            </ResponsiveContainer>
                        ) : (
                            <div className="flex flex-col items-center justify-center h-full text-slate-500">
                                <FlaskConical size={48} className="mb-4 opacity-20" />
                                <p>查無此日期的排程或紀錄數據</p>
                            </div>
                        )}
                    </Card>
                </div>
            </div>

            {/* 底部說明 */}
            <div className="bg-blue-900/20 border border-blue-500/30 rounded-lg p-4 text-xs text-blue-200">
                <strong>💡 統計說明：</strong>
                <ul className="list-disc pl-5 mt-1 space-y-1 text-slate-400">
                    <li><strong>每日總可用時數：</strong>設定為 15 小時 (09:00 ~ 24:00)。</li>
                    <li><strong>稼動率計算：</strong> ( 實際使用時數 / 15 ) × 100%。</li>
                    <li><strong>閒置時間：</strong> 15 - 實際使用時數。若使用超過15小時則閒置為0。</li>
                    <li><strong>資料來源：</strong> 排程表 (P01_formualte_schedule.db) 與 實際作業紀錄 (work_orders.db)。</li>
                    <li><strong>數據寫回：</strong> 系統會自動計算閒置時間並寫回 work_orders 資料庫。</li>
                </ul>
            </div>
        </div>
    );
};

export default TitrationStatistic;