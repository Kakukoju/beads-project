declare module "@nivo/heatmap" {
  import type { FunctionComponent } from "react";

  // 只補我們要用的 ResponsiveHeatMapCanvas，
  // 用 any 當 props 型別，避免再被各種 props 卡住。
  export const ResponsiveHeatMapCanvas: FunctionComponent<any>;
}
