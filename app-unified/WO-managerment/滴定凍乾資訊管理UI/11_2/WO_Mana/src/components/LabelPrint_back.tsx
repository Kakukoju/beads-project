import React, { useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import type { WorkOrderData } from "@/types";

type LabelPrintProps = {
  data: WorkOrderData; // ✅ 修正：應該是 WorkOrderData 而非 IWorkOrderData
  onBack: () => void;
};

/**
 * 🏷️ 標籤列印元件 (已修復重複顯示問題及批號判斷)
 */
export const LabelPrint: React.FC<LabelPrintProps> = ({ data, onBack }) => {
  const lots = data.disposeLots || [];
  const [copies, setCopies] = useState(1);
  const [offsetX, setOffsetX] = useState(0);
  const [offsetY, setOffsetY] = useState(0);

  const LABEL_W = 50; // mm
  const LABEL_H = 30; // mm

  // ✅ FIX: 安全地從第一個批次中獲取 Lot ID，並同時處理 string[] 或 { id: string }[] 的情況
  const firstLot = lots[0];
  const lot = (typeof firstLot === 'string' ? firstLot : (firstLot as any)?.id) ?? "N/A"; // ✅ 修正：取消註解
  const qrValue = `${data.markerName},${lot}`;

  return (
    <div id="label-print-root" className="p-4 bg-gray-50 min-h-screen">
      <style>{`
        /* === 紙張設定 === */
        @page {
          size: ${LABEL_W}mm ${LABEL_H}mm landscape;
          margin: 0;
        }

        :root {
          --label-w: ${LABEL_W}mm;
          --label-h: ${LABEL_H}mm;
          --offset-x: ${offsetX}mm;
          --offset-y: ${offsetY}mm;
        }

        html, body {
          margin: 0;
          padding: 0;
          background: #f8fafc;
          font-family: "Microsoft JhengHei", sans-serif;
        }

        #label-print-root {
          display: flex;
          flex-direction: column;
          align-items: center;
          padding: 20px;
          gap: 20px;
        }

        /* === 預覽樣式 === */
        .preview-label {
          width: var(--label-w);
          height: var(--label-h);
          border: 2px solid #000;
          border-radius: 4px;
          padding: 2mm;
          background: white;
          display: flex;
          align-items: center;
          justify-content: space-evenly;
          box-sizing: border-box;
          margin-top: 10px;
          box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }

        .qr-wrap {
          flex: 0 0 40%;
          display: flex;
          justify-content: center;
          align-items: center;
        }

        .txt-wrap {
          flex: 0 0 45%;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
        }

        .marker {
          font-size: 12px;
          font-weight: bold;
        }

        .lot {
          font-size: 10px;
          margin-top: 1.5mm;
        }
        
        /* 隱藏列印用的標籤，只在列印時顯示 */
        .print-page {
          display: none;
        }

        /* === 列印模式 === */
        @media print {
          /* 🚫 隱藏整個網站所有非標籤內容 */
          body * {
            visibility: hidden !important;
          }

          /* ✅ 只顯示標籤，並強制覆蓋全畫面 */
          #label-print-root,
          #label-print-root * {
            visibility: visible !important;
          }

          /* 🚫 預覽、控制列全部不印 */
          .no-print, .preview-label {
            display: none !important;
          }

          html, body {
            margin: 0;
            padding: 0;
            background: white !important;
            width: 100%;
            height: 100%;
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
          }

          #label-print-root {
            all: unset;
            position: fixed;
            inset: 0;
            margin: 0;
            padding: 0;
            background: white;
            display: flex;
            justify-content: center;
            align-items: center;
          }

          .print-page {
            position: relative;
            /* 讓它在列印時顯示出來 */
            display: flex !important; 
            align-items: center;
            justify-content: center;
            width: var(--label-w);
            height: var(--label-h);
            background: white;
            transform: translate(var(--offset-x), var(--offset-y));
          }

          .label-box {
            width: var(--label-w);
            height: var(--label-h);
            /* ✅ FIX: 列印時移除邊框，避免印出多餘的框線 */
            border: 0px solid; 
            border-radius: 0px; 
            padding: 2mm;
            background: white;
            display: flex;
            align-items: center;
            justify-content: space-evenly;
            box-sizing: border-box;
          }
        }
      `}</style>

      {/* === 控制區（只在畫面顯示） === */}
      <div className="no-print flex flex-wrap gap-4 items-center p-4 bg-white rounded-lg shadow-md max-w-4xl mx-auto">
        <label className="flex items-center text-sm font-medium text-gray-700">
          Copies：
          <input
            type="number"
            min={1}
            value={copies}
            onChange={(e) => setCopies(Number(e.target.value))}
            className="border border-gray-300 rounded w-20 p-1 text-center ml-2"
          />
        </label>
        <label className="flex items-center text-sm font-medium text-gray-700">
          左右移動 (mm)：
          <input
            type="number"
            value={offsetX}
            onChange={(e) => setOffsetX(Number(e.target.value))}
            className="border border-gray-300 rounded w-20 p-1 text-center ml-2"
          />
        </label>
        <label className="flex items-center text-sm font-medium text-gray-700">
          上下移動 (mm)：
          <input
            type="number"
            value={offsetY}
            onChange={(e) => setOffsetY(Number(e.target.value))}
            className="border border-gray-300 rounded w-20 p-1 text-center ml-2"
          />
        </label>

        <button
          onClick={() => window.print()}
          className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg transition duration-200 shadow-md"
        >
          🖨️ 列印標籤
        </button>
        <button
          onClick={onBack}
          className="bg-gray-400 hover:bg-gray-500 text-gray-800 px-4 py-2 rounded-lg transition duration-200 shadow-md"
        >
          ← 返回工單
        </button>
      </div>

      {/* === 🖥️ 預覽模式（只顯示一張，有邊框） === */}
      <div className="no-print mt-8">
        <h3 className="text-lg font-semibold text-gray-700 mb-2 text-center">單張標籤預覽 (50mm x 30mm)</h3>
        <div className="preview-label">
          <div className="qr-wrap">
            <QRCodeSVG value={qrValue} size={LABEL_H * 3.5} />
          </div>
          <div className="txt-wrap">
            <div className="marker">{data.markerName}</div>
            <div className="lot">{lot}</div>
          </div>
        </div>
      </div>

      {/* === 🖨️ 列印用 (螢幕上隱藏, 只在 @media print 中顯示) === */}
      {Array.from({ length: copies }).map((_, i) => (
        <div key={i} className="print-page">
          <div className="label-box">
            <div className="qr-wrap">
              <QRCodeSVG value={qrValue} size={LABEL_H * 1.5} />
            </div>
            <div className="txt-wrap">
              <div className="marker">{data.markerName}</div>
              <div className="lot">{lot}</div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};