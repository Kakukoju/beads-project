import React, { useEffect, useState } from "react";
import { CalendarDays, Loader2, Languages, Type } from "lucide-react";
import { Card } from "./ui/Card";

/* =========================
 * Types
 * ========================= */

interface DropletRow {
    record_date?: string;
    marker?: string;
    lyophilizer?: string;
    quantity?: number;
    rd_dose_time?: string;
    plan_titrate_time?: string;
    plan_end_time?: string;
    work_order?: string;
    lyophilizer_max_qty?: number;
    titration_port?: string;
    syringe?: string;
    store_expiry?: string;
    store_temp?: string;
    store_light_protect?: string;
    titration_light_protect?: string;
    titration_stir?: string;
    titration_ice_bath?: string;
    titration_volume?: number;
    pump_needle?: string;
    drug_acquire_time?: string;
    titration_start_time?: string;
    titration_end_time?: string;
    available_lyophilizer?: string;
    remark?: string;
    pre_stir?: string;
    pre_cool_temp?: string;
    record_time?: string;
    id?: number;

    /* UI only */
    _isSeparator?: boolean;
    _isGroupTitle?: boolean;
    _groupKey?: string;
}

type HeaderMode = 'default' | 'zh' | 'en';

/* =========================
 * Dictionary
 * ========================= */
const COLUMN_CONFIG = [
    { key: "port",        default: "Port",      zh: "滴定Port",  en: "Port",         width: "w-[80px]" },
    { key: "marker",      default: "Marker",    zh: "Beads",     en: "Beads",         width: "w-[120px]" },
    { key: "lyophilizer", default: "Lyophilizer", zh: "凍乾機",  en: "Lyophilizer" },
    { key: "qty",         default: "Qty",       zh: "數量",      en: "Quantity" },
    { key: "rd",          default: "R&D",       zh: "給藥時間",  en: "R&D Time" },
    { key: "plan_start",  default: "Plan Start", zh: "預計開始", en: "Plan Start" },
    { key: "plan_end",    default: "Plan End",  zh: "預計結束",  en: "Plan End" },
    { key: "workorder",   default: "WorkOrder", zh: "工單",      en: "Work Order" },
    { key: "pump_needle", default: "Needle",    zh: "針頭",      en: "Needle" },   // ✅ DB: pump_needle
    { key: "syringe",     default: "Pump No.",  zh: "Pump No.",  en: "Pump No." }, // ✅ DB: syringe
    { key: "store_temp",  default: "Store Temp", zh: "儲存溫度", en: "Store Temp" },
    { key: "store_light", default: "Store Light", zh: "儲存避光", en: "Store Light" },
    { key: "titr_light",  default: "Titr Light", zh: "滴定避光", en: "Titr Light" },
    { key: "stir",        default: "Stir",      zh: "攪拌",      en: "Stir" },
    { key: "ice",         default: "Ice",       zh: "冰浴",      en: "Ice Bath" },
    { key: "pre_stir",    default: "Pre Stir",  zh: "預攪拌",    en: "Pre Stir" },
    { key: "pre_cool",    default: "Pre Cool",  zh: "預冷溫度",  en: "Pre Cool Temp" },
    { key: "vol",         default: "Vol",       zh: "體積",      en: "Volume" },
    { key: "acquire",     default: "Acquire",   zh: "領藥時間",  en: "Acquire Time" },
    { key: "start",       default: "Start",     zh: "滴定開始",  en: "Start Time" },
    { key: "end",         default: "End",       zh: "滴定結束",  en: "End Time" },
    { key: "remark",      default: "Remark",    zh: "備註",      en: "Remark" },
];

/* =========================
 * Utils
 * ========================= */

const todayStr = () => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
        d.getDate()
    ).padStart(2, "0")}`;
};

const getGroupKey = (marker?: string) => {
    if (!marker) return "";
    return marker.split("-")[0];
};

/* =========================
 * Component
 * ========================= */

export default function DropletCondition() {
    const [date, setDate] = useState(todayStr());
    const [rows, setRows] = useState<DropletRow[]>([]);
    const [loading, setLoading] = useState(false);
    
    const [headerMode, setHeaderMode] = useState<HeaderMode>('zh');

    const fetchData = async (d: string) => {
        setLoading(true);
        try {
            const res = await fetch(`/api/droplet-records?date=${d}`);
            const data = await res.json();

            const raw: DropletRow[] = data.rows || [];

            const ivekRows = raw.filter(r => r.titration_port === "IVEK");
            const normalRows = raw
                .filter(r => r.titration_port !== "IVEK")
                .sort((a, b) => {
                    const aHasRD = !!a.rd_dose_time;
                    const bHasRD = !!b.rd_dose_time;
                    if (aHasRD !== bHasRD) return aHasRD ? -1 : 1;

                    const aHasWO = !!a.work_order;
                    const bHasWO = !!b.work_order;
                    if (aHasWO !== bHasWO) return aHasWO ? -1 : 1;

                    if (a.rd_dose_time && b.rd_dose_time) {
                        return a.rd_dose_time.localeCompare(b.rd_dose_time);
                    }
                    return 0;
                });

            const displayRows: DropletRow[] = [];
            let lastGroup: string | null = null;

            normalRows.forEach((r) => {
                const group = getGroupKey(r.marker);

                if (group !== lastGroup) {
                    displayRows.push({
                        _isGroupTitle: true,
                        _groupKey: group,
                    });
                    displayRows.push({
                        _isSeparator: true,
                    });
                }
                displayRows.push(r);
                lastGroup = group;
            });

            setRows([...ivekRows, ...displayRows]);
        } catch (e) {
            console.error("DropletCondition fetch failed", e);
            setRows([]);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData(date);
    }, [date]);

    const getHeaderText = (col: typeof COLUMN_CONFIG[0]) => {
        if (headerMode === 'zh') return col.zh;
        if (headerMode === 'en') return col.en;
        return col.default;
    };

    // 計算剩餘欄位數量 (總欄位 - 前2個固定欄位)
    const REST_COL_SPAN = COLUMN_CONFIG.length - 2;

    return (
        <Card className="p-4 space-y-2 h-full flex flex-col">
            {/* Header Control Area */}
            <div className="flex items-center justify-between mb-2 flex-shrink-0">
                <div className="flex items-center gap-4">
                    <h3 className="text-xl font-semibold text-slate-200 flex items-center gap-2">
                        <CalendarDays className="text-blue-400" />
                        滴定條件表
                    </h3>
                    
                    <div className="flex bg-slate-800 rounded-md p-1 border border-slate-700">
                        <button 
                            onClick={() => setHeaderMode('default')}
                            className={`px-3 py-1 text-xs rounded transition-colors ${headerMode === 'default' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-slate-200'}`}
                        >
                            Original
                        </button>
                        <button 
                            onClick={() => setHeaderMode('zh')}
                            className={`px-3 py-1 text-xs rounded transition-colors flex items-center gap-1 ${headerMode === 'zh' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-slate-200'}`}
                        >
                            <Languages size={12} /> 中文
                        </button>
                        <button 
                            onClick={() => setHeaderMode('en')}
                            className={`px-3 py-1 text-xs rounded transition-colors flex items-center gap-1 ${headerMode === 'en' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-slate-200'}`}
                        >
                            <Type size={12} /> English
                        </button>
                    </div>
                </div>

                <input
                    type="date"
                    value={date}
                    onChange={(e) => setDate(e.target.value)}
                    className="px-3 py-1.5 bg-slate-800 border border-slate-600 rounded text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
            </div>

            {loading ? (
                <div className="flex justify-center py-20 text-slate-400">
                    <Loader2 className="animate-spin mr-2" />
                    載入中…
                </div>
            ) : (
                <div className="overflow-auto border border-slate-700 rounded-md max-h-[75vh] relative isolate">
                    <table className="min-w-max text-xs border-collapse whitespace-nowrap">
                        <thead className="bg-slate-950 sticky top-0 z-40 shadow-lg ring-1 ring-blue-500/50">
                            <tr>
                                {COLUMN_CONFIG.map((col, index) => {
                                    let stickyClass = "";
                                    let zIndex = "z-20"; 
                                    
                                    if (index === 0) {
                                        stickyClass = "sticky left-0 bg-slate-950 border-r border-slate-700 shadow-[2px_0_5px_-2px_rgba(0,0,0,0.5)]";
                                        zIndex = "z-50"; 
                                    } 
                                    else if (index === 1) {
                                        stickyClass = "sticky left-[80px] bg-slate-950 border-r border-slate-700 shadow-[2px_0_5px_-2px_rgba(0,0,0,0.5)]";
                                        zIndex = "z-50"; 
                                    }

                                    return (
                                        <th 
                                            key={col.key} 
                                            className={`px-2 py-3 text-left text-white font-bold border-b border-blue-500/50 ${stickyClass} ${col.width || ''} ${zIndex}`}
                                        >
                                            {getHeaderText(col)}
                                        </th>
                                    );
                                })}
                            </tr>
                        </thead>

                        <tbody className="bg-slate-900/50">
                            {rows.map((r, idx) => {
                                // 1. 分組標題 (Group Title)
                                if (r._isGroupTitle) {
                                    return (
                                        <tr key={`title-${idx}`}>
                                            {/* FIXED: 拆分成兩個 TD
                                                TD1: 佔據 Port(80px) + Beads(120px) = 200px。固定在左側。
                                            */}
                                            <td 
                                                colSpan={2} 
                                                className="sticky left-0 z-30 px-2 py-1.5 text-sm font-semibold text-blue-300 bg-slate-900 border-t border-slate-700 w-[200px] max-w-[200px]"
                                            >
                                                ▸ {r._groupKey}
                                            </td>
                                            
                                            {/* TD2: 佔據剩餘欄位，隨資料捲動。背景色保持一致，確保視覺上像是一整列 */}
                                            <td 
                                                colSpan={REST_COL_SPAN} 
                                                className="px-2 py-1.5 bg-slate-900 border-t border-slate-700"
                                            >
                                                {/* 空白內容，僅作為背景延伸 */}
                                            </td>
                                        </tr>
                                    );
                                }

                                // 2. 分隔線 (Separator)
                                if (r._isSeparator) {
                                    return (
                                        <tr key={`sep-${idx}`}>
                                            {/* FIXED: 同樣拆分，確保分隔線在左側固定區也能顯示 */}
                                            <td 
                                                colSpan={2}
                                                className="sticky left-0 z-30 bg-slate-900 w-[200px]"
                                            >
                                                <div className="h-1 bg-slate-700/60" />
                                            </td>
                                            
                                            {/* 剩餘部分的分隔線 */}
                                            <td colSpan={REST_COL_SPAN} className="bg-slate-900">
                                                <div className="h-1 bg-slate-700/60" />
                                            </td>
                                        </tr>
                                    );
                                }

                                return (
                                    <tr
                                        key={r.id ?? idx}
                                        className="hover:bg-slate-800/60 transition-colors border-b border-slate-800/50 last:border-0"
                                    >
                                        {/* Fixed Port (80px) */}
                                        <td className="px-2 py-1.5 font-mono text-blue-400 font-medium sticky left-0 z-30 bg-slate-900 border-r border-slate-700 w-[80px]">
                                            {r.titration_port}
                                        </td>
                                        
                                        {/* Fixed Beads (120px) */}
                                        <td className="px-2 py-1.5 font-semibold text-slate-200 sticky left-[80px] z-30 bg-slate-900 border-r border-slate-700 w-[120px]">
                                            {r.marker}
                                        </td>

                                        <td className="px-2 py-1.5">{r.lyophilizer}</td>
<td className="px-2 py-1.5 text-right font-mono text-slate-300">{r.quantity}</td>
<td className="px-2 py-1.5 font-mono text-amber-200/80">{r.rd_dose_time}</td>
<td className="px-2 py-1.5 font-mono">{r.plan_titrate_time}</td>
<td className="px-2 py-1.5 font-mono">{r.plan_end_time}</td>
<td className="px-2 py-1.5 font-mono text-slate-400">{r.work_order}</td>
<td className="px-2 py-1.5">{r.pump_needle}</td>  {/* ✅ 針頭 */}
<td className="px-2 py-1.5">{r.syringe}</td>       {/* ✅ Pump No. */}
<td className="px-2 py-1.5 text-center">{r.store_temp}</td>
<td className="px-2 py-1.5 text-center">{r.store_light_protect}</td>
<td className="px-2 py-1.5 text-center">{r.titration_light_protect}</td>
<td className="px-2 py-1.5 text-center">{r.titration_stir}</td>
<td className="px-2 py-1.5 text-center">{r.titration_ice_bath}</td>
<td className="px-2 py-1.5 text-center">{r.pre_stir}</td>
<td className="px-2 py-1.5 text-center">{r.pre_cool_temp}</td>
<td className="px-2 py-1.5 text-right">{r.titration_volume}</td>
<td className="px-2 py-1.5 font-mono">{r.drug_acquire_time}</td>
<td className="px-2 py-1.5 font-mono text-emerald-300">{r.titration_start_time}</td>
<td className="px-2 py-1.5 font-mono text-emerald-300">{r.titration_end_time}</td>
<td className="px-2 py-1.5 text-slate-400">{r.remark}
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            )}
        </Card>
    );
}