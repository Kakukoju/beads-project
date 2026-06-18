import React from 'react';
import { normalizePercent } from "./utils/percent";

interface CircleProgressProps {
  percentage: number;
  size?: number;
  strokeWidth?: number;
  color?: string;
  trackColor?: string;
  showText?: boolean;
  textParams?: { value: string; sub?: string };
  children?: React.ReactNode;
}

export const CircleProgress: React.FC<CircleProgressProps> = ({
  percentage,
  size = 100,
  strokeWidth = 8,
  color = "#3b82f6",
  trackColor = "#1e293b",
  showText = true,
  textParams = { value: "", sub: "" },
  children
}) => {
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  // 處理 NaN 或無限大的保護措施
   const safePercentage = normalizePercent(percentage);
  const offset = circumference - (safePercentage / 100) * circumference;

  return (
    <div className="relative flex flex-col items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="transform -rotate-90">
        {/* 背景軌道 */}
        <circle 
          cx={size / 2} 
          cy={size / 2} 
          r={radius} 
          stroke={trackColor} 
          strokeWidth={strokeWidth} 
          fill="transparent" 
        />
        {/* 進度條 */}
        <circle 
          cx={size / 2} 
          cy={size / 2} 
          r={radius} 
          stroke={color} 
          strokeWidth={strokeWidth} 
          fill="transparent" 
          strokeDasharray={circumference} 
          strokeDashoffset={offset} 
          strokeLinecap="round" 
          className="transition-all duration-1000 ease-out" 
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-white">
        {children ? children : (showText && (
          <>
            <span className="text-xl font-bold">{textParams.value}</span>
            {textParams.sub && <span className="text-xs text-slate-400">{textParams.sub}</span>}
          </>
        ))}
      </div>
    </div>
  );
};