/* =========================
 * Enums / Unions
 * ========================= */

export type ResourceType = "IVEK" | "PORT";

export type ResourceState = "idle" | "running" | "finished" | "error";

/* =========================
 * Resource
 * ========================= */

export type Resource = {
  id: string;
  type: ResourceType;
  todayUsed?: boolean; // 選填
  state: ResourceState;
  currentJob: string | null;
  remainMin: number | null;
};

/* =========================
 * API Response
 * ========================= */

export type TitrationJob = {
  workOrder: string;
  marker: string;
  quantity: number;
  pumps: string[];
  estimateHours: number;
  estimatedEndTime: string;
  remainMin: number;
};

export type TitrationStatusResponse = {
  portsTotal: number;
  portsInUse: number;
  freePorts: number;
  nextReleaseMin: number | null;
  jobs: TitrationJob[];
  resources: Resource[];
};

/* =========================
 * Freeze Dryer 狀態相關型別
 * ========================= */

export type FreezerState =
  | "idle"
  | "reserved"
  | "preparing"
  | "running"
  | "finished"
  | "error";

export type StatusStyle = {
  label: string;
  color: string;
  bg: string;
};

/** Hover 內容（進行中 + 下一輪排程） */
export type HoverInfo = {
  running?: string[]; // 進行中所有工單（同台多張）
  nextSchedule?: {
    date: string;          // 例如 "2025/12/25"
    workOrders: string[];  // 下一輪排程多張
  };
};

export type ReservedInfo = {
  workOrder: string;
  date?: string;
  style: StatusStyle;
};

export type FreezerItem = {
  id: string;
  state: FreezerState;

  /** 主卡顯示：目前那張（你要求只顯示 1 張） */
  workOrder?: string;

  /** running 狀態才會有 */
  remainMin?: number;

  /** 後端直接給顏色 */
  style?: StatusStyle;

  /** 小 R badge 用的 reserved（今天/昨天排程） */
  reserved?: ReservedInfo | null;

  /** hover 用：同台多工單 + 下一輪 */
  hover?: HoverInfo | null;
};

/* =========================
 * Freeze API Response（可選）
 * =========================
 * 你前端現在是直接 data.resources，
 * 但如果你要型別更嚴謹可以用這個。
 */
export type FreezeStatusResponse = {
  freezersTotal: number;
  freezersInUse: number;
  freeFreezers: number;
  nextReleaseMin: number | null;
  resources: FreezerItem[];

  // optional: 後端若有回傳
  statusStyle?: Record<string, StatusStyle>;
  reservedBadgeStyle?: StatusStyle;
  timestamp?: string;
};
