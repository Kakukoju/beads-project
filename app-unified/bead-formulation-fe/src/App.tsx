// App.tsx
import React, { useEffect, useMemo, useRef, useState } from "react";

/** ====== 可調整區 ====== **/
const CONFIG = {
  API_BASE: "http://localhost:8055/api",   // ← 直接打 Flask
  DEFAULT_SERVER_DIR: "\\\\fls341\\Reagent RD\\配藥端 -配製紀錄表\\",
};


const PREFIX_DIR_MAP: Array<[RegExp, string]> = [
  [/^ALP配藥表/i, "\\\\fls341\\Reagent RD\\配藥端 -配製紀錄表\\ALP\\"],
  [/^BAP配藥表/i, "\\\\fls341\\Reagent RD\\配藥端 -配製紀錄表\\BAP\\"],
  [/^TMA配藥表/i, "\\\\fls341\\Reagent RD\\配藥端 -配製紀錄表\\TMA\\"],
  // 需要可自行繼續擴充
];

/** ====== 型別 ====== **/
type Step = "idle" | "uploading" | "uploaded" | "creating" | "created" | "previewing" | "previewed" | "saving" | "saved" | "qr";

interface UploadResp {
  ok: boolean;
  temp_id?: string;
  filename?: string;
  sheets?: string[];
  ingested?: any;
  message?: string;
}

interface CreateResp {
  ok: boolean;
  filled?: number;
  out_path?: string;
  table?: string;
  message?: string;
}

interface PreviewResp {
  ok: boolean;
  headers?: string[];
  rows?: (string | number | null)[][];
  message?: string;
}

interface SaveResp {
  ok: boolean;
  saved_path?: string;
  message?: string;
}

/** ====== 小工具 ====== **/
function guessServerDirByNameClient(filename: string | null): string | null {
  if (!filename) return null;
  const base = filename.replace(/^.*[\\/]/, "").replace(/\.(xlsx|xlsm|xls)$/i, "");
  for (const [pat, dir] of PREFIX_DIR_MAP) if (pat.test(base)) return dir;
  return null;
}

// 「配藥表…」→ 「配藥紀錄…」並固定 .xlsm
function suggestServerFilename(srcName: string | null): string | null {
  if (!srcName) return null;
  const nameOnly = srcName.replace(/^.*[\\/]/, "");
  const base = nameOnly.replace(/\.(xlsx|xlsm|xls)$/i, "");
  if (!base.includes("配藥表")) return null;
  const rep = base.replace("配藥表", "配藥紀錄");
  return `${rep}.xlsm`;
}

async function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.readAsDataURL(blob);
  });
}

/** ====== 主元件 ====== **/
export default function App() {
  // 檔案 / 上傳
  const [excelFile, setExcelFile] = useState<File | null>(null);
  const [srcFileName, setSrcFileName] = useState<string>("");
  const [isValidSrcName, setIsValidSrcName] = useState<boolean>(false);

  // 後端狀態
  const [tempId, setTempId] = useState<string | null>(null);
  const [availableSheets, setAvailableSheets] = useState<string[]>([]);
  const [selectedSheet, setSelectedSheet] = useState<string>("");

  // 業務欄位
  const [workOrder, setWorkOrder] = useState<string>("");

  // 儲存路徑與檔名
  const [serverDir, setServerDir] = useState<string>(CONFIG.DEFAULT_SERVER_DIR);
  const [serverFileName, setServerFileName] = useState<string>("");
  const [userEditedFileName, setUserEditedFileName] = useState<boolean>(false);

  // 預覽 / QR
  const [preview, setPreview] = useState<PreviewResp | null>(null);
  const [qrCells, setQrCells] = useState<string[]>(["V6"]);
  const [qrJoiner, setQrJoiner] = useState<string>("|");
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);

  // UI
  const [step, setStep] = useState<Step>("idle");
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!userEditedFileName && isValidSrcName && srcFileName) {
      const sug = suggestServerFilename(srcFileName);
      setServerFileName(sug || "");
    }
  }, [srcFileName, isValidSrcName, userEditedFileName]);

  const canCreate = useMemo(() => !!(tempId && workOrder.trim() && (selectedSheet || availableSheets[0])), [tempId, workOrder, selectedSheet, availableSheets]);

  /** ====== Handlers ====== **/
  function onExcelFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] || null;
    if (!f) {
      setExcelFile(null);
      setSrcFileName("");
      setIsValidSrcName(false);
      return;
    }
    // 必須包含「配藥表」
    if (!/配藥表/.test(f.name)) {
      setExcelFile(null);
      setSrcFileName("");
      setIsValidSrcName(false);
      setServerFileName("");
      setError("所選檔名未包含「配藥表」，請重新選擇正確的配藥表 Excel。");
      e.target.value = "";
      return;
    }

    setExcelFile(f);
    setSrcFileName(f.name);
    setIsValidSrcName(true);
    setError(null);

    // 按檔名猜路徑（立即顯示）
    const dirGuess = guessServerDirByNameClient(f.name);
    setServerDir(dirGuess || CONFIG.DEFAULT_SERVER_DIR);

    // 依檔名自動轉成「配藥紀錄… .xlsm」
    if (!userEditedFileName) {
      setServerFileName(suggestServerFilename(f.name) || "");
    }
  }

  async function handleUpload() {
    try {
      setError(null);
      if (!excelFile) return setError("請先選擇 Excel 檔案");
      if (!isValidSrcName) return setError("所選檔名未包含「配藥表」，請重選");

      setLoading(true);
      setStep("uploading");

      const fd = new FormData();
      fd.append("file", excelFile);

      const resp = await fetch(`${CONFIG.API_BASE}/upload_excel`, { method: "POST", body: fd });
      if (!resp.ok) {
        const t = await resp.text().catch(() => "");
        throw new Error(`upload_excel HTTP ${resp.status} - ${t.slice(0, 200)}`);
      }
      const data: UploadResp = await resp.json();
      if (!data.ok || !data.temp_id) throw new Error(data.message || "上傳失敗");

      setTempId(data.temp_id);
      setAvailableSheets(data.sheets || []);
      setSelectedSheet((data.sheets && data.sheets[0]) || "");
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
      if (!canCreate) return setError("請先上傳 Excel、輸入工單號碼，並選取工作表");
      setLoading(true);
      setStep("creating");

      const body = {
        work_order: workOrder.trim(),
        temp_id: tempId,
        table: selectedSheet, // 後端會自動正規化表名
      };
      const resp = await fetch(`${CONFIG.API_BASE}/create_record`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const t = await resp.text().catch(() => "");
        throw new Error(`create_record HTTP ${resp.status} - ${t.slice(0, 200)}`);
      }
      const data: CreateResp = await resp.json();
      if (!data.ok) throw new Error(data.message || "建立失敗");

      setStep("created");
      // 建立後可直接載入預覽
      await handlePreview();
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
      if (!tempId) return setError("請先上傳並建立暫存檔");
      setLoading(true);
      setStep("previewing");

      const resp = await fetch(`${CONFIG.API_BASE}/template_preview?temp_id=${encodeURIComponent(tempId)}`);
      if (!resp.ok) throw new Error(`template_preview HTTP ${resp.status}`);
      const data: PreviewResp = await resp.json();
      if (!data.ok) throw new Error(data.message || "讀取預覽失敗");

      setPreview(data);
      setStep("previewed");
    } catch (e: any) {
      setError(e.message || String(e));
      setStep("created");
    } finally {
      setLoading(false);
    }
  }

  async function handleDownloadExcel() {
    try {
      setError(null);
      if (!tempId) return setError("沒有暫存檔可下載");
      setLoading(true);

      const resp = await fetch(`${CONFIG.API_BASE}/template_file?temp_id=${encodeURIComponent(tempId)}`);
      if (!resp.ok) throw new Error(`template_file HTTP ${resp.status}`);

      const blob = await resp.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `配藥紀錄_${workOrder || "未命名"}.xlsm`;
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
      if (!tempId) return setError("請先上傳 Excel");
      if (!workOrder.trim()) return setError("請先輸入工單號碼");
      if (!serverFileName.trim()) return setError("伺服器儲存檔名為空");

      setLoading(true);
      setStep("saving");

      const resp = await fetch(`${CONFIG.API_BASE}/save_template`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          temp_id: tempId,
          work_order: workOrder.trim(),
          server_dir: serverDir.trim(),
          filename: serverFileName.trim().endsWith(".xlsm") ? serverFileName.trim() : `${serverFileName.trim()}.xlsm`,
        }),
      });
      if (!resp.ok) {
        const t = await resp.text().catch(() => "");
        throw new Error(`save_template HTTP ${resp.status} - ${t.slice(0, 200)}`);
      }
      const data: SaveResp = await resp.json();
      if (!data.ok || !data.saved_path) throw new Error(data.message || "伺服器儲存失敗");

      setStep("saved");
      alert(`✅ 已儲存：\n${data.saved_path}`);

      // 儲存成功後自動產 QR（以實際儲存檔案為來源）
      try {
        const qrResp = await fetch(`${CONFIG.API_BASE}/qr_png_from_cells`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            work_order: workOrder.trim(),
            file_path: data.saved_path,
            cells: qrCells.filter((c) => c.trim().length > 0),
            joiner: qrJoiner,
          }),
        });
        if (qrResp.ok) {
          const b = await qrResp.blob();
          setQrDataUrl(await blobToDataUrl(b));
          setStep("qr");
        }
      } catch {
        // ignore
      }
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
      if (!/配藥表/.test(excelFile.name)) return setError("所選檔名未包含「配藥表」，請重選");
      if (!workOrder.trim()) return setError("請先輸入工單號碼");

      setLoading(true);

      // 1) 上傳
      if (!tempId) {
        setStep("uploading");
        const fd = new FormData();
        fd.append("file", excelFile);
        const up = await fetch(`${CONFIG.API_BASE}/upload_excel`, { method: "POST", body: fd });
        if (!up.ok) throw new Error(`upload_excel HTTP ${up.status}`);
        const u: UploadResp = await up.json();
        if (!u.ok || !u.temp_id) throw new Error(u.message || "上傳失敗");
        setTempId(u.temp_id);
        setAvailableSheets(u.sheets || []);
        setSelectedSheet((u.sheets && u.sheets[0]) || "");
        setStep("uploaded");
      }

      // 2) 建立
      setStep("creating");
      const mk = await fetch(`${CONFIG.API_BASE}/create_record`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ work_order: workOrder.trim(), temp_id: tempId, table: selectedSheet }),
      });
      if (!mk.ok) throw new Error(`create_record HTTP ${mk.status}`);
      const mkData: CreateResp = await mk.json();
      if (!mkData.ok) throw new Error(mkData.message || "建立失敗");
      setStep("created");

      // 3) 儲存
      setStep("saving");
      const fname = serverFileName?.trim() || suggestServerFilename(srcFileName) || "";
      if (!fname) throw new Error("伺服器儲存檔名為空");
      const sv = await fetch(`${CONFIG.API_BASE}/save_template`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          temp_id: tempId,
          work_order: workOrder.trim(),
          server_dir: serverDir.trim(),
          filename: fname.endsWith(".xlsm") ? fname : `${fname}.xlsm`,
        }),
      });
      if (!sv.ok) throw new Error(`save_template HTTP ${sv.status}`);
      const svData: SaveResp = await sv.json();
      if (!svData.ok || !svData.saved_path) throw new Error(svData.message || "伺服器儲存失敗");
      setStep("saved");

      // 4) 產 QR
      try {
        const qrResp = await fetch(`${CONFIG.API_BASE}/qr_png_from_cells`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            work_order: workOrder.trim(),
            file_path: svData.saved_path,
            cells: qrCells.filter((c) => c.trim().length > 0),
            joiner: qrJoiner,
          }),
        });
        if (qrResp.ok) {
          const blob = await qrResp.blob();
          setQrDataUrl(await blobToDataUrl(blob));
          setStep("qr");
        }
      } catch {}

      alert(`✅ 一鍵完成！\n已儲存：${svData.saved_path}`);
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  /** ====== UI ====== **/
  const statusText: Record<Step, string> = {
    idle: "待機",
    uploading: "上傳中",
    uploaded: "已上傳",
    creating: "建立中",
    created: "已建立",
    previewing: "讀取預覽",
    previewed: "已預覽",
    saving: "儲存中",
    saved: "已儲存",
    qr: "已產生 QR",
  };

  return (
    <div className="min-h-screen bg-white text-zinc-900">
      <div className="max-w-6xl mx-auto p-6 space-y-6">
        <header className="flex items-center justify-between">
          <div className="text-2xl font-semibold tracking-wider">配藥紀錄建立平台</div>
          <div className="text-sm px-2 py-1 rounded border border-zinc-200 bg-zinc-50">{statusText[step]}</div>
        </header>

        {error && (
          <div className="border border-red-200 bg-red-50 text-red-700 text-sm p-3 rounded">{error}</div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* 左：檔案與工單 */}
          <div className="border border-zinc-200 rounded-lg p-4 space-y-4 lg:col-span-1">
            <div className="space-y-2">
              <div className="font-medium">選擇配藥表 Excel（檔名需含「配藥表」）</div>
              {/* ✅ 原生 file input */}
              <input
                type="file"
                accept=".xls,.xlsx,.xlsm"
                ref={fileInputRef}
                onChange={onExcelFileChange}
                className="block w-full rounded-md border border-zinc-300 px-3 py-2 text-sm file:mr-3 file:rounded-md file:border-0 file:bg-zinc-100 file:px-3 file:py-1 file:text-sm"
              />
              {srcFileName && <div className="text-xs text-zinc-600">已選：{srcFileName}</div>}
            </div>

            <div className="h-px bg-zinc-200 my-2" />

            <div className="space-y-2">
              <div className="font-medium">工單號碼</div>
              <input
                value={workOrder}
                onChange={(e) => setWorkOrder(e.target.value)}
                placeholder="請輸入工單號碼，例如：TMRA25I177"
                className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm"
              />
            </div>

            {/* Sheet 選擇（上傳後顯示） */}
            {availableSheets.length > 0 && (
              <div className="space-y-2">
                <div className="font-medium">選擇資料表（對應上傳檔案的工作表）</div>
                <select
                  value={selectedSheet}
                  onChange={(e) => setSelectedSheet(e.target.value)}
                  className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm bg-white"
                >
                  {availableSheets.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
                <div className="text-xs text-zinc-500">未選擇時預設使用第一張工作表。</div>
              </div>
            )}

            <div className="flex flex-wrap gap-2 pt-2">
              <button
                onClick={handleOneClick}
                disabled={loading || !excelFile || !isValidSrcName || !workOrder.trim()}
                className="px-3 py-2 rounded bg-zinc-900 text-white text-sm disabled:opacity-50"
              >
                一鍵建立並儲存
              </button>

              <button
                onClick={handleUpload}
                disabled={loading || !excelFile || !isValidSrcName}
                className="px-3 py-2 rounded border border-zinc-300 text-sm bg-white disabled:opacity-50"
              >
                上傳 Excel（先跑巨集）
              </button>

              <button
                onClick={handleCreate}
                disabled={loading || !canCreate}
                className="px-3 py-2 rounded border border-zinc-300 text-sm bg-white disabled:opacity-50"
              >
                執行創建配藥紀錄
              </button>
            </div>
          </div>

          {/* 右：預覽與輸出 */}
          <div className="border border-zinc-200 rounded-lg p-4 space-y-4 lg:col-span-2">
            <div className="flex gap-2">
              <button
                onClick={handlePreview}
                disabled={loading || !tempId}
                className="px-3 py-2 rounded border border-zinc-300 text-sm bg-white disabled:opacity-50"
              >
                重新讀取預覽
              </button>
              <button
                onClick={handleDownloadExcel}
                disabled={loading || !tempId}
                className="px-3 py-2 rounded border border-zinc-300 text-sm bg-white disabled:opacity-50"
              >
                下載 Excel
              </button>
            </div>

            <div className="rounded-lg border border-zinc-200 overflow-hidden">
              <div className="max-h-[400px] overflow-auto">
                {preview?.ok && preview.headers && preview.rows ? (
                  <table className="w-full text-sm">
                    <thead className="sticky top-0 bg-zinc-100">
                      <tr>
                        {preview.headers.map((h, i) => (
                          <th key={i} className="text-left font-medium px-3 py-2 border-b border-zinc-200 whitespace-nowrap">
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {preview.rows.map((r, i) => (
                        <tr key={i} className={i % 2 ? "bg-zinc-50" : "bg-white"}>
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
                    尚無預覽，請先『上傳 Excel（先跑巨集）』與『執行創建配藥紀錄』。
                  </div>
                )}
              </div>
            </div>

            {/* QR 區塊 */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-center">
              <div className="md:col-span-2 space-y-2">
                <div className="grid sm:grid-cols-2 gap-3">
                  <div>
                    <div className="font-medium">QR 來源 Cells（可多個）</div>
                    {qrCells.map((cell, idx) => (
                      <div key={idx} className="flex gap-2 mt-1">
                        <input
                          value={cell}
                          onChange={(e) => {
                            const next = [...qrCells];
                            next[idx] = e.target.value;
                            setQrCells(next);
                          }}
                          placeholder="例如：V6 或 Sheet1!A1"
                          className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm"
                        />
                        <button
                          onClick={() => setQrCells(qrCells.filter((_, i) => i !== idx))}
                          disabled={qrCells.length === 1}
                          className="px-2 py-2 rounded border border-zinc-300 text-sm bg-white disabled:opacity-50"
                        >
                          刪除
                        </button>
                      </div>
                    ))}
                    <button
                      onClick={() => setQrCells([...qrCells, ""])}
                      className="mt-2 px-3 py-1.5 rounded border border-zinc-300 text-sm bg-white"
                    >
                      新增一列
                    </button>
                  </div>

                  <div>
                    <div className="font-medium">合併字元（Joiner）</div>
                    <input
                      value={qrJoiner}
                      onChange={(e) => setQrJoiner(e.target.value)}
                      className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm mt-1"
                    />
                    <div className="text-xs text-zinc-500 mt-1">
                      以伺服器已儲存的檔案讀取這些 cells。
                    </div>
                    <button
                      onClick={handleServerSave}
                      disabled={loading || !tempId || !workOrder || !serverFileName}
                      className="mt-2 px-3 py-2 rounded bg-zinc-900 text-white text-sm disabled:opacity-50"
                    >
                      以目前設定重新儲存並產生 QR
                    </button>
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
          </div>
        </div>

        {/* 伺服器端存檔區 */}
        <div className="border border-zinc-200 rounded-lg p-4 space-y-3">
          <div className="text-base font-medium">伺服器端存檔</div>
          <div className="grid sm:grid-cols-3 gap-3">
            <div className="sm:col-span-2 space-y-2">
              <div className="text-sm">伺服器資料夾</div>
              <input
                value={serverDir}
                onChange={(e) => setServerDir(e.target.value)}
                className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm"
              />
              <div className="text-sm mt-2">檔名</div>
              <input
                value={serverFileName}
                onChange={(e) => { setServerFileName(e.target.value); setUserEditedFileName(true); }}
                className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm"
              />
              <div className="text-[12px] text-zinc-500">
                只有當「所選檔名包含『配藥表』」時才會自動轉為「配藥紀錄… .xlsm」；否則請自行輸入。
              </div>
            </div>
            <div className="sm:col-span-1 flex items-end">
              <button
                onClick={handleServerSave}
                disabled={loading || !tempId || !workOrder || !serverFileName}
                className="w-full px-3 py-2 rounded bg-zinc-900 text-white text-sm disabled:opacity-50"
              >
                伺服器儲存
              </button>
            </div>
          </div>
        </div>

        <footer className="text-xs text-zinc-600 pt-2">
          流程：上傳（後端先跑 VBA 宏）→ 匯表入 SQLite → 建立配藥紀錄（由表/工單號）→ 預覽/下載 → 伺服器儲存 → 依儲存檔產 QR
        </footer>
      </div>
    </div>
  );
}
