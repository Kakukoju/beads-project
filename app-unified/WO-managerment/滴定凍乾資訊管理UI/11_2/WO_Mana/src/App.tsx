// src/App.tsx
import React, { useState, useEffect } from "react";
import { Loader2, Search, Printer, User } from "lucide-react";
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
import LoginPage from "@/pages/LoginPage";
import { Toaster } from "sonner";
import { Routes, Route, useNavigate } from "react-router-dom";
import { PrintView } from "@/pages/PrintView";

const App: React.FC = () => {
  const [loggedIn, setLoggedIn] = useState(false);
  const [username, setUsername] = useState<string | null>(null);
  const [workOrder, setWorkOrder] = useState("");
  const [data, setData] = useState<WorkOrderData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activePage, setActivePage] = useState<
    | "dashboard"
    | "beadTable"
    | "disposeLot"
    | "qcInfo"
    | "qrCode"
    | "summary"
    | "external"
    | "labelPrint"
  >("dashboard");

  const { qrValue, qrArray, QR_FIELDS, EXPECTED_LEN } = useQRCodeData(data);
  const navigate = useNavigate();

  // ✅ 登入檢查
  useEffect(() => {
    const savedUser = localStorage.getItem("username");
    if (savedUser) {
      setUsername(savedUser);
      setLoggedIn(true);
      setActivePage("dashboard");
    }
  }, []);

  // ✅ 登入
  const handleLogin = (name: string) => {
    setUsername(name);
    localStorage.setItem("username", name);
    setLoggedIn(true);
    setActivePage("dashboard");
  };

  // ✅ 登出
  const handleLogout = () => {
    localStorage.removeItem("username");
    setLoggedIn(false);
    setData(null);
  };

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
    } catch {
      alert("❌ 儲存失敗，請檢查伺服器。");
    }
  };

  // ===== ✅ 改良列印 (自動導向 PrintView) =====
  const handlePrint = () => {
    if (!data) return;
    navigate("/print", { state: data });
  };

  // ===== 主內容區 =====
  const renderContent = () => {
    if (!data && !["dashboard", "external"].includes(activePage)) return null;

    switch (activePage) {
      case "dashboard":
        return (
          <MainDashboard
            data={data ?? ({} as WorkOrderData)}
            onSelectPage={(page) =>
              setActivePage(page as typeof activePage)
            }
          />
        );
      case "beadTable":
        return (
          <BeadTable
            data={data ?? ({} as WorkOrderData)}
            onSave={handleSave}
            onBack={() => setActivePage("dashboard")}
          />
        );
      case "disposeLot":
        return (
          <DisposeLotTable
            lots={data?.disposeLots ?? []}
            onBack={() => setActivePage("dashboard")}
          />
        );
      case "qcInfo":
        return (
          <QcInfoPage
            data={data ?? ({} as WorkOrderData)}
            onBack={() => setActivePage("dashboard")}
          />
        );
      case "summary":
        return (
          <InterfaceView
            data={data ?? ({} as WorkOrderData)}
            onBack={() => setActivePage("dashboard")}
          />
        );
      case "labelPrint":
        return (
          <LabelPrint
            data={data ?? ({} as WorkOrderData)}
            onBack={() => setActivePage("dashboard")}
          />
        );
      case "qrCode":
        return (
          <div className="flex flex-col items-center w-full">
            <h2 className="text-2xl font-bold text-gray-800 mb-4">
              QR Code 頁面
            </h2>
            <QRCodeBlock
              qrValue={qrValue}
              data={data ?? ({} as WorkOrderData)}
              qrArray={qrArray}
              QR_FIELDS={QR_FIELDS}
              EXPECTED_LEN={EXPECTED_LEN}
              onBack={() => setActivePage("dashboard")}
            />
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

  if (!loggedIn) return <LoginPage onLogin={handleLogin} />;

  return (
    <Routes>
      {/* ✅ 主畫面 */}
      <Route
        path="/"
        element={
          <main className="bg-gray-50 min-h-screen flex flex-col items-center pt-10 overflow-y-auto">
            {/* === 標題區 === */}
            <div className="flex items-center justify-between w-[1000px] mb-4">
              <h1 className="text-4xl font-extrabold text-gray-900 tracking-wide">
                滴定凍乾資訊管理系統
              </h1>
              <div className="flex items-center gap-3">
                <User className="text-purple-700" />
                <span className="text-gray-800 text-lg font-semibold">
                  {username}
                </span>
                <Button
                  onClick={handleLogout}
                  className="bg-gray-200 hover:bg-gray-300 px-3 py-1"
                >
                  登出
                </Button>
              </div>
            </div>

            {/* === 搜尋列 === */}
            {activePage === "dashboard" && (
              <div className="flex flex-row items-center gap-3 bg-white shadow-md rounded-xl p-5 w-[800px] justify-center mb-10">
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
            )}

            {error && (
              <p className="text-red-600 text-lg font-semibold">{error}</p>
            )}

            <AnimatePresence mode="wait">
              <motion.div
                key={activePage}
                initial={{ opacity: 0, x: 40 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -40 }}
                transition={{ duration: 0.35 }}
                className="w-full flex justify-center"
              >
                {renderContent()}
              </motion.div>
            </AnimatePresence>

            <Toaster
              position="top-right"
              expand={true}
              richColors
              toastOptions={{
                duration: 3500,
                className:
                  "text-lg px-5 py-4 rounded-xl shadow-lg border-l-4 border-[#007BFF]",
                style: {
                  background: "#f8fbff",
                  color: "#003366",
                  borderLeftColor: "#007BFF",
                },
              }}
            />
          </main>
        }
      />

      {/* ✅ 乾淨列印頁 */}
      <Route path="/print" element={<PrintView />} />
    </Routes>
  );
};

export default App;
