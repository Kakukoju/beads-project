// =============================================
// TimetableView.tsx - 抽離後的獨立排程表模組
// =============================================

import { useState, useEffect } from "react";


// ---- ScheduleRow 型別（你提供的） ----
export interface ScheduleRow {
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

// ---- 排程表主組件 ----
export default function TimetableView() {
    // ----------------------------------------
    // 1. State 區域（你的全部 state 全抽出）
    // ----------------------------------------
    const [hoveredRow, setHoveredRow] = useState<number | null>(null);
    const [scheduleData, setScheduleData] = useState<ScheduleRow[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const [searchType, setSearchType] = useState<"week" | "date">("week");
    const [searchWeek, setSearchWeek] = useState<string>("");
    const [searchDate, setSearchDate] = useState<string>("");
    const [operatorFilter, setOperatorFilter] = useState<string>("");

    const [isEditing, setIsEditing] = useState(false);
    const [editedData, setEditedData] = useState<ScheduleRow[]>([]);
    const [modifiedRows, setModifiedRows] = useState<Set<number>>(new Set());
    const [isSaving, setIsSaving] = useState(false);

    // ----------------------------------------
    // 2. Functions 區域（全部照你的原樣抽出）
    // ----------------------------------------

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
            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            setScheduleData(data);
        } catch (err: any) {
            setError(err.message ?? "搜尋失敗");
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
            if (!confirm(`有 ${modifiedRows.size} 筆資料已修改，確定要放棄修改嗎？`)) return;
        }
        setIsEditing(false);
        setEditedData([]);
        setModifiedRows(new Set());
    };

    // 更新欄位
    const handleCellChange = (
        rowIndex: number,
        field: keyof ScheduleRow,
        value: string
    ) => {
        const newData = [...editedData];
        newData[rowIndex] = { ...newData[rowIndex], [field]: value };
        setEditedData(newData);

        const updated = new Set(modifiedRows);
        updated.add(rowIndex);
        setModifiedRows(updated);
    };

    // 保存修改
    const handleSaveChanges = async () => {
        if (modifiedRows.size === 0) {
            alert("沒有修改任何資料");
            return;
        }

        if (!confirm(`確定要保存 ${modifiedRows.size} 筆修改嗎？`)) return;

        try {
            setIsSaving(true);

            const dataToSave = Array.from(modifiedRows).map(
                (i) => editedData[i]
            );

            const response = await fetch("/api/schedule/save", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
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
        } catch (err: any) {
            alert(`保存失敗：${err.message ?? "未知錯誤"}`);
        } finally {
            setIsSaving(false);
        }
    };


    useEffect(() => {
        if (searchWeek || searchDate) {
            handleSearch();
        }
    }, []);
    // ----------------------------------------
    // 3. UI Rendering（整段保留你的原始 UI）
    // ----------------------------------------

    return (
        <div className="p-6">
            <h2 className="text-xl font-bold mb-4 text-slate-200">排程表</h2>

            {/* ---- 搜尋區 ---- */}
            <div className="bg-slate-800/50 p-4 rounded-lg border border-slate-700 mb-4">
                <div className="flex gap-6 mb-3">
                    <label className="flex items-center gap-2 text-slate-300">
                        <input
                            type="radio"
                            value="week"
                            checked={searchType === "week"}
                            onChange={() => setSearchType("week")}
                        />
                        按週搜尋
                    </label>

                    <label className="flex items-center gap-2 text-slate-300">
                        <input
                            type="radio"
                            value="date"
                            checked={searchType === "date"}
                            onChange={() => setSearchType("date")}
                        />
                        按日期搜尋
                    </label>
                </div>

                {/* 週別或日期輸入框 */}
                <div className="flex flex-wrap gap-4 mb-4">
                    {searchType === "week" ? (
                        <input
                            value={searchWeek}
                            onChange={(e) => setSearchWeek(e.target.value)}
                            placeholder="例如：2025_W45"
                            className="px-3 py-2 rounded bg-slate-900 border border-slate-600 text-slate-200"
                        />
                    ) : (
                        <input
                            type="date"
                            value={searchDate}
                            onChange={(e) => setSearchDate(e.target.value)}
                            className="px-3 py-2 rounded bg-slate-900 border border-slate-600 text-slate-200"
                        />
                    )}

                    {/* 配藥人員搜尋 */}
                    <input
                        value={operatorFilter}
                        onChange={(e) => setOperatorFilter(e.target.value)}
                        placeholder="配藥人員（可選）"
                        className="px-3 py-2 rounded bg-slate-900 border border-slate-600 text-slate-200"
                    />

                    {/* 搜尋按鈕 */}
                    <button
                        onClick={handleSearch}
                        disabled={loading}
                        className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-slate-500"
                    >
                        {loading ? "搜尋中..." : "搜尋"}
                    </button>

                    {/* 清除配藥人員 */}
                    {operatorFilter && (
                        <button
                            onClick={() => {
                                setOperatorFilter("");
                                handleSearch();
                            }}
                            className="px-4 py-2 bg-slate-500 text-white rounded hover:bg-slate-600"
                        >
                            清除
                        </button>
                    )}
                </div>

                {operatorFilter && (
                    <div className="text-slate-400 text-sm">
                        🔍 正在過濾：配藥人 = <span className="text-blue-400">{operatorFilter}</span>
                    </div>
                )}
            </div>

            {/* ---- 錯誤訊息 ---- */}
            {error && (
                <div className="mb-4 p-3 bg-red-900/40 border border-red-700 rounded-lg text-red-300">
                    ⚠ {error}
                </div>
            )}

            {/* ---- 表格區 ---- */}
            <div className="space-y-2">
                {/* 沒資料 */}
                {!loading && scheduleData.length === 0 && (
                    <div className="text-center py-8 text-slate-500">
                        尚無資料，請輸入搜尋條件
                    </div>
                )}

                {/* Skeleton */}
                {loading &&
                    [1, 2, 3].map((i) => (
                        <div
                            key={i}
                            className="rounded p-3 bg-slate-800/40 animate-pulse"
                        />
                    ))}

                {/* 有資料 → 表格 */}
                {!loading &&
                    (isEditing ? editedData : scheduleData).map((row, i) => {
                        const isModified = modifiedRows.has(i);
                        const isHovered = hoveredRow === i;

                        return (
                            <div
                                key={`${row.date}-${i}`}
                                className={`grid grid-cols-13 gap-2 p-2 rounded transition-colors
          ${isModified
                                        ? "bg-amber-100 border border-amber-500"
                                        : isHovered
                                            ? "bg-slate-700/70 border border-slate-500"
                                            : "bg-slate-800/30"
                                    }
        `}
                                onMouseEnter={() => !isEditing && setHoveredRow(i)}
                                onMouseLeave={() => !isEditing && setHoveredRow(null)}
                            >
                                {/* 日期 */}
                                <span className="text-slate-200">{row.date || "-"}</span>

                                {/* Marker */}
                                {isEditing ? (
                                    <input
                                        value={row.marker ?? ""}
                                        onChange={(e) => handleCellChange(i, "marker", e.target.value)}
                                        className="px-1 py-0.5 rounded bg-slate-900 text-slate-200 border border-slate-600"
                                    />
                                ) : (
                                    <span className="text-slate-300">{row.marker || "-"}</span>
                                )}

                                {/* 滴定機 */}
                                <span className="text-slate-300">{row.machine}</span>

                                {/* 凍乾機 */}
                                {isEditing ? (
                                    <input
                                        value={row.dryer ?? ""}
                                        onChange={(e) => handleCellChange(i, "dryer", e.target.value)}
                                        className="px-1 py-0.5 rounded bg-slate-900 text-slate-200 border border-slate-600"
                                    />
                                ) : (
                                    <span className="text-slate-300">{row.dryer || "-"}</span>
                                )}

                                {/* 配藥人員 */}
                                {isEditing ? (
                                    <input
                                        value={row.operator ?? ""}
                                        onChange={(e) => handleCellChange(i, "operator", e.target.value)}
                                        className="px-1 py-0.5 rounded bg-slate-900 text-slate-200 border border-slate-600"
                                    />
                                ) : (
                                    <span className="text-slate-300">{row.operator}</span>
                                )}

                                {/* RD 給藥時間 */}
                                {isEditing ? (
                                    <input
                                        type="time"
                                        value={row.rdTime ?? ""}
                                        onChange={(e) => handleCellChange(i, "rdTime", e.target.value)}
                                        className="px-1 py-0.5 rounded bg-slate-900 text-slate-200 border border-slate-600"
                                    />
                                ) : (
                                    <span className="text-slate-300">{row.rdTime || "-"}</span>
                                )}

                                {/* 預計滴定 */}
                                {isEditing ? (
                                    <input
                                        type="time"
                                        value={row.start ?? ""}
                                        onChange={(e) => handleCellChange(i, "start", e.target.value)}
                                        className="px-1 py-0.5 rounded bg-slate-900 text-slate-200 border border-slate-600"
                                    />
                                ) : (
                                    <span className="text-slate-300">{row.start}</span>
                                )}

                                {/* 收藥時間 */}
                                {isEditing ? (
                                    <input
                                        type="time"
                                        value={row.end ?? ""}
                                        onChange={(e) => handleCellChange(i, "end", e.target.value)}
                                        className="px-1 py-0.5 rounded bg-slate-900 text-slate-200 border border-slate-600"
                                    />
                                ) : (
                                    <span className="text-slate-300">{row.end}</span>
                                )}

                                {/* 數量 */}
                                {isEditing ? (
                                    <input
                                        value={row.qty ?? ""}
                                        onChange={(e) => handleCellChange(i, "qty", e.target.value)}
                                        className="px-1 py-0.5 rounded bg-slate-900 text-slate-200 border border-slate-600"
                                    />
                                ) : (
                                    <span className="text-slate-300">{row.qty || "-"}</span>
                                )}

                                {/* 料號 */}
                                {isEditing ? (
                                    <input
                                        value={row.pn ?? ""}
                                        onChange={(e) => handleCellChange(i, "pn", e.target.value)}
                                        className="px-1 py-0.5 rounded bg-slate-900 text-slate-200 border border-slate-600"
                                    />
                                ) : (
                                    <span className="text-slate-300 truncate" title={row.pn}>
                                        {row.pn || "-"}
                                    </span>
                                )}

                                {/* 批號 */}
                                {isEditing ? (
                                    <input
                                        value={row.batch ?? ""}
                                        onChange={(e) => handleCellChange(i, "batch", e.target.value)}
                                        className="px-1 py-0.5 rounded bg-slate-900 text-slate-200 border border-slate-600"
                                    />
                                ) : (
                                    <span className="text-slate-300 truncate">{row.batch}</span>
                                )}

                                {/* 工單 */}
                                {isEditing ? (
                                    <input
                                        value={row.workOrder ?? ""}
                                        onChange={(e) => handleCellChange(i, "workOrder", e.target.value)}
                                        className="px-1 py-0.5 rounded bg-slate-900 text-slate-200 border border-slate-600"
                                    />
                                ) : (
                                    <span className="text-slate-300 truncate">{row.workOrder}</span>
                                )}

                                {/* 備註 */}
                                {isEditing ? (
                                    <input
                                        value={row.remark ?? ""}
                                        onChange={(e) => handleCellChange(i, "remark", e.target.value)}
                                        className="px-1 py-0.5 rounded bg-slate-900 text-slate-200 border border-slate-600"
                                    />
                                ) : (
                                    <span className="text-slate-300 truncate">{row.remark}</span>
                                )}
                            </div>
                        );
                    })}
            </div>

            {/* ---- 統計資訊 ---- */}
            {scheduleData.length > 0 && (
                <div className="text-right text-slate-400 mt-4">
                    共 {scheduleData.length} 筆排程
                    {isEditing && modifiedRows.size > 0 && (
                        <span className="ml-2 text-amber-400">
                            （已修改 {modifiedRows.size} 筆）
                        </span>
                    )}
                </div>
            )}

            {/* ---- 編輯按鈕 ---- */}
            <div className="mt-6 flex gap-3">
                {!isEditing ? (
                    <button
                        onClick={handleStartEdit}
                        className="px-4 py-2 bg-emerald-600 text-white rounded hover:bg-emerald-700"
                    >
                        ✏️ 編輯
                    </button>
                ) : (
                    <>
                        <button
                            onClick={handleSaveChanges}
                            disabled={isSaving || modifiedRows.size === 0}
                            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-slate-500"
                        >
                            {isSaving ? "保存中..." : `💾 保存 (${modifiedRows.size})`}
                        </button>

                        <button
                            onClick={handleCancelEdit}
                            className="px-4 py-2 bg-slate-600 text-white rounded hover:bg-slate-700"
                        >
                            ✖ 取消
                        </button>
                    </>
                )}
            </div>
        </div>
    );
}