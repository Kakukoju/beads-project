// src/types.ts

// === Bead：單筆試劑 ===
export type Bead = {
  beadName: string;
  beadPN: string;
  unit: string;
  qtyPerBead: number; // 單顆重量
  totalQty: number;   // 總重量
  lotNo: string;
  remark?: string;
};

// === Reagent：配藥人員與操作確認 ===
export type Reagent = {
  preparedBy: string;
  confirm: {
    suspension: boolean; // 懸浮物
    storeLight: boolean; // 儲存時避光
    storeIce: boolean;   // 儲存時冰浴
    dyeing: boolean;     // 滴定時避光
    washing: boolean;    // 滴定時冰浴
    stir: boolean;       // 滴定時攪拌
  };
};

// === BufferBaseInfo：製劑 OD 數值 ===
export type BufferBaseInfo = {
  L1OD: number;
  L2OD: number;
  L1StartOD: number; // L1 起始 OD
  L2StartOD: number; // L2 起始 OD
};

// === QC 範圍（Liquid Form QC 來源表） ===
export type QcRanges = {
  "L1-OD"?: string | null;
  "L2-OD"?: string | null;
  "L1-起始OD"?: string | null;
  "L2-起始OD"?: string | null;
};

// === QC 檢查項目 ===
export type QcCheckItem = {
  value?: number | null;       // 實測值（可選，若無 QC）
  qc_range?: string | null;    // QC 標準範圍（如 "0.2~0.35"）
  pass?: boolean | null;       // true=通過, false=不通過, null=未檢
};

// === QC 檢查結果 ===
export type QcCheckResult = {
  L1OD?: QcCheckItem;
  L2OD?: QcCheckItem;
  L1StartOD?: QcCheckItem;
  L2StartOD?: QcCheckItem;
};

// === DisposeLot：凍乾/滴定機台 ===
export type DisposeLot = {
  id: string;         // lot 號
  port: string;       // 灌注 port
  lane?: number;      // 通道 (可選)
  pump?: number;      // pump 編號
  freezeDry?: number; // 凍乾機台
};

// === WorkOrderData：整筆工單資料 ===
export type WorkOrderData = {
  workOrderNo: string;
  productModel: string;
  markerName?: string;        // ex. ALP-D, CK-MB
  productQuantity?: number;   // 製令數量 (顆)
  date: string;
  beads: Bead[];
  reagent: Reagent;
  bufferBase: BufferBaseInfo;
  disposeLots: DisposeLot[];

  /** ✅ Liquid Form QC 表中的標準範圍 */
  qcRanges?: QcRanges;

  /** ✅ 製劑 OD 實測比對結果（含通過狀態） */
  qcCheckResult?: QcCheckResult;
};
