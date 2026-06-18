import React, { useState, useEffect } from "react";
import {
  FlaskConical,
  Snowflake,
  ClipboardCheck,
  FileText,
  QrCode,
  ExternalLink,
} from "lucide-react";
import { motion } from "framer-motion";
import type { WorkOrderData } from "@/types";

type Props = {
  data: WorkOrderData;
  onSelectPage: (page: string) => void;
};

const MainDashboard: React.FC<Props> = ({ data, onSelectPage }) => {
  const [activeTab, setActiveTab] = useState<"formulation" | "lyophilization">(
    (localStorage.getItem("activeTab") as "formulation" | "lyophilization") ||
      "formulation"
  );

  useEffect(() => {
    localStorage.setItem("activeTab", activeTab);
  }, [activeTab]);

  const handleNavClick = (tab: "formulation" | "lyophilization") => {
    setActiveTab(tab);
  };

  // ✅ 左側「滴定凍乾紀錄」點擊 → 切換到 external 頁面
  const handleExternalClick = () => {
    onSelectPage("external");
  };

  return (
    <div className="flex h-[calc(100vh-4rem)] bg-gray-50 relative">
      {/* === 🧭 左側導航欄 === */}
      <aside
        className="
          w-60 
          bg-white/95 
          rounded-r-2xl 
          shadow-xl shadow-gray-200 
          flex flex-col 
          backdrop-blur-sm 
          z-10
        "
      >
        <div className="px-5 py-5 border-b border-gray-100">
          <h2 className="text-lg font-bold text-gray-700 tracking-wide">
            工單紀錄類型
          </h2>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1">
          <button
            onClick={() => handleNavClick("formulation")}
            className={`w-full text-left px-4 py-2.5 rounded-md font-medium transition-all ${
              activeTab === "formulation"
                ? "bg-blue-100 text-blue-800 shadow-inner"
                : "text-gray-800 hover:bg-blue-50 hover:text-blue-700"
            }`}
          >
            配藥紀錄
          </button>

          {/* ✅ 改成開啟外部頁面 */}
          <button
            onClick={handleExternalClick}
            className="w-full text-left px-4 py-2.5 rounded-md font-medium text-gray-800 hover:bg-blue-50 hover:text-blue-700 transition-all flex items-center justify-between"
          >
            <span>滴定凍乾紀錄</span>
            <ExternalLink className="w-4 h-4 opacity-70" />
          </button>
        </nav>
      </aside>

      {/* === 📋 主內容區 === */}
      <main className="flex-1 overflow-y-auto p-10">
        <motion.section
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="grid grid-cols-3 gap-6"
        >
          {[
            {
              title: "工單摘要",
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
              icon: <QrCode className="text-blue-600 w-6 h-6" />,
              page: "labelPrint",
            },
          ].map((card, idx) => (
            <motion.div
              key={card.title}
              onClick={() => onSelectPage(card.page)}
              whileHover={{
                scale: 1.05,
                y: -5,
                boxShadow:
                  "0px 12px 28px rgba(0, 102, 255, 0.25), 0px 0px 18px rgba(0, 128, 255, 0.25)",
                borderColor: "rgba(37, 99, 235, 0.6)",
              }}
              whileTap={{ scale: 0.97 }}
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{
                type: "spring",
                stiffness: 220,
                damping: 15,
                duration: 0.5,
                delay: idx * 0.06,
              }}
              className="
                cursor-pointer 
                bg-white 
                shadow-md 
                p-6 
                rounded-xl 
                flex 
                flex-col 
                justify-between 
                hover:bg-blue-50 
                border 
                border-transparent 
                transition-all 
                duration-300
              "
            >
              <div className="flex items-center gap-3 mb-2">
                {card.icon}
                <h3 className="text-lg font-semibold text-blue-700">
                  {card.title}
                </h3>
              </div>
              <p className="text-gray-600 text-sm flex-1">{card.desc}</p>
              <span className="text-blue-600 text-sm mt-3">
                進入詳細頁面 →
              </span>
            </motion.div>
          ))}
        </motion.section>
      </main>
    </div>
  );
};

export default MainDashboard;
