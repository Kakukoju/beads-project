'=============================================================
' modSyncUpload - Excel → EC2 SQLite 同步模組
'=============================================================
' 使用方式:
'   1. 在 VBE 中匯入此模組 (modSyncUpload.bas)
'   2. 修改下方 CONFIG 區的 SERVER_URL / DB_NAME / TABLE_NAME
'   3. 在 ThisWorkbook 貼上 Workbook_BeforeSave 事件 (見底部範例)
'   4. 或手動執行 SyncCurrentSheet / 插入按鈕呼叫
'=============================================================
Option Explicit

' ══════ CONFIG - 請依實際環境修改 ══════
Private Const SERVER_URL  As String = "http://<EC2_PRIVATE_IP>:8505"
Private Const DB_NAME     As String = "formulate"       ' formulate | bead_sort | ipqc
Private Const TABLE_NAME  As String = "DropletSchedule"  ' 目標 table 名稱
Private Const SYNC_ACTION As String = "replace"          ' replace | upsert | append
Private Const UPSERT_KEYS As String = ""                 ' upsert 時的主鍵, 逗號分隔 e.g. "PN,Batch"
Private Const SHEET_NAME  As String = ""                 ' 空字串 = 使用 ActiveSheet
Private Const HEADER_ROW  As Long = 1                    ' 表頭所在列
Private Const DATA_START  As Long = 2                    ' 資料起始列
Private Const LAST_COL    As String = ""                 ' 空字串 = 自動偵測 UsedRange 最後欄
' ══════════════════════════════════════

' ── 主要入口: 手動按鈕呼叫 ──
Public Sub SyncCurrentSheet()
    On Error GoTo ErrHandler
    
    Dim ws As Worksheet
    If SHEET_NAME = "" Then
        Set ws = ActiveSheet
    Else
        Set ws = ThisWorkbook.Sheets(SHEET_NAME)
    End If
    
    Dim lastRow As Long, lastCol As Long
    lastRow = GetLastDataRow(ws)
    If lastRow < DATA_START Then
        Exit Sub
    End If
    
    If LAST_COL = "" Then
        lastCol = ws.UsedRange.Columns.Count
    Else
        lastCol = ColLetterToNum(LAST_COL)
    End If
    
    Dim csvText As String
    csvText = BuildCSV(ws, HEADER_ROW, DATA_START, lastRow, 1, lastCol)
    If Len(csvText) = 0 Then Exit Sub
    
    Dim url As String
    url = SERVER_URL & "/api/sync/" & DB_NAME & "/" & TABLE_NAME & "?action=" & SYNC_ACTION
    If UPSERT_KEYS <> "" Then url = url & "&keys=" & UPSERT_KEYS
    
    Dim result As String
    result = HttpPost(url, csvText)
    
    If InStr(1, result, """ok"":true", vbTextCompare) > 0 Or _
       InStr(1, result, """ok"": true", vbTextCompare) > 0 Then
        Application.StatusBar = "V 同步成功 " & TABLE_NAME & " @ " & Format(Now, "hh:mm:ss")
    Else
        MsgBox "同步失敗:" & vbCrLf & Left(result, 500), vbExclamation, "Sync Error"
    End If
    Exit Sub

ErrHandler:
    MsgBox "同步發生錯誤:" & vbCrLf & Err.Description, vbCritical, "Sync Error"
End Sub

' ── 靜默版 (給 BeforeSave 用, 不彈 MsgBox) ──
Public Sub SyncSilent()
    On Error Resume Next
    
    Dim ws As Worksheet
    If SHEET_NAME = "" Then
        Set ws = ActiveSheet
    Else
        Set ws = ThisWorkbook.Sheets(SHEET_NAME)
    End If
    
    Dim lastRow As Long, lastCol As Long
    lastRow = GetLastDataRow(ws)
    If lastRow < DATA_START Then Exit Sub
    
    If LAST_COL = "" Then
        lastCol = ws.UsedRange.Columns.Count
    Else
        lastCol = ColLetterToNum(LAST_COL)
    End If
    
    Dim csvText As String
    csvText = BuildCSV(ws, HEADER_ROW, DATA_START, lastRow, 1, lastCol)
    If Len(csvText) = 0 Then Exit Sub
    
    Dim url As String
    url = SERVER_URL & "/api/sync/" & DB_NAME & "/" & TABLE_NAME & "?action=" & SYNC_ACTION
    If UPSERT_KEYS <> "" Then url = url & "&keys=" & UPSERT_KEYS
    
    Dim result As String
    result = HttpPost(url, csvText)
    
    If InStr(1, result, """ok"":true", vbTextCompare) > 0 Or _
       InStr(1, result, """ok"": true", vbTextCompare) > 0 Then
        Application.StatusBar = "V 同步成功 " & TABLE_NAME & " @ " & Format(Now, "hh:mm:ss")
    Else
        Application.StatusBar = "X 同步失敗 " & TABLE_NAME & " - " & Left(result, 100)
    End If
End Sub

' ══════ 內部工具函式 ══════

Private Function BuildCSV(ws As Worksheet, headerR As Long, dataS As Long, _
                          dataE As Long, colS As Long, colE As Long) As String
    Dim sb As String
    Dim r As Long, c As Long
    Dim val As String
    
    ' Header row
    For c = colS To colE
        val = CsvEscape(CStr(ws.Cells(headerR, c).Value))
        If c > colS Then sb = sb & ","
        sb = sb & val
    Next c
    sb = sb & vbLf
    
    ' Data rows
    For r = dataS To dataE
        For c = colS To colE
            val = CellToString(ws.Cells(r, c))
            If c > colS Then sb = sb & ","
            sb = sb & CsvEscape(val)
        Next c
        sb = sb & vbLf
    Next r
    
    BuildCSV = sb
End Function

Private Function CellToString(cell As Range) As String
    If IsEmpty(cell.Value) Then
        CellToString = ""
    ElseIf IsDate(cell.Value) And Not IsNumeric(cell.Value) Then
        If cell.Value = Int(cell.Value) Then
            CellToString = Format(cell.Value, "yyyy/mm/dd")
        Else
            CellToString = Format(cell.Value, "hh:mm")
        End If
    Else
        CellToString = CStr(cell.Value)
    End If
End Function

Private Function CsvEscape(s As String) As String
    If InStr(s, ",") > 0 Or InStr(s, """") > 0 Or InStr(s, vbLf) > 0 Or InStr(s, vbCr) > 0 Then
        CsvEscape = """" & Replace(s, """", """""") & """"
    Else
        CsvEscape = s
    End If
End Function

Private Function GetLastDataRow(ws As Worksheet) As Long
    Dim lr As Long, lr2 As Long
    lr = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
    lr2 = ws.Cells(ws.Rows.Count, 2).End(xlUp).Row
    If lr2 > lr Then lr = lr2
    GetLastDataRow = lr
End Function

Private Function ColLetterToNum(col As String) As Long
    Dim i As Long, n As Long
    n = 0
    For i = 1 To Len(col)
        n = n * 26 + (Asc(UCase(Mid(col, i, 1))) - 64)
    Next i
    ColLetterToNum = n
End Function

Private Function HttpPost(url As String, body As String) As String
    Dim http As Object
    Set http = CreateObject("WinHttp.WinHttpRequest.5.1")
    http.SetTimeouts 30000, 30000, 60000, 120000
    http.Open "POST", url, False
    http.SetRequestHeader "Content-Type", "text/csv; charset=utf-8"
    http.Send body
    HttpPost = http.ResponseText
    Set http = Nothing
End Function
