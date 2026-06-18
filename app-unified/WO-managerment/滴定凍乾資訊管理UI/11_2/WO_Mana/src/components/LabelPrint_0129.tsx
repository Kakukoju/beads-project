import React, { useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import type { WorkOrderData } from "@/types";

type LabelPrintProps = {
  data: WorkOrderData;
  onBack: () => void;
};

/**
 * 🏷️ 標籤列印元件 (QR code 置中，文字兩側旋轉 90 度，支援多批次列印)
 */
export const LabelPrint: React.FC<LabelPrintProps> = ({ data, onBack }) => {
  const lots = data.disposeLots || [];
  const [copies, setCopies] = useState(1);
  const [offsetX, setOffsetX] = useState(0);
  const [offsetY, setOffsetY] = useState(0);

  const LABEL_W = 50; // mm
  const LABEL_H = 30; // mm

  // ✅ 為每個批次生成標籤資料
  const getLotId = (lot: any): string => {
    return (typeof lot === 'string' ? lot : lot?.id) ?? "N/A";
  };

  // ✅ 生成所有要列印的標籤 (所有批次 × 份數)
  const allLabels = lots.flatMap((lot) => {
    const lotId = getLotId(lot);
    const qrValue = `${data.markerName},${lotId}`;
    return Array.from({ length: copies }).map((_, idx) => ({
      key: `${lotId}-${idx}`,
      markerName: data.markerName,
      lotId,
      qrValue,
    }));
  });

  // 預覽用：只顯示第一個批次
  const firstLot = lots[0];
  const previewLotId = getLotId(firstLot);
  const previewQrValue = `${data.markerName},${previewLotId}`;

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

        /* === 預覽樣式 (新佈局：左文字-中QR-右文字) === */
        .preview-label {
          width: var(--label-w);
          height: var(--label-h);
          border: 2px solid #000;
          border-radius: 4px;
          padding: 2mm;
          background: white;
          display: flex;
          align-items: center;
          justify-content: space-between;
          box-sizing: border-box;
          margin-top: 10px;
          box-shadow: 0 4px 6px rgba(0,0,0,0.1);
          position: relative;
        }

        /* 左側文字（旋轉 -90 度） */
        .txt-left {
          writing-mode: vertical-rl;
          transform: rotate(180deg);
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          font-size: 10px;
          font-weight: bold;
          letter-spacing: 1px;
          flex: 0 0 auto;
          padding: 0 2mm;
        }

        /* 中央 QR code */
        .qr-center {
          flex: 1;
          display: flex;
          justify-content: center;
          align-items: center;
          max-width: 60%;
        }

        /* 右側文字（旋轉 90 度） */
        .txt-right {
          writing-mode: vertical-rl;
          transform: rotate(0deg);
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          font-size: 10px;
          font-weight: bold;
          letter-spacing: 1px;
          flex: 0 0 auto;
          padding: 0 2mm;
        }
        
        /* 隱藏列印用的標籤，只在列印時顯示 */
        .print-page {
          display: none;
        }

        /* === 列印模式 === */
        @media print {
          /* 隱藏整個網站所有非標籤內容 */
          body * {
            visibility: hidden !important;
          }

          /* 只顯示標籤 */
          #label-print-root,
          #label-print-root * {
            visibility: visible !important;
          }

          /* 預覽、控制列不印 */
          .no-print, .preview-label {
            display: none !important;
          }

          html, body {
            margin: 0;
            padding: 0;
            background: white !important;
            width: 100%;
            height: auto !important;
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
          }

          #label-print-root {
          
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            margin: 0;
            padding: 0;
            background: white;
            display: block;
          }

          /* 🔥 強制每個標籤佔一整頁 */
          .print-page {
            position: relative;
            display: flex !important; 
            align-items: center;
            justify-content: center;
            width: 100vw;
            height: 100vh;
            background: white;
            page-break-after: always;
            break-after: page;
            page-break-before: auto;
            break-before: auto;
            page-break-inside: avoid;
            break-inside: avoid;
          }

          /* 最後一個標籤不需要分頁 */
          .print-page:last-child {
            page-break-after: auto;
            break-after: auto;
          }

          .label-box {
            width: var(--label-w);
            height: var(--label-h);
            border: 0;
            border-radius: 0;
            padding: 2mm;
            background: white;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-sizing: border-box;
            transform: translate(var(--offset-x), var(--offset-y));
          }

          /* 列印時的文字佈局 */
          .label-box .txt-left {
            writing-mode: vertical-rl;
            transform: rotate(180deg);
            font-size: 10px;
            font-weight: bold;
            letter-spacing: 1px;
            padding: 0 2mm;
          }

          .label-box .qr-center {
            flex: 1;
            display: flex;
            justify-content: center;
            align-items: center;
          }

          .label-box .txt-right {
            writing-mode: vertical-rl;
            transform: rotate(0deg);
            font-size: 10px;
            font-weight: bold;
            letter-spacing: 1px;
            padding: 0 2mm;
          }
        }
      `}</style>

      {/* === 控制區（只在畫面顯示） === */}
      <div className="no-print flex flex-wrap gap-4 items-center p-4 bg-white rounded-lg shadow-md max-w-4xl mx-auto">
        <div className="text-sm font-medium text-gray-700">
          共 <span className="font-bold text-blue-600">{lots.length}</span> 個批次，
          每批次 <span className="font-bold text-blue-600">{copies}</span> 張 = 
          <span className="font-bold text-green-600"> {lots.length * copies}</span> 張標籤
        </div>
      </div>

      <div className="no-print flex flex-wrap gap-4 items-center p-4 bg-white rounded-lg shadow-md max-w-4xl mx-auto">
        <label className="flex items-center text-sm font-medium text-gray-700">
          每批次份數：
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

      {/* === 🖥️ 預覽模式（新佈局：左文字-中QR-右文字） === */}
      <div className="no-print mt-8">
        <h3 className="text-lg font-semibold text-gray-700 mb-2 text-center">
          單張標籤預覽 (50mm x 30mm)
        </h3>
        <div className="preview-label">
          {/* 左側：Marker 名稱（旋轉 -90 度） */}
          <div className="txt-left">
            {data.markerName}
          </div>

          {/* 中央：QR code */}
          <div className="qr-center">
            <QRCodeSVG value={previewQrValue} size={80} />
          </div>

          {/* 右側：Lot ID（旋轉 90 度） */}
          <div className="txt-right">
            {previewLotId}
          </div>
        </div>
      </div>

      {/* === 顯示所有批次資訊 === */}
      <div className="no-print mt-4 bg-white p-4 rounded-lg shadow-md max-w-4xl">
        <h4 className="font-semibold text-gray-700 mb-2">批次列表：</h4>
        <div className="space-y-1">
          {lots.map((lot, idx) => (
            <div key={idx} className="text-sm text-gray-600">
              批次 {idx + 1}: <span className="font-mono font-bold">{getLotId(lot)}</span> × {copies} 張（每張獨立一頁）
            </div>
          ))}
        </div>
      </div>

      {/* === 🖨️ 列印用 (所有批次 × 份數，每張標籤獨立一頁) === */}
      {allLabels.map((label, i) => (
        <div key={label.key || i} className="print-page">
          <div className="label-box">
            {/* 左側：Marker 名稱 */}
            <div className="txt-left">
              {label.markerName}
            </div>

            {/* 中央：QR code */}
            <div className="qr-center">
              <QRCodeSVG value={label.qrValue} size={60} />
            </div>

            {/* 右側：Lot ID */}
            <div className="txt-right">
              {label.lotId}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};