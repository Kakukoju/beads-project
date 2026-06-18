import React, { useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import type { WorkOrderData } from "@/types";

type Props = {
  data: WorkOrderData;
  onBack: () => void;
};

export const LabelPrint: React.FC<Props> = ({ data, onBack }) => {
  const lots = data.disposeLots || [];
  const [copies, setCopies] = useState(1);
  const [offsetX, setOffsetX] = useState(0);
  const [offsetY, setOffsetY] = useState(0);

  const LABEL_W = 50; // mm
  const LABEL_H = 30; // mm
  const PAGE_W = 210; // mm
  const PAGE_H = 297; // mm

  const lot = lots[0]?.id ?? "N/A";
  const qrValue = `${data.markerName},${lot}`;

  return (
    <div id="label-print-root">
      <style>{`
        @page { size: A4 portrait; margin: 0; }

        :root {
          --label-w: ${LABEL_W}mm;
          --label-h: ${LABEL_H}mm;
          --offset-x: ${offsetX}mm;
          --offset-y: ${offsetY}mm;
        }

        /* ======= 預設螢幕樣式 ======= */
        html, body {
          background: #f8fafc;
        }

        #label-print-root {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 20px;
          padding: 20px;
          font-family: "Microsoft JhengHei", sans-serif;
        }

        .print-page {
          display: none !important; /* ✅ 關鍵：螢幕時完全隱藏列印內容 */
        }

        #preview-container {
          display: flex;
          align-items: center;
          justify-content: center;
          min-height: 240px;
        }

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
          position: relative;
        }

        .preview-label::after {
          content: "";
          position: absolute;
          top: 10%;
          bottom: 10%;
          left: 50%;
          width: 1px;
          background-color: #000;
          transform: translateX(-50%);
        }

        /* ======= 列印模式 ======= */
        @media print {
          .no-print { display: none !important; }
          #preview-container { display: none !important; }

          html, body {
            width: ${PAGE_W}mm;
            height: ${PAGE_H}mm;
            margin: 0;
            padding: 0;
            background: white !important;
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
          }

          .print-page {
            display: block !important; /* ✅ 只在列印時顯示 */
            position: relative;
            width: ${PAGE_W}mm;
            height: ${PAGE_H}mm;
            page-break-after: always;
          }

          .label-box {
            position: absolute;
            left: calc(5mm + var(--offset-x));
            top: calc( (${PAGE_H}mm - var(--label-h)) / 2 + var(--offset-y) );
            width: var(--label-w);
            height: var(--label-h);
            border: 2px solid #000;
            border-radius: 4px;
            padding: 2mm;
            display: flex;
            align-items: center;
            justify-content: space-evenly;
            background: white;
            box-sizing: border-box;
          }

          .label-box::after {
            content: "";
            position: absolute;
            top: 10%;
            bottom: 10%;
            left: 50%;
            width: 1px;
            background-color: #000;
            transform: translateX(-50%);
          }

          .qr-wrap {
            flex: 0 0 45%;
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
            color: #111;
          }

          .lot {
            font-size: 10px;
            color: #333;
            margin-top: 1.5mm;
          }
        }
      `}</style>

      {/* 控制區 */}
      <div className="no-print flex flex-wrap gap-3 items-center">
        <label>
          Copies：
          <input
            type="number"
            min={1}
            value={copies}
            onChange={(e) => setCopies(Number(e.target.value))}
            className="border rounded w-20 p-1 text-center ml-1"
          />
        </label>
        <label>
          左右移動 (mm)：
          <input
            type="number"
            value={offsetX}
            onChange={(e) => setOffsetX(Number(e.target.value))}
            className="border rounded w-20 p-1 text-center ml-1"
          />
        </label>
        <label>
          上下移動 (mm)：
          <input
            type="number"
            value={offsetY}
            onChange={(e) => setOffsetY(Number(e.target.value))}
            className="border rounded w-20 p-1 text-center ml-1"
          />
        </label>

        <button
          onClick={() => window.print()}
          className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded"
        >
          🖨️ 列印標籤
        </button>
        <button
          onClick={onBack}
          className="bg-gray-300 hover:bg-gray-400 text-gray-800 px-4 py-2 rounded"
        >
          ← 返回
        </button>
      </div>

      {/* 🖥️ 預覽模式 */}
      <div id="preview-container" className="no-print">
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

      {/* 🖨️ 列印內容（螢幕不顯示） */}
      {Array.from({ length: copies }).map((_, i) => (
        <div key={i} className="print-page">
          <div className="label-box">
            <div className="qr-wrap">
              <QRCodeSVG value={qrValue} size={LABEL_H * 3.5} />
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
