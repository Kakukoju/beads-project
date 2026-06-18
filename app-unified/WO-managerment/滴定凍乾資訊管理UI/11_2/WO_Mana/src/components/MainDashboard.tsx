// =====================================
// MainDashboard.tsx - 修復後的完整代碼（關鍵部分）
// 適用於整合到 Beads Ops 系統中
// =====================================

import React, { useState, useEffect } from "react";
import {
  FlaskConical,
  Snowflake,
  ClipboardCheck,
  FileText,
  QrCode,
  Tag,
  Database,
  Search,
  ArrowLeft,
  Save,
  Edit3,
  X,
} from "lucide-react";
import { motion } from "framer-motion";
import { toast } from "sonner";
import type { WorkOrderData } from "@/types";
import { API_ENDPOINTS, API_BASE_URL } from "@/config/api";

type Props = {
  data: WorkOrderData;
  onSelectPage: (page: string) => void;
};

const DB_COLUMNS = [
  "工單號碼",
  "BeadsLot",
  "試劑配製日期",
  "配製人員",
  "料號",
  "化學品名",
  "FillerName",
  "重量紀錄",
  "Filler_Lot",
  "L1OD",
  "L2OD",
  "起始L1OD",
  "起始L2OD",
  "總重量",
  "配製備註",
];

const MainDashboard: React.FC<Props> = ({ data, onSelectPage }) => {
  // ===== State 定義 =====
  const [activeTab, setActiveTab] = useState<"formulation" | "database">("formulation");
  const [searchQuery, setSearchQuery] = useState("");
  const [dbResults, setDbResults] = useState<any[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchedTable, setSearchedTable] = useState("");
  const [lastSearchedId, setLastSearchedId] = useState("");
  const [isEditMode, setIsEditMode] = useState(false);
  const [editedData, setEditedData] = useState<any[]>([]);
  const [isSaving, setIsSaving] = useState(false);

  // ===== Effects =====
  useEffect(() => {
    const savedTab = localStorage.getItem("activeTab") as "formulation" | "database" | null;
    if (savedTab) {
      setActiveTab(savedTab);
    }
  }, []);

  useEffect(() => {
    localStorage.setItem("activeTab", activeTab);
  }, [activeTab]);

  useEffect(() => {
    if (data?.workOrderNo) {
      setSearchQuery(data.workOrderNo);
    }
  }, [data]);

  useEffect(() => {
    if (activeTab === "database" && data?.workOrderNo && data.workOrderNo !== lastSearchedId) {
      handleDbSearch(data.workOrderNo);
    }
  }, [activeTab, data?.workOrderNo]);

  // ===== Computed Values =====
  const hasData = !!data && Object.keys(data).length > 0;

  // ===== Handlers =====
  const handleCardClick = (page: string) => {
    if (!hasData) {
      toast.warning("⚠ 請先輸入工單號碼再進入此頁面！", {
        duration: 3500,
        style: {
          background: "#E8F1FF",
          color: "#003366",
          borderLeft: "5px solid #007BFF",
          fontSize: "1.05rem",
          padding: "16px 20px",
        },
      });
      return;
    }
    onSelectPage(page);
  };

  const handleDbSearch = async (targetOrder?: string) => {
    const queryTerm = targetOrder || searchQuery;
    if (!queryTerm.trim()) {
      toast.error("請輸入工單號碼");
      return;
    }

    setIsSearching(true);
    setDbResults([]);
    setSearchedTable("");
    setIsEditMode(false);

    try {
      const res = await fetch(
        `${API_ENDPOINTS.SEARCH_571_TABLES}?work_order=${encodeURIComponent(queryTerm)}`
      );
      const json = await res.json();

      if (res.ok && json.ok) {
        setDbResults(json.rows);
        setEditedData(JSON.parse(JSON.stringify(json.rows)));
        setSearchedTable(json.table);
        setLastSearchedId(queryTerm);
        toast.success(`搜尋成功，來源表: ${json.table}`);
      } else {
        toast.error(json.message || "查無資料");
      }
    } catch (error) {
      console.error(error);
      toast.error("搜尋發生錯誤，請檢查後端連線");
    } finally {
      setIsSearching(false);
    }
  };

  const handleSave = async () => {
    if (!searchedTable || editedData.length === 0) {
      toast.error("無資料可儲存");
      return;
    }

    setIsSaving(true);
    try {
      const res = await fetch(API_ENDPOINTS.UPDATE_571_TABLE, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          table: searchedTable,
          rows: editedData,
          work_order: searchQuery,
        }),
      });

      const json = await res.json();
      if (res.ok && json.ok) {
        toast.success(`✅ ${json.message || "儲存成功"}`);
        setIsEditMode(false);
        await handleDbSearch();
      } else {
        toast.error(json.message || "儲存失敗");
      }
    } catch (error) {
      console.error(error);
      toast.error("儲存發生錯誤");
    } finally {
      setIsSaving(false);
    }
  };

  const handleCellChange = (rowIndex: number, colName: string, value: string) => {
    const newData = [...editedData];
    newData[rowIndex] = { ...newData[rowIndex], [colName]: value };
    setEditedData(newData);
  };

  const getCellValue = (row: any, colName: string) => {
    if (row[colName] !== undefined) return row[colName];
    const cleanColName = colName.replace(/_/g, "");
    if (row[cleanColName] !== undefined) return row[cleanColName];

    if (colName === "工單號碼") {
      if (row["工單編號"]) return row["工單編號"];
      if (row["WorkOrder"]) return row["WorkOrder"];
      if (row["work_order"]) return row["work_order"];
      const keys = Object.keys(row);
      if (keys.length > 0) return row[keys[0]];
    }
    return "";
  };

  return (
    // ✅ 修改 1：最外層容器 - 添加最小寬度和橫向滾動
    <div className="flex h-full bg-gray-50 relative min-w-[1200px] overflow-x-auto">
      
      {/* ✅ 修改 2：左側導航欄 - 固定寬度，防止收縮 */}
      <aside className="w-60 min-w-[240px] max-w-[240px] bg-white/95 rounded-r-2xl shadow-xl shadow-gray-200 flex flex-col backdrop-blur-sm z-10 flex-shrink-0">
        <div className="px-5 py-5 border-b border-gray-100">
          <h2 className="text-lg font-bold text-gray-700 tracking-wide">工單紀錄類型</h2>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1">
          <button
            onClick={() => setActiveTab("formulation")}
            className={`w-full text-left px-4 py-2.5 rounded-md font-medium transition-all flex items-center gap-2 ${
              activeTab === "formulation"
                ? "bg-blue-100 text-blue-800 shadow-inner"
                : "text-gray-800 hover:bg-blue-50 hover:text-blue-700"
            }`}
          >
            <FlaskConical className="w-4 h-4" />
            配藥紀錄
          </button>

          <button
            onClick={() => setActiveTab("database")}
            className={`w-full text-left px-4 py-2.5 rounded-md font-medium transition-all flex items-center gap-2 ${
              activeTab === "database"
                ? "bg-blue-100 text-blue-800 shadow-inner"
                : "text-gray-800 hover:bg-blue-50 hover:text-blue-700"
            }`}
          >
            <Database className="w-4 h-4" />
            配藥資料庫
          </button>
        </nav>
      </aside>

      {/* ✅ 修改 3：主內容區 - 允許滾動，減小 padding */}
      <main className={`flex-1 overflow-auto min-w-0 flex flex-col ${activeTab === "database" ? "p-4 pl-6" : "p-6"}`}>
        
        {/* 配藥紀錄 Dashboard */}
        {activeTab === "formulation" && (
          <motion.section
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            className="flex-1 overflow-y-auto"
          >
            <div className="grid grid-cols-3 gap-6">
              {[
                {
                  title: "建立與檢視工單",
                  desc: "顯示工單的整體摘要資料。",
                  icon: <FileText className="text-blue-600 w-6 h-6" />,
                  page: "summary",
                },
                {
                  title: "配藥資訊",
                  desc: "編輯 Bead、批號及備註等詳細配藥資料。",
                  icon: <FlaskConical className="text-blue-600 w-6 h-6" />,
                  page: "beadTable",
                },
                {
                  title: "品質檢驗資訊",
                  desc: "檢查製劑狀況與 OD 數據。",
                  icon: <ClipboardCheck className="text-blue-600 w-6 h-6" />,
                  page: "qcInfo",
                },
                {
                  title: "滴定凍乾資訊",
                  desc: "顯示滴定與凍乾批次資料。",
                  icon: <Snowflake className="text-blue-600 w-6 h-6" />,
                  page: "disposeLot",
                },
                {
                  title: "QR Code",
                  desc: "檢視並列印工單的 QR 資料。",
                  icon: <QrCode className="text-blue-600 w-6 h-6" />,
                  page: "qrCode",
                },
                {
                  title: "列印標籤",
                  desc: "生成含 QR code 的標籤列印頁。",
                  icon: <Tag className="text-blue-600 w-6 h-6" />,
                  page: "labelPrint",
                },
              ].map((card, idx) => (
                <motion.div
                  key={card.title}
                  onTap={() => handleCardClick(card.page)}
                  initial={{ opacity: 0, y: 15 }}
                  animate={{ opacity: 1, y: 0 }}
                  whileHover={{ scale: 1.05, y: -5 }}
                  whileTap={{ scale: 0.97 }}
                  transition={{
                    type: "spring",
                    stiffness: 220,
                    damping: 15,
                    duration: 0.5,
                    delay: idx * 0.06,
                  }}
                  style={{ cursor: "pointer" }}
                >
                  <div className="h-full bg-white shadow-md p-6 rounded-xl flex flex-col justify-between border border-transparent transition-all duration-300 hover:bg-blue-50 hover:border-blue-500/60 hover:shadow-[0px_12px_28px_rgba(0,102,255,0.25)]">
                    <div className="flex items-center gap-3 mb-2">
                      {card.icon}
                      <h3 className="text-lg font-semibold text-blue-700">{card.title}</h3>
                    </div>
                    <p className="text-gray-600 text-sm flex-1">{card.desc}</p>
                    <span className="text-blue-600 text-sm mt-3">進入詳細頁面 →</span>
                  </div>
                </motion.div>
              ))}
            </div>
          </motion.section>
        )}

        {/* ✅ 修改 4：配藥資料庫查詢 - 添加最小寬度 */}
        {activeTab === "database" && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.3 }}
            className="bg-white rounded-xl shadow-lg border border-gray-100 flex flex-col h-full w-full min-w-[800px]"
          >
            {/* Header */}
            <div className="px-8 py-4 border-b border-gray-100 bg-gray-50/50 flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => setActiveTab("formulation")}
                    className="flex-shrink-0 flex items-center gap-1.5 px-4 py-2 bg-white border-2 border-gray-300 text-gray-700 text-sm font-semibold hover:text-blue-600 hover:border-blue-500 hover:bg-blue-50 rounded-lg shadow-md transition-all"
                  >
                    <ArrowLeft className="w-4 h-4" />
                    返回
                  </button>

                  <h2 className="text-lg font-bold text-gray-800 flex items-center gap-2">
                    <Database className="w-5 h-5 text-blue-600" />
                    配藥資料庫查詢
                  </h2>
                </div>

                <div className="flex items-center gap-3">
                  {searchedTable && (
                    <div className="text-sm text-green-600 font-medium bg-green-50 px-3 py-1 rounded-full border border-green-100">
                      ✓ 來源表: {searchedTable}
                    </div>
                  )}

                  {dbResults.length > 0 && (
                    <>
                      {!isEditMode ? (
                        <button
                          onClick={() => setIsEditMode(true)}
                          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg font-medium hover:bg-blue-700 transition-all shadow-md"
                        >
                          <Edit3 className="w-4 h-4" />
                          編輯
                        </button>
                      ) : (
                        <>
                          <button
                            onClick={() => {
                              setIsEditMode(false);
                              setEditedData(JSON.parse(JSON.stringify(dbResults)));
                            }}
                            className="flex items-center gap-2 px-4 py-2 bg-gray-500 text-white text-sm rounded-lg font-medium hover:bg-gray-600 transition-all shadow-md"
                          >
                            <X className="w-4 h-4" />
                            取消
                          </button>
                          <button
                            onClick={handleSave}
                            disabled={isSaving}
                            className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white text-sm rounded-lg font-medium hover:bg-green-700 transition-all shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            <Save className="w-4 h-4" />
                            {isSaving ? "儲存中..." : "儲存"}
                          </button>
                        </>
                      )}
                    </>
                  )}
                </div>
              </div>

              {/* Search Bar */}
              <div className="flex gap-2 max-w-2xl">
                <div className="relative flex-1">
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleDbSearch()}
                    placeholder="輸入工單號碼搜尋 (例如: 24120901)..."
                    className="w-full pl-9 pr-4 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all shadow-sm"
                  />
                  <Search className="absolute left-3 top-2.5 text-gray-400 w-4 h-4" />
                </div>
                <button
                  onClick={() => handleDbSearch()}
                  disabled={isSearching}
                  className="px-5 py-2 bg-blue-600 text-white text-sm rounded-lg font-medium hover:bg-blue-700 active:scale-95 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-md shadow-blue-200 whitespace-nowrap"
                >
                  {isSearching ? "搜尋中..." : "搜尋"}
                </button>
              </div>
            </div>

            {/* ✅ 修改 5：表格容器 - 移除 justify-center，添加 min-w-0 */}
            <div className="flex-1 overflow-auto relative w-full min-w-0 rounded-b-xl">
              {dbResults.length > 0 ? (
                // ✅ 修改 6：表格內層容器 - 移除 max-w 限制，table 添加最小寬度
                <div className="w-full px-4 py-4">
                  <table className="w-full text-left border-collapse min-w-[1400px]">
                    <thead className="sticky top-0 z-10">
                      <tr className="bg-blue-100 text-blue-900 border-b border-blue-200 shadow-sm">
                        {DB_COLUMNS.map((col, idx) => (
                          <th
                            key={col}
                            className={`px-3 py-3 text-xs font-bold whitespace-nowrap ${
                              idx === 0 ? "w-28" : ""
                            } ${col === "BeadsLot" ? "w-24" : ""} ${
                              col === "試劑配製日期" ? "w-28" : ""
                            } ${col === "配製人員" ? "w-20" : ""} ${col === "料號" ? "w-32" : ""} ${
                              col === "FillerName" ? "w-20" : ""
                            } ${col === "重量紀錄" ? "w-24" : ""} ${col === "Filler_Lot" ? "w-28" : ""}`}
                          >
                            {col}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {(isEditMode ? editedData : dbResults).map((row, idx) => (
                        <tr key={idx} className="hover:bg-blue-50/50 transition-colors even:bg-gray-50/30">
                          {DB_COLUMNS.map((col, cIdx) => (
                            <td
                              key={`${idx}-${col}`}
                              className={`px-3 py-2.5 text-xs text-gray-700 whitespace-nowrap ${
                                cIdx === 0 ? "font-medium text-gray-900" : ""
                              }`}
                            >
                              {isEditMode ? (
                                <input
                                  type="text"
                                  value={getCellValue(row, col) || ""}
                                  onChange={(e) => handleCellChange(idx, col, e.target.value)}
                                  className="w-full px-2 py-1 text-xs border border-gray-300 rounded focus:ring-1 focus:ring-blue-500 focus:border-blue-500 outline-none"
                                />
                              ) : (
                                getCellValue(row, col)
                              )}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-full text-gray-400">
                  <div className="bg-gray-50 p-4 rounded-full mb-3">
                    <Search className="w-10 h-10 opacity-30" />
                  </div>
                  <p className="text-sm font-medium">請輸入工單號碼進行搜尋</p>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </main>
    </div>
  );
};

export default MainDashboard;

// =====================================
// 🎯 修改總結
// =====================================
/*
✅ 已完成的 6 處關鍵修改：

1. 最外層 div (Line 177)
   - h-[calc(100vh-4rem)] → h-full
   - 添加: min-w-[1200px] overflow-x-auto

2. 左側 aside (Line 180)
   - 添加: min-w-[240px] max-w-[240px]
   - shrink-0 → flex-shrink-0

3. 主內容 main (Line 216)
   - overflow-hidden → overflow-auto
   - 添加: min-w-0
   - padding 縮小: p-8 pl-12 → p-4 pl-6

4. 配藥資料庫容器 (Line 279)
   - 添加: min-w-[800px]

5. 表格外層 (Line 358)
   - 移除: flex justify-center
   - 添加: min-w-0

6. 表格內層和 table (Line 361-362)
   - max-w-[95%] mx-auto → px-4
   - table 添加: min-w-[1400px]

這些修改確保：
✅ 左側導航固定寬度，不會被擠壓
✅ 視窗小於 1200px 時出現橫向滾動條
✅ 表格有足夠空間顯示所有欄位
✅ 內容不會被切斷或丟失
✅ 完美整合到 Beads Ops 系統中
*/
