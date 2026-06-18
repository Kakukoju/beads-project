// src/components/InterfaceView.tsx
import React, { useEffect, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import type { WorkOrderData } from "@/types";
import { useQRCodeData } from "@/hooks/useQRCodeData";
import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";



type Props = {
  data: WorkOrderData;
  onBack?: () => void;
};

export const InterfaceView: React.FC<Props> = ({ data, onBack }) => {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const qrRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [qrFixed, setQrFixed] = useState(false);
  const { qrValue } = useQRCodeData(data);

  /** ✅ 動態縮放控制 */
  useEffect(() => {
    const adjustScale = () => {
      const wrap = wrapperRef.current;
      const content = contentRef.current;
      const qr = qrRef.current;
      if (!wrap || !content || !qr) return;

      const A4_HEIGHT = 1122;
      const GAP = 20;
      content.style.transform = "none";
      const totalHeight = content.scrollHeight + qr.offsetHeight + GAP;
      const scaleFactor = Math.min(1, (A4_HEIGHT - GAP) / totalHeight);
      const clamped = Math.max(0.82, scaleFactor);
      setScale(clamped);
      setQrFixed(totalHeight > A4_HEIGHT);
    };

    adjustScale();
    window.addEventListener("resize", adjustScale);
    return () => window.removeEventListener("resize", adjustScale);
  }, [data]);

  /** ✅ QC 比對單元格 */
  const renderQcCell = (
    label: string,
    key: keyof WorkOrderData["qcCheckResult"],
    value: number
  ) => {
    const qc = data.qcCheckResult?.[key];
    const pass = qc?.pass;
    const color = pass === true ? "green" : pass === false ? "red" : "gray";
    const symbol = pass === true ? "✅" : pass === false ? "❌" : "⚠️";
    return (
      <td style={{ color, fontWeight: 500 }}>
        {symbol} {value ?? "-"}
      </td>
    );
  };

  const hasQcFail =
    data.qcCheckResult &&
    Object.values(data.qcCheckResult).some((r) => r.pass === false);

  // ✅ 顯示 QC 標準範圍表頭
  const qcRanges = data.qcRanges || {};
  const rangeLine = [
    `L1-OD: ${qcRanges["L1-OD"] ?? "—"}`,
    `L2-OD: ${qcRanges["L2-OD"] ?? "—"}`,
    `L1-起始OD: ${qcRanges["L1-起始OD"] ?? "—"}`,
    `L2-起始OD: ${qcRanges["L2-起始OD"] ?? "—"}`,
  ].join("　");

  return (
    <div
      ref={wrapperRef}
      id="print-root"
      style={{
        width: "210mm",
        height: "283mm",
        margin: "0",
        padding: "0",
        position: "relative",
        left: "-12mm",
        background: "white",
        fontFamily: "Microsoft JhengHei, sans-serif",
        fontSize: "13px",
        overflow: "hidden",
      }}
    >
      <style>{`
        @page { size: A4 portrait; margin: 0; }
        table {
          border-collapse: collapse;
          width: 100%;
          margin-top: 4px;
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
          margin: 6mm 0 4mm;
          letter-spacing: 1mm;
        }
        .no-break { break-inside: avoid; page-break-inside: avoid; }
        @media print { .no-print { display: none !important; } }
      `}</style>

      {/* ===== 可縮放內容 ===== */}
      <div
        ref={contentRef}
        className="no-break"
        style={{
          marginLeft: "10mm",
          marginRight: "6mm",
          transform: `scale(${scale})`,
          transformOrigin: "top left",
          transition: "transform 0.3s ease",
          width: "calc(100% - 16mm)",
        }}
      >
        {/* === 標題 + 返回首頁 === */}
        {/* === 標題 + 返回首頁 === */}
        <div
          style={{
            position: "relative",
            textAlign: "center",
            marginBottom: "4mm",
          }}
        >
          {/* ✅ 標題置中 */}
          <h2 style={{ margin: 0, fontWeight: 600 }}>
            {data.markerName
              ? `${data.markerName} 滴定凍乾工單總表`
              : "滴定凍乾工單總表"}
          </h2>

          {/* ✅ 返回首頁按鈕靠右上角 */}
          <div
            style={{
              position: "absolute",
              right: 0,
              top: 0,
            }}
            className="no-print"
          >
            <Button
              variant="outline"
              onClick={onBack}
              className="flex items-center gap-1 border-gray-400 text-gray-700"
            >
              <ArrowLeft className="w-4 h-4" /> 返回首頁
            </Button>
          </div>
        </div>



        {/* === 基本資料 === */}
        <table>
          <tbody>
            <tr>
              <th style={{ width: "20%" }}>工單號碼</th>
              <td style={{ width: "30%" }}>{data.workOrderNo}</td>
              <th style={{ width: "20%" }}>產品型號</th>
              <td style={{ width: "30%" }}>{data.productModel}</td>
            </tr>
            <tr>
              <th>日期</th>
              <td>{data.date}</td>
              <th>總重量 (mg)</th>
              <td>{data.beads?.[0]?.qtyPerBead ?? ""}</td>
            </tr>
            <tr>
              <th>製令數量 (顆)</th>
              <td colSpan={3}>{data.productQuantity ?? "-"}</td>
            </tr>
          </tbody>
        </table>

        {/* === 配藥資料 === */}
        <h3 style={{ marginTop: "6mm", marginBottom: "2mm" }}>配藥資料</h3>
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

        {/* === 製劑點檢項目 === */}
        <h3 style={{ marginTop: "6mm", marginBottom: "2mm" }}>製劑點檢項目</h3>
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

        {/* === 試劑 OD 區塊 (含 QC 標準範圍) === */}
        <h3 style={{ marginTop: "6mm", marginBottom: "2mm" }}>試劑 OD</h3>
        <div
          style={{
            fontSize: "12px",
            color: "#444",
            marginBottom: "2mm",
            lineHeight: 1.4,
          }}
        >
          QC 標準範圍：{rangeLine}
        </div>
        <table>
          <thead>
            <tr>
              <th>L1 起始 OD</th>
              <th>L1 反應 OD</th>
              <th>L2 起始 OD</th>
              <th>L2 反應 OD</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              {renderQcCell("L1 起始 OD", "L1StartOD", data.bufferBase?.L1StartOD ?? 0)}
              {renderQcCell("L1 OD", "L1OD", data.bufferBase?.L1OD ?? 0)}
              {renderQcCell("L2 起始 OD", "L2StartOD", data.bufferBase?.L2StartOD ?? 0)}
              {renderQcCell("L2 OD", "L2OD", data.bufferBase?.L2OD ?? 0)}
            </tr>
          </tbody>
        </table>
        {hasQcFail && (
          <div style={{ color: "red", fontWeight: "bold", marginTop: "3mm" }}>
            ⚠️ OD 超出 QC 範圍，請複查！
          </div>
        )}

        {/* === Dispense Lot === */}
        <h3 style={{ marginTop: "6mm", marginBottom: "2mm" }}>
          Dispense Lot & 凍乾機
        </h3>
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
      </div>

      {/* ===== QR Code 區塊 ===== */}
      <div
        ref={qrRef}
        style={{
          position: qrFixed ? "absolute" : "relative",
          bottom: qrFixed ? "10mm" : "auto",
          left: "8mm",
          right: "8mm",
          display: "grid",
          gridTemplateColumns: "1fr auto",
          alignItems: "center",
          columnGap: "10mm",
          padding: "5mm 8mm",
          border: "1px solid #ccc",
          borderRadius: 4,
          background: "white",
          width: "calc(100% - 16mm)",
          boxSizing: "border-box",
        }}
      >
        <div style={{ fontSize: 12, lineHeight: 1.6, textAlign: "left" }}>
          <div><strong>Bead：</strong>{data.markerName}</div>
          <div><strong>工單號：</strong>{data.workOrderNo}</div>
          <div><strong>產品型號：</strong>{data.productModel}</div>
          <div><strong>工單數目：</strong>{data.productQuantity}</div>
          <div><strong>日期：</strong>{data.date}</div>
        </div>
        <div style={{ justifySelf: "end" }}>
          <QRCodeSVG value={qrValue} size={120} />
        </div>
      </div>


    </div>
  );
};
