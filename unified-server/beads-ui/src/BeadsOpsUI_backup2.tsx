import React, { useMemo, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectTrigger, SelectContent, SelectValue, SelectItem } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Switch } from "@/components/ui/switch";
import { Loader2, Play, Undo2, FileOutput, Settings, Calendar, TerminalSquare, Upload, HardDrive, FolderOpen } from "lucide-react";
import { motion } from "framer-motion";

const SectionTitle: React.FC<{ title: string; subtitle?: string }> = ({ title, subtitle }) => (
  <div className="mb-4">
    <h2 className="text-2xl font-semibold tracking-tight">{title}</h2>
    {subtitle && <p className="text-sm text-muted-foreground mt-1">{subtitle}</p>}
  </div>
);

const Field: React.FC<{ label: string; children: React.ReactNode; hint?: string; right?: React.ReactNode }> = ({
  label,
  children,
  hint,
  right,
}) => (
  <div className="grid grid-cols-12 items-center gap-3">
    <Label className="col-span-3 text-right">{label}</Label>
    <div className="col-span-7">{children}</div>
    <div className="col-span-2 flex items-center justify-end">{right}</div>
    {hint && <div className="col-span-12 text-xs text-muted-foreground pl-3">{hint}</div>}
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
    return <Badge variant={s.variant as any}>{s.label}</Badge>;
  }, [status]);

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
      <Card className="rounded-2xl shadow-sm h-full">
        <CardContent className="p-5 space-y-5">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold">{name}</h3>
              {desc && <p className="text-sm text-muted-foreground">{desc}</p>}
            </div>
            <div>{statusBadge}</div>
          </div>
          <div className="space-y-4">{children}</div>
          {footer && <div className="pt-2 border-t mt-2">{footer}</div>}
        </CardContent>
      </Card>
    </motion.div>
  );
};

const PlaceholderIO: React.FC = () => (
  <div className="grid gap-4">
    <Field label="Input">
      <Input placeholder="選擇或輸入來源檔/參數" />
    </Field>
    <Field label="執行">
      <Button disabled variant="secondary" className="w-full" title="尚未接後端">
        待接後端
      </Button>
    </Field>
    <Field label="Output">
      <Input placeholder="輸出檔名或目的地" />
    </Field>
    <div className="flex justify-end">
      <Button variant="ghost" size="sm">
        <Undo2 className="w-4 h-4 mr-1" />
        Back
      </Button>
    </div>
  </div>
);

export default function BeadsOpsUI() {
  const [year, setYear] = useState<string>("2025");
  const [dateMMDD, setDateMMDD] = useState<string>("");
  const [scriptPath, setScriptPath] = useState<string>(
    String.raw`D:\OneDrive - 天亮醫療器材股份有限公司\.vscode\Bead_auto_update_schedule\plan_to_bead_requirements_1.py`
  );
  const [writeBackPath, setWriteBackPath] = useState<string>("");
  const [dryRun, setDryRun] = useState<boolean>(false);
  const [running, setRunning] = useState<boolean>(false);
  const [logEntries, setLogEntries] = useState<{ ts: string; msg: string }[]>([]);
  const [rows, setRows] = useState<any[]>([]);
  const [copiedAt, setCopiedAt] = useState<number | null>(null);

  // --- 排程限制模組 state / methods ---
type Src = "upload" | "path" | "server";

// 需求檔（排程用）
const [schedNeedSource, setSchedNeedSource] = useState<Src>("path");
const [schedNeedPath, setSchedNeedPath] = useState<string>("");
const [schedNeedFile, setSchedNeedFile] = useState<File | null>(null);
const [uploadingNeed, setUploadingNeed] = useState(false);

// 限制檔（配藥限制）
const [schedLimitSource, setSchedLimitSource] = useState<Src>("path");
const [schedLimitPath, setSchedLimitPath] = useState<string>("");
const [schedLimitFile, setSchedLimitFile] = useState<File | null>(null);
const [uploadingLimit, setUploadingLimit] = useState(false);

// 空白模板與輸出資料夾（用你給的預設）
const [tmplPath, setTmplPath] = useState<string>(
  String.raw`\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\空白排程.xlsm`
);
const [outDir, setOutDir] = useState<string>(
  String.raw`\\fls341\MBBU_FAB\MB_PD\生管自動化\滴定\beadsSchedule`
);

// 排程日期（MM/DD）
const [schedMMDD, setSchedMMDD] = useState<string>("");
const validSchedMMDD = useMemo(
  () => /^(0[1-9]|1[0-2])\/(0[1-9]|[12][0-9]|3[01])$/.test(schedMMDD),
  [schedMMDD]
);

// 執行狀態 / 日誌 / 預覽
const [schedRunning, setSchedRunning] = useState(false);
const [schedLogs, setSchedLogs] = useState<{ ts: string; msg: string }[]>([]);
const [schedPreview, setSchedPreview] = useState<any[]>([]);

// 上傳 Excel（需求/限制通用）
const uploadExcel = async (
  file: File,
  endpoint: string,
  onDone: (p: string) => void,
  setBusy: (b: boolean) => void
) => {
  setBusy(true);
  try {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(endpoint, { method: "POST", body: form });
    const data = await res.json();
    if (data.ok && data.savedPath) {
      onDone(data.savedPath);
      setSchedLogs((prev) => [{ ts: new Date().toLocaleString(), msg: `✓ 上傳成功：${data.savedPath}` }, ...prev]);
    } else {
      setSchedLogs((prev) => [{ ts: new Date().toLocaleString(), msg: `✗ 上傳失敗：${data.message ?? "Unknown"}` }, ...prev]);
    }
  } catch (err: any) {
    setSchedLogs((prev) => [{ ts: new Date().toLocaleString(), msg: `✗ 上傳例外：${err?.message ?? err}` }, ...prev]);
  } finally {
    setBusy(false);
  }
};

// 伺服器端選檔
const pickOnServer = async (type: string, onDone: (p: string) => void) => {
  try {
    const res = await fetch(`/api/pick-file?type=${encodeURIComponent(type)}`, { method: "POST" });
    const data = await res.json();
    if (data.ok && data.path) {
      onDone(data.path);
      setSchedLogs((prev) => [{ ts: new Date().toLocaleString(), msg: `✓ 已選擇：${data.path}` }, ...prev]);
    } else {
      setSchedLogs((prev) => [{ ts: new Date().toLocaleString(), msg: `✗ 選檔失敗：${data.message ?? "Unknown"}` }, ...prev]);
    }
  } catch (err: any) {
    setSchedLogs((prev) => [{ ts: new Date().toLocaleString(), msg: `✗ 選檔例外：${err?.message ?? err}` }, ...prev]);
  }
};

// 是否可執行排程
const canRunSchedule = useMemo(() => {
  if (!validSchedMMDD) return false;
  if (!schedNeedPath || !schedLimitPath || !tmplPath || !outDir) return false;
  return true;
}, [validSchedMMDD, schedNeedPath, schedLimitPath, tmplPath, outDir]);

// 執行排程
const runSchedule = async () => {
  setSchedRunning(true);
  setSchedPreview([]);
  setSchedLogs((prev) => [{ ts: new Date().toLocaleString(), msg: "▶ 開始產生一週排程..." }, ...prev]);

  try {
    const payload = {
      dateMMDD: schedMMDD,
      needPath: schedNeedPath,
      limitPath: schedLimitPath,
      templatePath: tmplPath,
      outDir,
      dryRun, // 共用 Dry Run
    };
    const res = await fetch("/api/run/beads-schedule", {
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


  const copyPath = async () => {
    if (!writeBackPath) return;
    try {
      await navigator.clipboard.writeText(writeBackPath);
    } finally {  
      setCopiedAt(Date.now());
      setTimeout(() => setCopiedAt(null), 1500);
    }
  };

  // 檔名（方案B：主檔名 + 後綴）
  const fileName = useMemo(() => writeBackPath.split(/[\\/]/).pop() || "", [writeBackPath]);
  const [baseName, suffix] = useMemo(() => {
    if (!fileName) return ["", ""];
    const m = fileName.match(/(.*-OUTPUT-)(.*)/);
    return m ? [m[1], m[2]] : [fileName, ""];
  }, [fileName]);

  const runDemand = async () => {
    setRunning(true);
    setRows([]);
    setLogEntries((prev) => [{ ts: new Date().toLocaleString(), msg: "▶ 開始執行需求統計..." }, ...prev]);

    try {
      const payload = { year: Number(year), dateMMDD, scriptPath, writeBackPath, dryRun };
      const res = await fetch("/api/run/beads-demand", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();

      if (data.ok) {
        if (dryRun && data.data) {
          setRows(data.data);
          setWriteBackPath("");
          setLogEntries((prev) => [{ ts: new Date().toLocaleString(), msg: `✓ Dry Run 完成，共 ${data.data.length} 筆` }, ...prev]);
        } else {
          setWriteBackPath(data.outPath || "");
          setLogEntries((prev) => [{ ts: new Date().toLocaleString(), msg: `✓ 已寫入：${data.outPath}` }, ...prev]);
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

  const years = useMemo(() => Array.from({ length: 7 }, (_, i) => 2024 + i).map(String), []);

  return (
    <div className="p-6 md:p-10 space-y-8 min-h-screen w-full">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Beads 排程作業系統</h1>
          <p className="text-sm text-muted-foreground mt-1">主畫面：排程產生系統 / 表單產生系統</p>
        </div>
        <Button variant="outline">
          <Settings className="w-4 h-4 mr-2" />
          設定
        </Button>
      </div>

      <Tabs defaultValue="scheduler" className="w-full">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="scheduler">排程產生系統</TabsTrigger>
          <TabsTrigger value="forms">表單產生系統</TabsTrigger>
        </TabsList>

        <TabsContent value="scheduler" className="space-y-6 mt-4">
          <SectionTitle title="排程產生系統" subtitle="包含兩個模組，每個模組皆有 Input / 執行 / Output / Back" />

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ModuleCard
              name="Beads 需求統計模組"
              desc="輸入年份與日期（MM/DD），按『計算未來三週需求』並寫回指定工作表"
              status={running ? "running" : "ready"}
              footer={
                <div className="grid gap-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <TerminalSquare className="w-4 h-4" />
                      <span>腳本</span>
                    </div>
                    <Badge variant="outline">plan_to_bead_requirements_1.py</Badge>
                  </div>

                  <div className="text-xs space-y-1 max-h-40 overflow-y-auto border p-2 rounded bg-muted/30">
                    {logEntries.map((e, idx) => (
                      <div key={idx}>
                        <span className="text-gray-500">{e.ts}</span> {e.msg}
                      </div>
                    ))}
                  </div>

                  {rows.length > 0 && (
                    <div className="overflow-x-auto mt-4">
                      <table className="min-w-full border text-xs">
                        <thead>
                          <tr className="bg-gray-100">
                            <th className="px-2 py-1 border">藥名</th>
                            <th className="px-2 py-1 border">料號</th>
                            <th className="px-2 py-1 border">品名</th>
                            <th className="px-2 py-1 border">凍乾數</th>
                            <th className="px-2 py-1 border">庫存+滴定</th>
                            <th className="px-2 py-1 border">第一周需求</th>
                            <th className="px-2 py-1 border">第二周需求</th>
                            <th className="px-2 py-1 border">第三周需求</th>
                          </tr>
                        </thead>
                        <tbody>
                          {rows.map((row, idx) => (
                            <tr key={idx}>
                              <td className="px-2 py-1 border">{row["藥名"]}</td>
                              <td className="px-2 py-1 border">{row["料號"]}</td>
                              <td className="px-2 py-1 border">{row["品名"]}</td>
                              <td className="px-2 py-1 border">{row["凍乾數"]}</td>
                              <td className="px-2 py-1 border">{row["庫存+滴定"]}</td>
                              <td className="px-2 py-1 border">{row["第一周需求"]}</td>
                              <td className="px-2 py-1 border">{row["第二周需求"]}</td>
                              <td className="px-2 py-1 border">{row["第三周需求"]}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              }
            >
              <div className="grid gap-4">
                <Field label="Year">
                  <Select value={year} onValueChange={setYear}>
                    <SelectTrigger>
                      <SelectValue placeholder="選擇年份" />
                    </SelectTrigger>
                    <SelectContent>
                      {Array.from({ length: 7 }, (_, i) => 2024 + i).map((y) => (
                        <SelectItem key={y} value={String(y)}>
                          {y}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>

                <Field label="Date (MM/DD)" hint="僅輸入月/日，例如 08/28">
                  <div className="flex gap-2">
                    <Input value={dateMMDD} onChange={(e) => setDateMMDD(e.target.value)} placeholder="MM/DD" />
                    <Button
                      variant="outline"
                      type="button"
                      onClick={() => {
                        const d = new Date();
                        const mm = String(d.getMonth() + 1).padStart(2, "0");
                        const dd = String(d.getDate()).padStart(2, "0");
                        setDateMMDD(`${mm}/${dd}`);
                      }}
                    >
                      <Calendar className="w-4 h-4 mr-2" />
                      今天
                    </Button>
                  </div>
                </Field>

                <Field label="Python 路徑" hint="將呼叫此腳本執行需求計算">
                  <Input value={scriptPath} onChange={(e) => setScriptPath(e.target.value)} />
                </Field>

                <Field
                  label="Output 寫回路徑"
                  hint={!dryRun ? "非 Dry Run 時，這裡會更新為實際寫出的檔名（可能為 -OUTPUT- 時戳檔）" : undefined}
                >
                  {/* 讓整行更寬 */}
                  <div className="flex items-center gap-2 w-full">
                    {/* 文字框只顯示檔名，變得更長 */}
                    <Input
                      value={fileName || ""}          // ★ 只顯示檔名
                      readOnly
                      className="truncate bg-muted/50 cursor-not-allowed flex-1 min-w-0 px-3"
                      tabIndex={-1}
                      placeholder="輸出檔名（尚未產生）"
                    />

                    {/* 顯示檔名徽章（單擊複製完整路徑），拿掉雙擊開 Excel */}
                    {fileName && (
                      <Badge
                        role="button"
                        onClick={copyPath}             // ★ 單擊複製完整路徑（writeBackPath）
                        title="單擊複製完整路徑"
                        variant="outline"
                        className="truncate max-w-[320px] hover:bg-muted cursor-pointer select-none"
                      >
                        {fileName}
                        {copiedAt && <span className="ml-2 text-[10px] text-emerald-600">已複製</span>}
                      </Badge>
                    )}

                  </div>
                </Field>


                <Field label="Dry Run" right={dryRun ? <span className="text-xs text-muted-foreground">不寫回，只產生預覽</span> : undefined}>
                  <Switch checked={dryRun} onCheckedChange={setDryRun} />
                </Field>

                <div className="flex gap-2 justify-end">
                  <Button variant="ghost">
                    <Undo2 className="w-4 h-4 mr-1" />
                    Back
                  </Button>
                  <Button onClick={runDemand} disabled={running || !year || !dateMMDD || !scriptPath}>
                    {running ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        執行中...
                      </>
                    ) : (
                      <>
                        <Play className="w-4 h-4 mr-2" />
                        計算未來三週需求
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </ModuleCard>

            {/* 另外兩個模組維持版面平衡 */}
            <ModuleCard
              name="Beads 排程模組"
              desc="讀取 EN 試作/設備限制，整合庫存生成可行排程"
              status={schedRunning ? "running" : "ready"}
              footer={
                <div className="grid gap-3">
                  <div className="text-xs space-y-1 max-h-40 overflow-y-auto border p-2 rounded bg-muted/30">
                    {schedLogs.map((e, idx) => (
                      <div key={idx}>
                        <span className="text-gray-500">{e.ts}</span> {e.msg}
                      </div>
                    ))}
                  </div>

                  {schedPreview.length > 0 && (
                    <div className="overflow-x-auto mt-4">
                      <table className="min-w-full border text-xs">
                        <thead>
                          <tr className="bg-gray-100">
                            <th className="px-2 py-1 border">日期</th>
                            <th className="px-2 py-1 border">滴定機</th>
                            <th className="px-2 py-1 border">凍乾機</th>
                            <th className="px-2 py-1 border">料號</th>
                            <th className="px-2 py-1 border">數量</th>
                            <th className="px-2 py-1 border">備註</th>
                          </tr>
                        </thead>
                        <tbody>
                          {schedPreview.map((row, idx) => (
                            <tr key={idx}>
                              <td className="px-2 py-1 border">{row.date}</td>
                              <td className="px-2 py-1 border">{row.titrate}</td>
                              <td className="px-2 py-1 border">{row.freeze}</td>
                              <td className="px-2 py-1 border">{row.pn}</td>
                              <td className="px-2 py-1 border">{row.qty}</td>
                              <td className="px-2 py-1 border">{row.note}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              }
            >
              <div className="grid gap-4">
                {/* 當週第一天 */}
                <Field label="當週第一天 (MM/DD)" hint="會依序產生 6 天排程">
                  <div className="flex gap-2">
                    <Input value={schedMMDD} onChange={(e) => setSchedMMDD(e.target.value)} placeholder="MM/DD" />
                    <Button
                      variant="outline"
                      type="button"
                      onClick={() => {
                        const d = new Date();
                        const mm = String(d.getMonth() + 1).padStart(2, "0");
                        const dd = String(d.getDate()).padStart(2, "0");
                        setSchedMMDD(`${mm}/${dd}`);
                      }}
                    >
                      <Calendar className="w-4 h-4 mr-2" />
                      今天
                    </Button>
                  </div>
                  {!validSchedMMDD && schedMMDD && (
                    <div className="text-xs text-destructive mt-1">格式需為 MM/DD，例如 09/09</div>
                  )}
                </Field>

                {/* 需求檔（供排程） */}
                <Field label="需求檔來源" hint="Beads需求模組 Excel：可上傳/路徑/伺服器選檔">
                  <div className="flex gap-2 mb-2">
                    <Button variant={schedNeedSource === "upload" ? "default" : "outline"} onClick={() => setSchedNeedSource("upload")}>
                      <Upload className="w-4 h-4 mr-1" /> 上傳檔
                    </Button>
                    <Button variant={schedNeedSource === "path" ? "default" : "outline"} onClick={() => setSchedNeedSource("path")}>
                      <HardDrive className="w-4 h-4 mr-1" /> 輸入路徑
                    </Button>
                    <Button variant={schedNeedSource === "server" ? "default" : "outline"} onClick={() => setSchedNeedSource("server")}>
                      <FolderOpen className="w-4 h-4 mr-1" /> 伺服器選檔
                    </Button>
                  </div>

                  {schedNeedSource === "upload" && (
                    <div className="flex items-center gap-2">
                      <Input type="file" accept=".xlsx,.xlsm" onChange={(e) => setSchedNeedFile(e.target.files?.[0] ?? null)} />
                      <Button
                        type="button"
                        onClick={() => schedNeedFile && uploadExcel(schedNeedFile, "/api/upload/need-excel", setSchedNeedPath, setUploadingNeed)}
                        disabled={!schedNeedFile || uploadingNeed}
                      >
                        {uploadingNeed ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />上傳中...</> : <>上傳</>}
                      </Button>
                    </div>
                  )}

                  {schedNeedSource === "path" && (
                    <Input value={schedNeedPath} onChange={(e) => setSchedNeedPath(e.target.value)} placeholder="\\\\fls341\\MBBU_FAB\\...\\需求檔.xlsx" />
                  )}

                  {schedNeedSource === "server" && (
                    <div className="flex items-center gap-2">
                      <Button variant="outline" type="button" onClick={() => pickOnServer("need", setSchedNeedPath)}>
                        <FolderOpen className="w-4 h-4 mr-2" /> 選擇檔案
                      </Button>
                      <Input value={schedNeedPath} readOnly className="bg-muted/50" placeholder="尚未選擇" />
                    </div>
                  )}
                </Field>

                {/* 限制檔（配藥限制） */}
                <Field label="限制檔來源" hint="滴定限制 Excel（sheet: 配藥限制）">
                  <div className="flex gap-2 mb-2">
                    <Button variant={schedLimitSource === "upload" ? "default" : "outline"} onClick={() => setSchedLimitSource("upload")}>
                      <Upload className="w-4 h-4 mr-1" /> 上傳檔
                    </Button>
                    <Button variant={schedLimitSource === "path" ? "default" : "outline"} onClick={() => setSchedLimitSource("path")}>
                      <HardDrive className="w-4 h-4 mr-1" /> 輸入路徑
                    </Button>
                    <Button variant={schedLimitSource === "server" ? "default" : "outline"} onClick={() => setSchedLimitSource("server")}>
                      <FolderOpen className="w-4 h-4 mr-1" /> 伺服器選檔
                    </Button>
                  </div>

                  {schedLimitSource === "upload" && (
                    <div className="flex items-center gap-2">
                      <Input type="file" accept=".xlsx,.xlsm" onChange={(e) => setSchedLimitFile(e.target.files?.[0] ?? null)} />
                      <Button
                        type="button"
                        onClick={() => schedLimitFile && uploadExcel(schedLimitFile, "/api/upload/limit-excel", setSchedLimitPath, setUploadingLimit)}
                        disabled={!schedLimitFile || uploadingLimit}
                      >
                        {uploadingLimit ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />上傳中...</> : <>上傳</>}
                      </Button>
                    </div>
                  )}

                  {schedLimitSource === "path" && (
                    <Input value={schedLimitPath} onChange={(e) => setSchedLimitPath(e.target.value)} placeholder="\\\\fls341\\MBBU_FAB\\...\\滴定限制.xlsx" />
                  )}

                  {schedLimitSource === "server" && (
                    <div className="flex items-center gap-2">
                      <Button variant="outline" type="button" onClick={() => pickOnServer("limit", setSchedLimitPath)}>
                        <FolderOpen className="w-4 h-4 mr-2" /> 選擇檔案
                      </Button>
                      <Input value={schedLimitPath} readOnly className="bg-muted/50" placeholder="尚未選擇" />
                    </div>
                  )}
                </Field>

                {/* 空白模板 */}
                <Field label="空白排程模板">
                  <div className="flex items-center gap-2">
                    <Input value={tmplPath} onChange={(e) => setTmplPath(e.target.value)} placeholder="\\\\fls341\\MBBU_FAB\\MB_PD\\生管自動化\\滴定\\空白排程.xlsm" />
                    <Button variant="outline" type="button" onClick={() => pickOnServer("template", setTmplPath)}>
                      <FolderOpen className="w-4 h-4 mr-2" /> 伺服器選擇
                    </Button>
                  </div>
                </Field>

                {/* 輸出資料夾 */}
                <Field label="輸出資料夾" hint="預設輸出到 beadsSchedule；會產生 beads排程_yyyymmdd_1..6.xlsm">
                  <div className="flex items-center gap-2">
                    <Input value={outDir} onChange={(e) => setOutDir(e.target.value)} placeholder="\\\\fls341\\MBBU_FAB\\MB_PD\\生管自動化\\滴定\\beadsSchedule" />
                    <Button variant="outline" type="button" onClick={() => pickOnServer("outdir", setOutDir)}>
                      <FolderOpen className="w-4 h-4 mr-2" /> 選擇資料夾
                    </Button>
                  </div>
                </Field>

                {/* 共用 DryRun（沿用上方的 dryRun 狀態） */}
                <Field label="Dry Run" right={dryRun ? <span className="text-xs text-muted-foreground">不另存，僅預覽</span> : undefined}>
                  <Switch checked={dryRun} onCheckedChange={setDryRun} />
                </Field>

                {/* 操作 */}
                <div className="flex gap-2 justify-end">
                  <Button variant="ghost">
                    <Undo2 className="w-4 h-4 mr-1" />
                    Back
                  </Button>
                  <Button onClick={runSchedule} disabled={schedRunning || !canRunSchedule}>
                    {schedRunning ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        產生一週排程
                      </>
                    ) : (
                      <>
                        <Play className="w-4 h-4 mr-2" />
                        產生一週排程
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </ModuleCard>
          </div>
        </TabsContent>
      </Tabs>

      <footer className="text-xs text-muted-foreground pt-6 border-t">
        <div className="flex items-center gap-2">
          <FileOutput className="w-3 h-3" />
          v0.5 UI — / 移除開資料夾 / 徽章雙擊直接開 Excel
        </div>
      </footer>
    </div>
  );
}
