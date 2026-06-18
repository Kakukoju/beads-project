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
import { Loader2, Play, Undo2, FileOutput, Settings, Calendar, TerminalSquare } from "lucide-react";
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
      <Card className="rounded-2xl shadow-sm">
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

  const copyPath = async () => {
    if (!writeBackPath) return;
    try {
      await navigator.clipboard.writeText(writeBackPath);
    } finally {
      setCopiedAt(Date.now());
      setTimeout(() => setCopiedAt(null), 1500);
    }
  };

  // 直接叫後端製作 Excel deeplink（ms-excel:ofe|u|...）
  const openInExcel = async () => {
    if (!writeBackPath) return;
    try {
      const r = await fetch(`/api/excel-deeplink?path=${encodeURIComponent(writeBackPath)}`);
      const data = await r.json();
      if (data?.ok && data?.deeplink) {
        window.location.href = data.deeplink;
      }
    } catch (e) {
      // 可加 toast
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
    <div className="p-6 md:p-10 space-y-8">
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
          <SectionTitle title="排程產生系統" subtitle="包含三個模組，每個模組皆有 Input / 執行 / Output / Back" />

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
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
                  <div className="flex items-center gap-2">
                    <Input
                      value={writeBackPath}
                      readOnly
                      title={writeBackPath}
                      className="truncate bg-muted/50 cursor-not-allowed flex-[3]"
                      tabIndex={-1}
                      placeholder="\\\\fls341\\...\\beads 需求模組.xlsx"
                    />

                    {fileName && (
                      <Badge
                        role="button"
                        onClick={copyPath}           // 單擊複製
                        onDoubleClick={openInExcel}  // 雙擊直接用 Excel 開啟
                        title="單擊複製路徑 / 雙擊用 Excel 開啟"
                        variant="outline"
                        className="truncate max-w-[200px] hover:bg-muted cursor-pointer select-none flex-[1]"
                      >
                        {baseName}
                        {suffix && <span className="text-gray-500 ml-1">{suffix}</span>}
                        {copiedAt && <span className="ml-2 text-[10px] text-emerald-600">已複製</span>}
                      </Badge>
                    )}

                    {/* 用 Excel 開啟 */}
                    <Button
                      type="button"
                      variant="default"
                      size="sm"
                      onClick={openInExcel}
                      disabled={!writeBackPath}
                      title="用桌面版 Excel 直接開啟"
                      className="flex-none"
                    >
                      用 Excel 開啟
                    </Button>
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
            <ModuleCard name="Beads 排程限制模組" desc="讀取 EN 試作/設備限制，整合庫存生成可行排程" status="idle">
              <PlaceholderIO />
            </ModuleCard>

            <ModuleCard name="空白 Beads 排程表模組" desc="產生空白模板供人工調整" status="idle">
              <PlaceholderIO />
            </ModuleCard>
          </div>
        </TabsContent>
      </Tabs>

      <footer className="text-xs text-muted-foreground pt-6 border-t">
        <div className="flex items-center gap-2">
          <FileOutput className="w-3 h-3" />
          v0.5 UI — Excel Deeplink / 移除開資料夾 / 徽章雙擊直接開 Excel
        </div>
      </footer>
    </div>
  );
}
