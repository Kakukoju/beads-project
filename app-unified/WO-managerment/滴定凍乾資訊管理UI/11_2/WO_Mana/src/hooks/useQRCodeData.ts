import { useMemo } from "react";
import type { WorkOrderData } from "@/types";




// ✅ 日期格式化工具
export const formatDate = (input?: string | Date): string => {
  if (!input) return "";
  try {
    if (input instanceof Date) {
      const y = input.getFullYear();
      const m = String(input.getMonth() + 1).padStart(2, "0");
      const d = String(input.getDate()).padStart(2, "0");
      return `${y}-${m}-${d}`;
    }
    const parsed = new Date(input);
    if (!isNaN(parsed.getTime())) {
      const y = parsed.getFullYear();
      const m = String(parsed.getMonth() + 1).padStart(2, "0");
      const d = String(parsed.getDate()).padStart(2, "0");
      return `${y}-${m}-${d}`;
    }
    const match = input.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (match) {
      const [, m, d, y] = match;
      return `${y}-${m.padStart(2, "0")}-${d.padStart(2, "0")}`;
    }
    return input;
  } catch {
    return String(input);
  }
};

export const useQRCodeData = (data: WorkOrderData | null) => {
  // === 固定常數 ===
  const EXPECTED_LEN = 32;
  const QR_FIELDS = [
    "工單號", "製令數量", "bead_name", "PN", "是否懸浮", "日期",
    "L1_反應_OD", "L1_起始_OD", "L2_反應_OD", "L2_起始_OD",
    "liquid_storge_避光", "liquid_storge_冰浴",
    "滴定_避光", "滴定_冰浴", "滴定_攪拌",
    "Dispense_Lot_1", "port_1", "pump_1", "凍乾機_1",
    "Dispense_Lot_2", "port_2", "pump_2", "凍乾機_2",
    "Dispense_Lot_3", "port_3", "pump_3", "凍乾機_3",
    "Dispense_Lot_4", "port_4", "pump_4", "凍乾機_4",
    "淨重g",
  ];

  // === 先生成穩定的空陣列（保證 hook 不報錯） ===
  const emptyArray = useMemo(() => Array(EXPECTED_LEN).fill(""), []);

  // === 用 useMemo 安全包裹 ===
  const qrArray = useMemo<(string | number)[]>(() => {
    if (!data) return emptyArray; // ✅ 改：返回穩定的 memoized 陣列
    return [
      data.workOrderNo ?? "",
      data.productQuantity ?? "",
      data.markerName ?? "",
      data.productModel ?? "",
      data.reagent?.confirm?.suspension ? "true" : "false",
      formatDate(data.date) || "",
      data.bufferBase?.L1OD ?? "",
      data.bufferBase?.L1StartOD ?? "",
      data.bufferBase?.L2OD ?? "",
      data.bufferBase?.L2StartOD ?? "",
      data.reagent?.confirm?.storeLight ? "true" : "false",
      data.reagent?.confirm?.storeIce ? "true" : "false",
      data.reagent?.confirm?.dyeing ? "true" : "false",
      data.reagent?.confirm?.washing ? "true" : "false",
      data.reagent?.confirm?.stir ? "true" : "false",
      data.disposeLots?.[0]?.id ?? "",
      data.disposeLots?.[0]?.port ?? "",
      data.disposeLots?.[0]?.pump ?? "",
      data.disposeLots?.[0]?.freezeDry ?? "",
      data.disposeLots?.[1]?.id ?? "",
      data.disposeLots?.[1]?.port ?? "",
      data.disposeLots?.[1]?.pump ?? "",
      data.disposeLots?.[1]?.freezeDry ?? "",
      data.disposeLots?.[2]?.id ?? "",
      data.disposeLots?.[2]?.port ?? "",
      data.disposeLots?.[2]?.pump ?? "",
      data.disposeLots?.[2]?.freezeDry ?? "",
      data.disposeLots?.[3]?.id ?? "",
      data.disposeLots?.[3]?.port ?? "",
      data.disposeLots?.[3]?.pump ?? "",
      data.disposeLots?.[3]?.freezeDry ?? "",
      data.beads?.[0]?.totalQty ?? "",
    ];
  }, [data, emptyArray]);

  const qrValue = useMemo(() => qrArray.map(String).join(","), [qrArray]);

  return { qrArray, qrValue, QR_FIELDS, EXPECTED_LEN };
};
