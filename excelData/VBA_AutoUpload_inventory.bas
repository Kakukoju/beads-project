' ============================================================
' 放在 beads_inventory.xlsm 的 ThisWorkbook 模組
' 存檔時只傳 BEADS庫存表 sheet 的資料（JSON），不傳整個檔案
' 速度提升：原本上傳 MB 級檔案 → 現在只傳 KB 級 JSON
' ============================================================

Private Sub Workbook_AfterSave(ByVal Success As Boolean)
    If Not Success Then Exit Sub
    Call UploadSheetAsJSON
End Sub

Private Sub UploadSheetAsJSON()
    Const API_URL As String = "https://52-192-28-39.sslip.io/api/upload-beads-json"
    Const API_KEY As String = "beadsops-upload-key"
    Const SHEET_NAME As String = "BEADS庫存表(202405~"
    Const HEADER_ROW As Long = 5        ' 第5行是欄位名
    Const START_COL As Long = 1         ' A欄
    Const END_COL As Long = 15          ' O欄
    
    Application.StatusBar = Chr(&H23F3) & " 正在上傳庫存資料..."
    
    ' --- 確認 sheet 存在 ---
    Dim ws As Worksheet
    On Error Resume Next
    Set ws = ThisWorkbook.Sheets(SHEET_NAME)
    On Error GoTo 0
    If ws Is Nothing Then
        Application.StatusBar = False
        MsgBox "找不到 sheet: " & SHEET_NAME, vbCritical, "Upload Error"
        Exit Sub
    End If
    
    ' --- 讀取欄位名稱 ---
    Dim headers() As String
    ReDim headers(START_COL To END_COL)
    Dim c As Long
    For c = START_COL To END_COL
        headers(c) = Trim(CStr(ws.Cells(HEADER_ROW, c).Value))
    Next c
    
    ' --- 找最後一列 ---
    Dim lastRow As Long
    lastRow = ws.Cells(ws.Rows.Count, START_COL).End(xlUp).Row
    If lastRow <= HEADER_ROW Then
        Application.StatusBar = False
        MsgBox "Sheet 沒有資料列", vbExclamation, "Upload"
        Exit Sub
    End If
    
    ' --- 組裝 JSON 陣列 ---
    Dim json As String
    Dim r As Long
    Dim rowJson As String
    Dim v As Variant
    Dim isEmptyRow As Boolean
    
    json = "["
    Dim firstRow As Boolean
    firstRow = True
    
    For r = HEADER_ROW + 1 To lastRow
        ' 跳過全空列
        isEmptyRow = True
        For c = START_COL To END_COL
            If Len(Trim(CStr(ws.Cells(r, c).Value & ""))) > 0 Then
                isEmptyRow = False
                Exit For
            End If
        Next c
        If isEmptyRow Then GoTo NextRow
        
        ' 組裝這一列的 JSON object
        rowJson = "{"
        For c = START_COL To END_COL
            v = ws.Cells(r, c).Value
            If c > START_COL Then rowJson = rowJson & ","
            rowJson = rowJson & """" & EscapeJson(headers(c)) & """:"
            If IsMissing(v) Or IsEmpty(v) Or IsError(v) Then
                rowJson = rowJson & "null"
            ElseIf IsNull(v) Then
                rowJson = rowJson & "null"
            ElseIf VarType(v) = vbString Then
                If Len(Trim(v)) = 0 Then
                    rowJson = rowJson & "null"
                Else
                    rowJson = rowJson & """" & EscapeJson(CStr(v)) & """"
                End If
            ElseIf IsNumeric(v) And Not IsDate(v) Then
                rowJson = rowJson & CStr(v)
            ElseIf IsDate(v) Then
                rowJson = rowJson & """" & Format(v, "yyyy-mm-dd") & """"
            Else
                rowJson = rowJson & """" & EscapeJson(CStr(v)) & """"
            End If
        Next c
        rowJson = rowJson & "}"
        
        If Not firstRow Then json = json & ","
        json = json & rowJson
        firstRow = False
NextRow:
    Next r
    json = json & "]"
    
    ' --- 發送 HTTP POST ---
    Dim http As Object
    Set http = CreateObject("MSXML2.ServerXMLHTTP.6.0")
    
    ' 設定較長的 timeout（連線30秒、傳送60秒、接收60秒）
    http.setTimeouts 30000, 30000, 60000, 60000
    
    http.Open "POST", API_URL, False
    http.setRequestHeader "Content-Type", "application/json; charset=utf-8"
    http.setRequestHeader "X-Api-Key", API_KEY
    http.send json
    
    Application.StatusBar = False
    
    ' --- 確認結果 ---
    If http.Status = 200 Then
        Dim resp As String
        resp = http.responseText
        If InStr(resp, """ok""") > 0 And InStr(resp, "true") > 0 Then
            Application.StatusBar = Chr(&H2705) & " 上傳成功 " & Format(Now, "hh:mm:ss")
        Else
            MsgBox Chr(&H26A0) & " 伺服器回應異常：" & vbCrLf & resp, vbExclamation, "Upload"
        End If
    Else
        MsgBox Chr(&H274C) & " 上傳失敗！" & vbCrLf & _
               "HTTP " & http.Status & vbCrLf & _
               http.responseText, vbCritical, "Upload"
    End If
    
    Set http = Nothing
End Sub

Private Function EscapeJson(ByVal s As String) As String
    s = Replace(s, "\", "\\")
    s = Replace(s, """", "\""")
    s = Replace(s, vbCr, "\r")
    s = Replace(s, vbLf, "\n")
    s = Replace(s, vbTab, "\t")
    EscapeJson = s
End Function
