// src/components/QcInfoPage.tsx
import React from "react";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { WorkOrderData } from "@/types";
import { ReagentInfo } from "@/components/ReagentInfo";
import { BufferBaseTable } from "@/components/BufferBaseTable";

type Props = {
  data: WorkOrderData;
  onBack: () => void;
};

export const QcInfoPage: React.FC<Props> = ({ data, onBack }) => {
  React.useEffect(() => {
    console.log("📦 收到的 data:", data);
    console.log("📦 reagent.confirm:", data?.reagent?.confirm);
  }, [data]);

  return (
    <div className="w-full px-10 py-6">
      {/* 標題列 */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-800">品質檢驗資訊</h2>
          <p className="text-gray-600 text-sm">
            工單號：<span className="font-mono">{data.workOrderNo}</span>
            產品型號：<span className="font-mono">{data.productModel}</span>
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
      
      {/* 上方表格：製劑點檢 */}
      <div className="bg-white shadow rounded-lg p-6 mb-8 border">
        <ReagentInfo reagent={data.reagent} />
      </div>

      {/* 下方表格：製劑 OD */}
      <div className="bg-white shadow rounded-lg p-6 border">
        <BufferBaseTable
          data={data.bufferBase}
          qcRanges={data.qcRanges}
          qcCheckResult={data.qcCheckResult}
          digits={4}
        />
      </div>
    </div>
  );
};
function useEffect(arg0: () => void, arg1: WorkOrderData[]): React.ReactNode {
  throw new Error("Function not implemented.");
}

