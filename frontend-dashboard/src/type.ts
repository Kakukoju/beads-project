// src/types.ts

export type ResourceState = "unused" | "idle" | "running" | "finished";

export interface IvekResource {
  todayUsed: boolean;
  state: ResourceState;
  currentJob?: string | null;
}

export interface PumpJob {
  workOrder: string;
  marker: string;
  quantity: number;
  pumps: string[];
  remainMin: number;
  endAt: string;
}

export interface TitrationStatusResponse {
  pumpsTotal: number;
  pumpsInUse: number;
  freePumps: number;
  nextReleaseMin: number | null;
  jobs: PumpJob[];
  ivek: IvekResource;
}
