import React, { useState, useEffect } from 'react';
import { io } from 'socket.io-client';
import { AlertTriangle, X, Clock } from 'lucide-react';

// 設定您的後端網址 (Flask 運行的 IP:Port)
// 如果是在同一台電腦開發，通常是 http://localhost:5100
const SOCKET_URL = "http://54.199.19.240";

interface AbnormalData {
  id: number;
  station: string;
  machine_id: string;
  description: string;
  created_at: string;
  user: string;
}

export const AbnormalInfor = () => {
  const [alert, setAlert] = useState<AbnormalData | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // 1. 建立 WebSocket 連線
    const socket = io(SOCKET_URL, {
      transports: ['websocket'], // 強制使用 WebSocket 協定
    });

    // 2. 監聽連線成功
    socket.on('connect', () => {
      console.log("🟢 WebSocket Connected:", socket.id);
    });

    // 3. 監聽後端發出的 'new_abnormal' 事件
    socket.on('new_abnormal', (data: AbnormalData) => {
      console.log("🔔 收到異常推播:", data);
      setAlert(data);
      setVisible(true);

      // 播放音效 (可選)
      // const audio = new Audio('/alert.mp3');
      // audio.play().catch(e => console.log("Audio play failed:", e));

      // 15秒後自動關閉通知
      setTimeout(() => setVisible(false), 15000);
    });

    // 4. 清除連線 (組件卸載時)
    return () => {
      socket.disconnect();
      console.log("🔴 WebSocket Disconnected");
    };
  }, []);

  if (!visible || !alert) return null;

  // 根據描述內容決定顏色 (緊急關鍵字)
  const isUrgent = alert.description.includes("緊急") || alert.description.includes("阻塞");
  const borderColor = isUrgent ? "border-red-500" : "border-amber-500";
  const iconColor = isUrgent ? "text-red-500" : "text-amber-500";

  return (
    <div className={`fixed bottom-6 right-6 z-[9999] max-w-sm w-full bg-slate-900/95 backdrop-blur-md border-l-4 ${borderColor} shadow-2xl rounded-r-lg overflow-hidden animate-in slide-in-from-right-10 fade-in duration-500`}>
      <div className="p-4">
        <div className="flex justify-between items-start">
          <div className="flex items-center gap-2">
            <AlertTriangle className={iconColor} size={24} />
            <h3 className="font-bold text-white text-lg">異常事件通報</h3>
          </div>
          <button 
            onClick={() => setVisible(false)}
            className="text-slate-400 hover:text-white transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        <div className="mt-3 space-y-1">
          <div className="flex justify-between text-sm">
            <span className="text-slate-400">發生站點：</span>
            <span className="text-amber-400 font-mono font-bold">{alert.station}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-slate-400">機台編號：</span>
            <span className="text-white font-mono">{alert.machine_id}</span>
          </div>
          <div className="mt-2 text-sm text-slate-200 bg-slate-800/50 p-2 rounded border border-slate-700">
            {/* 去掉 (附x張圖) 文字，讓版面乾淨 */}
            {alert.description.split(' (附')[0]}
          </div>
        </div>

        <div className="mt-3 flex justify-between items-center text-xs text-slate-500 border-t border-slate-800 pt-2">
          <div className="flex items-center gap-1">
            <Clock size={12} />
            {new Date(alert.created_at).toLocaleTimeString()}
          </div>
          <span>通報人: {alert.user || 'Unknown'}</span>
        </div>
      </div>
      
      {/* 底部進度條 (倒數關閉動畫) */}
      <div className="h-1 bg-slate-800 w-full">
        <div className="h-full bg-amber-500 w-full animate-[shrink_15s_linear_forwards]"></div>
      </div>
      
      <style>{`
        @keyframes shrink {
          from { width: 100%; }
          to { width: 0%; }
        }
      `}</style>
    </div>
  );
};