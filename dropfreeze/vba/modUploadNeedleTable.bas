'=============================================================
' modUploadNeedleTable - 滴定針頭號數表 → EC2 SQLite
'=============================================================
' 匯入此模組後，指派按鈕呼叫 UploadNeedleTable 即可
'=============================================================
Option Explicit

' ══════ CONFIG ══════
Private Const SERVER_URL  As String = "http://54.199.19.240:8505"
Private Const DB_NAME     As String = "formulate"
Private Const TABLE_NAME  As String = "滴定針頭號數表"
Private Const SYNC_ACTION As String = "replace"
Private Const HEADER_ROW  As Long = 1
Private Const DATA_START  As Long = 2
' ════════════════════

Public Sub UploadNeedleTable()
    On Error GoTo ErrHandler

    Dim ws As Worksheet
    Set ws = ActiveSheet

    Dim lastRow As Long, lastCol As Long
    lastRow = GetLastRow(ws)
    If lastRow < DATA_START Then
        MsgBox "無資料可上傳", vbInformation
        Exit Sub
    End If
    lastCol = ws.UsedRange.Columns.Count

    Dim csvText As String
    csvText = BuildCSV(ws, HEADER_ROW, DATA_START, lastRow, 1, lastCol)
    If Len(csvText) = 0 Then Exit Sub

    Dim url As String
    url = SERVER_URL & "/api/sync/" & DB_NAME & "/" & UrlEncodeUTF8(TABLE_NAME) & "?action=" & SYNC_ACTION

    Dim result As String
    result = HttpPost(url, csvText)

    If InStr(1, result, """ok"":true", vbTextCompare) > 0 Or _
       InStr(1, result, """ok"": true", vbTextCompare) > 0 Then
        MsgBox "上傳成功: " & TABLE_NAME, vbInformation
    Else
        MsgBox "上傳失敗:" & vbCrLf & Left(result, 500), vbExclamation
    End If
    Exit Sub

ErrHandler:
    MsgBox "錯誤:" & vbCrLf & Err.Description, vbCritical
End Sub

' ══════ 內部工具 ══════

Private Function BuildCSV(ws As Worksheet, headerR As Long, dataS As Long, _
                          dataE As Long, colS As Long, colE As Long) As String
    Dim sb As String, r As Long, c As Long, val As String
    For c = colS To colE
        If c > colS Then sb = sb & ","
        sb = sb & CsvEscape(CStr(ws.Cells(headerR, c).Value))
    Next c
    sb = sb & vbLf
    For r = dataS To dataE
        For c = colS To colE
            If c > colS Then sb = sb & ","
            sb = sb & CsvEscape(CellStr(ws.Cells(r, c)))
        Next c
        sb = sb & vbLf
    Next r
    BuildCSV = sb
End Function

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
    Dim lr As Long
    lr = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
    Dim lr2 As Long
    lr2 = ws.Cells(ws.Rows.Count, 2).End(xlUp).Row
    GetLastRow = IIf(lr2 > lr, lr2, lr)
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
