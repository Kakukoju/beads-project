import React, { useState, useEffect } from 'react';
import {
  FlaskConical,
  Bot,
  Snowflake,
  AlertTriangle,
  Activity,
  CheckCircle2,
  Clock,
  BarChart3,
  LayoutDashboard,
  FileText,
  QrCode,
  CalendarDays,
  AlertOctagon,
  Users,
  Microscope,
  FileSpreadsheet,
  CheckSquare,
  Square,
  X,
  List,
  Loader2 // 如果原
} from 'lucide-react';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  Legend,
  ResponsiveContainer,
  Tooltip
} from "recharts";

// ==========================================
// 1. 集中式數據區域 (Mock Data)
// ==========================================

const DASHBOARD_DATA = {
  header: {
    title: "Beads Ops 生產資訊系統",
    status: "Online",
    time: new Date().toLocaleString('zh-TW', { hour12: false, dateStyle: 'short', timeStyle: 'short' }),
  },
  dailyTasks: {
    currentCount: 0,
    totalInfo: "載入中...",
  },
  taskEfficiency: {
    overall: 92,
    items: [
      { label: "周良率", value: 95, color: "bg-sky-500" },
      { label: "月良率", value: 88, color: "bg-teal-500" },
      { label: "季良率", value: 91, color: "bg-purple-500" },
    ],
  },
  scheduleOverview: {
    timelines: [
      { time: "10:30", label: "滴定 Batch-A", duration: 60, color: "bg-blue-500", width: "60%" },
      { time: "11:00", label: "系統維護", duration: 30, color: "bg-indigo-500", width: "30%" },
      { time: "13:30", label: "滴乾 Batch-B", duration: 90, color: "bg-purple-500", width: "80%" },
    ]
  },
  scheduleVariance: {
    items: [
      { time: "10:30", value: 70, color: "bg-blue-600" },
      { time: "09:30", value: 40, color: "bg-sky-500" },
      { time: "15:30", value: 90, color: "bg-indigo-500" },
    ]
  },
  alert: {
    hasAlert: true,
    title: "GLU B Port3 可能阻塞",
    message: "涵蓋範圍 Port 12 需再次人工確認",
    chartData: [40, 20, 60, 80, 30]
  }
};

const TABS = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "schedule", label: "Beads 排程作業", icon: CalendarDays },
  { id: "info", label: "滴定凍乾e工單資訊", icon: FileText },
  { id: "qrcode", label: "工單 QR 掃描追蹤", icon: QrCode },
  { id: "timetable", label: "排程表", icon: FileSpreadsheet },
  { id: "conflict", label: "衝突", icon: AlertOctagon },
  { id: "dispatch", label: "配藥人員派工", icon: Users },
  { id: "ipqc", label: "Beads IPQC資料", icon: Microscope },
];

// ==========================================
// 2. 共用 UI 組件 (Dashboard 風格)
// ==========================================

const Card = ({ children, className = "", title }: { children: React.ReactNode; className?: string; title?: string }) => (
  <div className={`bg-slate-800/50 backdrop-blur-md border border-slate-700/50 rounded-xl p-5 shadow-lg relative overflow-hidden ${className}`}>
    <div className="absolute -top-10 -right-10 w-32 h-32 bg-blue-500/10 rounded-full blur-3xl pointer-events-none"></div>
    {title && <h3 className="text-slate-300 text-lg font-medium mb-4 flex items-center gap-2">{title}</h3>}
    {children}
  </div>
);

const CircleProgress = ({ percentage, size = 100, strokeWidth = 8, color = "#3b82f6", trackColor = "#1e293b", showText = true, textParams = { value: "", sub: "" }, children }: any) => {
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const offset = circumference - (percentage / 100) * circumference;
  return (
    <div className="relative flex flex-col items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="transform -rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} stroke={trackColor} strokeWidth={strokeWidth} fill="transparent" />
        <circle cx={size / 2} cy={size / 2} r={radius} stroke={color} strokeWidth={strokeWidth} fill="transparent" strokeDasharray={circumference} strokeDashoffset={offset} strokeLinecap="round" className="transition-all duration-1000 ease-out" />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-white">
        {children ? children : (showText && <><span className="text-xl font-bold">{textParams.value}</span>{textParams.sub && <span className="text-xs text-slate-400">{textParams.sub}</span>}</>)}
      </div>
    </div>
  );
};

const DoubleCircleProgress = ({
  innerPercentage,
  outerPercentage,
  size = 110,
  strokeWidth = 6,
  innerColor = "#2dd4bf",
  outerColor = "#818cf8",
  trackColor = "#1e293b"
}: any) => {
  const safeInner = Number.isFinite(Number(innerPercentage)) ? Number(innerPercentage) : 0;
  const safeOuter = Number.isFinite(Number(outerPercentage)) ? Number(outerPercentage) : 0;

  const outerRadius = (size - strokeWidth) / 2;
  const innerRadius = outerRadius - strokeWidth - 4;
  const outerCircumference = outerRadius * 2 * Math.PI;
  const innerCircumference = innerRadius * 2 * Math.PI;

  const outerOffset = outerCircumference - (safeOuter / 100) * outerCircumference;
  const innerOffset = innerCircumference - (safeInner / 100) * innerCircumference;

  return (
    <div className="relative flex flex-col items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="transform -rotate-90">
        <circle cx={size / 2} cy={size / 2} r={outerRadius} stroke={trackColor} strokeWidth={strokeWidth} fill="transparent" />
        <circle cx={size / 2} cy={size / 2} r={innerRadius} stroke={trackColor} strokeWidth={strokeWidth} fill="transparent" />
        <circle cx={size / 2} cy={size / 2} r={outerRadius} stroke={outerColor} strokeWidth={strokeWidth} fill="transparent" strokeDasharray={outerCircumference} strokeDashoffset={outerOffset} strokeLinecap="round" className="transition-all duration-1000 ease-out" />
        <circle cx={size / 2} cy={size / 2} r={innerRadius} stroke={innerColor} strokeWidth={strokeWidth} fill="transparent" strokeDasharray={innerCircumference} strokeDashoffset={innerOffset} strokeLinecap="round" className="transition-all duration-1000 ease-out" />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-white text-xs font-mono font-bold">
        <div style={{ color: outerColor }}>{safeOuter}%</div>
        <div style={{ color: innerColor }}>{safeInner}%</div>
      </div>
    </div>
  );
};

// ==========================================
// 3. 子頁面組件
// ==========================================
// ==========================================
// 🆕 低良率項目 Modal 組件
// ==========================================
interface LowYieldItem {
  key: string;
  lot_no: string;
  work_order: string;
  product_name: string;
  titration_qty: number;
  actual_qty: number;
  warehouse_date: string;
  status: string;
  yield: number;
  ignored: boolean;
}

interface LowYieldModalProps {
  onUpdate?: () => void;
}

const LowYieldModal: React.FC<LowYieldModalProps> = ({ onUpdate }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<LowYieldItem[]>([]);
  const [error, setError] = useState('');
  const [processingKeys, setProcessingKeys] = useState<Set<string>>(new Set());

  // 開啟視窗並載入資料
  const handleOpen = async () => {
    setIsOpen(true);
    setLoading(true);
    setError('');
    
    try {
      const response = await fetch('/api/dashboard/low-yield-items');
      const data = await response.json();
      
      if (data.ok) {
        // 只顯示未被忽略的項目
        setItems(data.items.filter((item: LowYieldItem) => !item.ignored));
      } else {
        setError('無法取得資料');
      }
    } catch (err) {
      setError('連線錯誤');
    } finally {
      setLoading(false);
    }
  };

  // 處理忽略 (Check)
  const handleIgnore = async (item: LowYieldItem) => {
    const originalItems = [...items];
    setItems(prev => prev.filter(i => i.key !== item.key));
    setProcessingKeys(prev => new Set(prev).add(item.key));

    try {
      const res = await fetch('/api/dashboard/toggle-yield-ignore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          key: item.key,
          lot_no: item.lot_no,
          work_order: item.work_order,
          ignore: true
        })
      });
      
      const result = await res.json();
      if (result.ok) {
        if (onUpdate) onUpdate();
      } else {
        throw new Error(result.error);
      }
    } catch (err) {
      console.error("Ignore failed", err);
      setItems(originalItems);
      alert("操作失敗，請稍後再試");
    } finally {
      setProcessingKeys(prev => {
        const next = new Set(prev);
        next.delete(item.key);
        return next;
      });
    }
  };

  if (!isOpen) {
    return (
      <button 
        onClick={handleOpen}
        className="px-3 py-1.5 text-xs text-amber-400 border border-amber-400/30 rounded hover:bg-amber-400/10 transition-colors flex items-center gap-1"
      >
        <AlertTriangle size={14} />
        查看低良率項目
      </button>
    );
  }

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-slate-800 border border-slate-700 rounded-xl shadow-2xl w-full max-w-6xl max-h-[85vh] flex flex-col">
        
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-700 bg-slate-800/50">
          <div>
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              <AlertTriangle className="text-amber-500" size={20} />
              低良率項目（2周 &lt; 95%）
              <span className="text-sm font-normal text-slate-400 bg-slate-700 px-2 py-0.5 rounded-full">
                {items.length} 筆
              </span>
            </h3>
            <p className="text-xs text-slate-400 mt-1">勾選項目以標記為忽略（下次不顯示）</p>
          </div>
          <button 
            onClick={() => setIsOpen(false)} 
            className="p-1 text-slate-400 hover:text-white bg-slate-700/50 hover:bg-slate-700 rounded-lg transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-0">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-20 text-slate-400">
              <Loader2 className="animate-spin h-8 w-8 text-blue-500 mb-2" />
              <p>載入詳細資料中...</p>
            </div>
          ) : error ? (
            <div className="text-red-400 text-center py-10">{error}</div>
          ) : items.length === 0 ? (
            <div className="text-slate-500 text-center py-20 flex flex-col items-center">
              <CheckCircle2 size={48} className="mb-4 opacity-20" />
              目前沒有低良率項目（全部 ≥ 95%）
            </div>
          ) : (
            <table className="w-full text-left border-collapse">
              <thead className="bg-slate-900/80 text-slate-400 text-xs uppercase sticky top-0 z-10 backdrop-blur-md">
                <tr>
                  <th className="p-3 font-medium text-center w-16">忽略</th>
                  <th className="p-3 font-medium">LOT NO</th>
                  <th className="p-3 font-medium">工單號碼</th>
                  <th className="p-3 font-medium">品名</th>
                  <th className="p-3 font-medium text-right">滴定數</th>
                  <th className="p-3 font-medium text-right">實際入庫</th>
                  <th className="p-3 font-medium text-right">良率</th>
                  <th className="p-3 font-medium text-center">狀態</th>
                  <th className="p-3 font-medium text-right">入庫日期</th>
                </tr>
              </thead>
              <tbody className="text-sm divide-y divide-slate-700/50">
                {items.map((item) => (
                  <tr 
                    key={item.key} 
                    className={`hover:bg-slate-700/30 transition-colors group ${
                      item.yield < 90 ? 'bg-red-900/10' : 
                      item.yield < 95 ? 'bg-amber-900/10' : ''
                    }`}
                  >
                    <td className="p-3 text-center">
                      <button
                        onClick={() => handleIgnore(item)}
                        disabled={processingKeys.has(item.key)}
                        className="text-slate-500 hover:text-green-400 transition-colors disabled:opacity-50"
                        title="點擊以標記為忽略"
                      >
                        {processingKeys.has(item.key) ? (
                          <Loader2 className="animate-spin h-4 w-4 mx-auto" />
                        ) : (
                          <Square size={18} />
                        )}
                      </button>
                    </td>
                    <td className="p-3 font-mono text-blue-300 font-medium text-xs">
                      {item.lot_no}
                    </td>
                    <td className="p-3 text-slate-300 font-mono text-xs">
                      {item.work_order}
                    </td>
                    <td className="p-3 text-slate-300 text-xs">
                      {item.product_name}
                    </td>
                    <td className="p-3 text-slate-400 font-mono text-xs text-right">
                      {item.titration_qty.toLocaleString()}
                    </td>
                    <td className="p-3 text-slate-300 font-mono text-xs text-right font-semibold">
                      {item.actual_qty.toLocaleString()}
                    </td>
                    <td className="p-3 text-right">
                      <span className={`font-bold text-sm ${
                        item.yield < 90 ? 'text-red-400' : 
                        item.yield < 95 ? 'text-amber-400' : 
                        'text-green-400'
                      }`}>
                        {item.yield.toFixed(1)}%
                      </span>
                    </td>
                    <td className="p-3 text-center">
                      <span className="bg-slate-700/50 px-2 py-0.5 rounded text-xs border border-slate-600/50">
                        {item.status || '-'}
                      </span>
                    </td>
                    <td className="p-3 text-slate-400 font-mono text-xs text-right">
                      {item.warehouse_date}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-700 bg-slate-800/50">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <div className="flex items-center gap-4">
              <span className="flex items-center gap-1">
                <span className="w-3 h-3 rounded bg-red-900/30 border border-red-500/50"></span>
                &lt; 90%（嚴重）
              </span>
              <span className="flex items-center gap-1">
                <span className="w-3 h-3 rounded bg-amber-900/30 border border-amber-500/50"></span>
                90-95%（警示）
              </span>
            </div>
            <span>良率閾值：95%</span>
          </div>
        </div>
      </div>
    </div>
  );
};
// ==========================================
// 新增組件: 未入庫工單列表 Modal (Portal 版本 - 完美浮動置中)
// ==========================================
import { createPortal } from 'react-dom'; // 👈 關鍵引入

// 1. 定義資料型別
interface OrderDetail {
  WorkOrder: string;
  Lot: string;
  Marker: string;
  Date: string;
}

// 2. 定義 Props 型別
interface UnstockedOrderModalProps {
  periodLabel: string;
  days: number;
  onUpdate?: () => void;
}

const UnstockedOrderModal: React.FC<UnstockedOrderModalProps> = ({ periodLabel, days, onUpdate }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [orders, setOrders] = useState<OrderDetail[]>([]); 
  const [error, setError] = useState('');
  const [processingIds, setProcessingIds] = useState<Set<string>>(new Set());
  const [mounted, setMounted] = useState(false);

  // 確保在客戶端渲染後才掛載 Portal
  useEffect(() => {
    setMounted(true);
  }, []);

  const handleOpen = async () => {
  setIsOpen(true);
  setLoading(true);
  setError('');
  try {
    // 修正路徑加上 -stats
    const response = await fetch(`/api/workorder/unpackaged-ratio-stats`); 
    const data = await response.json();
    
    if (data.success) {
      // 根據傳入的 days 選擇正確的數據段落 (7天對應 weekly, 30天對應 monthly...)
      let targetData = [];
      if (days <= 7) targetData = data.weekly.details;
      else if (days <= 30) targetData = data.monthly.details;
      else targetData = data.quarterly.details;
      
      setOrders(targetData || []);
    } else {
      setError('無法取得資料');
    }
  } catch (err) {
    setError('連線錯誤');
  } finally {
    setLoading(false);
  }
};

  const handleIgnore = async (workOrder: string) => {
    const originalOrders = [...orders];
    setOrders(prev => prev.filter(o => o.WorkOrder !== workOrder));
    setProcessingIds(prev => new Set(prev).add(workOrder));

    try {
      const res = await fetch('/api/workorder/ignore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ work_order: workOrder, ignore: true })
      });
      
      const result = await res.json();
      if (result.success) {
        if (onUpdate) onUpdate();
      } else {
        throw new Error(result.error);
      }
    } catch (err) {
      console.error("Ignore failed", err);
      setOrders(originalOrders);
      alert("操作失敗，請稍後再試");
    } finally {
      setProcessingIds(prev => {
        const next = new Set(prev);
        next.delete(workOrder);
        return next;
      });
    }
  };

  // 按鈕部分 (這會留在原本的卡片裡)
  if (!isOpen) {
    return (
      <button 
        onClick={handleOpen}
        className="ml-auto px-2 py-1 text-[10px] text-blue-400 border border-blue-400/30 rounded hover:bg-blue-400/10 transition-colors flex items-center gap-1"
      >
        <List size={12} />
        查看明細
      </button>
    );
  }

  // 如果還沒掛載，不渲染 Portal
  if (!mounted) return null;

  // 彈出視窗部分 (使用 Portal 傳送到 body)
  return createPortal(
    <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4">
      
      {/* 背景遮罩 (點擊空白處關閉) */}
      <div 
        className="absolute inset-0 bg-black/80 backdrop-blur-sm animate-in fade-in duration-300"
        onClick={() => setIsOpen(false)}
      />

      {/* 視窗本體 (浮現動畫 + 寬版設計) */}
      <div className="relative bg-slate-900 border border-slate-700 rounded-xl shadow-2xl w-full max-w-7xl h-[85vh] flex flex-col overflow-hidden animate-in zoom-in-95 fade-in duration-300">
        
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700 bg-slate-800 shrink-0">
          <div className="flex items-center gap-4">
            <div className="p-2 bg-blue-500/20 rounded-lg">
              <List className="text-blue-400" size={24} />
            </div>
            <div>
              <h3 className="text-xl font-bold text-white flex items-center gap-3">
                {periodLabel}未入庫工單
                <span className="text-sm font-normal text-slate-300 bg-slate-700 px-3 py-0.5 rounded-full border border-slate-600">
                  共 {orders.length} 筆
                </span>
              </h3>
              <p className="text-sm text-slate-400 mt-0.5">請勾選以忽略不需要追蹤的工單</p>
            </div>
          </div>
          <button 
            onClick={() => setIsOpen(false)} 
            className="p-2 text-slate-400 hover:text-white bg-slate-700 hover:bg-red-600 rounded-lg transition-all duration-200 shadow-md"
          >
            <X size={24} />
          </button>
        </div>

        {/* Body (表格區域) */}
        <div className="flex-1 overflow-auto bg-slate-900 scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-transparent">
          {loading ? (
            <div className="flex flex-col items-center justify-center h-full text-slate-400">
              <Loader2 size={48} className="animate-spin mb-4 text-blue-500" />
              <p className="text-lg font-medium">正在從資料庫撈取資料...</p>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center h-full text-red-400">
              <p className="text-xl font-bold mb-2">發生錯誤</p>
              <p>{error}</p>
            </div>
          ) : orders.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-slate-500">
              <CheckCircle2 size={80} className="mb-6 opacity-20 text-green-500" />
              <p className="text-2xl font-medium text-slate-400">完美！目前沒有滯留工單</p>
              <p className="text-slate-600 mt-2">所有生產的工單都已完成入庫程序</p>
            </div>
          ) : (
            <table className="w-full text-left border-collapse min-w-[800px]">
              <thead className="bg-slate-800 text-slate-300 text-sm uppercase sticky top-0 z-10 shadow-lg">
                <tr>
                  <th className="p-4 font-bold text-center w-24 border-b border-slate-700 bg-slate-800">忽略</th>
                  <th className="p-4 font-bold border-b border-slate-700 bg-slate-800">工單號碼</th>
                  <th className="p-4 font-bold border-b border-slate-700 bg-slate-800">Lot No.</th>
                  <th className="p-4 font-bold border-b border-slate-700 bg-slate-800">Marker</th>
                  <th className="p-4 font-bold text-right border-b border-slate-700 bg-slate-800">生產日期</th>
                </tr>
              </thead>
              <tbody className="text-base divide-y divide-slate-800/50">
                {orders.map((order, index) => (
                  <tr key={order.WorkOrder} className={`hover:bg-slate-800/80 transition-colors group ${index % 2 === 0 ? 'bg-slate-900' : 'bg-slate-900/30'}`}>
                    <td className="p-4 text-center">
                      <button
                        onClick={() => handleIgnore(order.WorkOrder)}
                        disabled={processingIds.has(order.WorkOrder)}
                        className="text-slate-500 hover:text-green-400 transition-all transform hover:scale-110 disabled:opacity-50 p-2 hover:bg-slate-700 rounded-md"
                        title="點擊忽略此工單"
                      >
                        {processingIds.has(order.WorkOrder) ? (
                           <Loader2 className="animate-spin h-6 w-6 text-blue-500 mx-auto" />
                        ) : (
                           <Square size={24} />
                        )}
                      </button>
                    </td>
                    <td className="p-4 font-mono text-blue-300 font-bold text-lg tracking-wide group-hover:text-blue-200">
                      {order.WorkOrder}
                    </td>
                    <td className="p-4 text-slate-300 font-mono text-base">
                      {order.Lot || '-'}
                    </td>
                    <td className="p-4 text-slate-300">
                      <span className="bg-slate-800 px-3 py-1 rounded-md text-sm border border-slate-700 text-slate-200 inline-block min-w-[80px] text-center font-medium">
                        {order.Marker || '-'}
                      </span>
                    </td>
                    <td className="p-4 text-slate-400 font-mono text-right">
                      {order.Date}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-700 bg-slate-800 shrink-0 flex justify-between items-center">
          <div className="text-xs text-slate-500">
            資料來源：配藥排程系統 & WIP 入庫系統
          </div>
          <button 
            onClick={() => setIsOpen(false)}
            className="px-8 py-2.5 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors font-medium border border-slate-600 hover:border-slate-500 shadow-lg"
          >
            關閉視窗
          </button>
        </div>

      </div>
    </div>,
    document.body // 傳送目標：將 HTML 直接掛載到 body 下，跳脫任何 overflow:hidden 的限制
  );
};
// --- 3.1 Dashboard View ---
const DashboardView = () => {
  const { taskEfficiency, scheduleOverview, scheduleVariance, alert } = DASHBOARD_DATA;
  const [dailyTasks, setDailyTasks] = useState(DASHBOARD_DATA.dailyTasks);

  //良率 初始值
  const [efficiencyData, setEfficiencyData] = useState({
    overall: 0,
    total_year: 0,  // ✅ 加入此欄位
    items: [
      { label: "周良率", value: 0, total: 0, color: "bg-sky-500" },
      { label: "月良率", value: 0, total: 0, color: "bg-teal-500" },
      { label: "季良率", value: 0, total: 0, color: "bg-purple-500" },
    ]
  });
  const [completionData, setCompletionData] = useState({
    date: "", total_orders: 0, dispensing_rate: 0, titration_rate: 0, freeze_drying_rate: 0, dispensing_completed: 0, titration_completed: 0, freeze_drying_completed: 0,
  });
  const [utilizationMode, setUtilizationMode] = useState<"day" | "week" | "month">("day");
  const [utilizationData, setUtilizationData] = useState({
    mode: "day", period: "", titration_utilization: 0, dryer_utilization: 0, titration_used: 0, titration_capacity: 0, dryer_used: 0, dryer_capacity: 0, work_days: 0,
  });

  // 入庫比例數據（用於生產入庫統計）
  const [customDays, setCustomDays] = useState(14);
  const [packagingRatioData, setPackagingRatioData] = useState({
    weekly: { ratio: 0, packaged: 0, produced: 0 },
    monthly: { ratio: 0, packaged: 0, produced: 0 },
    custom: { ratio: 0, packaged: 0, produced: 0, days: 14 }
  });

  // 未入庫比例數據（用於未入庫工單統計）
const [unpackagedRatioData, setUnpackagedRatioData] = useState({
  weekly: { ratio: 0, unpackaged: 0, produced: 0, packaged: 0 },
  monthly: { ratio: 0, unpackaged: 0, produced: 0, packaged: 0 },
  quarterly: { ratio: 0, unpackaged: 0, produced: 0, packaged: 0 }
});

 const fetchUnpackagedRatio = async () => {
    try {
      const response = await fetch('/api/workorder/unpackaged-ratio-stats');
      const data = await response.json();
      if (data.success) {
        setUnpackagedRatioData(data);
      }
    } catch (err) {
      console.error("載入未入庫比例失敗:", err);
    }
  };

  useEffect(() => {
    fetchUnpackagedRatio();
    const interval = setInterval(fetchUnpackagedRatio, 300000); // 每5分鐘更新
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const fetchTodayStats = async () => {
      try {
        const response = await fetch("/api/schedule/today-stats");
        const data = await response.json();
        if (data.ok) {
          setDailyTasks({ currentCount: data.tasks, totalInfo: `共 ${data.titration_machines} 滴定 / ${data.dryers} 凍乾` });
        }
      } catch (err) { console.error("載入今日任務失敗:", err); }
    };
    fetchTodayStats();
    const interval = setInterval(fetchTodayStats, 60000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const fetchCompletionRate = async () => {
      try {
        const response = await fetch(`/api/schedule/completion-rate`);
        const data = await response.json();
        if (data.ok) setCompletionData(data);
      } catch (err) { console.error("載入完成率失敗:", err); }
    };
    fetchCompletionRate();
    const interval = setInterval(fetchCompletionRate, 60000);
    return () => clearInterval(interval);
  }, []);

  // 獲取生產良率的 useEffect (每2小時更新)
const fetchYieldStats = async () => {
  try {
    const response = await fetch("/api/dashboard/yield-stats");
    const data = await response.json();

    if (data.ok) {
      setEfficiencyData({
        overall: data.overall,
        total_year: data.total_year,
        items: data.items  // 包含 2周/月/季良率
      });
    }
  } catch (err) {
    console.error("載入生產良率失敗:", err);
  }
};

useEffect(() => {
  fetchYieldStats();
  const interval = setInterval(fetchYieldStats, 7200000); // 2小時
  return () => clearInterval(interval);
}, []);

  useEffect(() => {
    const fetchUtilization = async () => {
      try {
        const dateObj = new Date();
        const today = `${dateObj.getFullYear()}-${String(dateObj.getMonth() + 1).padStart(2, '0')}-${String(dateObj.getDate()).padStart(2, '0')}`;
        const response = await fetch(`/api/schedule/utilization?mode=${utilizationMode}&date=${today}`);
        const data = await response.json();
        if (data.ok) {
          setUtilizationData(prev => ({ ...prev, ...data, titration_utilization: Number(data.titration_utilization) || 0, dryer_utilization: Number(data.dryer_utilization) || 0 }));
        }
      } catch (err) { console.error("載入稼動率失敗:", err); }
    };
    fetchUtilization();
    const interval = setInterval(fetchUtilization, 60000);
    return () => clearInterval(interval);
  }, [utilizationMode]);

  const completionItems = [
    { id: 1, label: "配藥", value: completionData.dispensing_rate, icon: "flask", color: "text-cyan-400", ringColor: "#22d3ee", subText: `${completionData.dispensing_completed}/${completionData.total_orders}` },
    { id: 2, label: "滴定", value: completionData.titration_rate, icon: "bot", color: "text-teal-400", ringColor: "#2dd4bf", subText: `${completionData.titration_completed}/${completionData.total_orders}` },
    { id: 3, label: "凍乾", value: completionData.freeze_drying_rate, icon: "snowflake", color: "text-indigo-400", ringColor: "#818cf8", subText: `${completionData.freeze_drying_completed}/${completionData.total_orders}` },
  ];


  // 在 DashboardView 組件內，替換原本的 return (...)

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 h-full animate-in fade-in duration-500 pb-10">
      
      {/* --- 左側欄位 (佔 1/3 寬度) --- */}
      <div className="space-y-6">
        
        {/* 1. 今日任務 (移至左側第一位) */}
        <Card title="今日任務" className="h-64 flex flex-col justify-between">
          <div className="flex items-center justify-between h-full">
            <div>
              <div className="text-6xl font-bold text-white mb-2">{dailyTasks.currentCount}</div>
              <div className="text-slate-400 text-sm">{dailyTasks.totalInfo}</div>
              <div className="mt-4 flex gap-1">
                {["day", "week", "month"].map((mode) => (
                  <button key={mode} onClick={() => setUtilizationMode(mode as any)} className={`text-[10px] px-2 py-1 rounded border transition-colors ${utilizationMode === mode ? "bg-slate-700 border-slate-500 text-white" : "bg-transparent border-slate-700 text-slate-500 hover:text-slate-300"}`}>{mode === "day" ? "日" : mode === "week" ? "周" : "月"}</button>
                ))}
              </div>
            </div>
            <div className="flex flex-col items-center gap-2">
              <DoubleCircleProgress innerPercentage={utilizationData.titration_utilization} outerPercentage={utilizationData.dryer_utilization} size={110} />
              <div className="flex gap-3 text-[10px] mt-1">
                <span className="flex items-center gap-1 text-indigo-400"><span className="w-2 h-2 rounded-full bg-indigo-400"></span>凍乾</span>
                <span className="flex items-center gap-1 text-teal-400"><span className="w-2 h-2 rounded-full bg-teal-400"></span>滴定</span>
              </div>
              <span className="text-xs text-slate-400">機台稼動率</span>
            </div>
          </div>
        </Card>

        {/* 2. Beads 生產良率 (修改：顯示低良率警示) */}
<Card title="Beads 生產良率" className="h-64">
  <div className="flex items-center gap-4 h-full pb-6">
    <div className="flex-1 space-y-4">
      {efficiencyData.items.map((item, idx) => (
        <div key={idx}>
          <div className="flex justify-between text-xs text-slate-400 mb-1">
            <span className="flex items-center gap-1">
              {item.label}
              {item.label === "2周良率" && item.value < 95 && (
                <AlertTriangle size={12} className="text-amber-500" />
              )}
              <span className="text-[10px] text-slate-500">
                (共 {item.total} 批)
              </span>
            </span>
            <span className={`text-slate-200 font-semibold ${
              item.value < 90 ? 'text-red-400' :
              item.value < 95 ? 'text-amber-400' : ''
            }`}>
              {item.value}%
            </span>
          </div>
          <div className="w-full bg-slate-700/50 rounded-full h-3">
            <div
              className={`h-3 rounded-full ${
                item.value < 90 ? 'bg-red-500' :
                item.value < 95 ? 'bg-amber-500' :
                item.color
              } transition-all duration-1000`}
              style={{ width: `${item.value}%` }}
            ></div>
          </div>
        </div>
      ))}
      
      {/* 🆕 低良率警示按鈕 */}
      {efficiencyData.items.length > 0 && 
       efficiencyData.items[0].value < 95 && (
        <div className="pt-2 border-t border-slate-700/50">
          <LowYieldModal onUpdate={fetchYieldStats} />
        </div>
      )}
    </div>
    
    <div className="flex flex-col items-center justify-center">
      <CircleProgress
        percentage={efficiencyData.overall}
        size={90}
        color={
          efficiencyData.overall < 90 ? "#ef4444" :
          efficiencyData.overall < 95 ? "#f59e0b" :
          "#10b981"
        }
        trackColor="#334155"
        strokeWidth={8}
        textParams={{ value: `${efficiencyData.overall}%` }}
      />
      <div className="text-center mt-2">
        <div className="text-xs text-slate-400">年良率(總)</div>
        <div className="text-emerald-400 text-[11px] font-semibold mt-0.5">
          {efficiencyData.total_year?.toLocaleString('zh-TW') || 0} 批
        </div>
      </div>
    </div>
  </div>
</Card>

        {/* 3. 製成未入庫工單數量 (移至左側第三位) */}
        <Card title="製成未入庫工單數量" className="h-auto min-h-[16rem]">
          <div className="flex flex-col justify-center h-full gap-3 pb-4">
            
            {/* 周待處理 */}
            <div className="space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-amber-500"></span>
                  本周待入庫工單
                </span>
                {/* Modal 按鈕 */}
                <UnstockedOrderModal 
                  periodLabel="本周" 
                  days={7} 
                  onUpdate={fetchUnpackagedRatio} 
                />
              </div>
              <div className="flex items-baseline justify-between">
                 <div className="text-[10px] text-slate-500">
                   已生產 {unpackagedRatioData.weekly.produced} / 已入庫 {unpackagedRatioData.weekly.packaged}
                 </div>
                 <span className="text-amber-400 font-bold text-2xl">
                   {unpackagedRatioData.weekly.unpackaged}
                 </span>
              </div>
            </div>

            {/* 月待處理 */}
            <div className="space-y-1 pt-2 border-t border-slate-700/30">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-orange-500"></span>
                  本月待入庫工單
                </span>
                <UnstockedOrderModal 
                  periodLabel="本月" 
                  days={30} 
                  onUpdate={fetchUnpackagedRatio} 
                />
              </div>
              <div className="flex items-baseline justify-between">
                 <div className="text-[10px] text-slate-500">
                   已生產 {unpackagedRatioData.monthly.produced} / 已入庫 {unpackagedRatioData.monthly.packaged}
                 </div>
                 <span className="text-orange-400 font-bold text-2xl">
                   {unpackagedRatioData.monthly.unpackaged}
                 </span>
              </div>
            </div>

            {/* 季待處理 */}
            <div className="space-y-1 pt-2 border-t border-slate-700/30">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-red-500"></span>
                  本季待入庫工單
                </span>
                <UnstockedOrderModal 
                  periodLabel="本季" 
                  days={90} 
                  onUpdate={fetchUnpackagedRatio} 
                />
              </div>
              <div className="flex items-baseline justify-between">
                 <div className="text-[10px] text-slate-500">
                   已生產 {unpackagedRatioData.quarterly.produced} / 已入庫 {unpackagedRatioData.quarterly.packaged}
                 </div>
                 <span className="text-red-400 font-bold text-2xl">
                   {unpackagedRatioData.quarterly.unpackaged}
                 </span>
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* --- 右側欄位 (佔 2/3 寬度) --- */}
      <div className="md:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-6 h-full content-start">
        
        {/* 1. 任務完成率 (右側第一位) */}
        <Card title="任務完成率" className="md:col-span-2 h-64">
          <div className="flex justify-around items-center h-full pb-4">
            {completionItems.map((item) => (
              <div key={item.id} className="flex flex-col items-center gap-3">
                <div className="relative">
                  <CircleProgress percentage={item.value} size={100} color={item.ringColor} strokeWidth={6} showText={false}>
                    {item.icon === 'flask' && <FlaskConical size={28} className={item.color} />}
                    {item.icon === 'bot' && <Bot size={28} className={item.color} />}
                    {item.icon === 'snowflake' && <Snowflake size={28} className={item.color} />}
                  </CircleProgress>
                  <div className={`absolute inset-0 rounded-full blur-xl opacity-20`} style={{ backgroundColor: item.ringColor }}></div>
                </div>
                <div className="text-center">
                  <div className={`text-xl font-bold ${item.color}`}>{item.value}%</div>
                  <div className="text-slate-400 text-xs tracking-wider mb-1">{item.label}</div>
                  <div className="text-slate-500 text-[10px] font-mono">{item.subText}</div>
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* 2. 生產排程總覽 (右側第二位) */}
        <Card title="生產排程總覽" className="md:col-span-2 h-64">
          <div className="flex flex-col justify-around h-full pb-2">
            {scheduleOverview.timelines.map((task, idx) => (
              <div key={idx} className="flex items-center gap-4 group">
                <div className="text-xs text-slate-500 font-mono w-10">{task.time}</div>
                <div className="flex-1 relative h-10 bg-slate-700/20 rounded-lg flex items-center px-2 overflow-hidden">
                  <div className={`absolute left-0 top-0 bottom-0 ${task.color} opacity-20 group-hover:opacity-30 transition-opacity`} style={{ width: task.width }}></div>
                  <div className={`absolute left-0 bottom-0 h-1 ${task.color}`} style={{ width: task.width }}></div>
                  <div className="relative z-10 flex justify-between w-full items-center px-2">
                    <span className="text-sm text-slate-200 font-medium">{task.label}</span>
                    <span className="text-xs text-slate-400 flex items-center gap-1"><Clock size={12} /> {task.duration} min</span>
                  </div>
                </div>
                <div className="text-xs text-slate-500 font-mono w-10 text-right">{parseInt(task.time.split(':')[0]) + 1}:{task.time.split(':')[1]}</div>
              </div>
            ))}
          </div>
        </Card>

        {/* 3. 即時監控 (右側第三位) */}
        <Card title="即時監控" className="md:col-span-2 h-48 border-t-4 border-t-amber-500">
          <div className="flex items-center gap-6 h-full">
            <div className="flex-1">
              <div className="flex items-start gap-3 mb-2">
                <AlertTriangle className="text-amber-500 shrink-0" size={24} />
                <div>
                  <h4 className="text-lg font-bold text-white">{alert.title}</h4>
                  <p className="text-slate-400 text-sm mt-1">{alert.message}</p>
                </div>
              </div>
            </div>
            <div className="flex items-end gap-2 h-24 w-48 pb-2">
              {alert.chartData.map((h, i) => (
                <div key={i} className="flex-1 bg-slate-700 rounded-t-sm relative group cursor-pointer">
                  <div className={`absolute bottom-0 w-full rounded-t-sm ${i === 3 ? 'bg-amber-500' : 'bg-blue-600'} transition-all duration-500`} style={{ height: `${h}%` }}>
                    <div className="opacity-0 group-hover:opacity-100 absolute -top-8 left-1/2 -translate-x-1/2 bg-slate-900 text-xs px-2 py-1 rounded border border-slate-600 whitespace-nowrap transition-opacity">Value: {h}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};
// --- 3.2 Dispatch View (配藥人員派工頁面) ---
const DispatchView = () => {
  const [workloadMode, setWorkloadMode] = useState<"week" | "month">("week");
  const [workloadData, setWorkloadData] = useState<any>({
    mode: "week",
    period: "",
    staff_stats: [],
    total_assignments: 0,
  });
  const [workloadLoading, setWorkloadLoading] = useState(false);

  useEffect(() => {
    const fetchWorkloadStats = async () => {
      try {
        setWorkloadLoading(true);
        const dateObj = new Date();
        const today = `${dateObj.getFullYear()}-${String(dateObj.getMonth() + 1).padStart(2, '0')}-${String(dateObj.getDate()).padStart(2, '0')}`;
        const response = await fetch(
          `/api/schedule/workload-stats?mode=${workloadMode}&date=${today}`
        );
        const data = await response.json();

        if (data.ok) {
          setWorkloadData(data);
        }
      } catch (err) {
        console.error("載入工作分派統計失敗:", err);
      } finally {
        setWorkloadLoading(false);
      }
    };

    fetchWorkloadStats();
    const interval = setInterval(fetchWorkloadStats, 600000);
    return () => clearInterval(interval);
  }, [workloadMode]);

  return (
    <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
      <Card className="p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4">
          <h3 className="font-semibold text-xl text-slate-200">
            配藥人員工作分派統計
          </h3>
          <button
            onClick={() => setWorkloadMode((prev) => (prev === "week" ? "month" : "week"))}
            disabled={workloadLoading}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 transition disabled:bg-slate-700 disabled:text-slate-500"
          >
            {workloadMode === "week" ? "切換至月統計" : "切換至周統計"}
          </button>
        </div>

        <div className="mb-6 flex items-center gap-3">
          <div className="text-xs px-3 py-1 bg-blue-500/20 text-blue-300 rounded-full font-medium border border-blue-500/30">
            {workloadMode === "week" ? "本周統計" : "本月至本周統計"}
          </div>
          <div className="text-sm text-slate-400">
            {workloadData.period}
            {workloadData.total_assignments > 0 && (
              <span className="ml-2 font-semibold text-slate-300">
                總工單數：{workloadData.total_assignments}
              </span>
            )}
          </div>
        </div>

        {workloadLoading ? (
          <div className="text-center py-16">
            <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
            <p className="mt-4 text-slate-300">載入中...</p>
          </div>
        ) : workloadData.staff_stats.length > 0 ? (
          <>
            <div className="h-[400px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={workloadData.staff_stats}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis
                    dataKey="name"
                    tick={{ fontSize: 13, fill: "#94a3b8" }}
                    stroke="#475569"
                  />
                  <YAxis
                    tick={{ fontSize: 13, fill: "#94a3b8" }}
                    stroke="#475569"
                    label={{ value: "工單數", angle: -90, position: "insideLeft", fill: "#94a3b8" }}
                  />
                  <RechartsTooltip
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        const data = payload[0].payload;
                        return (
                          <div className="bg-slate-800 p-4 rounded-lg shadow-lg border border-slate-700 text-slate-200">
                            <p className="font-semibold text-lg">{data.name}</p>
                            <p className="text-sm text-slate-400 mt-1">
                              工單數：<span className="font-semibold text-white">{data.count}</span>
                            </p>
                            <p className="text-sm text-slate-400">
                              佔比：<span className="font-semibold text-white">{data.percentage}%</span>
                            </p>
                          </div>
                        );
                      }
                      return null;
                    }}
                  />
                  <Bar dataKey="count" radius={[8, 8, 0, 0]}>
                    {workloadData.staff_stats.map((_: any, index: number) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={[
                          "#3b82f6", "#10b981", "#8b5cf6", "#f59e0b",
                          "#ef4444", "#06b6d4", "#ec4899", "#84cc16",
                        ][index % 8]}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* 詳細數據表格 */}
            <div className="mt-8 pt-6 border-t border-slate-700">
              <h4 className="font-semibold text-slate-300 mb-4">詳細數據</h4>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {workloadData.staff_stats.map((staff: any, index: number) => (
                  <div key={index} className="p-4 bg-slate-800/50 rounded-lg border border-slate-700 hover:bg-slate-800 transition-colors">
                    <div className="font-semibold text-slate-200">{staff.name}</div>
                    <div className="text-2xl font-bold text-blue-400 mt-2">{staff.count}</div>
                    <div className="text-xs text-slate-500 mt-1">佔比 {staff.percentage}%</div>
                  </div>
                ))}
              </div>
            </div>
          </>
        ) : (
          <div className="text-center py-16 text-slate-300">
            <p className="text-lg">📊 暫無工作分派資料</p>
            <p className="text-sm mt-2 opacity-60">請確認資料庫中有配藥記錄</p>
          </div>
        )}

        <div className="mt-6 p-4 bg-blue-900/20 border border-blue-500/30 rounded-lg">
          <p className="text-sm text-blue-300">
            <strong>📌 統計說明：</strong>
            本統計以「工單號碼 (WorkOrder)」為單位,計算每位配藥人員負責的工單數量。
            相同的 [工單號碼 + 配藥人員] 組合只計算一次。
          </p>
        </div>
      </Card>
    </div>
  );
};

// --- 3.3 BeadsIPQCPage 整合 (統一深色風格) ---
const BeadsIPQCPage = () => {
  const [activeTab, setActiveTab] = useState("OD");
  const [odYear, setOdYear] = useState(new Date().getFullYear());
  const [odMonth, setOdMonth] = useState<number | null>(new Date().getMonth() + 1);
  const [odWeekly, setOdWeekly] = useState<string | null>(null);
  const [odMarker, setOdMarker] = useState("");
  const [odData, setOdData] = useState([]);
  const [odLoading, setOdLoading] = useState(false);
  const [cvYear, setCvYear] = useState(new Date().getFullYear());
  const [cvMonth, setCvMonth] = useState<number | null>(new Date().getMonth() + 1);
  const [cvWeekly, setCvWeekly] = useState<string | null>(null);
  const [cvMarker, setCvMarker] = useState("");
  const [cvData, setCvData] = useState([]);
  const [cvLoading, setCvLoading] = useState(false);
  const [cvType, setCvType] = useState("OD_CV");
  const [availableYears, setAvailableYears] = useState<any[]>([]);
  const [weeklyList, setWeeklyList] = useState<any[]>([]);
  const [markerList, setMarkerList] = useState<any[]>([]);

  const monthOptions = [
    { value: null, label: "全部" },
    ...Array.from({ length: 12 }, (_, i) => ({
      value: i + 1,
      label: `${i + 1}月`,
    })),
  ];

  useEffect(() => {
    const fetchYears = async () => {
      try {
        const response = await fetch("/api/beads-ipqc/available-years");
        const data = await response.json();

        if (data.ok && data.years.length > 0) {
          setAvailableYears(data.years);
          if (!data.years.includes(odYear)) {
            setOdYear(data.years[0]);
            setCvYear(data.years[0]);
          }
        }
      } catch (err) {
        console.error("載入年份失敗:", err);
      }
    };

    fetchYears();
  }, []);

  useEffect(() => {
    const fetchWeeklyList = async () => {
      try {
        const response = await fetch(`/api/beads-ipqc/weekly-list?year=${odYear}`);
        const data = await response.json();

        if (data.ok) {
          setWeeklyList(data.weekly_list || []);
        }
      } catch (err) {
        console.error("載入週別列表失敗:", err);
      }
    };

    if (odYear) {
      fetchWeeklyList();
      setCvYear(odYear);
    }
  }, [odYear]);

  useEffect(() => {
    const fetchMarkerList = async () => {
      try {
        const response = await fetch(`/api/beads-ipqc/marker-list?year=${odYear}`);
        const data = await response.json();

        if (data.ok && data.marker_list.length > 0) {
          setMarkerList(data.marker_list);
          if (!odMarker) {
            setOdMarker(data.marker_list[0]);
          }
          if (!cvMarker) {
            setCvMarker(data.marker_list[0]);
          }
        }
      } catch (err) {
        console.error("載入 Marker 列表失敗:", err);
      }
    };

    if (odYear) {
      fetchMarkerList();
    }
  }, [odYear]);

  useEffect(() => {
    const fetchOdData = async () => {
      if (!odMarker) return;

      try {
        setOdLoading(true);

        const params = new URLSearchParams({
          year: odYear.toString(),
          marker: odMarker,
        });

        if (odMonth) {
          params.append("month", odMonth.toString());
        }

        if (odWeekly) {
          params.append("weekly", odWeekly);
        }

        const response = await fetch(`/api/beads-ipqc/od-trend-data?${params}`);
        const data = await response.json();

        if (data.ok) {
          setOdData(data.data || []);
        }
      } catch (err) {
        console.error("載入 OD 趨勢數據失敗:", err);
      } finally {
        setOdLoading(false);
      }
    };

    fetchOdData();
  }, [odYear, odMonth, odWeekly, odMarker]);

  useEffect(() => {
    const fetchCvData = async () => {
      if (!cvMarker) return;

      try {
        setCvLoading(true);

        const params = new URLSearchParams({
          year: cvYear.toString(),
          marker: cvMarker,
          cv_type: cvType,
        });

        if (cvMonth) params.append("month", cvMonth.toString());
        if (cvWeekly) params.append("weekly", cvWeekly);

        const response = await fetch(`/api/beads-ipqc/cv-trend-data?${params}`);
        const data = await response.json();

        if (data.ok) {
          const convert = (v: any) =>
            v === null || v === "" || v === undefined || v === " " ? null : Number(v);

          const spec_L1 = convert(data.spec_data?.L1_SPEC);
          const spec_L2 = convert(data.spec_data?.L2_SPEC);

          const fixed = (data.data || []).map((r: any) => ({
            ...r,
            L1_OD_CV: convert(r.L1_OD_CV),
            L2_OD_CV: convert(r.L2_OD_CV),
            N1_OD_CV: convert(r.N1_OD_CV),
            N3_OD_CV: convert(r.N3_OD_CV),
            L1_Conc_CV: convert(r.L1_Conc_CV),
            L2_Conc_CV: convert(r.L2_Conc_CV),
            N1_Conc_CV: convert(r.N1_Conc_CV),
            N3_Conc_CV: convert(r.N3_Conc_CV),
            L1_SPEC: spec_L1,
            L2_SPEC: spec_L2,
          }));

          setCvData(fixed);
        }
      } catch (err) {
        console.error("載入 CV 趨勢數據失敗:", err);
      } finally {
        setCvLoading(false);
      }
    };

    fetchCvData();
  }, [cvYear, cvMonth, cvWeekly, cvMarker, cvType]);

  return (
    <div className="space-y-6">
      <div className="border-b border-slate-700">
        <nav className="flex gap-4">
          <button
            type="button"
            onClick={() => setActiveTab("OD")}
            className={`
              py-2 px-4 text-sm font-bold rounded-t-md border transition-all duration-200
              ${activeTab === "OD"
                ? "bg-gray-900 border-blue-500 text-blue-400 border-b-black"
                : "bg-black border-gray-700 text-gray-500 hover:border-gray-500 hover:text-gray-300"
              }
            `}
          >
            OD 趨勢圖
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("CV")}
            className={`
              py-2 px-4 text-sm font-bold rounded-t-md border transition-all duration-200
              ${activeTab === "CV"
                ? "bg-gray-900 border-blue-500 text-blue-400 border-b-black"
                : "bg-black border-gray-700 text-gray-500 hover:border-gray-500 hover:text-gray-300"
              }
            `}
          >
            CV 趨勢圖
          </button>
        </nav>
      </div>

      {activeTab === "OD" && (
        <Card className="p-6">
          <h3 className="text-xl font-semibold text-slate-200 mb-4">Beads OD 趨勢圖</h3>

          <div className="grid grid-cols-4 gap-4 mb-6">
            <div>
              <label className="block text-sm font-semibold text-slate-300 mb-1">年份</label>
              <select
                value={odYear}
                onChange={(e) => setOdYear(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-lg bg-slate-700 text-white border border-slate-600"
              >
                {availableYears.map((year: any) => (
                  <option key={year} value={year}>
                    {year}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-semibold text-slate-300 mb-1">月份</label>
              <select
                value={odMonth || ""}
                onChange={(e) => setOdMonth(e.target.value ? Number(e.target.value) : null)}
                className="w-full px-3 py-2 rounded-lg bg-slate-700 text-white border border-slate-600"
              >
                {monthOptions.map((opt) => (
                  <option key={opt.label} value={opt.value || ""}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-semibold text-slate-300 mb-1">週別</label>
              <select
                value={odWeekly || ""}
                onChange={(e) => setOdWeekly(e.target.value || null)}
                className="w-full px-3 py-2 rounded-lg bg-slate-700 text-white border border-slate-600"
              >
                <option value="">全部</option>
                {weeklyList.map((w: any) => (
                  <option key={w} value={w}>
                    {w}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-semibold text-slate-300 mb-1">Marker</label>
              <select
                value={odMarker}
                onChange={(e) => setOdMarker(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-slate-700 text-white border border-slate-600"
              >
                {markerList.map((m: any) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="text-sm text-slate-300 mb-4">
            📊 顯示：{odYear} 年
            {odMonth && ` ${odMonth} 月`}
            {odWeekly && ` ${odWeekly}`}
            {odMarker && ` | Marker: ${odMarker}`}
            {odData.length > 0 && ` | 共 ${odData.length} 筆數據`}
          </div>

          {odLoading ? (
            <div className="text-center py-16">
              <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
              <p className="mt-4 text-slate-300">載入中...</p>
            </div>
          ) : odData.length > 0 ? (
            <ResponsiveContainer width="100%" height={400}>
              <LineChart data={odData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis
                  dataKey="batch"
                  tick={{ fontSize: 12 }}
                  stroke="#64748b"
                  angle={-45}
                  textAnchor="end"
                  height={100}
                />
                <YAxis
                  tick={{ fontSize: 12 }}
                  stroke="#64748b"
                  label={{ value: "OD 值", angle: -90, position: "insideLeft" }}
                  domain={["auto", "auto"]}
                />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="L1_Mean_OD" stroke="#2563eb" strokeWidth={2} name="L1 Mean OD" dot={{ r: 4 }} connectNulls />
                <Line type="monotone" dataKey="L2_Mean_OD" stroke="#0d9488" strokeWidth={2} name="L2 Mean OD" dot={{ r: 4 }} connectNulls />
                <Line type="monotone" dataKey="N1_OD" stroke="#ca8a04" strokeWidth={2} name="N1 OD" dot={{ r: 4 }} connectNulls />
                <Line type="monotone" dataKey="N3_OD" stroke="#7e22ce" strokeWidth={2} name="N3 OD" dot={{ r: 4 }} connectNulls />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-center py-16 text-slate-300">
              <p className="text-lg">📊 暫無 OD 趨勢資料</p>
              <p className="text-sm mt-2">請調整篩選條件或確認資料庫中有對應的數據</p>
            </div>
          )}
        </Card>
      )}

      {activeTab === "CV" && (
        <Card className="p-6">
          <h3 className="text-xl font-semibold text-slate-200 mb-4">Beads CV 趨勢圖</h3>

          <div className="grid grid-cols-5 gap-4 mb-6">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">年份</label>
              <select
                value={cvYear}
                onChange={(e) => setCvYear(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-lg bg-slate-700 text-white border border-slate-600"
              >
                {availableYears.map((year: any) => (
                  <option key={year} value={year}>
                    {year}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">月份</label>
              <select
                value={cvMonth || ""}
                onChange={(e) => setCvMonth(e.target.value ? Number(e.target.value) : null)}
                className="w-full px-3 py-2 rounded-lg bg-slate-700 text-white border border-slate-600"
              >
                {monthOptions.map((opt) => (
                  <option key={opt.label} value={opt.value || ""}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">週別</label>
              <select
                value={cvWeekly || ""}
                onChange={(e) => setCvWeekly(e.target.value || null)}
                className="w-full px-3 py-2 rounded-lg bg-slate-700 text-white border border-slate-600"
              >
                <option value="">全部</option>
                {weeklyList.map((w: any) => (
                  <option key={w} value={w}>
                    {w}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">Marker</label>
              <select
                value={cvMarker}
                onChange={(e) => setCvMarker(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-slate-700 text-white border border-slate-600"
              >
                {markerList.map((m: any) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">CV 類型</label>
              <select
                value={cvType}
                onChange={(e) => setCvType(e.target.value as "OD_CV" | "Conc_CV")}
                className="w-full px-3 py-2 rounded-lg bg-slate-700 text-white border border-slate-600"
              >
                <option value="OD_CV">OD CV</option>
                <option value="Conc_CV">Conc. CV</option>
              </select>
            </div>
          </div>

          <div className="text-sm text-slate-300 mb-4">
            📊 顯示：{cvYear} 年
            {cvMonth && ` ${cvMonth} 月`}
            {cvWeekly && ` ${cvWeekly}`}
            {cvMarker && ` | Marker: ${cvMarker}`}
            {` | 模式: ${cvType === "OD_CV" ? "OD CV" : "Conc. CV"}`}
            {cvData.length > 0 && ` | 共 ${cvData.length} 筆數據`}
          </div>

          {cvLoading ? (
            <div className="text-center py-16">
              <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
              <p className="mt-4 text-slate-300">載入中...</p>
            </div>
          ) : cvData.length > 0 ? (
            <ResponsiveContainer width="100%" height={400}>
              <LineChart data={cvData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis
                  dataKey="batch"
                  tick={{ fontSize: 12 }}
                  stroke="#64748b"
                  angle={-45}
                  textAnchor="end"
                  height={100}
                />
                <YAxis
                  tick={{ fontSize: 12 }}
                  stroke="#64748b"
                  label={{ value: "CV 值 (%)", angle: -90, position: "insideLeft" }}
                  domain={["auto", "auto"]}
                />
                <Tooltip />
                <Legend />

                {cvType === "OD_CV" && (
                  <>
                    <Line type="monotone" dataKey="L1_OD_CV" stroke="#2563eb" strokeWidth={2} name="L1 OD CV" dot={{ r: 4 }} connectNulls />
                    <Line type="monotone" dataKey="L2_OD_CV" stroke="#0d9488" strokeWidth={2} name="L2 OD CV" dot={{ r: 4 }} connectNulls />
                    <Line type="monotone" dataKey="N1_OD_CV" stroke="#ca8a04" strokeWidth={2} name="N1 OD CV" dot={{ r: 4 }} connectNulls />
                    <Line type="monotone" dataKey="N3_OD_CV" stroke="#0ea5e9" strokeWidth={2} name="N3 OD CV" dot={{ r: 4 }} connectNulls />
                  </>
                )}

                {cvType === "Conc_CV" && (
                  <>
                    <Line type="monotone" dataKey="L1_Conc_CV" stroke="#2563eb" strokeWidth={2} name="L1 Conc CV" dot={{ r: 4 }} connectNulls />
                    <Line type="monotone" dataKey="L2_Conc_CV" stroke="#0d9488" strokeWidth={2} name="L2 Conc CV" dot={{ r: 4 }} connectNulls />
                    <Line type="monotone" dataKey="N1_Conc_CV" stroke="#ca8a04" strokeWidth={2} name="N1 Conc CV" dot={{ r: 4 }} connectNulls />
                    <Line type="monotone" dataKey="N3_Conc_CV" stroke="#0ea5e9" strokeWidth={2} name="N3 Conc CV" dot={{ r: 4 }} connectNulls />
                  </>
                )}

                <Line type="monotone" dataKey="L1_SPEC" stroke="#dc2626" strokeWidth={2} strokeDasharray="6 6" dot={false} name="L1 SPEC" connectNulls />
                <Line type="monotone" dataKey="L2_SPEC" stroke="#dc2626" strokeWidth={2} strokeDasharray="6 6" dot={false} name="L2 SPEC" connectNulls />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-center py-16 text-slate-300">
              <p className="text-lg">📊 暫無 CV 趨勢資料</p>
              <p className="text-sm mt-2">請調整篩選條件或確認資料庫中有對應的數據</p>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

// --- 3.4 排程表組件 (Schedule Table View) ---
interface ScheduleRow {
  date: string;
  marker?: string;
  machine: string;
  dryer?: string;
  operator: string;
  rdTime?: string;
  start: string;
  end: string;
  qty?: string;
  pn?: string;
  batch?: string;
  workOrder?: string;
  remark?: string;
}

const ScheduleTableView = () => {
  const [searchType, setSearchType] = useState<"week" | "date">("week");
  const [searchWeek, setSearchWeek] = useState("");
  const [searchDate, setSearchDate] = useState("");
  const [operatorFilter, setOperatorFilter] = useState("");
  const [scheduleData, setScheduleData] = useState<ScheduleRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editedData, setEditedData] = useState<ScheduleRow[]>([]);
  const [modifiedRows, setModifiedRows] = useState<Set<number>>(new Set());
  const [isSaving, setIsSaving] = useState(false);

  // 初始化：設定當前週別
  useEffect(() => {
    const today = new Date();
    const isoWeek = getISOWeek(today);
    setSearchWeek(isoWeek);

    // 設定當前日期
    const dateStr = today.toISOString().split('T')[0];
    setSearchDate(dateStr);
  }, []);

  // 計算 ISO 週數
  const getISOWeek = (date: Date): string => {
    const target = new Date(date.valueOf());
    const dayNr = (date.getDay() + 6) % 7;
    target.setDate(target.getDate() - dayNr + 3);
    const firstThursday = target.valueOf();
    target.setMonth(0, 1);
    if (target.getDay() !== 4) {
      target.setMonth(0, 1 + (((4 - target.getDay()) + 7) % 7));
    }
    const weekNumber = 1 + Math.ceil((firstThursday - target.valueOf()) / 604800000);
    const year = new Date(firstThursday).getFullYear();
    return `${year}_W${weekNumber.toString().padStart(2, "0")}`;
  };

  // 執行搜尋
  const handleSearch = async () => {
    try {
      setLoading(true);
      setError(null);

      const searchValue = searchType === "week" ? searchWeek : searchDate;

      if (!searchValue) {
        setError("請輸入搜尋條件");
        setLoading(false);
        return;
      }

      let url = `/api/schedule/search?searchType=${searchType}&searchValue=${encodeURIComponent(searchValue)}`;

      if (operatorFilter.trim()) {
        url += `&operator=${encodeURIComponent(operatorFilter.trim())}`;
      }

      const response = await fetch(url);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      setScheduleData(data);
    } catch (err) {
      console.error("搜尋失敗:", err);
      setError(err instanceof Error ? err.message : "搜尋失敗");
    } finally {
      setLoading(false);
    }
  };

  // 進入編輯模式
  const handleStartEdit = () => {
    setIsEditing(true);
    setEditedData(JSON.parse(JSON.stringify(scheduleData)));
    setModifiedRows(new Set());
  };

  // 取消編輯
  const handleCancelEdit = () => {
    if (modifiedRows.size > 0) {
      if (!confirm(`有 ${modifiedRows.size} 筆資料已修改，確定要放棄修改嗎？`)) {
        return;
      }
    }
    setIsEditing(false);
    setEditedData([]);
    setModifiedRows(new Set());
  };

  // 更新單個欄位
  const handleCellChange = (rowIndex: number, field: keyof ScheduleRow, value: string) => {
    const newData = [...editedData];
    newData[rowIndex] = { ...newData[rowIndex], [field]: value };
    setEditedData(newData);

    const newModified = new Set(modifiedRows);
    newModified.add(rowIndex);
    setModifiedRows(newModified);
  };

  // 保存到資料庫
  const handleSaveChanges = async () => {
    if (modifiedRows.size === 0) {
      alert("沒有修改任何資料");
      return;
    }

    if (!confirm(`確定要保存 ${modifiedRows.size} 筆修改嗎？`)) {
      return;
    }

    try {
      setIsSaving(true);

      const dataToSave = Array.from(modifiedRows).map((index) => editedData[index]);

      const response = await fetch("/api/schedule/save", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(dataToSave),
      });

      const result = await response.json();

      if (result.ok) {
        alert(result.message || "保存成功！");
        setScheduleData(editedData);
        setIsEditing(false);
        setEditedData([]);
        setModifiedRows(new Set());
      } else {
        alert(`保存失敗：${result.message}`);
      }
    } catch (err) {
      console.error("保存失敗:", err);
      alert(`保存失敗：${err instanceof Error ? err.message : "未知錯誤"}`);
    } finally {
      setIsSaving(false);
    }
  };

  const displayData = isEditing ? editedData : scheduleData;

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <Card className="p-6">
        {/* 搜尋控制區 */}
        <div className="mb-6">
          <h3 className="text-xl font-semibold text-slate-200 mb-4 flex items-center gap-2">
            <FileSpreadsheet size={24} className="text-blue-400" />
            排程表查詢
          </h3>

          {/* 搜尋類型切換 */}
          <div className="flex gap-2 mb-4">
            <button
              onClick={() => setSearchType("week")}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition ${searchType === "week"
                ? "bg-blue-600 text-white"
                : "bg-slate-700 text-slate-300 hover:bg-slate-600"
                }`}
            >
              按週別搜尋
            </button>
            <button
              onClick={() => setSearchType("date")}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition ${searchType === "date"
                ? "bg-blue-600 text-white"
                : "bg-slate-700 text-slate-300 hover:bg-slate-600"
                }`}
            >
              按日期搜尋
            </button>
          </div>

          {/* 搜尋輸入區 */}
          <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
            {searchType === "week" ? (
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">週別 (格式: 2025_W01)</label>
                <input
                  type="text"
                  value={searchWeek}
                  onChange={(e) => setSearchWeek(e.target.value)}
                  placeholder="例如: 2025_W01"
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            ) : (
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">日期</label>
                <input
                  type="date"
                  value={searchDate}
                  onChange={(e) => setSearchDate(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">操作員 (選填)</label>
              <input
                type="text"
                value={operatorFilter}
                onChange={(e) => setOperatorFilter(e.target.value)}
                placeholder="輸入操作員名稱"
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            <div className="flex items-end">
              <button
                onClick={handleSearch}
                disabled={loading}
                className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition disabled:bg-slate-600 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {loading ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                    搜尋中...
                  </>
                ) : (
                  "搜尋"
                )}
              </button>
            </div>

            {/* 編輯控制按鈕（與搜尋同一行） */}
            {scheduleData.length > 0 && (
              <div className="flex items-end gap-2">
                {!isEditing ? (
                  <button
                    onClick={handleStartEdit}
                    className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition flex items-center gap-2 whitespace-nowrap"
                  >
                    <Activity size={16} />
                    開始編輯
                  </button>
                ) : (
                  <>
                    <button
                      onClick={handleSaveChanges}
                      disabled={isSaving || modifiedRows.size === 0}
                      className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition disabled:bg-slate-600 disabled:cursor-not-allowed flex items-center gap-2 whitespace-nowrap"
                    >
                      {isSaving ? (
                        <>
                          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                          保存中...
                        </>
                      ) : (
                        <>
                          <CheckCircle2 size={16} />
                          保存 {modifiedRows.size > 0 && `(${modifiedRows.size})`}
                        </>
                      )}
                    </button>
                    <button
                      onClick={handleCancelEdit}
                      disabled={isSaving}
                      className="px-4 py-2 bg-slate-600 text-white rounded-lg hover:bg-slate-700 transition disabled:bg-slate-700 disabled:cursor-not-allowed whitespace-nowrap"
                    >
                      取消
                    </button>
                  </>
                )}
              </div>
            )}
          </div>

          {/* 錯誤訊息 */}
          {error && (
            <div className="mt-4 p-3 bg-red-900/20 border border-red-500/50 rounded-lg text-red-400 text-sm">
              ⚠️ {error}
            </div>
          )}
        </div>

        {/* 資料表格 */}
        {loading ? (
          <div className="text-center py-16">
            <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
            <p className="mt-4 text-slate-300">載入中...</p>
          </div>
        ) : displayData.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-700/50 sticky top-0">
                <tr>
                  {isEditing && <th className="px-3 py-3 text-left text-slate-300 font-medium">狀態</th>}
                  <th className="px-3 py-3 text-left text-slate-300 font-medium">日期</th>
                  <th className="px-3 py-3 text-left text-slate-300 font-medium">Marker</th>
                  <th className="px-3 py-3 text-left text-slate-300 font-medium">機台</th>
                  <th className="px-3 py-3 text-left text-slate-300 font-medium">凍乾機</th>
                  <th className="px-3 py-3 text-left text-slate-300 font-medium">操作員</th>
                  <th className="px-3 py-3 text-left text-slate-300 font-medium">R&D時間</th>
                  <th className="px-3 py-3 text-left text-slate-300 font-medium">開始</th>
                  <th className="px-3 py-3 text-left text-slate-300 font-medium">結束</th>
                  <th className="px-3 py-3 text-left text-slate-300 font-medium">數量</th>
                  <th className="px-3 py-3 text-left text-slate-300 font-medium">P/N</th>
                  <th className="px-3 py-3 text-left text-slate-300 font-medium">Batch</th>
                  <th className="px-3 py-3 text-left text-slate-300 font-medium">工單號碼</th>
                  <th className="px-3 py-3 text-left text-slate-300 font-medium">備註</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {displayData.map((row, index) => (
                  <tr
                    key={index}
                    className={`hover:bg-slate-700/30 transition ${modifiedRows.has(index) ? "bg-blue-900/20" : ""
                      }`}
                  >
                    {isEditing && (
                      <td className="px-3 py-2">
                        {modifiedRows.has(index) && (
                          <span className="inline-block w-2 h-2 bg-blue-500 rounded-full"></span>
                        )}
                      </td>
                    )}
                    <td className="px-3 py-2 text-slate-300">{row.date}</td>
                    <td className="px-3 py-2">
                      {isEditing ? (
                        <input
                          type="text"
                          value={row.marker || ""}
                          onChange={(e) => handleCellChange(index, "marker", e.target.value)}
                          className="w-full px-2 py-1 bg-slate-700 border border-slate-600 rounded text-white text-sm"
                        />
                      ) : (
                        <span className="text-slate-300">{row.marker}</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-slate-300">{row.machine}</td>
                    <td className="px-3 py-2">
                      {isEditing ? (
                        <input
                          type="text"
                          value={row.dryer || ""}
                          onChange={(e) => handleCellChange(index, "dryer", e.target.value)}
                          className="w-full px-2 py-1 bg-slate-700 border border-slate-600 rounded text-white text-sm"
                        />
                      ) : (
                        <span className="text-slate-300">{row.dryer}</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {isEditing ? (
                        <input
                          type="text"
                          value={row.operator}
                          onChange={(e) => handleCellChange(index, "operator", e.target.value)}
                          className="w-full px-2 py-1 bg-slate-700 border border-slate-600 rounded text-white text-sm"
                        />
                      ) : (
                        <span className="text-slate-300">{row.operator}</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {isEditing ? (
                        <input
                          type="text"
                          value={row.rdTime || ""}
                          onChange={(e) => handleCellChange(index, "rdTime", e.target.value)}
                          placeholder="HH:MM"
                          className="w-full px-2 py-1 bg-slate-700 border border-slate-600 rounded text-white text-sm"
                        />
                      ) : (
                        <span className="text-slate-300">{row.rdTime}</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {isEditing ? (
                        <input
                          type="text"
                          value={row.start}
                          onChange={(e) => handleCellChange(index, "start", e.target.value)}
                          placeholder="HH:MM"
                          className="w-full px-2 py-1 bg-slate-700 border border-slate-600 rounded text-white text-sm"
                        />
                      ) : (
                        <span className="text-slate-300">{row.start}</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {isEditing ? (
                        <input
                          type="text"
                          value={row.end}
                          onChange={(e) => handleCellChange(index, "end", e.target.value)}
                          placeholder="HH:MM"
                          className="w-full px-2 py-1 bg-slate-700 border border-slate-600 rounded text-white text-sm"
                        />
                      ) : (
                        <span className="text-slate-300">{row.end}</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {isEditing ? (
                        <input
                          type="text"
                          value={row.qty || ""}
                          onChange={(e) => handleCellChange(index, "qty", e.target.value)}
                          className="w-full px-2 py-1 bg-slate-700 border border-slate-600 rounded text-white text-sm"
                        />
                      ) : (
                        <span className="text-slate-300">{row.qty}</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {isEditing ? (
                        <input
                          type="text"
                          value={row.pn || ""}
                          onChange={(e) => handleCellChange(index, "pn", e.target.value)}
                          className="w-full px-2 py-1 bg-slate-700 border border-slate-600 rounded text-white text-sm"
                        />
                      ) : (
                        <span className="text-slate-300">{row.pn}</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {isEditing ? (
                        <input
                          type="text"
                          value={row.batch || ""}
                          onChange={(e) => handleCellChange(index, "batch", e.target.value)}
                          className="w-full px-2 py-1 bg-slate-700 border border-slate-600 rounded text-white text-sm"
                        />
                      ) : (
                        <span className="text-slate-300">{row.batch}</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {isEditing ? (
                        <input
                          type="text"
                          value={row.workOrder || ""}
                          onChange={(e) => handleCellChange(index, "workOrder", e.target.value)}
                          className="w-full px-2 py-1 bg-slate-700 border border-slate-600 rounded text-white text-sm"
                        />
                      ) : (
                        <span className="text-slate-300">{row.workOrder}</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {isEditing ? (
                        <input
                          type="text"
                          value={row.remark || ""}
                          onChange={(e) => handleCellChange(index, "remark", e.target.value)}
                          className="w-full px-2 py-1 bg-slate-700 border border-slate-600 rounded text-white text-sm"
                        />
                      ) : (
                        <span className="text-slate-300">{row.remark}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-16 text-slate-300">
            <FileSpreadsheet size={64} className="mx-auto mb-4 text-slate-600" />
            <p className="text-lg">尚無排程資料</p>
            <p className="text-sm mt-2">請使用上方搜尋功能查詢排程表</p>
          </div>
        )}

        {/* 資料統計 */}
        {displayData.length > 0 && (
          <div className="mt-4 pt-4 border-t border-slate-700">
            <div className="flex justify-between text-sm text-slate-400">
              <span>共 {displayData.length} 筆排程資料</span>
              {isEditing && modifiedRows.size > 0 && (
                <span className="text-blue-400">已修改 {modifiedRows.size} 筆</span>
              )}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
};

// --- 3.5 Placeholder View (其他尚未實作的 Tab) ---
const PlaceholderView = ({ title, icon: Icon }: { title: string, icon: any }) => (
  <div className="flex flex-col items-center justify-center h-[60vh] text-slate-500 animate-in zoom-in-95 duration-300">
    <div className="bg-slate-800/50 p-8 rounded-full mb-6">
      <Icon size={64} className="text-slate-600" />
    </div>
    <h2 className="text-2xl font-bold text-slate-300 mb-2">{title}</h2>
    <p className="text-slate-400">此功能模組正在開發中...</p>
    <div className="mt-8 flex gap-2">
      <span className="px-3 py-1 rounded-full bg-slate-800 text-xs border border-slate-700">系統建置中</span>
      <span className="px-3 py-1 rounded-full bg-slate-800 text-xs border border-slate-700">權限控管</span>
    </div>
  </div>
);

// ==========================================
// 4. 主頁面組件 (Main Layout)
// ==========================================

export default function BeadsOpsDashboard() {
  const [currentTab, setCurrentTab] = useState("dashboard");
  const { header } = DASHBOARD_DATA;

  // 根據 Tab ID 渲染對應內容
  const renderContent = () => {
    switch (currentTab) {
      case "dashboard": return <DashboardView />;
      case "ipqc": return <BeadsIPQCPage />;
      case "dispatch": return <DispatchView />;
      case "timetable": return <ScheduleTableView />;
      case "qrcode": return (
        <div className="w-full h-[calc(100vh-200px)] animate-in fade-in duration-500">
          <Card className="p-0 h-full overflow-hidden">
            <iframe
              src="http://10.6.182.47:8502"
              className="w-full h-full border-0"
              title="工單 QR 掃描追蹤"
            />
          </Card>
        </div>
      );
      case "info": return (
        <div className="w-full h-[calc(100vh-200px)] animate-in fade-in duration-500">
          <Card className="p-0 h-full overflow-hidden bg-slate-900">
            {/* 深色背景層 */}
            <div className="relative w-full h-full bg-slate-900">
              <iframe
                src="http://10.6.182.47:8056"
                className="w-full h-full border-0 bg-white"
                title="滴定凍乾e工單資訊"
              />
              {/* 可選：添加深色邊框效果 */}
              <div className="absolute inset-0 pointer-events-none border-4 border-slate-800/50 rounded-xl"></div>
            </div>
          </Card>
        </div>
      );

      case "schedule": return (
        <div className="w-full h-[calc(100vh-200px)] animate-in fade-in duration-500">
          <Card className="p-0 h-full overflow-hidden bg-slate-900">
            <div className="relative w-full h-full bg-slate-900">
              <iframe
                src="http://10.6.182.47:8505"
                className="w-full h-full border-0 bg-white"
                title="Beads 排程作業"
              />
              <div className="absolute inset-0 pointer-events-none border-4 border-slate-800/50 rounded-xl"></div>
            </div>
          </Card>
        </div>
      );
      default:
        const tabInfo = TABS.find(t => t.id === currentTab);
        return <PlaceholderView title={tabInfo?.label || ""} icon={tabInfo?.icon || FileText} />;
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-white font-sans selection:bg-blue-500/30 flex flex-col">
      {/* 頂部標題列 */}
      <header className="bg-slate-900/50 backdrop-blur-md border-b border-slate-800 sticky top-0 z-50">
        <div className="px-4 md:px-8 pt-4 pb-0">
          <div className="flex justify-between items-center mb-4">
            <div>
              <h1 className="text-2xl md:text-3xl font-bold bg-gradient-to-r from-blue-400 to-cyan-300 bg-clip-text text-transparent">
                {header.title}
              </h1>
              <p className="text-slate-400 text-xs mt-1 tracking-wider opacity-80">SMART MANUFACTURING DASHBOARD</p>
            </div>
            <div className="text-right hidden md:block">
              <div className="flex items-center gap-2 text-green-400 mb-1 justify-end">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
                </span>
                <span className="text-xs font-bold tracking-widest">{header.status}</span>
              </div>
              <div className="text-slate-500 text-xs font-mono">{header.time}</div>
            </div>
          </div>

          {/* 導航 Tabs */}
          <div className="flex overflow-x-auto no-scrollbar gap-1">
            {TABS.map((tab) => {
              const Icon = tab.icon;
              const isActive = currentTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setCurrentTab(tab.id)}
                  className={`
                    flex items-center gap-2 px-4 py-3 text-sm font-medium whitespace-nowrap transition-all border-b-2
                    ${isActive
                      ? "text-blue-400 border-blue-500 bg-slate-800/30 rounded-t-lg"
                      : "text-slate-400 border-transparent hover:text-slate-200 hover:bg-slate-800/10"
                    }
                  `}
                >
                  <Icon size={16} className={isActive ? "text-blue-400" : "text-slate-500"} />
                  {tab.label}
                </button>
              );
            })}
          </div>
        </div>
      </header>

      {/* 主要內容區域 */}
      <main className="flex-1 p-4 md:p-8 overflow-y-auto">
        {renderContent()}
      </main>
    </div>
  );
}