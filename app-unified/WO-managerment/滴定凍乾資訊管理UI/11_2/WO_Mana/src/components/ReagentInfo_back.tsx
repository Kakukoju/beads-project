// src/components/ReagentInfo.tsx
import React, {
  useImperativeHandle,
  useState,
  forwardRef,
  useEffect,
} from "react";
import type { Reagent } from "@/types";

export type ReagentStatus = Record<
  "suspension" | "storeLight" | "storeIce" | "dyeing" | "washing" | "stir",
  boolean
>;

type Props = {
  reagent: Reagent;
  onSave?: (status: ReagentStatus) => Promise<void>;
};

export const ReagentInfo = forwardRef(({ reagent }: Props, ref) => {
  // ✅ 初始化 confirm 狀態
  const [checkboxes, setCheckboxes] = useState<ReagentStatus>({
    suspension: reagent.confirm.suspension ?? false,
    storeLight: reagent.confirm.storeLight ?? false,
    storeIce: reagent.confirm.storeIce ?? false,
    dyeing: reagent.confirm.dyeing ?? false,
    washing: reagent.confirm.washing ?? false,
    stir: reagent.confirm.stir ?? false,
  });

  // ✅ 當 reagent 改變時自動刷新
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

  // ✅ 切換欄位狀態
  const toggle = (key: keyof ReagentStatus) => {
    setCheckboxes((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  // ✅ 提供父層存取
  useImperativeHandle(ref, () => ({
    getReagentStatus: () => checkboxes,
  }));

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
    stir: "滴定時攪拌",
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
                      className="border px-4 py-2 text-center cursor-pointer select-none hover:bg-green-50"
                      onClick={() => toggle(key)}
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
});
