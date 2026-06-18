// src/components/WorkOrderSheet.tsx
import React from "react";
import type { WorkOrderData } from "@/types";
import { QRCodeBlock } from "@/components/QRCodeBlock";
import { useQRCodeData } from "@/hooks/useQRCodeData";
import { Droplet, Snowflake } from "lucide-react";

type Props = { data: WorkOrderData };

export const WorkOrderSheet: React.FC<Props> = ({ data }) => {
  if (!data) {
    return <div style={{ color: "red", padding: 20 }}>⚠️ 無工單資料</div>;
  }

  const { qrArray, qrValue, QR_FIELDS, EXPECTED_LEN, formatDate } =
    useQRCodeData(data);

  return (
    <div
      className="workorder-sheet mx-auto font-[Microsoft_JhengHei]"
      style={{
        width: "100%",
        maxWidth: "190mm", // ✅ 限制在 A4 可印範圍
        padding: "10mm 10mm",
      }}
    >
      <style>{`
        .sheet-title {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 12px;
          font-size: 32px;
          font-weight: bold;
          letter-spacing: 10px;
          margin: 12px 0 14px 0;
        }
        table {
          width: 100%;
          border-collapse: collapse;
          margin: 6px 0;
          font-size: 13px; /* ✅ 字體統一 */
        }
        th, td {
          border: 1px solid #333;
          padding: 4px 6px;
          text-align: center;
          vertical-align: middle;
          word-break: keep-all;
          white-space: nowrap;
        }
        th {
          background-color: #f8f8f8;
          font-weight: bold;
        }
        .section-title {
          font-weight: bold;
          font-size: 15px;
          margin-top: 10px;
          margin-bottom: 4px;
        }
        .highlight-table th {
          background-color: #f8f8f8;
        }
        .qrcode {
          margin-top: 12px;
          text-align: center;
        }
        @media print {
          @page {
            size: A4 portrait;
            margin: 8mm;
          }
          body {
            margin: 0;
          }
          .workorder-sheet {
            zoom: 0.95; /* ✅ 自動縮放以適配 A4 */
            page-break-inside: avoid;
          }
        }
      `}</style>

      {/* ✅ 主標題（保留滴定+凍乾圖示） */}
      <h1 className="sheet-title">
        <Droplet className="w-9 h-9 text-green-600" />
        <Snowflake className="w-9 h-9 text-green-600" />
        {data.markerName
          ? `${data.markerName} 滴定凍乾工單總表`
          : "滴定凍乾工單總表"}
      </h1>

      {/* ✅ 基本資料 */}
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
            <td>{formatDate(data.date)}</td>
            <th>總重量 (mg)</th>
            <td>{data.beads?.[0]?.qtyPerBead ?? ""}</td>
          </tr>
          <tr>
            <th>製令數量 (顆)</th>
            <td colSpan={3}>{data.productQuantity || "-"}</td>
          </tr>
        </tbody>
      </table>

      {/* ✅ 配藥資訊 */}
      <div className="section-title">配藥資訊</div>
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
          {data.beads?.length ? (
            data.beads.map((b, i) => (
              <tr key={i}>
                <td>{b.beadPN}</td>
                <td>{b.unit}</td>
                <td style={{ textAlign: "right" }}>{b.totalQty}</td>
                <td>{b.lotNo}</td>
                <td>{(b as any).remark ?? ""}</td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={5} style={{ color: "#999" }}>
                （無配藥資料）
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {/* ✅ 製劑點檢項目 */}
      <div className="section-title">製劑點檢項目</div>
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
          <tr>
            <td colSpan={7}>製劑人員：{data.reagent.preparedBy}</td>
          </tr>
        </tbody>
      </table>

      {/* ✅ 製劑 OD 檢查項目 */}
      <div className="section-title">製劑 OD 檢查項目</div>
      <table>
        <thead>
          <tr>
            <th>L1 OD</th>
            <th>L2 OD</th>
            <th>L1 起始 OD</th>
            <th>L2 起始 OD</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>{data.bufferBase.L1OD}</td>
            <td>{data.bufferBase.L2OD}</td>
            <td>{data.bufferBase.L1StartOD}</td>
            <td>{data.bufferBase.L2StartOD}</td>
          </tr>
        </tbody>
      </table>

      {/* ✅ 滴定凍乾機 */}
      <div className="section-title">Dispense Lot & 凍乾機</div>
      <table className="highlight-table">
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
          {data.disposeLots?.length ? (
            data.disposeLots.map((lot, i) => (
              <tr key={i}>
                <td>{i + 1}</td>
                <td>{lot.id}</td>
                <td>{lot.port}</td>
                <td>{lot.pump}</td>
                <td>{lot.freezeDry}</td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={5} style={{ color: "#999" }}>
                （無凍乾機資料）
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {/* ✅ QR Code 區塊 */}
      <div className="section-title">QRCode</div>
      <QRCodeBlock
        qrValue={qrValue}
        data={data}
        qrArray={qrArray}
        QR_FIELDS={QR_FIELDS}
        EXPECTED_LEN={EXPECTED_LEN}
      />
    </div>
  );
};
