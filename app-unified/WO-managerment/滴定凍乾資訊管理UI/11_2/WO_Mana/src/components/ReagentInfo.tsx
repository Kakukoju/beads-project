// src/components/ReagentInfo.tsx
import React, {
  // useImperativeHandle, // <- 移除
  useState,
  // forwardRef, // <- 移除
  useEffect,
} from "react";
import type { Reagent } from "@/types";

export type ReagentStatus = Record<
  "suspension" | "storeLight" | "storeIce" | "dyeing" | "washing" | "stir",
  boolean
>;

type Props = {
  reagent: Reagent;
  // onSave?: (status: ReagentStatus) => Promise<void>; // <- 移除
};

// 移除 forwardRef，改為標準的 React.FC
export const ReagentInfo: React.FC<Props> = ({ reagent }) => {
  // ✅ 初始化 confirm 狀態
  // ✅ 加上 debug
  console.log("📦 ReagentInfo 收到的 reagent:", reagent);
  console.log("📦 reagent.confirm:", reagent.confirm);
  const [checkboxes, setCheckboxes] = useState<ReagentStatus>({
    suspension: reagent.confirm.suspension ?? false,
    storeLight: reagent.confirm.storeLight ?? false,
    storeIce: reagent.confirm.storeIce ?? false,
    dyeing: reagent.confirm.dyeing ?? false,
    washing: reagent.confirm.washing ?? false,
    stir: reagent.confirm.stir ?? false,
  });
   console.log("📦 checkboxes:", checkboxes); // ✅ 加上這行
  // ✅ 當 reagent 改變時自動刷新 (這個保留，確保 props 更新時 UI 也更新)
  useEffect(() => {
    setCheckboxes({
      suspension: reagent.confirm.suspension ?? false,
      storeLight: reagent.confirm.storeLight ?? false,
      storeIce: reagent.confirm.storeIce ?? false,
      dyeing: reagent.confirm.dyeing ?? false,
      washing: reagent.confirm.washing ?? false,
      stir: reagent.confirm.stir ?? false,
    });
  }, [reagent]);

  // 🔽 移除 toggle 函式 和 useImperativeHandle
  // const toggle = ... 
  // useImperativeHandle(...)

  const columns: (keyof ReagentStatus)[] = [
    "suspension",
    "storeLight",
    "storeIce",
    "dyeing",
    "washing",
    "stir",
  ];

  const labels: Record<keyof ReagentStatus, string> = {
    suspension: "懸浮物",
    storeLight: "儲存時避光",
    storeIce: "儲存時冰浴",
    dyeing: "滴定時避光",
    washing: "滴定時冰浴",
    stir: "滴定_Mixing",
  };

  return (
    <div className="w-full">
      <h3 className="text-lg font-semibold mb-2 text-gray-800">
        製劑點檢項目
      </h3>
      <p className="text-sm text-gray-600 mb-4">
        製劑人員：<span className="font-medium">{reagent.preparedBy}</span>
      </p>

      <div className="overflow-x-auto border rounded-lg shadow bg-white">
        <table className="min-w-full border-collapse text-sm text-gray-800">
          <thead className="bg-gray-100">
            {/* ... (thead 內容不變) ... */}
            <tr>
              <th className="border px-4 py-2 text-center w-[80px]"></th>
              {columns.map((key) => (
                <th
                  key={key}
                  className="border px-4 py-2 text-center font-semibold"
                >
                  {labels[key]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {["是", "否"].map((label) => (
              <tr key={label} className="even:bg-gray-50">
                <td className="border px-4 py-2 text-center font-medium text-gray-700">
                  {label}
                </td>
                {columns.map((key) => {
                  const checked = checkboxes[key];
                  const isThisRow =
                    (label === "是" && checked) ||
                    (label === "否" && !checked);
                  return (
                    <td
                      key={key + label}
                      // 🔽 移除互動樣式和 onClick 事件
                      className="border px-4 py-2 text-center" 
                      // onClick={() => toggle(key)} // <- 移除
                    >
                      {isThisRow ? "✔" : ""}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};