import { useEffect, useState } from "react";
import type {
    TitrationStatusResponse,
    Resource,
    TitrationJob,
} from "../types/ops";

/* =========================
 * Utils
 * ========================= */

function formatMin(min: number | null) {
    if (min == null) return "--";
    if (min < 60) return `${min} min`;
    const h = Math.floor(min / 60);
    const m = min % 60;
    return `${h}h ${m}m`;
}

function stateColor(state: Resource["state"]) {
    switch (state) {
        case "running":
            return "bg-red-500/20 text-red-400 border-red-500/40";
        case "idle":
            return "bg-yellow-500/20 text-yellow-400 border-yellow-500/40";
        case "finished":
            return "bg-green-500/20 text-green-400 border-green-500/40";
        default:
            return "bg-slate-700/40 text-slate-400 border-slate-600";
    }
}

/* =========================
 * Component
 * ========================= */

export default function TitrationIvekCard() {
    const [data, setData] = useState<TitrationStatusResponse | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchData = () => {
            fetch("/api/ops/titration-status")
                .then((r) => r.json())
                .then((d: TitrationStatusResponse) => {
                    setData(d);
                    setLoading(false);
                })
                .catch(() => setLoading(false));
        };

        fetchData();
        const intervalId = setInterval(fetchData, 10000);
        return () => clearInterval(intervalId);
    }, []);

    if (loading) {
        return (
            <div className="rounded-xl border border-slate-700 bg-slate-900 p-6 text-slate-400">
                Loading titration status...
            </div>
        );
    }

    if (!data) {
        return (
            <div className="rounded-xl border border-red-500/40 bg-red-500/10 p-6 text-red-400">
                Failed to load titration status
            </div>
        );
    }

    /* =========================
     * 資源拆分
     * ========================= */
    const ivek = data.resources.find((r) => r.id === "IVEK");

    // 計算總數
    const pumpsTotal = 12;
    // 透過 types/ops.ts 修正後，這裡的 r.type === "PORT" 不會再報錯
    const pumpsInUse = data.resources.filter(
        (r) => r.type === "PORT" && r.state === "running"
    ).length;
    const freePumps = Math.max(0, pumpsTotal - pumpsInUse);

    /* =========================
     * Render
     * ========================= */
    return (
        <div className="flex flex-col h-full rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 text-slate-100">
            
            {/* ===== Header ===== */}
            <div className="mb-4 flex flex-none items-center justify-between">
                <div className="flex items-center gap-2">
                    <h3 className="text-lg font-semibold">⚙️ 滴定 / IVEK 狀態</h3>
                    {/* 呼吸燈 */}
                    <span className="relative flex h-2 w-2">
                        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75"></span>
                        <span className="relative inline-flex h-2 w-2 rounded-full bg-green-500"></span>
                    </span>
                </div>

                {ivek?.todayUsed && (
                    <span className="rounded bg-red-600/20 px-2 py-0.5 text-xs text-red-400">
                        今日已用
                    </span>
                )}
            </div>

            {/* ===== Summary ===== */}
            <div className="mb-2 grid flex-none grid-cols-4 gap-2 text-xs">
                <div className="rounded bg-slate-800 p-2">
                    <div className="text-slate-400">Pumps Total</div>
                    <div className="text-xl font-semibold">{pumpsTotal}</div>
                </div>
                <div className="rounded bg-slate-800 p-2">
                    <div className="text-slate-400">In Use</div>
                    <div className="text-xl font-semibold text-red-400">
                        {pumpsInUse}
                    </div>
                </div>
                <div className="rounded bg-slate-800 p-2">
                    <div className="text-slate-400">Free</div>
                    <div className="text-xl font-semibold text-green-400">
                        {freePumps}
                    </div>
                </div>
                <div className="rounded bg-slate-800 p-2">
                    <div className="text-slate-400">Next Release</div>
                    <div className="text-xl font-semibold">
                        {formatMin(data.nextReleaseMin)}
                    </div>
                </div>
            </div>

            {/* ===== IVEK Card ===== */}
            {ivek && (
                <div className="mb-2 flex-none rounded border border-slate-700 bg-slate-800 p-2">
                    <div className="mb-1 flex items-center justify-between">
                        <span className="font-medium">IVEK</span>
                        <div className="flex items-center gap-2">
                            {/* 顯示 IVEK 剩餘時間 */}
                            {ivek.state === "running" && (
                                <span className="text-sm font-mono text-red-300">
                                    {formatMin(ivek.remainMin)}
                                </span>
                            )}
                            <span
                                className={`rounded border px-2 py-0.5 text-xs ${stateColor(
                                    ivek.state
                                )}`}
                            >
                                {ivek.state}
                            </span>
                        </div>
                    </div>
                    <div className="text-xs text-slate-400">
                        {ivek.currentJob
                            ? `工單 ${ivek.currentJob}`
                            : "無執行中工單"}
                    </div>
                </div>
            )}

            {/* ===== Pumps / Ports Grid ===== */}
            <div className="grid flex-none grid-cols-3 gap-2">
                {Array.from({ length: 12 }).map((_, i) => {
                    const portNo = i + 1;
                    const portId = `Port-${portNo.toString().padStart(2, "0")}`;

                    // 從 resources 找對應的 Port 物件
                    const resource = data.resources.find(
                        (r) => r.id === portId
                    );
                    const running = resource?.state === "running";

                    return (
                        <div
                            key={portId}
                            className={`rounded border p-2 text-xs ${
                                running
                                    ? "bg-red-500/20 text-red-400 border-red-500/40"
                                    : "bg-yellow-500/20 text-yellow-400 border-yellow-500/40"
                            }`}
                        >
                            <div className="flex justify-between font-medium">
                                <span>{portId}</span>
                                {/* 顯示 Port 剩餘時間 */}
                                {running && (
                                    <span className="font-mono">
                                        {formatMin(resource?.remainMin ?? null)}
                                    </span>
                                )}
                            </div>
                            <div className="mt-1 text-[11px] text-slate-400">
                                {running ? "running" : "idle"}
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* ===== Jobs List ===== */}
            {data.jobs.length > 0 && (
                <div className="mt-2 flex flex-1 flex-col overflow-hidden">
                    <div className="mb-1 flex-none text-sm font-semibold text-slate-300">
                        滴定中工單
                    </div>
                    <div className="flex-1 overflow-y-auto pr-1 space-y-2">
                        {data.jobs.map((j: TitrationJob) => (
                            <div
                                key={j.workOrder}
                                className="rounded border border-slate-700 bg-slate-800 p-3 text-sm"
                            >
                                <div className="flex justify-between">
                                    <span className="font-medium">
                                        {j.workOrder} · {j.marker}
                                    </span>
                                    <span className="text-red-400">
                                        {formatMin(j.remainMin)}
                                    </span>
                                </div>
                                <div className="mt-1 text-xs text-slate-400">
                                    Pumps: {[...new Set(j.pumps)].join(", ")} |
                                    Qty: {j.quantity}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}