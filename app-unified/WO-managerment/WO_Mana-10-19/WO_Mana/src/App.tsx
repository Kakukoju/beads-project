import React, { useState } from "react";
import { Loader2, Search, Printer } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import MainDashboard from "@/components/MainDashboard";
import { BeadTable } from "@/components/BeadTable";
import { DisposeLotTable } from "@/components/DisposeLotTable";
import { QcInfoPage } from "@/components/QcInfoPage";
import { useQRCodeData } from "@/hooks/useQRCodeData";
import { QRCodeBlock } from "@/components/QRCodeBlock";
import { InterfaceView } from "@/components/InterfaceView";
import type { WorkOrderData } from "@/types";
import { getWorkOrder, saveWorkOrder } from "@/api/workOrder";
import { AnimatePresence, motion } from "framer-motion";
import { LabelPrint } from "@/components/LabelPrint";
import ExternalPage from "@/pages/ExternalPage";

const App: React.FC = () => {
  const [workOrder, setWorkOrder] = useState("");
  const [data, setData] = useState<WorkOrderData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activePage, setActivePage] = useState<
    | "search"
    | "dashboard"
    | "beadTable"
    | "disposeLot"
    | "qcInfo"
    | "qrCode"
    | "summary"
    | "external"
    | "labelPrint"
  >("search");

  const { qrValue, qrArray, QR_FIELDS, EXPECTED_LEN } = useQRCodeData(data);

  // ===== 查詢工單 =====
  const handleSearch = async () => {
    if (!workOrder.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await getWorkOrder(workOrder.trim());
      setData(res);
      setActivePage("dashboard");
    } catch (err: any) {
      console.error(err);
      setError(err.message || "查詢失敗");
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  // ===== 儲存工單 =====
  const handleSave = async (updated: WorkOrderData) => {
    try {
      await saveWorkOrder(updated);
      alert("✅ 資料已更新成功！");
      setData(updated);
    } catch (err: any) {
      console.error("❌ 儲存失敗:", err);
      alert("❌ 儲存失敗，請檢查伺服器。");
    }
  };

  // ===== 自動列印 A4 InterfaceView =====
  const handlePrint = async () => {
    if (!data) return;
    setActivePage("summary");
    await new Promise((r) => setTimeout(r, 600));
    window.print();
    setTimeout(() => setActivePage("dashboard"), 800);
  };

  // ===== 主畫面內容 =====
  const renderContent = () => {
    if (!data) return null;

    switch (activePage) {
      case "dashboard":
        return (
          <MainDashboard data={data} onSelectPage={(page) => setActivePage(page)} />
        );

      case "beadTable":
        return (
          <BeadTable
            data={data}
            onSave={handleSave}
            onBack={() => setActivePage("dashboard")}
          />
        );

      case "disposeLot":
        return (
          <DisposeLotTable
            lots={data.disposeLots}
            onBack={() => setActivePage("dashboard")}
          />
        );

      case "qcInfo":
        return <QcInfoPage data={data} onBack={() => setActivePage("dashboard")} />;

      case "summary":
        return <InterfaceView data={data} onBack={() => setActivePage("dashboard")} />;

      case "labelPrint":
        return <LabelPrint data={data} onBack={() => setActivePage("dashboard")} />;

      case "qrCode":
        return (
          <div className="flex flex-col items-center w-full">
            <h2 className="text-2xl font-bold text-gray-800 mb-4">QR Code 頁面</h2>
            <QRCodeBlock
              qrValue={qrValue}
              data={data}
              qrArray={qrArray}
              QR_FIELDS={QR_FIELDS}
              EXPECTED_LEN={EXPECTED_LEN}
            />
            <div className="mt-6">
              <button
                onClick={() => setActivePage("dashboard")}
                className="px-4 py-2 bg-gray-200 hover:bg-gray-300 rounded-md"
              >
                ← 返回首頁
              </button>
            </div>
          </div>
        );

      case "external":
        return (
          <ExternalPage
            url="http://10.6.182.47:8502/"
            onBack={() => setActivePage("dashboard")}
          />
        );

      default:
        return null;
    }
  };

  return (
    <main
      className={`relative bg-gray-50 min-h-screen flex flex-col items-center overflow-y-auto ${
        activePage === "external" ? "pt-0" : "pt-10"
      }`}
    >
      <style>{`
        @media print {
          h1, .search-section, .no-print {
            display: none !important;
          }
          body, main {
            background: white !important;
            margin: 0;
            padding: 0;
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
          }
          #print-root {
            margin-left: auto !important;
            margin-right: auto !important;
            left: 0 !important;
            transform: none !important;
          }
        }
      `}</style>

      {/* ===== 標題 & 搜尋區塊（ExternalPage 時隱藏） ===== */}
      {activePage !== "external" && (
        <>
          {/* 標題 */}
          <h1 className="text-5xl font-extrabold mb-8 text-gray-900 tracking-wide">
            工單資訊管理系統
          </h1>

          {/* 搜尋區 */}
          <div className="search-section flex flex-row items-center gap-3 bg-white shadow-lg rounded-xl p-5 w-[700px] justify-center mb-10 no-print">
            <Input
              type="text"
              value={workOrder}
              onChange={(e) => setWorkOrder(e.target.value)}
              placeholder="請輸入工單號碼，例如 TMRA251178"
              className="flex-1 border border-gray-300 rounded-md p-2 text-lg"
            />
            <Button
              onClick={handleSearch}
              disabled={loading}
              className="bg-green-500 hover:bg-green-600 text-white flex items-center gap-2"
            >
              {loading ? (
                <>
                  <Loader2 className="animate-spin w-4 h-4" /> 查詢中...
                </>
              ) : (
                <>
                  <Search className="w-4 h-4" /> 查詢工單
                </>
              )}
            </Button>

            <Button
              onClick={handlePrint}
              disabled={!data}
              className="bg-green-500 hover:bg-green-600 text-white flex items-center gap-2"
            >
              <Printer className="w-4 h-4" /> 列印工單
            </Button>
          </div>
        </>
      )}

      {/* 錯誤訊息 */}
      {error && <p className="text-red-600 text-lg font-semibold">{error}</p>}

      {/* 搜尋提示 or 主內容 */}
      {activePage === "search" && !loading && (
        <p className="text-gray-500 text-lg mt-10">
          🔍 請輸入工單號碼後點擊「查詢工單」
        </p>
      )}

      {/* 🎞️ 動畫切換區 */}
      <div className="w-full flex justify-center px-6">
        <AnimatePresence mode="wait">
          <motion.div
            key={activePage}
            initial={{ opacity: 0, x: 40, scale: 0.98 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: -40, scale: 0.98 }}
            transition={{ duration: 0.35, ease: "easeInOut" }}
            className={
              activePage === "summary"
                ? "w-full flex justify-center"
                : "w-full max-w-[1200px] mx-auto"
            }
          >
            {renderContent()}
          </motion.div>
        </AnimatePresence>
      </div>
    </main>
  );
};

export default App;
