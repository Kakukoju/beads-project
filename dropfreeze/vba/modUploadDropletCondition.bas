'=============================================================
' modUploadDropletCondition - 滴定條件 → EC2 SQLite
'=============================================================
' Excel header 在第 4 列 (HEADER_ROW=4), 資料從第 5 列開始
' 欄位名稱與 DB 不同，用 COLUMN_MAP 做對應
'=============================================================
Option Explicit

' ══════ CONFIG ══════
Private Const SERVER_URL  As String = "http://54.199.19.240:8505"
Private Const DB_NAME     As String = "formulate"
Private Const TABLE_NAME  As String = "滴定條件"
Private Const SYNC_ACTION As String = "upsert"
Private Const UPSERT_KEYS As String = "PN"
Private Const HEADER_ROW  As Long = 4
Private Const DATA_START  As Long = 5
Private Const COL_START   As Long = 2   'B column
Private Const COL_COUNT   As Long = 14
' ════════════════════

' 第 n 個欄位 (1-based) → DB column name
Private Function GetDbColName(n As Long) As String
    Select Case n
        Case 1:  GetDbColName = "PN"
        Case 2:  GetDbColName = "Name"
        Case 3:  GetDbColName = "Liquid_storge_time"
        Case 4:  GetDbColName = "儲存時冰浴"
        Case 5:  GetDbColName = "儲存時避光"
        Case 6:  GetDbColName = "滴定時避光"
        Case 7:  GetDbColName = "滴定時攪拌"
        Case 8:  GetDbColName = "滴定_Mixing"
        Case 9:  GetDbColName = "滴定時冰浴"
        Case 10: GetDbColName = "滴定_degas"
        Case 11: GetDbColName = "滴定_drop_Vol_RD"
        Case 12: GetDbColName = "滴定_drop_Vol_MFG"
        Case 13: GetDbColName = "滴定_Weight"
        Case 14: GetDbColName = "滴定_管_數量"
        Case Else: GetDbColName = "col" & n
    End Select
End Function

Public Sub UploadDropletCondition()
    On Error GoTo ErrHandler

    Dim ws As Worksheet
    Set ws = ThisWorkbook.Sheets("保存_滴定_併管顆數")

    Dim lastRow As Long
    lastRow = GetLastRow(ws)
    If lastRow < DATA_START Then
        MsgBox "無資料可上傳", vbInformation
        Exit Sub
    End If

    ' Build CSV with DB column names
    Dim sb As String, r As Long, c As Long, n As Long, rowCount As Long
    rowCount = 0
    For n = 1 To COL_COUNT
        If n > 1 Then sb = sb & ","
        sb = sb & CsvEscape(GetDbColName(n))
    Next n
    sb = sb & vbLf

    For r = DATA_START To lastRow
        Dim pn As String
        pn = Trim(CStr(ws.Cells(r, COL_START).Value))
        If Left(pn, 4) <> "5714" Then GoTo NextRow

        rowCount = rowCount + 1
        For n = 1 To COL_COUNT
            c = COL_START + n - 1
            If n > 1 Then sb = sb & ","
            sb = sb & CsvEscape(CellStr(ws.Cells(r, c)))
        Next n
        sb = sb & vbLf
NextRow:
    Next r

    If rowCount = 0 Then
        MsgBox "無符合 5714* 的資料可上傳", vbExclamation, TABLE_NAME
        Exit Sub
    End If

    Dim url As String
    url = SERVER_URL & "/api/sync/" & DB_NAME & "/" & UrlEncodeUTF8(TABLE_NAME) & "?action=" & SYNC_ACTION & "&keys=" & UPSERT_KEYS

    Dim result As String
    result = HttpPost(url, sb)

    If InStr(1, result, """ok"":true", vbTextCompare) > 0 Or _
       InStr(1, result, """ok"": true", vbTextCompare) > 0 Then
        MsgBox "上傳成功: " & TABLE_NAME & vbCrLf & _
               "Sheet: 保存_滴定_併管顆數" & vbCrLf & _
               "筆數: " & rowCount, vbInformation
    Else
        MsgBox "上傳失敗:" & vbCrLf & Left(result, 500), vbCritical
    End If
    Exit Sub

ErrHandler:
    MsgBox "錯誤:" & vbCrLf & Err.Description, vbCritical
End Sub

' ══════ 內部工具 ══════

Private Function CellStr(cell As Range) As String
    If IsEmpty(cell.Value) Then
        CellStr = ""
    ElseIf IsDate(cell.Value) And Not IsNumeric(cell.Value) Then
        CellStr = IIf(cell.Value = Int(cell.Value), Format(cell.Value, "yyyy/mm/dd"), Format(cell.Value, "hh:mm"))
    Else
        CellStr = CStr(cell.Value)
    End If
End Function

Private Function CsvEscape(s As String) As String
    If InStr(s, ",") > 0 Or InStr(s, """") > 0 Or InStr(s, vbLf) > 0 Or InStr(s, vbCr) > 0 Then
        CsvEscape = """" & Replace(s, """", """""") & """"
    Else
        CsvEscape = s
    End If
End Function

Private Function GetLastRow(ws As Worksheet) As Long
    Dim lr As Long, c As Long
    GetLastRow = 0
    For c = COL_START To COL_START + COL_COUNT - 1
        lr = ws.Cells(ws.Rows.Count, c).End(xlUp).Row
        If lr > GetLastRow Then GetLastRow = lr
    Next c
End Function

Private Function UrlEncodeUTF8(s As String) As String
    Dim stm As Object, b() As Byte, i As Long, tmp As String
    Set stm = CreateObject("ADODB.Stream")
    stm.Type = 2: stm.Charset = "utf-8": stm.Open
    stm.WriteText s
    stm.Position = 0: stm.Type = 1: stm.Position = 3
    b = stm.Read: stm.Close: Set stm = Nothing
    For i = LBound(b) To UBound(b)
        If (b(i) >= 48 And b(i) <= 57) Or (b(i) >= 65 And b(i) <= 90) Or _
           (b(i) >= 97 And b(i) <= 122) Or b(i) = 45 Or b(i) = 46 Or b(i) = 95 Or b(i) = 126 Then
            tmp = tmp & Chr(b(i))
        Else
            tmp = tmp & "%" & Right("0" & Hex(b(i)), 2)
        End If
    Next i
    UrlEncodeUTF8 = tmp
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
