import React, { useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import type { WorkOrderData } from "@/types";

type LabelPrintProps = {
  data: WorkOrderData;
  onBack: () => void;
};

/**
 * 🏷️ 標籤列印元件 (純文字、置中排列、符合 label 大小)
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

  // ✅ 生成所有要列印的標籤
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

  // 預覽用
  const previewLotId = getLotId(lots[0]);
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

        /* === 標籤內容容器佈局（橫向：左文字-中QR-右文字） === */
        .content-container {
          display: flex;
          flex-direction: row;
          align-items: center;
          justify-content: center;
          width: 100%;
          height: 100%;
          text-align: center;
          gap: 2mm;
        }

        .qr-center {
          flex-shrink: 0;
        }

        .label-text-side {
          writing-mode: vertical-rl;
          text-orientation: mixed;
          font-size: 10pt;
          font-weight: bold;
          line-height: 1.2;
          word-break: break-all;
        }

        /* === 預覽樣式 === */
        .preview-label {
          width: var(--label-w);
          height: var(--label-h);
          border: 2px solid #000;
          border-radius: 4px;
          padding: 2mm;
          background: white;
          box-sizing: border-box;
          margin-top: 10px;
          box-shadow: 0 4px 6px rgba(0,0,0,0.1);
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .print-page {
          display: none;
        }

        /* === 列印模式 === */
        @media print {
          body * {
            visibility: hidden !important;
          }

          #label-print-root,
          #label-print-root * {
            visibility: visible !important;
          }

          .no-print, .preview-label {
            display: none !important;
          }

          html, body {
            margin: 0;
            padding: 0;
            background: white !important;
            width: 100%;
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

          .print-page {
            display: flex !important; 
            align-items: center;
            justify-content: center;
            width: 100vw;
            height: 100vh;
            page-break-after: always;
            break-after: page;
          }

          .label-box {
            width: var(--label-w);
            height: var(--label-h);
            padding: 2mm;
            box-sizing: border-box;
            display: flex;
            align-items: center;
            justify-content: center;
            transform: translate(var(--offset-x), var(--offset-y));
          }
        }
      `}</style>

      {/* === 控制區 === */}
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
          左右偏置 (mm)：
          <input
            type="number"
            value={offsetX}
            onChange={(e) => setOffsetX(Number(e.target.value))}
            className="border border-gray-300 rounded w-20 p-1 text-center ml-2"
          />
        </label>
        <label className="flex items-center text-sm font-medium text-gray-700">
          上下偏置 (mm)：
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
          🖨️ 開始列印
        </button>
        <button
          onClick={onBack}
          className="bg-gray-400 hover:bg-gray-500 text-gray-800 px-4 py-2 rounded-lg transition duration-200 shadow-md"
        >
          ← 返回
        </button>
      </div>

      {/* === 🖥️ 預覽模式 === */}
      <div className="no-print mt-8">
        <h3 className="text-lg font-semibold text-gray-700 mb-2 text-center">
          標籤預覽 (50mm x 30mm)
        </h3>
        <div className="preview-label">
          <div className="content-container">
            <div className="label-text-side">{data.markerName}</div>
            <div className="qr-center">
              <QRCodeSVG value={previewQrValue} size={80} />
            </div>
            <div className="label-text-side">{previewLotId}</div>
          </div>
        </div>
      </div>

      {/* === 🖨️ 列印用 === */}
      {allLabels.map((label, i) => (
        <div key={label.key || i} className="print-page">
          <div className="label-box">
            <div className="content-container">
              <div className="label-text-side">{label.markerName}</div>
              <div className="qr-center">
                <QRCodeSVG value={label.qrValue} size={80} />
              </div>
              <div className="label-text-side">{label.lotId}</div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};