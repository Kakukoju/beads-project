import React, { useState, useEffect } from 'react';
import { io } from 'socket.io-client';
import { AlertTriangle, Loader2, Image as ImageIcon, Maximize2, List, CheckSquare, Square, X, Send, ShieldCheck, UserCheck, Edit3 } from 'lucide-react';
import { createPortal } from 'react-dom';

const SOCKET_URL = "http://54.199.19.240";

// === 1. 明細 Modal (嚴格流程版) ===
const AbnormalListModal = ({ onClose, onUpdateStats, onResolveSuccess }: { onClose: () => void, onUpdateStats: (s: any) => void, onResolveSuccess: () => void }) => {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [actionType, setActionType] = useState<'resolve' | 'signoff' | null>(null);
  const [inputValue, setInputValue] = useState(""); 

  const fetchList = async () => {
    try {
      const res = await fetch(`${SOCKET_URL}/api/today_abnormals`);
      const data = await res.json();
      if (data.ok) setItems(data.data);
    } catch (e) { console.error(e); } finally { setLoading(false); }
  };

  useEffect(() => { fetchList(); }, []);

  const handleActionClick = (item: any) => {
    const status = item.status ?? 0; 
    
    if (status === 0) {
      // 階段 1: 填寫處置
      setActiveId(item.id);
      setActionType('resolve');
      setInputValue(""); 
    } else if (status === 1) {
      // 階段 2: 主管簽核
      setActiveId(item.id);
      setActionType('signoff');
      setInputValue(""); 
    }
  };

  const handleSubmit = async (id: number) => {
    if (!inputValue.trim()) return alert("請輸入內容");

    const payload: any = { id, action: actionType };
    if (actionType === 'resolve') {
      payload.note = inputValue;
    } else {
      payload.pin = inputValue;
      payload.signer = "Admin"; 
    }

    try {
      const res = await fetch(`${SOCKET_URL}/api/resolve_abnormal`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      
      if (data.ok) {
        setItems(prev => prev.map(item => {
          if (item.id === id) {
            const updated = { ...item };
            if (actionType === 'resolve') { updated.status = 1; updated.resolution_note = inputValue; updated.is_resolved = 1; }
            if (actionType === 'signoff') { updated.status = 2; updated.signer = 'Admin'; }
            return updated;
          }
          return item;
        }));
        if(data.stats) onUpdateStats(data.stats);
        setActiveId(null);
        onResolveSuccess();
      } else {
        alert("操作失敗: " + data.error);
      }
    } catch (err) {
      console.error(err);
      alert("連線錯誤");
    }
  };

  const formatTimeOnly = (isoString: string) => {
    if (!isoString) return "";
    try {
        const date = new Date(isoString);
        if (isNaN(date.getTime())) return isoString.split(' ')[1] || isoString; 
        const hour = String(date.getHours()).padStart(2, '0');
        const min = String(date.getMinutes()).padStart(2, '0');
        return `${hour}:${min}`;
    } catch { return isoString; }
  };

  return createPortal(
    <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-slate-900 border border-slate-700 rounded-xl shadow-2xl w-full max-w-4xl h-[80vh] flex flex-col animate-in zoom-in-95">
        
        <div className="flex items-center justify-between p-4 border-b border-slate-700 bg-slate-800">
          <h3 className="text-xl font-bold text-white flex items-center gap-2">
            <List className="text-blue-400" /> 本日異常明細表 (審核模式)
          </h3>
          <button onClick={onClose} className="p-2 hover:bg-slate-700 rounded-lg text-slate-400 hover:text-white"><X size={20} /></button>
        </div>

        <div className="flex-1 overflow-auto p-4 bg-slate-900/50">
          {loading ? <div className="flex justify-center py-10"><Loader2 className="animate-spin text-blue-500" /></div> : 
           items.length === 0 ? <div className="text-center py-10 text-slate-500">今日尚無異常紀錄</div> : 
           <div className="space-y-3">
              {items.map(item => {
                const status = item.status ?? 0;
                return (
                  <div key={item.id} className={`flex flex-col p-4 rounded-lg border transition-all ${status === 2 ? 'bg-slate-800/30 border-slate-800 opacity-60' : 'bg-slate-800 border-slate-600'}`}>
                    
                    <div className="flex items-start gap-4">
                      {/* === 狀態按鈕區 === */}
                      <div className="mt-1 shrink-0">
                        {status === 0 && (
                          <button onClick={() => handleActionClick(item)} className="text-blue-400 hover:text-blue-300 bg-blue-900/30 p-2 rounded-lg border border-blue-500/50" title="第一步：填寫異常處置">
                            <Edit3 size={20} />
                          </button>
                        )}
                        {status === 1 && (
                          <button onClick={() => handleActionClick(item)} className="text-amber-500 hover:text-amber-400 p-1 animate-pulse" title="第二步：主管簽核結案">
                            <Square size={28} strokeWidth={2.5} />
                          </button>
                        )}
                        {status === 2 && (
                          <div className="text-green-500 p-1" title="已結案"><CheckSquare size={28} /></div>
                        )}
                      </div>

                      <div className="flex-1 min-w-0">
                        <div className="flex justify-between items-start">
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-lg text-amber-400">{item.station}</span>
                            {item.machine_id && <span className="text-xs bg-slate-700 px-2 py-0.5 rounded text-white border border-slate-600">{item.machine_id}</span>}
                          </div>
                          <span className="text-xs text-slate-500 font-mono">{formatTimeOnly(item.created_at)}</span>
                        </div>
                        
                        <p className="text-base text-slate-200 mt-2 font-medium break-words">
                           <span className="text-slate-500 text-xs mr-2 border border-slate-600 px-1 rounded">描述</span>
                           {item.description}
                        </p>
                        
                        {item.resolution_note && (
                          <div className="mt-3 text-sm text-blue-300 bg-blue-900/20 p-3 rounded border border-blue-500/30 flex items-start gap-2">
                            <span className="bg-blue-600 text-white text-[10px] px-1.5 py-0.5 rounded shrink-0 mt-0.5">已處置</span>
                            <span>{item.resolution_note}</span>
                          </div>
                        )}

                        {item.signer && (
                          <div className="mt-2 text-xs text-green-400 flex items-center gap-1">
                            <UserCheck size={14} /> 最終簽核: {item.signer}
                          </div>
                        )}

                        <div className="flex justify-between items-center mt-3 text-xs text-slate-500 border-t border-slate-700/50 pt-2">
                          <span>通報人: {item.user}</span>
                          {item.photos && <a href={`https://beads-photos-harry.s3.ap-northeast-1.amazonaws.com/abnormal_photo/${item.photos.split(';')[0]}`} target="_blank" rel="noreferrer" className="text-blue-400 flex items-center gap-1 hover:underline"><ImageIcon size={14}/> 查看照片</a>}
                        </div>
                      </div>
                    </div>

                    {activeId === item.id && (
                      <div className="mt-4 pl-0 md:pl-10 animate-in fade-in slide-in-from-top-2">
                        <div className="flex gap-2 items-center bg-slate-950 p-3 rounded border border-blue-500 shadow-lg shadow-blue-500/20">
                          <input 
                            type={actionType === 'signoff' ? "password" : "text"} 
                            autoFocus
                            value={inputValue}
                            onChange={(e) => setInputValue(e.target.value)}
                            placeholder={actionType === 'signoff' ? "確認處置無誤，請輸入 PIN 碼結案" : "請輸入處置說明..."}
                            className="flex-1 px-3 py-2 bg-slate-800 border border-slate-600 rounded text-white focus:outline-none focus:border-blue-500 min-w-0"
                            onKeyDown={(e) => e.key === 'Enter' && handleSubmit(item.id)}
                          />
                          <button onClick={() => handleSubmit(item.id)} className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-500 flex items-center gap-2 whitespace-nowrap">
                            {actionType === 'signoff' ? <ShieldCheck size={16} /> : <Send size={16} />} <span className="hidden md:inline">確定</span>
                          </button>
                          <button onClick={() => setActiveId(null)} className="px-3 py-2 bg-slate-700 text-slate-300 rounded hover:bg-slate-600 whitespace-nowrap">取消</button>
                        </div>
                        {actionType === 'signoff' && <div className="text-xs text-amber-500 mt-1 ml-1">* 此操作將確認異常已排除並結案</div>}
                      </div>
                    )}
                  </div>
                );
              })}
           </div>
          }
        </div>
      </div>
    </div>,
    document.body
  );
};

// === 2. 主卡片組件 (監測 URL 開啟審核) ===
const Card = ({ children, className = "", title }: any) => (
  <div className={`bg-slate-800/50 backdrop-blur-md border border-slate-700/50 rounded-xl p-5 shadow-lg relative overflow-hidden ${className}`}>
    <div className="absolute -top-10 -right-10 w-32 h-32 bg-blue-500/10 rounded-full blur-3xl pointer-events-none"></div>
    {title && <h3 className="text-slate-300 text-lg font-medium mb-4 flex items-center gap-2">{title}</h3>}
    {children}
  </div>
);

export const AbnormalMonitorCard = () => {
  const [isConnected, setIsConnected] = useState(false);
  const [stats, setStats] = useState({ day: 0, week: 0, month: 0 });
  const [showModal, setShowModal] = useState(false); 
  
  const [alertInfo, setAlertInfo] = useState({
    hasAlert: false,
    title: "系統監控正常",
    message: "目前產線無異常回報",
    station: "",
    time: "",
    photoUrl: "",
    chartData: [20, 20, 20, 20, 20]
  });

  const formatDateTime = (isoString: string) => {
    if (!isoString) return "";
    try {
      const date = new Date(isoString);
      if (isNaN(date.getTime())) return isoString;
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, '0');
      const day = String(date.getDate()).padStart(2, '0');
      const hour = String(date.getHours()).padStart(2, '0');
      const min = String(date.getMinutes()).padStart(2, '0');
      return `${year}-${month}-${day} ${hour}:${min}`;
    } catch (e) { return isoString; }
  };

  const S3_BASE = "https://beads-photos-harry.s3.ap-northeast-1.amazonaws.com";

  const updateAlertUI = (data: any, newStats: any) => {
    if(newStats) setStats(newStats);
    if (!data) {
      setAlertInfo({
        hasAlert: false,
        title: "系統監控正常",
        message: "目前產線無異常回報",
        station: "", time: "", photoUrl: "",
        chartData: [20, 20, 20, 20, 20]
      });
      return;
    }

    let photoUrl = "";
    if (data.photos && data.photos.trim() !== "") {
      const firstPhoto = data.photos.split(';')[0];
      if (firstPhoto) photoUrl = `${S3_BASE}/abnormal_photo/${firstPhoto}`;
    }

    const displayTime = formatDateTime(data.created_at);

    setAlertInfo({
      hasAlert: true,
      title: `${data.station} ${data.machine_id || ''} 異常`, 
      message: data.description,
      station: data.station,
      time: displayTime,
      photoUrl: photoUrl,
      chartData: [40, 80, 60, 90, 30]
    });
  };

  const fetchLatestStatus = async () => {
    try {
      const res = await fetch(`${SOCKET_URL}/api/latest_abnormal`);
      const data = await res.json();
      if (data.ok) updateAlertUI(data.abnormal, data.stats);
    } catch (err) { console.error("API Error:", err); }
  };

  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('view') === 'audit') {
      setShowModal(true);
    }

    fetchLatestStatus();

    const socket = io(SOCKET_URL, {
      transports: ['polling', 'websocket'],
      reconnection: true,
    });

    socket.on('connect', () => setIsConnected(true));
    socket.on('disconnect', () => setIsConnected(false));
    socket.on('new_abnormal', (data: any) => updateAlertUI(data, data.stats));
    socket.on('latest_abnormal', (data: any) => updateAlertUI(data.abnormal, data.stats));
    socket.on('count_update', (data: any) => setStats(data.stats));

    // 30 秒 polling 保底，socket 不穩定時也能自動同步
    const poll = setInterval(fetchLatestStatus, 30000);

    return () => { socket.disconnect(); clearInterval(poll); };
  }, []);

  return (
    <>
      <Card 
        title={
          <div className="flex justify-between items-center w-full pr-2">
            <span>即時監控</span>
            <div className="flex items-center gap-2">
              <button 
                onClick={() => setShowModal(true)}
                className="flex items-center gap-2 bg-slate-900/80 px-2 py-1 rounded-lg border border-slate-600 hover:bg-slate-700 transition-all cursor-pointer group"
              >
                <div className="flex flex-col items-end leading-none">
                  <span className="text-[10px] text-slate-400">日/周/月</span>
                  <div className="text-xs font-bold text-slate-200">
                    <span className="text-red-400">{stats.day}</span> / {stats.week} / {stats.month}
                  </div>
                </div>
                <List size={16} className="text-slate-500 group-hover:text-blue-400" />
              </button>
              <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`}></div>
            </div>
          </div>
        } 
        className={`md:col-span-2 h-48 border-t-4 transition-all duration-500 ${alertInfo.hasAlert ? 'border-t-red-500 bg-red-900/10' : 'border-t-green-500'}`}
      >
        <div className="flex items-center gap-6 h-full">
          <div className="flex-1">
            <div className="flex items-start gap-3 mb-2">
              {alertInfo.hasAlert ? <AlertTriangle className="text-red-500 shrink-0 animate-pulse" size={32} /> : <div className="p-2 bg-green-500/20 rounded-full"><Loader2 className="text-green-500 animate-spin-slow" size={24} /></div>}
              <div className="w-full">
                <h4 className={`text-xl font-bold ${alertInfo.hasAlert ? 'text-red-400' : 'text-slate-200'}`}>{alertInfo.title}</h4>
                <p className="text-slate-400 text-sm mt-2 leading-relaxed line-clamp-2">{alertInfo.message.split(' (附')[0]}</p>
                {alertInfo.hasAlert && (
                  <div className="mt-2 text-xs text-slate-500 font-mono flex items-center gap-2">
                    <span>通報時間: {alertInfo.time}</span>
                    {alertInfo.photoUrl && <span className="flex items-center text-blue-400"><ImageIcon size={12} className="mr-1"/>有附圖</span>}
                  </div>
                )}
              </div>
            </div>
          </div>
          <div className="h-28 w-48 flex-shrink-0 flex items-end justify-center pb-1">
            {alertInfo.hasAlert && alertInfo.photoUrl ? (
              <div className="relative w-full h-full group">
                <div className="w-full h-full rounded-lg overflow-hidden border-2 border-slate-600/50 shadow-lg bg-black">
                  <img src={alertInfo.photoUrl} alt="異常照片" className="w-full h-full object-cover opacity-90 group-hover:opacity-100 transition-opacity duration-300" />
                </div>
                <a href={alertInfo.photoUrl} target="_blank" rel="noreferrer" className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity duration-200 rounded-lg cursor-pointer"><Maximize2 className="text-white drop-shadow-md" size={24} /></a>
              </div>
            ) : (
              <div className="flex items-end gap-2 w-full h-full opacity-80">
                {alertInfo.chartData.map((h, i) => (<div key={i} className="flex-1 bg-slate-700/50 rounded-t-sm relative group"><div className={`absolute bottom-0 w-full rounded-t-sm transition-all duration-500 ${alertInfo.hasAlert ? 'bg-red-500' : 'bg-green-500'}`} style={{ height: `${h}%` }}></div></div>))}
              </div>
            )}
          </div>
        </div>
      </Card>
      {showModal && <AbnormalListModal onClose={() => setShowModal(false)} onUpdateStats={setStats} onResolveSuccess={fetchLatestStatus} />}
    </>
  );
};