import React, { useState } from "react";
import { AlertTriangle, Loader2, X, CheckCircle2, Square } from "lucide-react";

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
  const [error, setError] = useState("");
  const [processingKeys, setProcessingKeys] = useState<Set<string>>(new Set());

  const handleOpen = async () => {
    setIsOpen(true);
    setLoading(true);
    setError("");

    try {
      const response = await fetch("/api/dashboard/low-yield-items");
      const data = await response.json();

      if (data.ok) {
        setItems(data.items);
      } else {
        setError("無法取得低良率資料");
      }
    } catch (err) {
      setError("連線錯誤");
    } finally {
      setLoading(false);
    }
  };

  const handleIgnore = async (item: LowYieldItem) => {
    const key = item.key;
    const ignore = true;

    setProcessingKeys(prev => new Set(prev).add(key));

    try {
      const res = await fetch("/api/dashboard/toggle-yield-ignore", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          key: key,
          lot_no: item.lot_no,
          work_order: item.work_order,
          ignore: ignore
        })
      });

      const result = await res.json();

      if (!result.ok) throw new Error(result.error);

      setItems(prev => prev.filter(i => i.key !== key));

      if (onUpdate) onUpdate();

    } catch (err) {
      console.error("Ignore failed:", err);
      alert("操作失敗，請稍後再試");
    } finally {
      setProcessingKeys(prev => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    }
  };

  if (!isOpen) {
    return (
      <button
        onClick={() => {
          handleOpen();
          setIsOpen(true);
        }}
        className="px-3 py-1.5 text-xs text-amber-400 border border-amber-400/30 rounded hover:bg-amber-400/10 transition-colors flex items-center gap-1"
      >
        <AlertTriangle size={14} />
        查看低良率項目
      </button>
    );
  }

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/70">
      <div className="bg-slate-800 border border-slate-700 rounded-xl w-full max-w-4xl max-h-[80vh] flex flex-col">
        <div className="flex justify-between p-4 border-b border-slate-700">
          <h3 className="text-white font-bold flex items-center gap-2">
            <AlertTriangle size={18} className="text-amber-500" />
            低良率項目
          </h3>

          <button onClick={() => setIsOpen(false)} className="text-slate-400 hover:text-white">
            <X size={20} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="flex flex-col items-center text-slate-400">
              <Loader2 className="animate-spin h-6 w-6 mb-2" />
              載入中...
            </div>
          ) : error ? (
            <div className="text-red-400 text-center">{error}</div>
          ) : items.length === 0 ? (
            <div className="text-slate-500 text-center flex flex-col items-center py-10">
              <CheckCircle2 size={40} className="opacity-20 mb-2" />
              目前沒有異常項目
            </div>
          ) : (
            <table className="w-full text-xs text-slate-300">
              <thead>
                <tr className="bg-slate-900 text-slate-400">
                  <th className="p-2 text-center">忽略</th>
                  <th className="p-2">LOT NO</th>
                  <th className="p-2">工單號碼</th>
                  <th className="p-2">品名</th>
                  <th className="p-2 text-right">良率</th>
                  <th className="p-2">入庫日期</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.key} className="border-b border-slate-700">
                    <td className="p-2 text-center">
                      {processingKeys.has(item.key) ? (
                        <Loader2 className="animate-spin h-4 w-4 mx-auto" />
                      ) : (
                        <button onClick={() => handleIgnore(item)}>
                          <Square size={16} />
                        </button>
                      )}
                    </td>

                    <td className="p-2 font-mono">{item.lot_no}</td>
                    <td className="p-2 font-mono">{item.work_order}</td>
                    <td className="p-2">{item.product_name}</td>
                    <td className="p-2 text-amber-400 text-right font-bold">
                      {item.yield.toFixed(1)}%
                    </td>
                    <td className="p-2">{item.warehouse_date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
};

export default LowYieldModal;
