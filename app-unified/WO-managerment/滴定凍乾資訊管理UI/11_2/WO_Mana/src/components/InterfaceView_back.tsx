// src/components/InterfaceView.tsx
import React, { useEffect, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import type { WorkOrderData } from "@/types";
import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";
import { useQRCodeData } from "@/hooks/useQRCodeData";

type Props = {
  data: WorkOrderData;
  onBack?: () => void;
};

export const InterfaceView: React.FC<Props> = ({ data, onBack }) => {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [zoomRatio, setZoomRatio] = useState(1);
  const { qrValue } = useQRCodeData(data);

  /** ✅ 自動調整 zoom，確保整份內容 fit 在 A4 一頁內 */
  useEffect(() => {
    const adjustZoom = () => {
      const el = wrapperRef.current;
      if (!el) return;
      const A4_HEIGHT = 1122; // 約等於 297mm @96dpi
      const h = el.scrollHeight;
      if (h > A4_HEIGHT) {
        const ratio = (A4_HEIGHT - 20) / h;
        setZoomRatio(Math.max(0.85, Math.min(1, ratio)));
      } else {
        setZoomRatio(1);
      }
    };
    adjustZoom();
    window.addEventListener("resize", adjustZoom);
    return () => window.removeEventListener("resize", adjustZoom);
  }, [data]);

  const username = localStorage.getItem("username") || "未知使用者";
  const printTime = new Date().toLocaleString("zh-TW", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div
      ref={wrapperRef}
      className="print-root"
      style={{
        width: "210mm",
        height: "auto",
        margin: "0 auto",
        background: "white",
        fontFamily: "Microsoft JhengHei, sans-serif",
        fontSize: "13px",
        overflow: "hidden",
        padding: "8mm 10mm 10mm",
        boxSizing: "border-box",
        zoom: zoomRatio, // ✅ 使用 zoom 而非 transform
      }}
    >
      <style>{`
        @page { size: A4 portrait; margin: 2mm; }
        * { box-sizing: border-box; }

        table {
          border-collapse: collapse;
          width: 100%;
          margin-top: 4px;
          page-break-inside: avoid !important;
        }

        th, td {
          border: 1px solid #333;
          padding: 3px 6px;
          text-align: center;
          vertical-align: middle;
        }

        th {
          background: #f8f8f8;
          font-weight: bold;
        }

        h2 {
          text-align: center;
          font-size: 18px;
          margin: 4mm 0;
          letter-spacing: 1mm;
        }

        h3 {
          margin-top: 4mm;
          margin-bottom: 2mm;
        }

        @media print {
          html, body {
            width: 210mm;
            height: 297mm;
            margin: 0;
            padding: 0;
            overflow: hidden;
            -webkit-print-color-adjust: exact;
          }
          .no-print { display: none !important; }
          .print-root {
            page-break-inside: avoid !important;
            page-break-before: avoid !important;
            page-break-after: avoid !important;
            zoom: 0.93 !important; /* ✅ 再次保險壓縮 */
          }
        }

        .footer-wrapper {
          page-break-inside: avoid !important;
          page-break-before: avoid !important;
          break-inside: avoid !important;
          margin-top: 2mm;
        }
      `}</style>

      {/* ===== 標題區 ===== */}
      <div style={{ position: "relative", textAlign: "center", marginBottom: "4mm" }}>
        <h2>
          {data.markerName
            ? `${data.markerName} 配藥紀錄表`
            : "配藥紀錄表"}
        </h2>
        <div
          style={{ position: "absolute", right: 0, top: 0 }}
          className="no-print"
        >
          <Button
            variant="outline"
            onClick={() => onBack?.()}
            className="flex items-center gap-1 border-gray-400 text-gray-700"
          >
            <ArrowLeft className="w-4 h-4" /> 返回首頁
          </Button>
        </div>
      </div>

      {/* ===== 基本資料 ===== */}
      <table>
        <tbody>
          <tr>
            <th>工單號碼</th>
            <td>{data.workOrderNo}</td>
            <th>產品型號</th>
            <td>{data.productModel}</td>
          </tr>
          <tr>
            <th>日期</th>
            <td>{data.date}</td>
            <th>總重量 (g)</th>
            <td>{data.beads?.[0]?.qtyPerBead ?? ""}</td>
          </tr>
          <tr>
            <th>製令數量 (顆)</th>
            <td colSpan={3}>{data.productQuantity ?? "-"}</td>
          </tr>
        </tbody>
      </table>

      {/* ===== 配藥資料 ===== */}
      <h3>配藥資料</h3>
      <table>
        <thead>
          <tr>
            <th>BOM P/N</th>
            <th>UOM</th>
            <th>Total Qty</th>
            <th>Lot No.</th>
            <th>備註</th>
          </tr>
        </thead>
        <tbody>
          {data.beads?.map((b, i) => (
            <tr key={i}>
              <td>{b.beadPN}</td>
              <td>{b.unit}</td>
              <td>{b.totalQty}</td>
              <td>{b.lotNo}</td>
              <td>{b.remark || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* ===== 製劑項目 ===== */}
      <h3>製劑點檢項目</h3>
      <div style={{ marginBottom: "2mm" }}>
        製劑人員：{data.reagent?.preparedBy || "—"}
      </div>
      <table>
        <thead>
          <tr>
            <th></th>
            <th>懸浮物</th>
            <th>儲存時避光</th>
            <th>儲存時冰浴</th>
            <th>滴定時避光</th>
            <th>滴定時冰浴</th>
            <th>滴定時攪拌</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>是</td>
            <td>{data.reagent.confirm.suspension ? "✓" : ""}</td>
            <td>{data.reagent.confirm.storeLight ? "✓" : ""}</td>
            <td>{data.reagent.confirm.storeIce ? "✓" : ""}</td>
            <td>{data.reagent.confirm.dyeing ? "✓" : ""}</td>
            <td>{data.reagent.confirm.washing ? "✓" : ""}</td>
            <td>{data.reagent.confirm.stir ? "✓" : ""}</td>
          </tr>
          <tr>
            <td>否</td>
            <td>{!data.reagent.confirm.suspension ? "✓" : ""}</td>
            <td>{!data.reagent.confirm.storeLight ? "✓" : ""}</td>
            <td>{!data.reagent.confirm.storeIce ? "✓" : ""}</td>
            <td>{!data.reagent.confirm.dyeing ? "✓" : ""}</td>
            <td>{!data.reagent.confirm.washing ? "✓" : ""}</td>
            <td>{!data.reagent.confirm.stir ? "✓" : ""}</td>
          </tr>
        </tbody>
      </table>

      {/* ===== Dispense Lot ===== */}
      <h3>Dispense Lot & 凍乾機</h3>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Dispense Lot</th>
            <th>滴定 port</th>
            <th>滴定 pump</th>
            <th>凍乾機</th>
          </tr>
        </thead>
        <tbody>
          {data.disposeLots?.map((lot, i) => (
            <tr key={i}>
              <td>{i + 1}</td>
              <td>{lot.id}</td>
              <td>{lot.port}</td>
              <td>{lot.pump}</td>
              <td>{lot.freezeDry}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* ===== Footer ===== */}
      <div className="footer-wrapper">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            paddingTop: "2mm",
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: "3mm" }}>
            <img
              src={`${import.meta.env.BASE_URL}skylaLogo.png`}
              alt="Skyla Logo"
              style={{ width: "28mm", height: "auto", objectFit: "contain" }}
            />
            <div
              style={{
                fontSize: "10px",
                color: "#333",
                lineHeight: 1.4,
                fontFamily: "Microsoft JhengHei",
              }}
            >
              <div><strong>列印者：</strong>{username}</div>
              <div><strong>列印時間：</strong>{printTime}</div>
              <div><strong>版本：</strong>MHAE-09 L</div>
            </div>
          </div>

          <div
            style={{
              border: "1px solid #ccc",
              borderRadius: 4,
              padding: "4mm 6mm",
              background: "white",
              boxShadow: "0 1px 3px rgba(0,0,0,0.1)",
              display: "flex",
              flexDirection: "row",
              alignItems: "center",
              gap: "6mm",
            }}
          >
            <div style={{ fontSize: 11, lineHeight: 1.5 }}>
              <div><strong>Bead：</strong>{data.markerName}</div>
              <div><strong>工單號：</strong>{data.workOrderNo}</div>
              <div><strong>產品型號：</strong>{data.productModel}</div>
              <div><strong>工單數目：</strong>{data.productQuantity}</div>
              <div><strong>日期：</strong>{data.date}</div>
            </div>
            <QRCodeSVG value={qrValue} size={90} />
          </div>
        </div>
      </div>
    </div>
  );
};
