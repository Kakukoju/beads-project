import React, { useEffect, useState } from "react";
import { CalendarDays, Loader2 } from "lucide-react";
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

    const fetchData = async (d: string) => {
        setLoading(true);
        try {
            const res = await fetch(`/api/droplet-records?date=${d}`);
            const data = await res.json();

            const raw: DropletRow[] = data.rows || [];

            /** 1️⃣ IVEK 固定置頂 */
            const ivekRows = raw.filter(r => r.titration_port === "IVEK");
            const normalRows = raw
                .filter(r => r.titration_port !== "IVEK")
                .sort((a, b) => {
                    const aHasRD = !!a.rd_dose_time;
                    const bHasRD = !!b.rd_dose_time;

                    // ① 沒有 R&D dose time → 往後
                    if (aHasRD !== bHasRD) {
                        return aHasRD ? -1 : 1;
                    }

                    const aHasWO = !!a.work_order;
                    const bHasWO = !!b.work_order;

                    // ② 沒有 WorkOrder → 再往後
                    if (aHasWO !== bHasWO) {
                        return aHasWO ? -1 : 1;
                    }

                    // ③ 兩個都有 rd_dose_time → 比時間
                    if (a.rd_dose_time && b.rd_dose_time) {
                        return a.rd_dose_time.localeCompare(b.rd_dose_time);
                    }

                    return 0;
                });


            /** 2️⃣ group 分組 + title + bar */
            const displayRows: DropletRow[] = [];
            let lastGroup: string | null = null;

            normalRows.forEach((r) => {
                const group = getGroupKey(r.marker);

                if (group !== lastGroup) {
                    // group title
                    displayRows.push({
                        _isGroupTitle: true,
                        _groupKey: group,
                    });

                    // separator bar
                    displayRows.push({
                        _isSeparator: true,
                    });
                }

                displayRows.push(r);
                lastGroup = group;
            });

            setRows([
                ...ivekRows,
                ...displayRows,
            ]);
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

    return (
        <Card className="p-6 space-y-4">
            {/* Header */}
            <div className="flex items-center justify-between">
                <h3 className="text-xl font-semibold text-slate-200 flex items-center gap-2">
                    <CalendarDays className="text-blue-400" />
                    滴定條件表
                </h3>

                <input
                    type="date"
                    value={date}
                    onChange={(e) => setDate(e.target.value)}
                    className="px-3 py-1.5 bg-slate-800 border border-slate-600 rounded text-slate-200"
                />
            </div>

            {/* Table */}
            {loading ? (
                <div className="flex justify-center py-20 text-slate-400">
                    <Loader2 className="animate-spin mr-2" />
                    載入中…
                </div>
            ) : (
                <div className="overflow-x-auto">
                    <table className="min-w-full text-xs border-collapse">
                        <thead className="bg-slate-800 sticky top-0 z-10">
                            <tr>
                                {[
                                    "Port", "Marker", "Lyophilizer", "Qty", "R&D",
                                    "Plan Start", "Plan End", "WorkOrder",
                                    "Needle", "Syringe", "Store Temp", "Store Light",
                                    "Titr Light", "Stir", "Ice", "Vol",
                                    "Acquire", "Start", "End", "Remark"
                                ].map(h => (
                                    <th key={h} className="px-2 py-2 text-left text-slate-300 border-b border-slate-700 whitespace-nowrap">
                                        {h}
                                    </th>
                                ))}
                            </tr>
                        </thead>

                        <tbody>
                            {rows.map((r, idx) => {
                                /** group title */
                                if (r._isGroupTitle) {
                                    return (
                                        <tr key={`title-${idx}`}>
                                            <td colSpan={20} className="px-2 py-2 text-sm font-semibold text-blue-300 bg-slate-900">
                                                ▸ {r._groupKey}
                                            </td>
                                        </tr>
                                    );
                                }

                                /** separator bar */
                                if (r._isSeparator) {
                                    return (
                                        <tr key={`sep-${idx}`}>
                                            <td colSpan={20}>
                                                <div className="h-3 bg-slate-700/60" />
                                            </td>
                                        </tr>
                                    );
                                }

                                /** normal row */
                                return (
                                    <tr
                                        key={r.id ?? idx}
                                        className="hover:bg-slate-800/40"
                                    >
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
<td className="px-2 py-1.5 text-slate-400">{r.remark}</td>
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
