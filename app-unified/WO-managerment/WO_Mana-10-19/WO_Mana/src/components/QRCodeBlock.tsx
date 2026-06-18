// src/components/QRCodeBlock.tsx
import React, { useRef, useState, useMemo } from "react";
import { QRCodeSVG } from "qrcode.react";
import { Button } from "@/components/ui/button";
import { Clipboard, ClipboardCheck } from "lucide-react";
import { formatDate } from "@/hooks/useQRCodeData";

interface QRCodeBlockProps {
  qrValue: string;
  data: any;
  qrArray: (string | number)[];
  QR_FIELDS: string[];
  EXPECTED_LEN: number;
}

export const QRCodeBlock: React.FC<QRCodeBlockProps> = ({
  qrValue,
  data,
  qrArray,
  QR_FIELDS,
  EXPECTED_LEN,
}) => {
  const [copied, setCopied] = useState(false);
  const printRef = useRef<HTMLDivElement>(null);
  const validLen = qrArray.length === EXPECTED_LEN;

  const effectiveQrValue = useMemo(() => qrArray.map(String).join(","), [qrArray]);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(effectiveQrValue);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const handlePrint = () => {
    const content = printRef.current;
    if (!content) return;

    const printWindow = window.open("", "", "width=400,height=600");
    if (!printWindow) return;

    const doc = printWindow.document;
    doc.open();
    doc.write(`
      <html>
        <head>
          <title>列印 QRCode</title>
          <style>
            body { text-align: center; font-family: system-ui, 'Noto Sans TC', sans-serif; padding: 20px; }
            @media print { .no-print { display: none !important; } }
          </style>
        </head>
        <body>${content.innerHTML}</body>
      </html>
    `);
    doc.close();

    printWindow.onload = () => {
      printWindow.print();
      printWindow.close();
    };
  };

  return (
    <div className="qrcode flex flex-col items-center" ref={printRef}>
      <QRCodeSVG value={effectiveQrValue} size={150} />

      <div className="mt-2 text-sm">
        <div>Bead:{data?.markerName || "—"}</div>
        <div>工單：{data?.workOrderNo || "—"}</div>
        <div>型號：{data?.productModel || "—"}</div>
        <div>數目: {data?.productQuantity || "—"}</div>
        <div>日期：{formatDate(data?.date) || "—"}</div>
      </div>

      {!validLen && (
        <div className="text-red-500 text-xs mt-2">
          ⚠️ QR_FIELDS 欄位數不符 ({qrArray.length}/{EXPECTED_LEN})
        </div>
      )}

      <div className="flex gap-2 mt-3 no-print">
        <Button onClick={handleCopy} variant="outline" size="sm">
          {copied ? (
            <>
              <ClipboardCheck className="w-4 h-4 mr-1" />
              已複製
            </>
          ) : (
            <>
              <Clipboard className="w-4 h-4 mr-1" />
              複製 QR 串
            </>
          )}
        </Button>

        <Button onClick={handlePrint} variant="outline" size="sm">
          🖨️ 列印 QRCode
        </Button>
      </div>

      <details className="mt-3 text-xs w-full no-print">
        <summary>顯示 QR 串內容與欄位對照</summary>
        <div className="break-all mt-1 font-mono text-left">
          <div className="text-gray-600 mb-2">{effectiveQrValue}</div>
          <table className="w-full text-[11px] border border-gray-300">
            <thead>
              <tr className="bg-gray-100">
                <th className="border border-gray-300 p-1">#</th>
                <th className="border border-gray-300 p-1">欄位名稱</th>
                <th className="border border-gray-300 p-1">值</th>
              </tr>
            </thead>
            <tbody>
              {QR_FIELDS.map((field, i) => (
                <tr key={i}>
                  <td className="border border-gray-300 p-1 text-center">{i + 1}</td>
                  <td className="border border-gray-300 p-1">{field}</td>
                  <td
                    className={`border border-gray-300 p-1 ${
                      qrArray[i] === "" ? "bg-red-50" : ""
                    }`}
                  >
                    {qrArray[i] === "" ? "（空）" : String(qrArray[i])}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
};
