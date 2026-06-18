import React, { useState, useEffect } from "react";
import { Loader2, Save, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { Bead, WorkOrderData } from "@/types";

type Props = {
  data: WorkOrderData;
  onSave: (updated: WorkOrderData) => Promise<void>;
  onBack: () => void; // 返回主畫面
};

export const BeadTable: React.FC<Props> = ({ data, onSave, onBack }) => {
  const [editableBeads, setEditableBeads] = useState<Bead[]>([]);
  const [saving, setSaving] = useState(false);

  // ✅ 初始化或切換工單時載入資料
  useEffect(() => {
    if (data?.beads) {
      setEditableBeads(data.beads.map((b) => ({ ...b, remark: b.remark ?? "" })));
    }
  }, [data]);

  // ✅ 備註修改
  const handleRemarkChange = (index: number, value: string) => {
    const updated = [...editableBeads];
    updated[index].remark = value;
    setEditableBeads(updated);
  };

  // ✅ 儲存資料
  const handleSave = async () => {
    try {
      setSaving(true);
      const updatedData: WorkOrderData = {
        ...data,
        beads: editableBeads.map((b) => ({ ...b, remark: b.remark ?? "" })),
      };
      await onSave(updatedData);
      alert("✅ 備註已儲存成功！");
    } catch (err) {
      alert(`❌ 儲存失敗：${(err as Error).message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="w-full px-10 py-6">
      {/* 🔙 返回與標題 */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-800 mb-1">配藥資訊</h2>
          <p className="text-gray-600 text-sm">
            工單號：<span className="font-mono">{data.workOrderNo}</span>　
            產品型號：<span className="font-mono">{data.productModel}</span>　
            Marker：<span className="font-mono">{data.markerName ?? "-"}</span>
          </p>
        </div>
        <Button
          variant="outline"
          onClick={onBack}
          className="flex items-center gap-1 text-gray-700 border-gray-400"
        >
          <ArrowLeft className="w-4 h-4" /> 返回首頁
        </Button>
      </div>

      {/* 📦 表格內容 */}
      <div className="overflow-x-auto border rounded-lg shadow bg-white">
        <table className="min-w-full text-sm text-gray-700 border-collapse">
          <thead className="bg-gray-100 text-gray-900">
            <tr>
              <th className="px-4 py-3 border">BOM P/N</th>
              <th className="px-4 py-3 border">UOM</th>
              <th className="px-4 py-3 border text-right">Total Qty</th>
              <th className="px-4 py-3 border">Lot No.</th>
              <th className="px-4 py-3 border w-[30%]">備註</th>
            </tr>
          </thead>
          <tbody>
            {editableBeads.map((bead, index) => (
              <tr
                key={index}
                className={index % 2 === 0 ? "bg-white" : "bg-gray-50"}
              >
                <td className="px-4 py-2 border font-mono">{bead.beadPN}</td>
                <td className="px-4 py-2 border text-center">{bead.unit}</td>
                <td className="px-4 py-2 border text-right">
                  {bead.totalQty.toLocaleString()}
                </td>
                <td className="px-4 py-2 border">{bead.lotNo}</td>
                <td className="px-4 py-2 border">
                  <Input
                    type="text"
                    value={bead.remark ?? ""}
                    placeholder="輸入備註..."
                    className="w-full h-8 text-sm"
                    onChange={(e) => handleRemarkChange(index, e.target.value)}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 💾 儲存按鈕 */}
      <div className="mt-6 flex justify-end">
        <Button
          onClick={handleSave}
          disabled={saving}
          className="bg-green-600 hover:bg-green-700 text-white"
        >
          {saving ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              儲存中...
            </>
          ) : (
            <>
              <Save className="mr-2 h-4 w-4" />
              儲存備註
            </>
          )}
        </Button>
      </div>
    </div>
  );
};
