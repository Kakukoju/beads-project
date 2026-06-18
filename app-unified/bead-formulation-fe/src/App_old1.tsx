/*
  配藥紀錄：Vite + React + TypeScript (單檔可貼用)
  -------------------------------------------------
  ✅ 一鍵建立 → 自動伺服器端存檔 → 回傳路徑提示
  ✅ WINDOWS 檔案選擇上傳 Excel
  ✅ 輸入工單號碼
  ✅ 自動呼叫後端流程並提示儲存位置
  ✅ 指定 Excel Cells 產生 QR（以實際儲存後檔案為來源）

  建置：
    - Vite + React + TS + Tailwind + shadcn/ui
    - 直接將本檔案當作 App.tsx 使用
*/

import { useMemo, useRef, useState, useEffect } from "react";

import {
  Upload,
  Save,
  Loader2,
  Settings,
  FolderOpen,
  FileSpreadsheet,
  HardDrive,
  FileOutput,
  Play,
  Download,
  Server,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
// 本地簡易分隔線（避免 shadcn 未安裝導致 TS 錯誤）
const Separator = () => <div className="h-px bg-zinc-200 my-2" />;

const CONFIG = {
  API_BASE: (window as any).ENV?.API_BASE || "/api",
  // ✅ Windows 網路路徑：使用雙反斜線並以反斜線結尾
  DEFAULT_SERVER_DIR: "\\\\fls341\\Reagent RD\\配藥端 -配製紀錄表\\",
  DEFAULT_FILE_PREFIX: "配藥紀錄_",
};

// === Helpers ===
async function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.readAsDataURL(blob);
  });
}

function classNames(...xs: Array<string | false | null | undefined>) {
  return xs.filter(Boolean).join(" ");
}

// 開發環境自檢
function devSelfTest() {
  if (typeof window !== "undefined" && !(import.meta as any).env?.PROD) {
    console.assert(CONFIG.DEFAULT_SERVER_DIR.endsWith("\\"), "DEFAULT_SERVER_DIR 必須以反斜線結尾");
    console.assert(CONFIG.DEFAULT_SERVER_DIR.includes("\\\\"), "DEFAULT_SERVER_DIR 需使用雙反斜線跳脫");
  }
}

// ===== Types =====
export interface PreviewResp {
  ok: boolean;
  headers?: string[];
  rows?: (string | number | null)[][];
  message?: string;
}

type Step =
  | "idle"
  | "uploading"
  | "uploaded"
  | "creating"
  | "created"
  | "saving"
  | "saved"
  | "previewing"
  | "previewed"
  | "qr";

export default function App() {
  const [excelFile, setExcelFile] = useState<File | null>(null);
  const [tempId, setTempId] = useState<string | null>(null);
  const [workOrder, setWorkOrder] = useState<string>("");
  const [fileName, setFileName] = useState<string>("");
  const [serverDir, setServerDir] = useState<string>(CONFIG.DEFAULT_SERVER_DIR);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [step, setStep] = useState<Step>("idle");

  const [preview, setPreview] = useState<PreviewResp | null>(null);
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);
  const [qrCells, setQrCells] = useState<string[]>(["V6"]);
  const [qrJoiner, setQrJoiner] = useState<string>("|");

  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    devSelfTest();
  }, []);

  useEffect(() => {
    if (workOrder.trim()) {
      setFileName(`${CONFIG.DEFAULT_FILE_PREFIX}${workOrder.trim()}.xlsm`);
    }
  }, [workOrder]);

  const canCreate = useMemo(() => !!(tempId && workOrder.trim()), [tempId, workOrder]);

  const statusBadge = useMemo(() => {
    const map: Record<Step, { label: string; variant: "default" | "secondary" | "destructive" | "outline" }> = {
      idle: { label: "待機", variant: "secondary" },
      uploading: { label: "上傳中", variant: "outline" },
      uploaded: { label: "已上傳", variant: "default" },
      creating: { label: "建立中", variant: "outline" },
      created: { label: "已建立", variant: "default" },
      saving: { label: "儲存中", variant: "outline" },
      saved: { label: "已儲存", variant: "default" },
      previewing: { label: "讀取預覽", variant: "outline" },
      previewed: { label: "已預覽", variant: "default" },
      qr: { label: "已產生 QR", variant: "default" },
    } as const;
    return map[step];
  }, [step]);

  // ===== Handlers =====
  async function handleUpload() {
    try {
      setError(null);
      if (!excelFile) return setError("請先選擇 Excel 檔案");
      setLoading(true);
      setStep("uploading");

      const fd = new FormData();
      fd.append("file", excelFile);
      const resp = await fetch(`${CONFIG.API_BASE}/upload_excel`, { method: "POST", body: fd });
      if (!resp.ok) throw new Error(`upload_excel HTTP ${resp.status}`);
      const data = await resp.json();
      if (!data?.ok) throw new Error(data?.message || "上傳失敗");
      setTempId(String(data.temp_id));
      setStep("uploaded");
    } catch (e: any) {
      setError(e.message || String(e));
      setStep("idle");
    } finally {
      setLoading(false);
    }
  }

  async function handleCreate() {
    try {
      setError(null);
      if (!canCreate) return setError("請先上傳 Excel 並輸入工單號碼");
      setLoading(true);
      setStep("creating");

      const resp = await fetch(`${CONFIG.API_BASE}/create_record`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ work_order: workOrder.trim(), temp_id: tempId }),
      });
      if (!resp.ok) throw new Error(`create_record HTTP ${resp.status}`);
      const data = await resp.json();
      if (!data?.ok) throw new Error(data?.message || "建立失敗");

      setStep("created");
    } catch (e: any) {
      setError(e.message || String(e));
      setStep("uploaded");
    } finally {
      setLoading(false);
    }
  }

  async function handlePreview() {
    try {
      setError(null);
      setLoading(true);
      setStep("previewing");

      const qs = new URLSearchParams({ work_order: workOrder.trim() });
      const resp = await fetch(`${CONFIG.API_BASE}/template_preview?${qs.toString()}`);
      if (!resp.ok) throw new Error(`template_preview HTTP ${resp.status}`);
      const data: PreviewResp = await resp.json();
      if (!data?.ok) throw new Error(data?.message || "讀取預覽失敗");

      setPreview(data);
      setStep("previewed");
    } catch (e: any) {
      setError(e.message || String(e));
      setStep("created");
    } finally {
      setLoading(false);
    }
  }

  async function handleGenerateQrFromSaved(savedPath: string) {
    const resp = await fetch(`${CONFIG.API_BASE}/qr_png_from_cells`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        work_order: workOrder.trim(),
        file_path: savedPath, // ✅ 使用真正儲存後的檔案
        cells: qrCells.filter((c) => c.trim().length > 0),
        joiner: qrJoiner,
      }),
    });
    if (!resp.ok) throw new Error(`qr_png_from_cells HTTP ${resp.status}`);
    const blob = await resp.blob();
    const url = await blobToDataUrl(blob);
    setQrDataUrl(url);
    setStep("qr");
  }

  async function handleDownloadExcel() {
    try {
      setError(null);
      setLoading(true);

      const qs = new URLSearchParams({ work_order: workOrder.trim() });
      const resp = await fetch(`${CONFIG.API_BASE}/template_file?${qs.toString()}`);
      if (!resp.ok) throw new Error(`template_file HTTP ${resp.status}`);
      const blob = await resp.blob();

      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${CONFIG.DEFAULT_FILE_PREFIX}${workOrder.trim() || "未命名"}.xlsm`;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function handleServerSave() {
    try {
      setError(null);
      setLoading(true);
      setStep("saving");

      const payload = { work_order: workOrder.trim(), server_dir: serverDir.trim(), filename: fileName.trim() };
      const resp = await fetch(`${CONFIG.API_BASE}/save_template`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) throw new Error(`save_template HTTP ${resp.status}`);
      const data = await resp.json();
      if (!data?.ok) throw new Error(data?.message || "伺服器儲存失敗");

      setStep("saved");
      try {
        await handleGenerateQrFromSaved(String(data.saved_path));
      } catch {
        /* ignore */
      }
      alert(`✅ 已儲存：\n${data.saved_path}`);
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  async function handleOneClick() {
    try {
      setError(null);
      if (!excelFile) return setError("請先選擇 Excel 檔案");
      if (!workOrder.trim()) return setError("請先輸入工單號碼");
      setLoading(true);

      // 1) 如果尚未上傳，先上傳 Excel
      if (!tempId) {
        setStep("uploading");
        const fd = new FormData();
        fd.append("file", excelFile);
        const up = await fetch(`${CONFIG.API_BASE}/upload_excel`, { method: "POST", body: fd });
        if (!up.ok) throw new Error(`upload_excel HTTP ${up.status}`);
        const upData = await up.json();
        if (!upData?.ok) throw new Error(upData?.message || "上傳失敗");
        setTempId(String(upData.temp_id));
        setStep("uploaded");
      }

      // 2) 建立配藥紀錄
      setStep("creating");
      const make = await fetch(`${CONFIG.API_BASE}/create_record`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ work_order: workOrder.trim(), temp_id: tempId }),
      });
      if (!make.ok) throw new Error(`create_record HTTP ${make.status}`);
      const mkData = await make.json();
      if (!mkData?.ok) throw new Error(mkData?.message || "建立失敗");
      setStep("created");

      // 3) 伺服器端存檔
      setStep("saving");
      const fname = fileName?.trim() || `${CONFIG.DEFAULT_FILE_PREFIX}${workOrder.trim()}.xlsm`;
      const save = await fetch(`${CONFIG.API_BASE}/save_template`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ work_order: workOrder.trim(), server_dir: serverDir.trim(), filename: fname }),
      });
      if (!save.ok) throw new Error(`save_template HTTP ${save.status}`);
      const svData = await save.json();
      if (!svData?.ok) throw new Error(svData?.message || "伺服器儲存失敗");
      setStep("saved");

      // 4) 產生 QR（以實際儲存後的檔案為來源）
      try {
        await handleGenerateQrFromSaved(String(svData.saved_path));
      } catch {
        /* ignore */
      }

      alert(`✅ 一鍵完成！\n已儲存：${svData.saved_path}`);
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  // ===== UI =====
  return (
    <div className="min-h-screen bg-white text-zinc-900">
      <div className="max-w-6xl mx-auto p-6 space-y-6">
        <header className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Settings className="w-6 h-6" />
            <h1 className="text-2xl font-semibold tracking-wider">配藥紀錄建立平台</h1>
            <Badge variant="outline" className="ml-2">Vite · React · TS</Badge>
          </div>
          <div>
            <Badge variant={statusBadge.variant}>{statusBadge.label}</Badge>
          </div>
        </header>

        {error && (
          <Card className="border-red-200 bg-red-50">
            <CardContent className="p-4 text-red-700 text-sm">{String(error)}</CardContent>
          </Card>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* 左：檔案與工單 */}
          <Card className="bg-white border-zinc-200 col-span-1">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FolderOpen className="w-5 h-5" /> 檔案與工單
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label>選擇配藥表 Excel</Label>
                <div className="flex items-center gap-2">
                  <Input
                    type="file"
                    accept=".xls,.xlsx,.xlsm"
                    ref={fileInputRef}
                    onChange={(e) => setExcelFile(e.target.files?.[0] || null)}
                  />
                  <Button variant="secondary" onClick={() => fileInputRef.current?.click()}>
                    <Upload className="w-4 h-4 mr-2" /> 選擇檔案
                  </Button>
                </div>
                {excelFile && <div className="text-xs text-zinc-600">已選：{excelFile.name}</div>}
              </div>

              <Separator />

              <div className="space-y-2">
                <Label>工單號碼</Label>
                <Input
                  placeholder="請輸入工單號碼"
                  value={workOrder}
                  onChange={(e) => setWorkOrder(e.target.value)}
                />
              </div>

              <div className="flex flex-wrap gap-2 pt-2">
                <Button onClick={handleOneClick} disabled={loading || !excelFile || !workOrder.trim()}>
                  {loading ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <Save className="w-4 h-4 mr-2" />
                  )}
                  一鍵建立並儲存
                </Button>

                <Button onClick={handleUpload} disabled={loading || !excelFile}>
                  {loading && step === "uploading" ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <FileSpreadsheet className="w-4 h-4 mr-2" />
                  )}
                  上傳 Excel
                </Button>

                <Button onClick={handleCreate} disabled={loading || !canCreate}>
                  {loading && step === "creating" ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <Play className="w-4 h-4 mr-2" />
                  )}
                  執行創建配藥紀錄
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* 右：預覽與輸出 */}
          <Card className="bg-white border-zinc-200 col-span-2">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileOutput className="w-5 h-5" /> 模板資料預覽
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-2">
                <Button variant="outline" onClick={handlePreview} disabled={loading || !workOrder}>
                  {loading && step === "previewing" ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <HardDrive className="w-4 h-4 mr-2" />
                  )}
                  重新讀取預覽
                </Button>

                <Button variant="secondary" onClick={handleDownloadExcel} disabled={loading || !workOrder}>
                  <Download className="w-4 h-4 mr-2" /> 下載 Excel
                </Button>
              </div>

              <div className="rounded-xl border border-zinc-200 overflow-hidden">
                <div className="max-h-[400px] overflow-auto">
                  {preview?.ok && preview.headers && preview.rows ? (
                    <table className="w-full text-sm">
                      <thead className="sticky top-0 bg-zinc-100">
                        <tr>
                          {preview.headers.map((h, i) => (
                            <th
                              key={i}
                              className="text-left font-medium px-3 py-2 border-b border-zinc-200 whitespace-nowrap"
                            >
                              {h}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {preview.rows.map((r, i) => (
                          <tr key={i} className={classNames(i % 2 ? "bg-zinc-50" : "bg-white")}>
                            {r.map((c, j) => (
                              <td key={j} className="px-3 py-2 border-b border-zinc-200 align-top">
                                {c === null ? "" : String(c)}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <div className="text-zinc-500 text-sm p-6">
                      尚無預覽，請先『執行創建配藥紀錄』或點『重新讀取預覽』。
                    </div>
                  )}
                </div>
              </div>

              {/* QR 區塊 */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-center">
                <div className="md:col-span-2 space-y-2">
                  <div className="text-sm text-zinc-600">
                    工單：<span className="text-zinc-900 font-mono">{workOrder || "(未填)"}</span>
                  </div>
                  <div className="grid sm:grid-cols-2 gap-3">
                    <div>
                      <Label>QR 來源 Cells（可多個）</Label>
                      {qrCells.map((cell, idx) => (
                        <div key={idx} className="flex gap-2 mt-1">
                          <Input
                            placeholder="例如：V6 或 B3 或 Sheet1!A1"
                            value={cell}
                            onChange={(e) => {
                              const next = [...qrCells];
                              next[idx] = e.target.value;
                              setQrCells(next);
                            }}
                          />
                          <Button
                            variant="secondary"
                            onClick={() => setQrCells(qrCells.filter((_, i) => i !== idx))}
                            disabled={qrCells.length === 1}
                          >
                            刪除
                          </Button>
                        </div>
                      ))}
                      <Button variant="outline" className="mt-2" onClick={() => setQrCells([...qrCells, ""]) }>
                        新增一列
                      </Button>
                    </div>

                    <div>
                      <Label>合併字元（Joiner）</Label>
                      <Input className="mt-1" value={qrJoiner} onChange={(e) => setQrJoiner(e.target.value)} />
                      <div className="text-xs text-zinc-500 mt-1">
                        實際資料來自伺服器端『已儲存檔案』所讀取的這些 cells。
                      </div>
                      <Button className="mt-2" onClick={async () => { try { await handleServerSave(); } catch { /* no-op */ } }}>
                        以目前設定重新儲存並產生 QR
                      </Button>
                    </div>
                  </div>
                </div>
                <div className="md:col-span-1 flex items-center justify-center">
                  {qrDataUrl ? (
                    <img
                      src={qrDataUrl}
                      alt="QR Code"
                      className="w-40 h-40 bg-white p-2 rounded-md border border-zinc-200"
                    />
                  ) : (
                    <div className="text-zinc-600 text-sm">尚未產生 QR</div>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* 儲存區塊（固定伺服器端存檔） */}
        <Card className="bg-white border-zinc-200">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Server className="w-4 h-4" /> 伺服器端存檔
            </CardTitle>
          </CardHeader>
          <CardContent className="grid sm:grid-cols-3 gap-3">
            <div className="sm:col-span-2 space-y-2">
              <Label>伺服器資料夾</Label>
              <Input value={serverDir} onChange={(e) => setServerDir(e.target.value)} />
              <Label className="mt-2">檔名</Label>
              <Input value={fileName} onChange={(e) => setFileName(e.target.value)} />
            </div>
            <div className="sm:col-span-1 flex items-end">
              <Button className="w-full" onClick={handleServerSave} disabled={loading || !workOrder}>
                <Save className="w-4 h-4 mr-2" /> 伺服器儲存
              </Button>
            </div>
          </CardContent>
        </Card>

        <footer className="text-xs text-zinc-600 pt-2">
          後端需負責：① 呼叫 Excel COM InsertNewByWorkOrderArrays（manuinsert 模組） ② 上傳 DB 與從 DB 回填模板 ③ 在伺服器路徑上存檔（固定伺服器端存檔流程）。
        </footer>
      </div>
    </div>
  );
}
