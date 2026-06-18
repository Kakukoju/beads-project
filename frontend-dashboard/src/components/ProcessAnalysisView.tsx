import { useState, useEffect, useRef } from "react";
import {
  Microscope, Search, Loader2, AlertTriangle,
  History, Clock, FlaskConical
} from "lucide-react";
import {
  BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer
} from "recharts";

const API = "";

interface AnalysisResult {
  ok: boolean;
  summary: any;
  analysis: any;
  ai_summary: string;
  history_id: number | null;
  work_orders: any[];
  ipqc: any[];
  droplet_records: any[];
  formulations: any[];
}

interface HistoryItem {
  id: number;
  created_at: string;
  marker: string;
  work_order: string;
  date_from: string;
  date_to: string;
  user_question: string;
  analysis_result: string;
  ai_summary: string;
}

export default function ProcessAnalysisView() {
  const [markers, setMarkers] = useState<string[]>([]);
  const [marker, setMarker] = useState("");
  const [workOrder, setWorkOrder] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState("");
  const [activeSection, setActiveSection] = useState<string>("ai-summary");
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    fetch(`${API}/api/process-analysis/marker-list`)
      .then(r => r.json())
      .then(d => { if (d.ok) setMarkers(d.markers); })
      .catch(() => {});
  }, []);

  const runAnalysis = async () => {
    if (!marker) { setError("請選擇 Marker"); return; }
    setLoading(true); setError(""); setResult(null);
    try {
      const res = await fetch(`${API}/api/process-analysis/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ marker, work_order: workOrder, date_from: dateFrom, date_to: dateTo, user_question: question }),
      });
      const data = await res.json();
      if (data.ok) setResult(data);
      else setError(data.error || "分析失敗");
    } catch (e: any) { setError(e.message || "連線錯誤"); }
    finally { setLoading(false); }
  };

  const loadHistory = async () => {
    try {
      const res = await fetch(`${API}/api/process-analysis/history?limit=20`);
      const data = await res.json();
      if (data.ok) setHistory(data.history);
    } catch {}
  };

  const toggleHistory = () => {
    if (!showHistory) loadHistory();
    setShowHistory(!showHistory);
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      {/* 輸入區 */}
      <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6">
        <h3 className="text-xl font-semibold text-slate-200 mb-4 flex items-center gap-2">
          <Microscope className="text-blue-400" size={24} />
          製程差異分析
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Marker (Bead)</label>
            <select value={marker} onChange={e => setMarker(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-slate-700 text-white border border-slate-600 focus:ring-2 focus:ring-blue-500">
              <option value="">-- 選擇 Marker --</option>
              {markers.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">工單號碼 (選填)</label>
            <input type="text" value={workOrder} onChange={e => setWorkOrder(e.target.value)}
              placeholder="如 TMRA26C214" className="w-full px-3 py-2 rounded-lg bg-slate-700 text-white border border-slate-600" />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">起始日期</label>
            <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-slate-700 text-white border border-slate-600" />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">結束日期</label>
            <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-slate-700 text-white border border-slate-600" />
          </div>
        </div>

        <div className="mb-4">
          <label className="block text-sm font-medium text-slate-300 mb-1">問題描述 (選填，會存入分析歷史)</label>
          <textarea value={question} onChange={e => setQuestion(e.target.value)} rows={2}
            placeholder="例如：最近 ALP-U 的 CV 偏高，想了解是否跟凍乾機或人員有關"
            className="w-full px-3 py-2 rounded-lg bg-slate-700 text-white border border-slate-600 resize-none" />
        </div>

        <div className="flex gap-3">
          <button onClick={runAnalysis} disabled={loading}
            className="px-6 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition disabled:bg-slate-600 flex items-center gap-2 font-medium">
            {loading ? <><Loader2 size={16} className="animate-spin" />分析中...</> : <><Search size={16} />執行分析</>}
          </button>
          <button onClick={toggleHistory}
            className="px-4 py-2.5 bg-slate-700 text-slate-300 rounded-lg hover:bg-slate-600 transition flex items-center gap-2">
            <History size={16} />{showHistory ? "隱藏歷史" : "分析歷史"}
          </button>
        </div>

        {error && <div className="mt-3 p-3 bg-red-900/30 border border-red-500/50 rounded-lg text-red-400 text-sm">⚠️ {error}</div>}
      </div>

      {/* 歷史記錄 */}
      {showHistory && (
        <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6">
          <h4 className="text-lg font-semibold text-slate-200 mb-3 flex items-center gap-2"><History size={20} />分析歷史</h4>
          {history.length === 0 ? <p className="text-slate-400">尚無歷史記錄</p> : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-slate-700/50">
                  <tr>
                    <th className="px-3 py-2 text-left text-slate-300">時間</th>
                    <th className="px-3 py-2 text-left text-slate-300">Marker</th>
                    <th className="px-3 py-2 text-left text-slate-300">工單</th>
                    <th className="px-3 py-2 text-left text-slate-300">問題</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700">
                  {history.map(h => (
                    <tr key={h.id} className="hover:bg-slate-700/30 cursor-pointer"
                      onClick={() => { setMarker(h.marker); setWorkOrder(h.work_order || ""); setDateFrom(h.date_from || ""); setDateTo(h.date_to || ""); setQuestion(h.user_question || ""); }}>
                      <td className="px-3 py-2 text-slate-400 whitespace-nowrap">{h.created_at}</td>
                      <td className="px-3 py-2 text-blue-300 font-medium">{h.marker}</td>
                      <td className="px-3 py-2 text-slate-300">{h.work_order || "-"}</td>
                      <td className="px-3 py-2 text-slate-400 truncate max-w-xs">{h.user_question || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* 分析結果 */}
      {result && (
        <>
          {/* Summary Cards */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            {[
              { label: "工單數", value: result.summary.total_work_orders, color: "text-blue-400" },
              { label: "IPQC 記錄", value: result.summary.total_ipqc_records, color: "text-green-400" },
              { label: "滴定紀錄", value: result.summary.total_droplet_records, color: "text-purple-400" },
              { label: "配藥紀錄", value: result.summary.total_formulation_records, color: "text-amber-400" },
              { label: "異常批次", value: result.summary.anomaly_batches ?? "-", color: "text-red-400" },
            ].map(c => (
              <div key={c.label} className="bg-slate-800/50 border border-slate-700 rounded-xl p-4">
                <div className="text-slate-400 text-sm">{c.label}</div>
                <div className={`text-3xl font-bold ${c.color} mt-1`}>{c.value}</div>
              </div>
            ))}
            {result.summary.main_ingredient && (
              <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4">
                <div className="text-slate-400 text-sm">主成分</div>
                <div className="text-base font-bold text-teal-400 mt-1 truncate">{result.summary.main_ingredient}</div>
              </div>
            )}
          </div>

          {/* Tab Navigation */}
          <div className="flex gap-1 border-b border-slate-700 flex-wrap">
            {[
              { id: "ai-summary", label: "🤖 AI 分析報告" },
              { id: "overview", label: "差異總覽" },
              { id: "anomaly", label: "異常批次" },
              { id: "process-time", label: "⏱️ 製程時間" },
              { id: "formulation", label: "🧪 配藥分析" },
              { id: "detail", label: "原始資料" },
            ].map(tab => (
              <button key={tab.id} onClick={() => setActiveSection(tab.id)}
                className={`px-4 py-2.5 text-sm font-medium transition border-b-2 ${activeSection === tab.id
                  ? "text-blue-400 border-blue-500 bg-slate-800/30" : "text-slate-400 border-transparent hover:text-slate-200"}`}>
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab Content */}
          {activeSection === "ai-summary" && <AISummarySection aiSummary={result.ai_summary} marker={marker} historyId={result.history_id} />}
          {activeSection === "overview" && <OverviewSection analysis={result.analysis} />}
          {activeSection === "anomaly" && <AnomalySection analysis={result.analysis} />}
          {activeSection === "process-time" && <ProcessTimeSection analysis={result.analysis} />}
          {activeSection === "formulation" && <FormulationSection analysis={result.analysis} />}
          {activeSection === "detail" && <DetailSection result={result} />}
        </>
      )}
    </div>
  );
}

// ── AI Summary Section ──

function AISummarySection({ aiSummary, marker, historyId }: { aiSummary: string; marker: string; historyId?: number | null }) {
  const boldify = (s: string) => s.replace(/\*\*(.+?)\*\*/g, '<strong class="text-white">$1</strong>');

  const renderMarkdown = (text: string) => {
    return text.split("\n").map((line, i) => {
      if (line.startsWith("# "))
        return <h1 key={i} className="text-2xl font-bold text-white mt-6 mb-3">{line.slice(2)}</h1>;
      if (line.startsWith("## "))
        return <h2 key={i} className="text-lg font-semibold text-slate-200 mt-5 mb-2 pb-1 border-b border-slate-700">{line.slice(3)}</h2>;
      if (line.startsWith("  - "))
        return <div key={i} className="ml-6 py-0.5 text-slate-300 flex items-start gap-1"><span className="text-slate-500 mt-1">•</span><span dangerouslySetInnerHTML={{ __html: boldify(line.slice(4)) }} /></div>;
      if (line.startsWith("- "))
        return <div key={i} className="ml-3 py-0.5 text-slate-300 flex items-start gap-1"><span className="text-slate-500 mt-1">•</span><span dangerouslySetInnerHTML={{ __html: boldify(line.slice(2)) }} /></div>;
      if (/^\d+\.\s/.test(line))
        return <div key={i} className="ml-3 py-1 text-slate-200" dangerouslySetInnerHTML={{ __html: boldify(line) }} />;
      if (line.startsWith("❗") || line.startsWith("⚠"))
        return <div key={i} className="py-1 px-3 my-1 bg-amber-900/20 border-l-2 border-amber-500 text-amber-200 rounded-r" dangerouslySetInnerHTML={{ __html: boldify(line) }} />;
      if (line.startsWith("✅"))
        return <div key={i} className="py-1 px-3 my-1 bg-green-900/20 border-l-2 border-green-500 text-green-200 rounded-r" dangerouslySetInnerHTML={{ __html: boldify(line) }} />;
      if (line.trim() === "") return <div key={i} className="h-2" />;
      return <p key={i} className="text-slate-300 py-0.5" dangerouslySetInnerHTML={{ __html: boldify(line) }} />;
    });
  };

  const handlePrint = () => {
    const w = window.open("", "_blank");
    if (!w) return;
    w.document.write(`<html><head><title>${marker} 製程分析報告</title>
      <style>body{font-family:sans-serif;max-width:800px;margin:40px auto;padding:0 20px;color:#222;line-height:1.6}
      h1{font-size:22px;border-bottom:2px solid #333;padding-bottom:8px}
      h2{font-size:16px;margin-top:24px;color:#444;border-bottom:1px solid #ddd;padding-bottom:4px}
      strong{color:#000} pre{white-space:pre-wrap}</style></head>
      <body><pre>${aiSummary}</pre></body></html>`);
    w.document.close();
    w.print();
  };

  const [qaList, setQaList] = useState<{ q: string; a: string }[]>([]);
  const [askInput, setAskInput] = useState("");
  const [askLoading, setAskLoading] = useState(false);
  const qaEndRef = useRef<HTMLDivElement>(null);

  const handleAsk = async () => {
    const q = askInput.trim();
    if (!q || askLoading) return;
    setAskLoading(true);
    setAskInput("");
    try {
      const res = await fetch(`${API}/api/process-analysis/ask-ai`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, ai_summary: aiSummary, marker, history_id: historyId }),
      });
      const data = await res.json();
      setQaList(prev => [...prev, { q, a: data.ok ? data.answer : `⚠️ ${data.error || "回覆失敗"}` }]);
    } catch (e: any) {
      setQaList(prev => [...prev, { q, a: `⚠️ 連線錯誤: ${e.message}` }]);
    } finally {
      setAskLoading(false);
      setTimeout(() => qaEndRef.current?.scrollIntoView({ behavior: "smooth" }), 100);
    }
  };

  return (
    <div className="space-y-4">
      <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h4 className="text-lg font-semibold text-slate-200 flex items-center gap-2">🤖 AI 製程分析報告</h4>
          <button onClick={handlePrint}
            className="px-3 py-1.5 bg-slate-700 text-slate-300 rounded-lg hover:bg-slate-600 transition text-sm flex items-center gap-1">
            🖨️ 列印報告
          </button>
        </div>
        <div className="max-w-none">{renderMarkdown(aiSummary)}</div>
      </div>

      {/* Ask Amazon Q Chat Box */}
      <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6">
        <h4 className="text-lg font-semibold text-slate-200 mb-4 flex items-center gap-2">
          <span className="inline-flex items-center justify-center w-7 h-7 rounded-lg bg-gradient-to-br from-blue-500 to-cyan-400 text-white text-xs font-bold">Q</span>
          追問 Amazon Q
        </h4>

        {/* QA History */}
        {qaList.length > 0 && (
          <div className="space-y-4 mb-4 max-h-[500px] overflow-y-auto pr-1">
            {qaList.map((item, i) => (
              <div key={i} className="space-y-2">
                <div className="flex justify-end">
                  <div className="bg-blue-600/30 border border-blue-500/30 rounded-xl px-4 py-2.5 max-w-[80%] text-sm text-blue-100">
                    {item.q}
                  </div>
                </div>
                <div className="flex justify-start">
                  <div className="bg-slate-700/50 border border-slate-600/50 rounded-xl px-4 py-3 max-w-[90%]">
                    <div className="max-w-none text-sm">{renderMarkdown(item.a)}</div>
                  </div>
                </div>
              </div>
            ))}
            <div ref={qaEndRef} />
          </div>
        )}

        {/* Input Area */}
        <div className="flex gap-2">
          <input
            type="text"
            value={askInput}
            onChange={e => setAskInput(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && !e.nativeEvent.isComposing) handleAsk(); }}
            placeholder={`針對 ${marker} 的分析結果提問，例如：CV 偏高的根因是什麼？異常批次的配藥紀錄有何差異？`}
            disabled={askLoading}
            className="flex-1 px-4 py-2.5 rounded-lg bg-slate-700 text-white border border-slate-600 focus:ring-2 focus:ring-blue-500 focus:border-transparent placeholder-slate-400 text-sm disabled:opacity-50"
          />
          <button
            onClick={handleAsk}
            disabled={askLoading || !askInput.trim()}
            className="px-5 py-2.5 bg-gradient-to-r from-blue-600 to-cyan-600 text-white rounded-lg hover:from-blue-700 hover:to-cyan-700 transition disabled:opacity-40 flex items-center gap-2 text-sm font-medium whitespace-nowrap"
          >
            {askLoading ? <><Loader2 size={14} className="animate-spin" />思考中...</> : <>發送</>}
          </button>
        </div>
        <p className="text-xs text-slate-500 mt-2">💡 Powered by Amazon Bedrock Claude — 可針對上方分析報告的任何建議深入追問</p>
      </div>
    </div>
  );
}

// ── Overview Section ──

function OverviewSection({ analysis }: { analysis: any }) {
  const varRank = analysis.variation_ranking || [];
  const numStats = analysis.numeric || {};

  return (
    <div className="space-y-6">
      <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6">
        <h4 className="text-lg font-semibold text-slate-200 mb-4">📊 參數變異排名 (CV%)</h4>
        {varRank.length > 0 ? (
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={varRank} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis type="number" tick={{ fill: "#94a3b8", fontSize: 12 }} />
                <YAxis dataKey="parameter" type="category" width={100} tick={{ fill: "#94a3b8", fontSize: 12 }} />
                <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #475569", borderRadius: 8 }} />
                <Bar dataKey="cv_percent" name="CV%">
                  {varRank.map((_: any, i: number) => (
                    <Cell key={i} fill={varRank[i].cv_percent > 30 ? "#ef4444" : varRank[i].cv_percent > 20 ? "#f59e0b" : "#10b981"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : <p className="text-slate-400">無數值型差異資料</p>}
      </div>

      {Object.keys(numStats).length > 0 && (
        <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6">
          <h4 className="text-lg font-semibold text-slate-200 mb-4">📈 數值型統計</h4>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-700/50">
                <tr>
                  {["參數", "筆數", "Min", "Max", "Range", "Mean", "Std", "CV%"].map(h => (
                    <th key={h} className="px-3 py-2 text-left text-slate-300 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {Object.entries(numStats).map(([k, v]: [string, any]) => (
                  <tr key={k} className="hover:bg-slate-700/30">
                    <td className="px-3 py-2 text-blue-300 font-medium">{k}</td>
                    <td className="px-3 py-2 text-slate-300">{v.count}</td>
                    <td className="px-3 py-2 text-slate-300">{v.min}</td>
                    <td className="px-3 py-2 text-slate-300">{v.max}</td>
                    <td className="px-3 py-2 text-slate-300">{v.range}</td>
                    <td className="px-3 py-2 text-slate-300">{v.mean}</td>
                    <td className="px-3 py-2 text-slate-300">{v.std}</td>
                    <td className={`px-3 py-2 font-bold ${(v.cv_percent || 0) > 30 ? "text-red-400" : (v.cv_percent || 0) > 20 ? "text-amber-400" : "text-green-400"}`}>
                      {v.cv_percent ?? "-"}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Anomaly Section ──

function AnomalySection({ analysis }: { analysis: any }) {
  const ranking = analysis.anomaly_ranking || [];
  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6">
      <h4 className="text-lg font-semibold text-slate-200 mb-4 flex items-center gap-2">
        <AlertTriangle className="text-amber-400" size={20} />
        異常批次排名 (Top 20)
      </h4>
      {ranking.length === 0 ? <p className="text-slate-400">無異常批次</p> : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-700/50">
              <tr>
                {["#", "工單號碼", "批號", "最終判定", "異常旗標", "L1ODCV", "L2ODCV", "異常分數"].map(h => (
                  <th key={h} className="px-3 py-2 text-left text-slate-300 font-medium whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700">
              {ranking.map((r: any, i: number) => {
                const isAccept = (r["最終判定"] || "").toUpperCase() === "ACCEPT";
                const flags = Object.entries(r.anomaly_flags || {}) as [string, string][];
                return (
                  <tr key={i} className={`hover:bg-slate-700/30 ${r.anomaly_score >= 10 ? "bg-red-900/10" : ""}`}>
                    <td className="px-3 py-2 text-slate-500">{i + 1}</td>
                    <td className="px-3 py-2 text-blue-300 font-mono">{r["工單號碼"] || "-"}</td>
                    <td className="px-3 py-2 text-slate-300 font-mono">{r["批號"] || "-"}</td>
                    <td className="px-3 py-2">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${isAccept ? "bg-green-900/50 text-green-300" : "bg-red-900/50 text-red-300"}`}>
                        {r["最終判定"] || "-"}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      {flags.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {flags.map(([k, v]) => (
                            <span key={k} className="px-1.5 py-0.5 bg-amber-900/40 text-amber-300 rounded text-xs whitespace-nowrap">{k}{v !== "1" ? `=${v}` : ""}</span>
                          ))}
                        </div>
                      ) : <span className="text-slate-600">-</span>}
                    </td>
                    <td className="px-3 py-2 text-slate-300">{r.L1ODCV != null ? Number(r.L1ODCV).toFixed(4) : "-"}</td>
                    <td className="px-3 py-2 text-slate-300">{r.L2ODCV != null ? Number(r.L2ODCV).toFixed(4) : "-"}</td>
                    <td className={`px-3 py-2 font-bold ${r.anomaly_score >= 10 ? "text-red-400" : r.anomaly_score >= 5 ? "text-amber-400" : "text-green-400"}`}>
                      {r.anomaly_score}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <div className="mt-4 p-3 bg-blue-900/20 border border-blue-500/30 rounded-lg text-sm text-blue-300">
        <strong>評分邏輯：</strong>最終判定非 Accept +10 分；外觀不良/CVNG/訊號異常/凍乾異常/配置異常/分藥異常各 +5 分；各 CV 值超過 2σ 加上 Z-score。
      </div>
    </div>
  );
}

// ── Process Time Section ──

function ProcessTimeSection({ analysis }: { analysis: any }) {
  const pt = analysis.process_time || {};
  const records = pt.records || [];
  const correlations = pt.correlations || {};

  const rColor = (r: number) => Math.abs(r) >= 0.7 ? "text-red-400" : Math.abs(r) >= 0.5 ? "text-amber-400" : "text-slate-400";

  return (
    <div className="space-y-6">
      {/* Time Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          { key: "titration_hours", label: "滴定時間 (hr)", color: "text-blue-400" },
          { key: "titration_hours_per_1k", label: "滴定時間/千顆 (hr)", color: "text-purple-400" },
          { key: "lyophilization_hours", label: "凍乾時間 (hr)", color: "text-teal-400" },
        ].map(({ key, label, color }) => {
          const s = pt[key];
          return (
            <div key={key} className="bg-slate-800/50 border border-slate-700 rounded-xl p-5">
              <div className="flex items-center gap-2 mb-3">
                <Clock size={16} className={color} />
                <span className="text-slate-200 font-medium text-sm">{label}</span>
              </div>
              {s ? (
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div className="text-slate-400">筆數</div><div className={`${color} font-bold`}>{s.count}</div>
                  <div className="text-slate-400">平均</div><div className="text-white font-bold">{s.mean}</div>
                  <div className="text-slate-400">最小</div><div className="text-slate-300">{s.min}</div>
                  <div className="text-slate-400">最大</div><div className="text-slate-300">{s.max}</div>
                </div>
              ) : <p className="text-slate-500 text-sm">無資料</p>}
            </div>
          );
        })}
      </div>

      {/* Pearson Correlations */}
      {Object.keys(correlations).length > 0 && (
        <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6">
          <h4 className="text-lg font-semibold text-slate-200 mb-4">📐 製程時間 vs 品質指標 Pearson 相關係數</h4>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-700/50">
                <tr>
                  <th className="px-3 py-2 text-left text-slate-300">時間指標</th>
                  {["L1ODCV","L2ODCV","L1ConcCV","L2ConcCV","L1_OD","L2_OD"].map(h => (
                    <th key={h} className="px-3 py-2 text-center text-slate-300">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {Object.entries(correlations).map(([label, metrics]: [string, any]) => (
                  <tr key={label} className="hover:bg-slate-700/30">
                    <td className="px-3 py-2 text-blue-300 font-medium">{label}</td>
                    {["L1ODCV","L2ODCV","L1ConcCV","L2ConcCV","L1_OD","L2_OD"].map(col => {
                      const p = metrics[col];
                      return (
                        <td key={col} className="px-3 py-2 text-center">
                          {p ? (
                            <span className={`font-mono font-bold ${rColor(p.r)}`} title={`n=${p.n}`}>
                              {p.r > 0 ? "+" : ""}{p.r}
                            </span>
                          ) : <span className="text-slate-700">—</span>}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-slate-500 mt-2">🔴 |r|≥0.7 強相關 &nbsp; 🟡 |r|≥0.5 中等相關 &nbsp; 需 n≥3 才計算</p>
        </div>
      )}

      {/* Per-WO time records */}
      {records.length > 0 && (
        <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6">
          <h4 className="text-lg font-semibold text-slate-200 mb-4">📋 各工單製程時間明細</h4>
          <div className="overflow-x-auto max-h-80">
            <table className="w-full text-xs">
              <thead className="bg-slate-700/50 sticky top-0">
                <tr>
                  {["工單號","製令數量","滴定時間(hr)","滴定/千顆(hr)","凍乾時間(hr)","L1ODCV","L2ODCV","L1ConcCV","L2ConcCV"].map(h => (
                    <th key={h} className="px-2 py-1.5 text-left text-slate-300 whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/50">
                {records.map((r: any, i: number) => (
                  <tr key={i} className="hover:bg-slate-700/20">
                    <td className="px-2 py-1 text-blue-300 font-mono">{r["工單號"] || "-"}</td>
                    <td className="px-2 py-1 text-slate-300">{r["製令數量"] ?? "-"}</td>
                    <td className="px-2 py-1 text-slate-300">{r["滴定時間hrs"] ?? "-"}</td>
                    <td className="px-2 py-1 text-slate-300">{r["滴定時間_每千顆"] ?? "-"}</td>
                    <td className="px-2 py-1 text-slate-300">{r["凍乾時間hrs"] ?? "-"}</td>
                    <td className="px-2 py-1 text-slate-400">{r["L1ODCV"] ?? "-"}</td>
                    <td className="px-2 py-1 text-slate-400">{r["L2ODCV"] ?? "-"}</td>
                    <td className="px-2 py-1 text-slate-400">{r["L1ConcCV"] ?? "-"}</td>
                    <td className="px-2 py-1 text-slate-400">{r["L2ConcCV"] ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!pt.titration_hours && !pt.lyophilization_hours && records.length === 0 && (
        <p className="text-slate-400">工單缺少時間欄位（時間_滴定開始/結束、時間_凍乾開始/結束），無法計算製程時間。</p>
      )}
    </div>
  );
}

// ── Formulation Analysis Section ──

function FormulationSection({ analysis }: { analysis: any }) {
  const fa = analysis.formulation_analysis || {};
  const summary = fa.ingredient_summary || {};
  const varByIngred = fa.variation_by_ingredient || [];
  const batchComp = fa.batch_composition || {};

  const chartData = varByIngred.slice(0, 15).map((x: any) => ({ name: x["化學品名"], cv: x["cv_percent"] }));

  return (
    <div className="space-y-6">
      {/* CV Chart */}
      {chartData.length > 0 && (
        <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6">
          <h4 className="text-lg font-semibold text-slate-200 mb-4 flex items-center gap-2">
            <FlaskConical size={18} className="text-teal-400" />
            配藥成分重量變異 (CV%)
          </h4>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis type="number" tick={{ fill: "#94a3b8", fontSize: 12 }} />
                <YAxis dataKey="name" type="category" width={140} tick={{ fill: "#94a3b8", fontSize: 11 }} />
                <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #475569", borderRadius: 8 }} />
                <Bar dataKey="cv" name="CV%">
                  {chartData.map((_: any, i: number) => (
                    <Cell key={i} fill={chartData[i].cv > 10 ? "#ef4444" : chartData[i].cv > 5 ? "#f59e0b" : "#10b981"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Ingredient Summary Table */}
      {Object.keys(summary).length > 0 && (
        <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6">
          <h4 className="text-lg font-semibold text-slate-200 mb-4">🧪 成分統計摘要</h4>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-700/50">
                <tr>
                  {["化學品名", "批次數", "平均重量(g)", "Std", "CV%", "平均佔比%"].map(h => (
                    <th key={h} className="px-3 py-2 text-left text-slate-300 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {Object.entries(summary)
                  .sort((a: any, b: any) => (b[1].weight_pct_mean || 0) - (a[1].weight_pct_mean || 0))
                  .map(([chem, v]: [string, any]) => (
                    <tr key={chem} className="hover:bg-slate-700/30">
                      <td className="px-3 py-2 text-teal-300 font-medium">{chem}</td>
                      <td className="px-3 py-2 text-slate-300">{v.count}</td>
                      <td className="px-3 py-2 text-slate-300">{v.mean_weight}</td>
                      <td className="px-3 py-2 text-slate-300">{v.std_weight}</td>
                      <td className={`px-3 py-2 font-bold ${(v.cv_percent || 0) > 10 ? "text-red-400" : (v.cv_percent || 0) > 5 ? "text-amber-400" : "text-green-400"}`}>
                        {v.cv_percent ?? "-"}%
                      </td>
                      <td className="px-3 py-2 text-slate-300">{v.weight_pct_mean ?? "-"}%</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Batch Composition */}
      {Object.keys(batchComp).length > 0 && (
        <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6">
          <h4 className="text-lg font-semibold text-slate-200 mb-4">📋 各工單配藥組成</h4>
          <div className="overflow-x-auto max-h-80">
            <table className="w-full text-xs">
              <thead className="bg-slate-700/50 sticky top-0">
                <tr>
                  {["工單號碼", "化學品名", "重量(g)", "佔比%"].map(h => (
                    <th key={h} className="px-2 py-1.5 text-left text-slate-300">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/50">
                {Object.entries(batchComp).flatMap(([wo, items]: [string, any]) =>
                  (items as any[]).map((item, j) => (
                    <tr key={`${wo}-${j}`} className="hover:bg-slate-700/20">
                      <td className="px-2 py-1 text-blue-300 font-mono">{j === 0 ? wo : ""}</td>
                      <td className="px-2 py-1 text-teal-300">{item["化學品名"]}</td>
                      <td className="px-2 py-1 text-slate-300">{item["重量"]}</td>
                      <td className="px-2 py-1 text-slate-400">{item["佔比%"] ?? "-"}%</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {Object.keys(summary).length === 0 && (
        <p className="text-slate-400">無配藥紀錄或配藥表不含重量欄位。</p>
      )}
    </div>
  );
}

// ── Detail Section ──

function DetailSection({ result }: { result: AnalysisResult }) {
  const [tab, setTab] = useState<"wo" | "ipqc" | "droplet" | "formulation">("wo");
  const dataMap: Record<string, any[]> = {
    wo: result.work_orders, ipqc: result.ipqc,
    droplet: result.droplet_records, formulation: result.formulations,
  };
  const rows = dataMap[tab] || [];
  const cols = rows.length > 0 ? Object.keys(rows[0]).filter(k => !k.startsWith("_") && !k.includes("照片")) : [];

  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6">
      <div className="flex gap-2 mb-4">
        {([
          ["wo", `工單 (${result.work_orders.length})`],
          ["ipqc", `IPQC (${result.ipqc.length})`],
          ["droplet", `滴定 (${result.droplet_records.length})`],
          ["formulation", `配藥 (${result.formulations.length})`],
        ] as [string, string][]).map(([id, label]) => (
          <button key={id} onClick={() => setTab(id as any)}
            className={`px-3 py-1.5 rounded text-sm transition ${tab === id ? "bg-blue-600 text-white" : "bg-slate-700 text-slate-300 hover:bg-slate-600"}`}>
            {label}
          </button>
        ))}
      </div>
      {rows.length === 0 ? <p className="text-slate-400">無資料</p> : (
        <div className="overflow-x-auto max-h-96">
          <table className="w-full text-xs">
            <thead className="bg-slate-700/50 sticky top-0">
              <tr>{cols.map(c => <th key={c} className="px-2 py-1.5 text-left text-slate-300 whitespace-nowrap">{c}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-slate-700/50">
              {rows.map((r, i) => (
                <tr key={i} className="hover:bg-slate-700/20">
                  {cols.map(c => <td key={c} className="px-2 py-1 text-slate-400 whitespace-nowrap max-w-[200px] truncate">{r[c] ?? ""}</td>)}
                </tr>
              ))}
            </tbody>
          </table>

        </div>
      )}
    </div>
  );
}
