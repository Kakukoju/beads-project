---
inclusion: auto
---

# Marker 排程核心約束規則

## 滴定機 (TECAN) 詳細約束

### 物理配置
- **TECAN 機台**有 **12 個 Port（基座）**：Port 1 ~ Port 12
- **Pump（泵）** 目前有 177 個，可能增加。每個 pump 專屬特定 marker（防汙染）
- Pump 插在 Port 上才能工作，一個 Port 一次只插一個 Pump
- 另有 **IVEK** 一台 2 port，只給 Na* 使用
- 工作時間：**09:00 ~ 01:00**（隔天凌晨 1 點）

### `pump No.` 表的意義
- 記錄「哪個 Pump 可以滴哪些 marker」（pump 與 marker 的對應關係）
- 排程用途：確認 marker 有對應的 pump 存在可用
- **不代表 177 個獨立機台**

### 排程規則
1. **每個時段最多 12 個 port 同時使用**
2. **每批使用 N 個 port**（N = `schedule."配藥限制".Port數`）
3. **滴定一批完才能換一批**（sequential per port）
4. **Port 從單數開始排**（1, 3, 5, 7, 9, 11 優先）
5. **Port 汙染規則**：Port數=1 的 marker 排了 port N，則相鄰 port N+1 不能被**其他 marker** 使用
   - **同 marker 系列不受此限制**：Cl-D 排 port 1，Cl-U 可排 port 2
6. 各 marker 可用的 pump 資訊在 `"P01_formualte_schedule"."pump No."` 表

### 滴定時間計算
- 滴定時間(hrs) = 每批生產量 / Port數 / 1700

---

## 凍乾機詳細約束

### 物理配置
- 共 11 台：No.3 ~ No.12 + 小台
- 各 marker 可用凍乾機 = `"P01_formualte_schedule".freezer_rules`（"v" = 可用）

### 排程規則
1. **凍乾結束 30 分鐘後**才能送進下一批藥（turnover time = 30 min）
2. 凍乾時間 = `schedule."配藥限制".凍乾時間`（小時）
3. 滴定完成後需要等凍乾機 status = 結束，才能進凍乾

### 流程順序
```
配藥 → 滴定（佔用 TECAN port） → 等凍乾機空出(+30min) → 凍乾（佔用凍乾機）
```

### 配藥人
- 各 marker 允許的配藥人 = `schedule."配藥限制"."配藥人-1"`, `"配藥人-2"`, `"配藥人-3"`
- 最多 3 人可配，NULL 代表該位置無人

### 生產參數
- 每批生產量 = `schedule."配藥限制".數量`
- 滴定時間 = 每批生產量 / Port數 / 1700 (hrs)

---

## D/U 配對規則 (雙劑型)

### 通用規則：`*-D` 和 `*-U` 後綴的 marker
- **同一天生產**
- **同一配藥人** 在 **同一時段** 配
- **一起滴定，不同滴定機**（各佔各的 port）
- **相同凍乾機**

### 例外：Na 系列
- `Na-D` / `Na-U` 或 `QNa-D` / `QNa-U`
- **分開生產**，但只能 **相差一天**

### 例外：GLIPA 系列
- `*GLIPA-D` / `*GLIPA-U`（假設應為 GLIPA-D + GLIPA-U 或類似）
- 同一天生產、同一配藥人同時段配、一起滴定不同滴定機
- **不同凍乾機**（這是唯一跟通用規則不同的地方）

---

## CREA 特殊規則 (三劑型)

CREA 需要三種藥：`tCRE-d`, `tCREA-D`, `tCREA-U`

- **同一天生產**
- `tCRE-d` + `tCREA-D`：一起配、同一配藥人、同一時段配、一起滴定不同滴定機
- `tCREA-U`：同一配藥人，但**不同時段**配、單獨一批滴定不同滴定機

---

## 特殊限制

### CRP
- `CRP-D` 和 `CRP-U` 不能連續排兩天，要 **隔天生產**

### Cl (氯離子)
- `Cl-D` 和 `Cl-U` 只能 **下午交藥**

### CA 系列 (鈣)
- `CA-*` 為單劑，只能 **下午交藥**
- 隔天 **不能安排配藥跟生產**（佔用隔天資源）

### NT4 diluent
- 佔用配藥人員 **一整天**

### ELISA 系列
以下 marker 佔用配藥人 **半天**（不需滴定機和凍乾機）：
- ELISA cTSH R1
- ELISA R2
- ELISA R3
- ELISA cPROG R1
- ELISA cCOR R1
- ELISA cPL R1
- ELISA fPL R1
- ELISA TEST LIQUID

---

## 資料表欄位對應

### `schedule."配藥限制"` 欄位
| 欄位 | 用途 |
|------|------|
| PN | 料號 |
| Name | Marker 名稱 |
| Port數 | 滴定時使用的 port 數量 |
| 數量 | 每批生產量 |
| 可用凍乾機 | (備用) |
| 配藥人-1 / -2 / -3 | 允許的配藥人 |
| 交藥時間 | 交藥時間限制 |
| 凍乾時間 | 凍乾所需時間 |
| U,D 劑分開生產排程 | 是否 D/U 分開 |
| 滴定後凍乾時間差距 (HR) | 滴定完到凍乾的間隔 |
| 配完後續要空著天數 | 配完後佔用天數 |
| 空閒產能時可優先安排生產 | 優先級提示 |
| 限制(一天只能兩輪) | 輪次限制 |

### `"P01_formualte_schedule".freezer_rules` 欄位
| 欄位 | 用途 |
|------|------|
| Marker | marker 名稱 |
| No. 3 ~ No. 12, 小台 | "v" = 可用該台凍乾機 |
| 數量 | 凍乾批量 |

### `"P01_formualte_schedule"."pump No."` 欄位
| 欄位 | 用途 |
|------|------|
| pump編號 | Port 編號 (1~12) |
| 可滴定之試劑-1 ~ -10 | 該 port 可滴定的 marker 名稱 |

注意：pump No. 表的結構是 **port → markers**（哪個 port 可以滴哪些 marker），
需要反轉為 **marker → allowed ports** 來使用。
