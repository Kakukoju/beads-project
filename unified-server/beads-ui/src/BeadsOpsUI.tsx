import React, { useMemo, useState, useCallback, useEffect, useRef } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectTrigger, SelectContent, SelectValue, SelectItem } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";
import { motion } from "framer-motion";
import { 
  Loader2, Play, Undo2, FileOutput, Settings, Calendar, 
  TerminalSquare, FolderOpen, AlertCircle, Database, 
  FileSpreadsheet, List, HardDrive, Upload, Save 
} from "lucide-react";

// === Constants Configuration ===
const DEFAULT_OUTDIR = String.raw`\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\beadsSchedule`;
const DEFAULT_DEMAND_TARGET = String.raw`\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\beads 需求模組.xlsx`;
const DB_PATH = String.raw`\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\資料庫\Beads_Schedule.db`;

// === Utility Components ===
const SectionTitle: React.FC<{ title: string; subtitle?: string }> = ({ title, subtitle }) => (
  <div className="mb-4">
    <h2 className="text-2xl font-semibold tracking-tight text-slate-100">{title}</h2>
    {subtitle && <p className="text-sm text-slate-400 mt-1">{subtitle}</p>}
  </div>
);

const Field: React.FC<{ label: string; children: React.ReactNode; hint?: React.ReactNode; right?: React.ReactNode }> = ({
  label,
  children,
  hint,
  right,
}) => (
  <div className="grid grid-cols-12 items-center gap-3">
    <Label className="col-span-3 text-right text-slate-300">{label}</Label>
    <div className="col-span-7">{children}</div>
    <div className="col-span-2 flex items-center justify-end">{right}</div>
    {hint && <div className="col-span-12 text-xs text-slate-500 pl-3 md:pl-[25%]">{hint}</div>}
  </div>
);

const ModuleCard: React.FC<{
  name: string;
  desc?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  status?: "idle" | "ready" | "success" | "error" | "running";
}> = ({ name, desc, children, footer, status = "idle" }) => {
  const statusBadge = useMemo(() => {
    const map: any = {
      idle: { label: "Idle", variant: "secondary" },
      ready: { label: "Ready", variant: "outline" },
      running: { label: "Running", variant: "default" },
      success: { label: "Success", variant: "default" },
      error: { label: "Error", variant: "destructive" },
    };
    const s = map[status] ?? map.idle;
    return <Badge variant={s.variant as any} className="bg-slate-700 text-slate-100 hover:bg-slate-600 border-slate-600">{s.label}</Badge>;
  }, [status]);

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="h-full">
      <Card className="rounded-2xl shadow-lg h-full flex flex-col bg-slate-900 border-slate-800 text-slate-200">
        <CardContent className="p-5 space-y-5 flex-1 flex flex-col">
          <div className="flex items-center justify-between shrink-0">
            <div>
              <h3 className="text-lg font-semibold text-slate-100">{name}</h3>
              {desc && <p className="text-sm text-slate-400">{desc}</p>}
            </div>
            <div>{statusBadge}</div>
          </div>
          <div className="space-y-4 flex-1">{children}</div>
          {footer && <div className="pt-2 border-t border-slate-800 mt-auto shrink-0">{footer}</div>}
        </CardContent>
      </Card>
    </motion.div>
  );
};

// === Helper Functions ===
const getWeekDateString = (baseMMDD: string, dayOffset: string): string | null => {
  try {
    const [month, day] = baseMMDD.split("/").map(Number);
    const currentYear = new Date().getFullYear();
    const monday = new Date(currentYear, month - 1, day);
    const mondayWeekday = monday.getDay();
    if (mondayWeekday !== 1) {
      const diff = mondayWeekday === 0 ? -6 : 1 - mondayWeekday;
      monday.setDate(monday.getDate() + diff);
    }
    const targetDate = new Date(monday);
    targetDate.setDate(monday.getDate() + parseInt(dayOffset) - 1);
    return `${targetDate.getMonth() + 1}/${targetDate.getDate()}`;
  } catch (e) {
    return null;
  }
};

const formatDateISO = (date: Date) => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
};

const getSixDaysArray = (yearStr: string, mmdd: string) => {
    try {
        const [mm, dd] = mmdd.split('/').map(Number);
        const start = new Date(parseInt(yearStr), mm - 1, dd);
        const dates = [];
        for (let i = 0; i < 6; i++) {
            const d = new Date(start);
            d.setDate(start.getDate() + i);
            dates.push(formatDateISO(d));
        }
        return dates;
    } catch {
        return [];
    }
};

// Fixed Table Structure Definition (Rows 1-34)
const createEmptyTableStructure = () => {
    const rows = [];
    // Row 1-2: IVEK
    rows.push({ type: 'fixed', label: 'IVEK', id: 'IVEK_1' });
    rows.push({ type: 'fixed', label: 'IVEK', id: 'IVEK_2' });
    // Row 3-4: Empty
    rows.push({ type: 'empty' }); rows.push({ type: 'empty' });
    // Row 5-16: Port1-12 (First Block / AM)
    for(let i=1; i<=12; i++) rows.push({ type: 'port', label: `Port${i}`, id: `Port${i}_1` });
    // Row 17: Empty
    rows.push({ type: 'empty' });
    // Row 18-29: Port1-12 (Second Block / PM)
    for(let i=1; i<=12; i++) rows.push({ type: 'port', label: `Port${i}`, id: `Port${i}_2` });
    // Row 30-34: Empty
    for(let i=0; i<5; i++) rows.push({ type: 'empty' });
    return rows;
};


// === Main Component ===
export default function BeadsOpsUI() {
  // State: Tab 1 - Demand Module
  const [year, setYear] = useState<string>("2025");
  const [dateMMDD, setDateMMDD] = useState<string>("");
  const [scriptPath, setScriptPath] = useState<string>(String.raw`D:/OneDrive - 天亮醫療器材股份有限公司/.vscode/Bead_auto_update_schedule/plan_to_bead_requirements_1.py`);
  const [demandTargetFile, setDemandTargetFile] = useState<string>(DEFAULT_DEMAND_TARGET);
  const [resultFilePath, setResultFilePath] = useState<string>("");
  const [dryRun, setDryRun] = useState<boolean>(false);
  const [running, setRunning] = useState<boolean>(false);
  const [logEntries, setLogEntries] = useState<{ ts: string; msg: string }[]>([]);
  const [rows, setRows] = useState<any[]>([]);
  const [copiedAt, setCopiedAt] = useState<number | null>(null);

  // State: Tab 1 - Scheduler Module
  const [schedNeedPath, setSchedNeedPath] = useState<string>("");
  const [outDir, setOutDir] = useState<string>(DEFAULT_OUTDIR);
  const [schedMMDD, setSchedMMDD] = useState<string>("");
  const validSchedMMDD = useMemo(() => /^(0[1-9]|1[0-2])\/(0[1-9]|[12][0-9]|3[01])$/.test(schedMMDD), [schedMMDD]);
  const [holidays, setHolidays] = useState<string[]>([]);
  const [batchNumbers, setBatchNumbers] = useState("");
  const [vacationStaff, setVacationStaff] = useState("");
  const [schedRunning, setSchedRunning] = useState(false);
  const [schedLogs, setSchedLogs] = useState<{ ts: string; msg: string }[]>([]);
  const [schedPreview, setSchedPreview] = useState<any[]>([]);

  // State: Tab 2 - Forms Generation
  const [formsLoading, setFormsLoading] = useState(false);
  const [formsData, setFormsData] = useState<Record<string, any[]> | null>(null); 
  const [formDates, setFormDates] = useState<string[]>([]);
  const [activeFormTab, setActiveFormTab] = useState<string>("");
  const [isSaving, setIsSaving] = useState(false);

  // Refs for Auto-Save
  const formsDataRef = useRef(formsData);
  const yearRef = useRef(year);

  // Update refs when state changes
  useEffect(() => {
    formsDataRef.current = formsData;
  }, [formsData]);

  useEffect(() => {
    yearRef.current = year;
  }, [year]);

  // === Functions: Tab 1 - Demand Module ===
  const copyPath = async () => { 
    if (!resultFilePath) return; 
    try {
        await navigator.clipboard.writeText(resultFilePath);
        setCopiedAt(Date.now()); 
        setTimeout(() => setCopiedAt(null), 1500);
    } catch(e) { console.error(e); }
  };
  
  const fileName = useMemo(() => resultFilePath.split(/[\\/]/).pop() || "", [resultFilePath]);
  
  const runDemand = async () => {
    setRunning(true);
    setRows([]);
    setLogEntries((prev) => [{ ts: new Date().toLocaleString(), msg: "▶ 開始執行需求統計..." }, ...prev]);

    try {
      const payload = { 
          year: Number(year), 
          dateMMDD, 
          scriptPath, 
          writeBackPath: demandTargetFile, 
          dryRun 
      } as any;
      
      const res = await fetch("/api/run/beads-demand", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();

      if (data.ok) {
        if (dryRun && data.data) {
          setRows(data.data);
          setResultFilePath("");
          setLogEntries((prev) => [{ ts: new Date().toLocaleString(), msg: `✓ Dry Run 完成，共 ${data.data.length} 筆` }, ...prev]);
          setSchedMMDD(dateMMDD);
        } else {
          setResultFilePath(data.outPath || "");
          setLogEntries((prev) => [{ ts: new Date().toLocaleString(), msg: `✓ 已寫入：${data.outPath}` }, ...prev]);
          setSchedMMDD(dateMMDD);
          setSchedNeedPath(data.outPath || "");
        }
      } else {
        setLogEntries((prev) => [{ ts: new Date().toLocaleString(), msg: `✗ 失敗：${data.message ?? "Unknown"}` }, ...prev]);
      }
    } catch (err: any) {
      setLogEntries((prev) => [{ ts: new Date().toLocaleString(), msg: `✗ 例外：${err?.message ?? err}` }, ...prev]);
    } finally {
      setRunning(false);
    }
  };

  const pickOnServer = async (type: string, onDone: (p: string) => void) => {
    try {
      const res = await fetch(`/api/pick-file?type=${encodeURIComponent(type)}`, { method: "POST" });
      const raw = await res.text();
      let data: any = null;
      try { data = JSON.parse(raw); } catch { return; }
      if (data.ok && data.path) {
        onDone(data.path);
      }
    } catch (err: any) {
      // ignore error
    }
  };
  
  const weekDays = [{ label: "週一", value: "1" }, { label: "週二", value: "2" }, { label: "週三", value: "3" }, { label: "週四", value: "4" }, { label: "週五", value: "5" }, { label: "週六", value: "6" }, { label: "週日", value: "7" }];
  
  useEffect(() => {
    if (!schedMMDD || !validSchedMMDD) { setHolidays([]); return; }
    const satStr = getWeekDateString(schedMMDD, "6");
    const sunStr = getWeekDateString(schedMMDD, "7");
    setHolidays([satStr, sunStr].filter(Boolean) as string[]);
  }, [schedMMDD, validSchedMMDD]);

  const toggleHoliday = useCallback((dayOffset: string) => { 
    if (!schedMMDD) return;
    const holidayStr = getWeekDateString(schedMMDD, dayOffset);
    if (!holidayStr) return;
    setHolidays((prev) => prev.includes(holidayStr) ? prev.filter((h) => h !== holidayStr) : [...prev, holidayStr]);
  }, [schedMMDD]);

  const canRunSchedule = useMemo(() => {
    if (!validSchedMMDD) return false;
    if (!schedNeedPath || !outDir) return false;
    return true;
  }, [validSchedMMDD, schedNeedPath, outDir]);

  // === Functions: Tab 1 - Scheduler Module ===
  const runSchedule = async () => {
    setSchedRunning(true);
    setSchedPreview([]);
    setSchedLogs((prev) => [{ ts: new Date().toLocaleString(), msg: "▶ 開始產生一週排程..." }, ...prev]);
    try {
      const payload = {
        dateMMDD: schedMMDD,
        needPath: schedNeedPath,
        holidays: holidays,
        batchNumbers: batchNumbers,
        vacationStaff: vacationStaff, 
        outDir: outDir || DEFAULT_OUTDIR,
        dryRun,
        scriptName: "beads_Scheduler_V9_9_7.py",
      };

      const res = await fetch(`/api/run/beads-schedule`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await res.json();
      if (data.ok) {
        if (dryRun && data.preview) {
          setSchedPreview(data.preview);
          setSchedLogs((prev) => [{ ts: new Date().toLocaleString(), msg: `✓ Dry Run 完成（預覽筆數 ${data.preview.length}）` }, ...prev]);
        } else {
          const outMsg = Array.isArray(data.outPaths) ? data.outPaths.join(", ") : data.outPath;
          setSchedLogs((prev) => [{ ts: new Date().toLocaleString(), msg: `✓ 已輸出：${outMsg}` }, ...prev]);
        }
      } else {
        setSchedLogs((prev) => [{ ts: new Date().toLocaleString(), msg: `✗ 失敗：${data.message ?? "Unknown"}` }, ...prev]);
      }
    } catch (err: any) {
      setSchedLogs((prev) => [{ ts: new Date().toLocaleString(), msg: `✗ 例外：${err?.message ?? err}` }, ...prev]);
    } finally {
      setSchedRunning(false);
    }
  };

  const backSchedule = async () => { 
    setSchedNeedPath(""); setOutDir(DEFAULT_OUTDIR); setSchedMMDD(""); 
    setSchedPreview([]); setSchedRunning(false); setHolidays([]); 
    setBatchNumbers(""); setVacationStaff("");
    setSchedLogs([{ ts: new Date().toLocaleString(), msg: "⏹ 已取消並清空" }, ...schedLogs]);
  };

  // === Functions: Tab 2 - Forms Generation (Real API) ===
  const generateForms = async () => {
    if (!validSchedMMDD || !year) return;
    setFormsLoading(true);
    
    // 1. Calculate date list
    const dates = getSixDaysArray(year, schedMMDD);
    setFormDates(dates);
    setActiveFormTab(dates[0]);

    try {
        // 2. Fetch data from backend
        const res = await fetch('/api/forms/fetch-schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                year: year,
                dates: dates
            })
        });
        
        const resp = await res.json();
        
        if (!resp.ok) {
            console.error("Fetch failed:", resp.message);
            setFormsData(null);
        } else {
            const fetchedData = resp.data || [];
            const processedData: Record<string, any[]> = {};

            // 3. Map data to table structure
            dates.forEach(date => {
                const rawStructure = createEmptyTableStructure();
                const dayRecords = fetchedData.filter((r: any) => r['日期'] === date);

                const filledRows = rawStructure.map(row => {
                    if (row.type === 'empty') return { ...row };

                    let targetRecord = null;

                    if (row.type === 'fixed') { // IVEK
                        const ivekRecords = dayRecords.filter((r: any) => r['滴定機'] === 'IVEK');
                        if (row.id === 'IVEK_1') targetRecord = ivekRecords[0];
                        if (row.id === 'IVEK_2') targetRecord = ivekRecords[1];
                        
                    } else if (row.type === 'port') {
                        const portName = row.label; 
                        const recordsForPort = dayRecords.filter((r: any) => r['滴定機'] === portName);
                        const isSecondSlot = row.id.endsWith('_2'); 
                        
                        if (!isSecondSlot && recordsForPort.length > 0) {
                            targetRecord = recordsForPort[0];
                        } else if (isSecondSlot && recordsForPort.length > 1) {
                            targetRecord = recordsForPort[1];
                        }
                    }

                    if (targetRecord) {
                        return {
                            ...row,
                            data: {
                                col1: targetRecord['滴定機'], 
                                col2: targetRecord['Marker'], 
                                col3: targetRecord['PN'], 
                                col4: targetRecord['凍乾機台'],
                                col5: targetRecord['數量'],
                                col6: targetRecord['配藥同仁'], 
                                col7: targetRecord['日期'], 
                                col8: targetRecord['RD給藥時間'], 
                                col9: targetRecord['預計滴定時間'], 
                                col10: targetRecord['預計結束'],
                                col11: targetRecord['工單號碼'], 
                                // ✅ 修正：若資料庫是 Batch，則優先讀取 Batch，否則讀取 Lot
                                col12: targetRecord['Batch'] || targetRecord['Lot'], 
                                col13: targetRecord['remark'] || ''
                            }
                        };
                    }
                    
                    return { 
                        ...row, 
                        data: { col1: row.label, col2:'', col3:'', col4:'', col5:'', col6:'', col7:'', col8:'', col9:'', col10:'', col11:'', col12:'', col13:'' } 
                    };
                });
                
                processedData[date] = filledRows;
            });
            
            setFormsData(processedData);
        }
    } catch (err) {
        console.error("API Call Error:", err);
        setFormsData(null);
    } finally {
        setFormsLoading(false);
    }
  };

  // ✅ Handle Cell Change
  const handleCellChange = (dateKey: string, rowIndex: number, colKey: string, value: string) => {
    setFormsData((prev) => {
      if (!prev) return null;
      const newData = { ...prev };
      const newRows = [...newData[dateKey]];
      const targetRow = { ...newRows[rowIndex] };
      
      if (targetRow.data) {
        targetRow.data = { ...targetRow.data, [colKey]: value };
      }
      
      newRows[rowIndex] = targetRow;
      newData[dateKey] = newRows;
      return newData;
    });
  };

  // ✅ Save Data Function
  const saveFormData = async () => {
    if (!formsData || !year) return;
    setIsSaving(true);
    try {
      const allRows: any[] = [];
      Object.keys(formsData).forEach(dateKey => {
        const dayRows = formsData[dateKey];
        dayRows.forEach((row: any) => {
          if (row.type !== 'empty' && row.data && row.data.col7 && row.data.col1) {
            allRows.push(row.data);
          }
        });
      });

      if (allRows.length === 0) {
        setIsSaving(false);
        return;
      }

      const res = await fetch('/api/forms/save-schedule', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ year: year, rows: allRows })
      });
      const data = await res.json();
      if (!data.ok) {
         console.error("Save failed:", data.message);
         alert("儲存失敗: " + (data.message || "未知錯誤"));
      } else {
         console.log("Saved rows:", data.updated);
      }
    } catch (e) {
      console.error("Save error:", e);
      alert("儲存發生錯誤");
    } finally {
      setIsSaving(false);
    }
  };

  // ✅ Auto-save on Unmount (Leaving the page)
  useEffect(() => {
    return () => {
      const currentData = formsDataRef.current;
      const currentYear = yearRef.current;
      if (currentData) {
        const allRows: any[] = [];
        Object.keys(currentData).forEach(dateKey => {
          currentData[dateKey].forEach((row: any) => {
            if (row.type !== 'empty' && row.data && row.data.col7 && row.data.col1) {
              allRows.push(row.data);
            }
          });
        });

        if (allRows.length > 0) {
           const payload = JSON.stringify({ year: currentYear, rows: allRows });
           // Use sendBeacon for reliability on page unload
           navigator.sendBeacon('/api/forms/save-schedule', new Blob([payload], {type: 'application/json'}));
        }
      }
    };
  }, []);

  return (
    <div className="p-6 md:p-10 space-y-8 min-h-screen w-full bg-slate-950 text-slate-200">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-100">Beads 排程作業系統</h1>
          <p className="text-sm text-slate-400 mt-1">主畫面：排程產生系統 / 表單產生系統</p>
        </div>
        <Button variant="outline" className="border-slate-700 text-slate-200 hover:bg-slate-800 hover:text-white">
          <Settings className="w-4 h-4 mr-2" />
          設定
        </Button>
      </div>

      <Tabs 
        defaultValue="scheduler" 
        className="w-full"
        onValueChange={(val) => {
            // Auto-save when switching away from 'forms' tab
            if (val !== "forms" && formsData) {
                saveFormData();
            }
        }}
      >
        <TabsList className="grid w-full grid-cols-2 bg-slate-900 border border-slate-800">
          <TabsTrigger value="scheduler" className="data-[state=active]:bg-slate-800 data-[state=active]:text-slate-100 text-slate-400">排程產生系統</TabsTrigger>
          <TabsTrigger value="forms" className="data-[state=active]:bg-slate-800 data-[state=active]:text-slate-100 text-slate-400">表單產生系統</TabsTrigger>
        </TabsList>

        {/* ================= Tab 1: 排程產生系統 ================= */}
        <TabsContent value="scheduler" className="space-y-6 mt-4">
          <SectionTitle title="排程產生系統" subtitle="包含兩個模組，每個模組皆有 Input / 執行 / Output / Back" />
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            {/* Module 1: Demand Stats */}
            <ModuleCard name="Beads 需求統計模組" desc="輸入年份與日期（MM/DD），計算需求並寫回工作表" status={running ? "running" : "ready"} footer={
                <div className="grid gap-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-xs text-slate-400"><TerminalSquare className="w-4 h-4" /><span>腳本</span></div>
                    <Badge variant="outline" className="text-slate-300 border-slate-600">plan_to_bead_requirements_1.py</Badge>
                  </div>
                  <div className="text-xs space-y-1 max-h-40 overflow-y-auto border border-slate-700 p-2 rounded bg-slate-950/50 font-mono text-slate-300">
                    {logEntries.map((e, idx) => (<div key={idx}><span className="text-slate-500 mr-2">{e.ts}</span>{e.msg}</div>))}
                  </div>
                   {rows.length > 0 && (
                    <div className="overflow-x-auto mt-4 rounded border border-slate-700">
                      <table className="min-w-full text-xs text-slate-300">
                        <thead>
                          <tr className="bg-slate-800 text-slate-200">
                            {Object.keys(rows[0]).map(h => <th key={h} className="px-2 py-1 border border-slate-700">{h}</th>)}
                          </tr>
                        </thead>
                        <tbody>
                          {rows.map((row, idx) => (
                            <tr key={idx} className="hover:bg-slate-800/50">
                              {Object.values(row).map((val: any, i) => <td key={i} className="px-2 py-1 border border-slate-700">{val}</td>)}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
            }>
              <div className="grid gap-4">
                <Field label="Year">
                  <Input type="number" value={year} onChange={(e) => setYear(e.target.value)} className="bg-slate-950 border-slate-800 text-slate-100" />
                </Field>
                <Field label="Date (MM/DD)">
                   <div className="flex gap-2">
                    <Input value={dateMMDD} onChange={(e) => setDateMMDD(e.target.value)} placeholder="MM/DD" className="bg-slate-950 border-slate-800 text-slate-100" />
                    <Button variant="outline" className="border-slate-700 text-slate-300 hover:bg-slate-800" onClick={()=>{const d=new Date();setDateMMDD(`${String(d.getMonth()+1).padStart(2,"0")}/${String(d.getDate()).padStart(2,"0")}`)}}>今天</Button>
                   </div>
                </Field>
                <Field label="Python 路徑"><Input value={scriptPath} onChange={(e) => setScriptPath(e.target.value)} className="bg-slate-950 border-slate-800 text-slate-100" /></Field>
                <Field label="寫回目標檔案" hint={<span className="flex items-center text-red-400 font-medium"><AlertCircle className="w-3 h-3 mr-1" />若檔案開啟中，程式將無法寫入</span>}>
                    <div className="flex gap-2">
                    <Input value={demandTargetFile} onChange={(e)=>setDemandTargetFile(e.target.value)} className="bg-slate-950 border-slate-800 text-slate-100" />
                    <Button variant="outline" className="border-slate-700 text-slate-300 hover:bg-slate-800" onClick={() => pickOnServer("target_excel", setDemandTargetFile)}><FolderOpen className="w-4 h-4" /></Button>
                    </div>
                </Field>
                <Field label="Output 結果">
                  <div className="flex items-center gap-2 w-full">
                    <Input value={fileName || ""} readOnly className="truncate bg-slate-950/50 border-slate-800 text-slate-400" placeholder="尚未執行" />
                    {fileName && <Badge role="button" onClick={copyPath} variant="outline" className="cursor-pointer hover:bg-slate-800 text-slate-300 border-slate-600">{copiedAt ? "已複製" : "複製路徑"}</Badge>}
                  </div>
                </Field>
                <Field label="Dry Run" right={dryRun ? <span className="text-xs text-slate-400">不寫回，只產生預覽</span> : undefined}><Switch checked={dryRun} onCheckedChange={setDryRun} className="data-[state=checked]:bg-emerald-600 data-[state=unchecked]:bg-slate-700" /></Field>
                <div className="flex justify-end pt-2"><Button onClick={runDemand} disabled={running || !year || !dateMMDD || !scriptPath} className="bg-slate-100 text-slate-900 hover:bg-slate-200">{running ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> 執行中...</> : <><Play className="w-4 h-4 mr-2" /> 計算未來三週需求</>}</Button></div>
              </div>
            </ModuleCard>

            {/* Module 2: Schedule Generation */}
            <ModuleCard name="Beads 排程模組" desc="選擇需求檔、設定參數，產生一週 6 份排程" status={schedRunning ? "running" : "ready"} footer={
                <div className="grid gap-3">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-xs text-slate-400"><TerminalSquare className="w-4 h-4" /><span>腳本</span></div>
                        <Badge variant="outline" className="text-slate-300 border-slate-600">beads_Scheduler_V9_9_7.py</Badge>
                    </div>
                    <div className="text-xs space-y-1 max-h-40 overflow-y-auto border border-slate-700 p-2 rounded bg-slate-950/50 font-mono text-slate-300">
                         {schedLogs.map((e, idx) => (<div key={idx}><span className="text-slate-500 mr-2">{e.ts}</span> {e.msg}</div>))}
                    </div>
                     {schedPreview.length > 0 && (
                      <div className="overflow-x-auto mt-4 rounded border border-slate-700">
                        <table className="min-w-full text-xs text-slate-300">
                          <thead>
                            <tr className="bg-slate-800 text-slate-200">
                              <th className="px-2 py-1 border border-slate-700">日期</th>
                              <th className="px-2 py-1 border border-slate-700">滴定機</th>
                              <th className="px-2 py-1 border border-slate-700">凍乾機</th>
                              <th className="px-2 py-1 border border-slate-700">料號</th>
                              <th className="px-2 py-1 border border-slate-700">數量</th>
                              <th className="px-2 py-1 border border-slate-700">配藥同仁</th>
                              <th className="px-2 py-1 border border-slate-700">品名</th>
                            </tr>
                          </thead>
                          <tbody>
                            {schedPreview.map((row: any, idx: number) => (
                              <tr key={idx} className="hover:bg-slate-800/50">
                                <td className="px-2 py-1 border border-slate-700">{row.date}</td>
                                <td className="px-2 py-1 border border-slate-700">{row.titrate}</td>
                                <td className="px-2 py-1 border border-slate-700">{row.freeze}</td>
                                <td className="px-2 py-1 border border-slate-700">{row.pn}</td>
                                <td className="px-2 py-1 border border-slate-700">{row.qty}</td>
                                <td className="px-2 py-1 border border-slate-700">{row.staff ?? ""}</td>
                                <td className="px-2 py-1 border border-slate-700">{row.Name ?? ""}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                </div>
            }>
              <div className="grid gap-4">
                <Field label="當週第一天 (MM/DD)" hint="依序產生 6 天排程">
                  <div className="flex gap-2">
                    <Input value={schedMMDD} onChange={(e) => setSchedMMDD(e.target.value)} className="bg-slate-950 border-slate-800 text-slate-100" placeholder="MM/DD (從左側連動)" />
                    <Button variant="outline" className="border-slate-700 text-slate-300 hover:bg-slate-800" onClick={()=>{const d=new Date();setSchedMMDD(`${String(d.getMonth()+1).padStart(2,"0")}/${String(d.getDate()).padStart(2,"0")}`)}}><Calendar className="w-4 h-4 mr-2" /> 今天</Button>
                  </div>
                  {validSchedMMDD && <div className="text-xs text-emerald-500 mt-1 pl-1">✓ 日期格式正確</div>}
                </Field>

                <Field label="需求檔來源" hint="只需按右側圖示選檔，路徑會自動填入">
                  <div className="flex items-center gap-2">
                    <Input value={schedNeedPath} readOnly className="bg-slate-950/50 border-slate-800 text-slate-400" placeholder="尚未選擇（將從左側模組連動）" />
                    <Button variant="outline" className="border-slate-700 text-slate-300 hover:bg-slate-800" type="button" onClick={() => pickOnServer("need", setSchedNeedPath)}>
                      <FolderOpen className="w-4 h-4 mr-2" /> 選擇檔案
                    </Button>
                  </div>
                </Field>

                <Field label="本周休假日" hint={holidays.length > 0 ? `已選: ${holidays.join(', ')}` : "請先輸入當週第一天"}>
                  <div className="grid grid-cols-4 gap-2 pt-2">
                    {weekDays.map((day) => {
                      const dayStr = getWeekDateString(schedMMDD, day.value);
                      const isChecked = dayStr ? holidays.includes(dayStr) : false;
                      return (
                        <div key={day.value} className="flex items-center space-x-2">
                          <Checkbox id={`holiday-${day.value}`} checked={isChecked} onCheckedChange={() => toggleHoliday(day.value)} disabled={!schedMMDD || !validSchedMMDD} className="border-slate-600 data-[state=checked]:bg-slate-100 data-[state=checked]:text-slate-900" />
                          <label htmlFor={`holiday-${day.value}`} className="text-sm font-medium leading-none cursor-pointer text-slate-300">{day.label}</label>
                        </div>
                      );
                    })}
                  </div>
                </Field>
                
                <Field label="批次編號起始值" hint="例如輸入 001，工單號碼將從 TMRA...001 開始">
                  <Input value={batchNumbers} onChange={(e) => setBatchNumbers(e.target.value)} placeholder="例如：111" type="number" min="1" max="999" className="bg-slate-950 border-slate-800 text-slate-100" />
                </Field>

                <Field label="本周休假人員" hint="格式範例：11/10-張三,11/11-李四">
                  <Input value={vacationStaff} onChange={(e) => setVacationStaff(e.target.value)} placeholder="例如：11/10-張三,11/11-李四" className="bg-slate-950 border-slate-800 text-slate-100" />
                </Field>

                <Field label="輸出資料夾" hint="預設=MBBU_FAB\MB_PD\生管自動化\滴定\beadsSchedule">
                  <div className="flex items-center gap-2">
                    <Input value={outDir} readOnly className="bg-slate-950/50 border-slate-800 text-slate-400" placeholder={DEFAULT_OUTDIR} />
                    <Button variant="outline" className="border-slate-700 text-slate-300 hover:bg-slate-800" type="button" onClick={() => pickOnServer("outdir", setOutDir)}>
                      <FolderOpen className="w-4 h-4 mr-2" /> 選擇資料夾
                    </Button>
                  </div>
                </Field>

                <Field label="Dry Run" right={dryRun ? <span className="text-xs text-slate-400">不另存，僅預覽</span> : undefined}>
                  <Switch checked={dryRun} onCheckedChange={setDryRun} className="data-[state=checked]:bg-emerald-600 data-[state=unchecked]:bg-slate-700" />
                </Field>

                <div className="flex gap-2 justify-end pt-2">
                  <Button variant="ghost" onClick={backSchedule} className="text-slate-300 hover:text-white hover:bg-slate-800"><Undo2 className="w-4 h-4 mr-1" /> Back</Button>
                  <Button onClick={runSchedule} disabled={schedRunning || !canRunSchedule} className="bg-slate-100 text-slate-900 hover:bg-slate-200">
                    {schedRunning ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> 產生中...</> : <><Play className="w-4 h-4 mr-2" /> 產生一週排程</>}
                  </Button>
                </div>
              </div>
            </ModuleCard>
          </div>
        </TabsContent>

        {/* ================= Tab 2: 表單產生系統 ================= */}
        <TabsContent value="forms" className="space-y-6 mt-4">
          <SectionTitle title="表單產生系統" subtitle="從資料庫讀取排程資料，並產生每日生產表單" />
          
          <Card className="rounded-xl shadow-lg bg-slate-900 border-slate-800">
            <CardContent className="p-5 flex flex-col md:flex-row gap-6 items-start md:items-end">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 flex-1 w-full">
                     <div className="space-y-2">
                        <Label className="text-slate-300 flex items-center gap-2"><Database className="w-4 h-4 text-blue-400" /> 資料庫來源 (DB Path)</Label>
                        <Input value={DB_PATH} readOnly className="bg-slate-950/50 border-slate-700 text-slate-400 text-xs font-mono" />
                     </div>
                     <div className="space-y-2">
                        <Label className="text-slate-300 flex items-center gap-2"><List className="w-4 h-4 text-green-400" /> 資料表 (Table)</Label>
                        <Input value={`schedule_${year}`} readOnly className="bg-slate-950/50 border-slate-700 text-slate-400 text-xs font-mono" />
                     </div>
                     <div className="space-y-2">
                        <Label className="text-slate-300 flex items-center gap-2"><Calendar className="w-4 h-4 text-yellow-400" /> 起始日期 (Start Date)</Label>
                        <Input value={validSchedMMDD ? `${year}/${schedMMDD} (共6天)` : "請先在 [排程產生系統] 設定日期"} readOnly className={`border-slate-700 text-xs font-mono ${validSchedMMDD ? "bg-slate-950/50 text-slate-200" : "bg-red-950/20 text-red-400 border-red-900"}`} />
                     </div>
                </div>
                
                <div className="flex gap-2">
                    <Button onClick={generateForms} disabled={formsLoading || !validSchedMMDD} className="w-full md:w-auto bg-blue-600 hover:bg-blue-500 text-white min-w-[140px]">
                        {formsLoading ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> 讀取中...</> : <><FileSpreadsheet className="w-4 h-4 mr-2" /> 讀取資料庫</>}
                    </Button>
                    <Button onClick={saveFormData} disabled={isSaving || !formsData} className="w-full md:w-auto bg-emerald-600 hover:bg-emerald-500 text-white min-w-[140px]">
                        {isSaving ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> 存檔中...</> : <><Save className="w-4 h-4 mr-2" /> 存回資料庫</>}
                    </Button>
                </div>
            </CardContent>
          </Card>

          {formsData && (
              <div className="space-y-4 animate-in fade-in slide-in-from-bottom-4 duration-500">
                  <Tabs value={activeFormTab} onValueChange={setActiveFormTab} className="w-full">
                      <div className="flex items-center justify-between mb-2">
                          <TabsList className="bg-slate-900 border border-slate-800 h-auto p-1 flex-wrap justify-start">
                              {formDates.map(date => (
                                  <TabsTrigger key={date} value={date} className="data-[state=active]:bg-blue-900 data-[state=active]:text-blue-100 text-slate-400 text-xs px-3 py-1.5">{date}</TabsTrigger>
                              ))}
                          </TabsList>
                          <div className="text-xs text-slate-500">顯示 Row 1~34 (固定格式) | 除「滴定機」外可編輯</div>
                      </div>

                      {formDates.map(date => (
                          <TabsContent key={date} value={date} className="mt-0">
                              <div className="border border-slate-700 rounded overflow-hidden overflow-x-auto bg-white">
                                  <table className="w-full text-[11px] border-collapse text-slate-900 min-w-[1000px]">
                                      <thead>
                                          <tr className="bg-blue-900 text-white h-8">
                                              <th className="border border-slate-500 w-16 px-1">滴定機</th>
                                              <th className="border border-slate-500 w-16 px-1">Marker</th>
                                              <th className="border border-slate-500 w-24 px-1">PN</th>
                                              <th className="border border-slate-500 w-16 px-1">凍乾機台</th>
                                              <th className="border border-slate-500 w-16 px-1">數量</th>
                                              <th className="border border-slate-500 w-16 px-1">配藥同仁</th>
                                              <th className="border border-slate-500 w-20 px-1">日期</th>
                                              <th className="border border-slate-500 w-20 px-1">RD給藥時間</th>
                                              <th className="border border-slate-500 w-20 px-1">預計滴定時間</th>
                                              <th className="border border-slate-500 w-16 px-1">預計結束</th>
                                              <th className="border border-slate-500 w-24 px-1">工單號碼</th>
                                              <th className="border border-slate-500 w-20 px-1">Lot</th>
                                              <th className="border border-slate-500 min-w-[50px] px-1">備註</th>
                                          </tr>
                                      </thead>
                                      <tbody>
                                          {formsData[date]?.map((row, idx) => {
                                              if (row.type === 'empty') {
                                                  return <tr key={idx} className="h-6"><td colSpan={13} className="border border-slate-300 bg-slate-50"></td></tr>;
                                              }
                                              const d = row.data || {};
                                              // Input style for editable cells
                                              const inputClass = "w-full h-full bg-transparent border-none outline-none text-center focus:ring-1 focus:ring-blue-500 px-1 text-slate-900 dark:text-slate-100";
                                              
                                              return (
                                                  <tr key={idx} className="h-6 hover:bg-blue-50 transition-colors">
                                                      {/* Fixed Column */}
                                                      <td className="border border-slate-400 px-1 text-center font-semibold bg-slate-100 select-none">{d.col1}</td>
                                                      
                                                      {/* Editable Columns */}
                                                      <td className="border border-slate-400 p-0"><input value={d.col2} onChange={(e) => handleCellChange(date, idx, 'col2', e.target.value)} className={inputClass} /></td>
                                                      <td className="border border-slate-400 p-0"><input value={d.col3} onChange={(e) => handleCellChange(date, idx, 'col3', e.target.value)} className={inputClass} /></td>
                                                      <td className="border border-slate-400 p-0"><input value={d.col4} onChange={(e) => handleCellChange(date, idx, 'col4', e.target.value)} className={inputClass} /></td>
                                                      <td className="border border-slate-400 p-0"><input value={d.col5} onChange={(e) => handleCellChange(date, idx, 'col5', e.target.value)} className={`${inputClass} text-right font-mono`} /></td>
                                                      <td className="border border-slate-400 p-0"><input value={d.col6} onChange={(e) => handleCellChange(date, idx, 'col6', e.target.value)} className={inputClass} /></td>
                                                      <td className="border border-slate-400 p-0"><input value={d.col7} onChange={(e) => handleCellChange(date, idx, 'col7', e.target.value)} className={inputClass} /></td>
                                                      <td className="border border-slate-400 p-0"><input value={d.col8} onChange={(e) => handleCellChange(date, idx, 'col8', e.target.value)} className={inputClass} /></td>
                                                      <td className="border border-slate-400 p-0"><input value={d.col9} onChange={(e) => handleCellChange(date, idx, 'col9', e.target.value)} className={inputClass} /></td>
                                                      <td className="border border-slate-400 p-0"><input value={d.col10} onChange={(e) => handleCellChange(date, idx, 'col10', e.target.value)} className={inputClass} /></td>
                                                      <td className="border border-slate-400 p-0"><input value={d.col11} onChange={(e) => handleCellChange(date, idx, 'col11', e.target.value)} className={inputClass} /></td>
                                                      <td className="border border-slate-400 p-0"><input value={d.col12} onChange={(e) => handleCellChange(date, idx, 'col12', e.target.value)} className={inputClass} /></td>
                                                      <td className="border border-slate-400 p-0"><input value={d.col13} onChange={(e) => handleCellChange(date, idx, 'col13', e.target.value)} className={`${inputClass} text-left`} /></td>
                                                  </tr>
                                              );
                                          })}
                                      </tbody>
                                  </table>
                              </div>
                          </TabsContent>
                      ))}
                  </Tabs>
              </div>
          )}
        </TabsContent>
      </Tabs>

      <footer className="text-xs text-slate-500 pt-6 border-t border-slate-800 flex items-center gap-2">
        <FileOutput className="w-3 h-3" />
        v2.2 UI — Forms with Correct Batch Mapping and Save Feature.
      </footer>
    </div>
  );
}