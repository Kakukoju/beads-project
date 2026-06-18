// src/api/workOrder.ts
import { API_BASE, DEFAULT_HEADERS } from "@/config";

export const getWorkOrder = async (workOrder: string) => {
  const url = `${API_BASE}/get_workorder?work_order=${encodeURIComponent(workOrder)}`;
  console.log("🔗 Fetching:", url);
  const res = await fetch(url);
  if (!res.ok) throw new Error(`查詢失敗 (${res.status})`);
  return await res.json();
};

// ✅ 儲存工單
export const saveWorkOrder = async (data: any) => {
  const url = `${API_BASE}/save_workorder`;
  console.log("💾 POST to:", url);

  const res = await fetch(url, {
    method: "POST",
    headers: DEFAULT_HEADERS,
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`儲存失敗 (${res.status})`);
  return await res.json();
};
