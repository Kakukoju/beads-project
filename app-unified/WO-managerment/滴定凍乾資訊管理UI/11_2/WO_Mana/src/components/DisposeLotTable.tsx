// src/components/DisposeLotTable.tsx
import React from "react";
import type { DisposeLot } from "@/types";
import { Button } from "@/components/ui/button";
import { ArrowLeft, Droplet, Snowflake } from "lucide-react";

type Props = {
  lots: DisposeLot[];
  onBack: () => void;
};

export const DisposeLotTable: React.FC<Props> = ({ lots, onBack }) => {
  if (!lots || lots.length === 0)
    return (
      <div className="p-6">
        {/* ✅ 標題含滴定+凍乾圖示 */}
        <div className="flex items-center gap-3 mb-4">
          <Droplet className="w-8 h-8 text-green-600" />
          <Snowflake className="w-8 h-8 text-green-600" />
          <h2 className="text-2xl font-bold text-gray-800">滴定凍乾資訊</h2>
        </div>

        <p className="text-gray-600">無 Dispense & FreezeDry 資料</p>
        <Button
          variant="outline"
          onClick={onBack}
          className="mt-6 flex items-center gap-1"
        >
          <ArrowLeft className="w-4 h-4" /> 返回首頁
        </Button>
      </div>
    );

  return (
    <div className="w-full px-10 py-6">
      {/* ✅ 返回與標題 */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Droplet className="w-8 h-8 text-green-600" />
          <Snowflake className="w-8 h-8 text-green-600" />
          <h2 className="text-2xl font-bold text-gray-800">滴定凍乾資訊</h2>
        </div>

        <Button
          variant="outline"
          onClick={onBack}
          className="flex items-center gap-1 text-gray-700 border-gray-400"
        >
          <ArrowLeft className="w-4 h-4" /> 返回首頁
        </Button>
      </div>

      {/* ✅ 表格內容 */}
      <div className="overflow-x-auto border rounded-lg shadow bg-white">
        <table className="min-w-full text-sm text-gray-700 border-collapse">
          <thead className="bg-gray-100 text-gray-900">
            <tr>
              <th className="px-4 py-3 border">#</th>
              <th className="px-4 py-3 border">Dispense Lot</th>
              <th className="px-4 py-3 border">滴定 Port</th>
              <th className="px-4 py-3 border">滴定 Pump</th>
              <th className="px-4 py-3 border">凍乾機</th>
            </tr>
          </thead>
          <tbody>
            {lots.map((lot, index) => (
              <tr
                key={lot.id}
                className={index % 2 === 0 ? "bg-white" : "bg-gray-50"}
              >
                <td className="px-4 py-2 border text-center">{index + 1}</td>
                <td className="px-4 py-2 border font-mono">{lot.id}</td>
                <td className="px-4 py-2 border text-center">{lot.port}</td>
                <td className="px-4 py-2 border text-center">{lot.pump}</td>
                <td className="px-4 py-2 border text-center">
                  {lot.freezeDry}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
