' =============================================================
' Production Plan VBA - ThisWorkbook module
' AfterSave: incremental upload (only today+ date columns)
' Manual: call UploadPlanFull for full sync
' =============================================================

Private Sub Workbook_AfterSave(ByVal Success As Boolean)
    If Not Success Then Exit Sub
    Call UploadPlan("incremental")
End Sub

Public Sub UploadPlanFull()
    Call UploadPlan("full")
End Sub

Private Sub UploadPlan(ByVal mode As String)
    Const API_URL As String = "https://52-192-28-39.sslip.io/api/upload-production-plan-json"
    Const API_KEY As String = "beadsops-upload-key"
    Const SHEET_NAME As String = "P_plan Reagent"
    Const HEADER_ROW As Long = 2

    Application.StatusBar = "Uploading plan (" & mode & ")..."

    Dim ws As Worksheet
    On Error Resume Next
    Set ws = ThisWorkbook.Sheets(SHEET_NAME)
    On Error GoTo 0
    If ws Is Nothing Then
        Application.StatusBar = False
        Exit Sub
    End If

    Dim lastCol As Long
    lastCol = ws.Cells(HEADER_ROW, ws.Columns.Count).End(xlToLeft).Column

    Dim headers() As String
    ReDim headers(1 To lastCol)
    Dim c As Long
    For c = 1 To lastCol
        Dim hVal As Variant
        hVal = ws.Cells(HEADER_ROW, c).Value
        If IsDate(hVal) And Not IsEmpty(hVal) Then
            headers(c) = Format(hVal, "yyyy-mm-dd")
        Else
            headers(c) = Trim(CStr(hVal & ""))
        End If
    Next c

    Dim pnCol As Long: pnCol = 0
    Dim planCol As Long: planCol = 0
    For c = 1 To lastCol
        If LCase(headers(c)) Like "*panel*no*" Then pnCol = c
        If LCase(headers(c)) = "plan" Then planCol = c
    Next c
    If pnCol = 0 Or planCol = 0 Then
        Application.StatusBar = False
        Exit Sub
    End If

    Dim startCol As Long
    If mode = "incremental" Then
        startCol = 0
        For c = planCol + 1 To lastCol
            If IsDate(ws.Cells(HEADER_ROW, c).Value) Then
                If CDate(ws.Cells(HEADER_ROW, c).Value) >= Date Then
                    startCol = c
                    Exit For
                End If
            End If
        Next c
        If startCol = 0 Then startCol = planCol + 1
    Else
        startCol = planCol + 1
    End If

    Dim lastRow As Long
    lastRow = ws.Cells(ws.Rows.Count, pnCol).End(xlUp).Row
    If lastRow <= HEADER_ROW Then
        Application.StatusBar = False
        Exit Sub
    End If

    Dim Q As String: Q = Chr(34)
    Dim json As String
    json = "{" & Q & "mode" & Q & ":" & Q & mode & Q & "," & Q & "data" & Q & ":["

    Dim firstRow As Boolean: firstRow = True
    Dim r As Long
    For r = HEADER_ROW + 1 To lastRow
        Dim pnVal As String
        pnVal = Trim(CStr(ws.Cells(r, pnCol).Value & ""))
        If Len(pnVal) = 0 Then GoTo NextRow
        If LCase(pnVal) Like "*panel*no*" Then GoTo NextRow

        Dim rowJson As String
        rowJson = "{" & Q & "Panel_NO" & Q & ":" & Q & EscapeJson(pnVal) & Q
        rowJson = rowJson & "," & Q & "Plan" & Q & ":" & Q & "Plan" & Q

        For c = startCol To lastCol
            If Len(headers(c)) >= 10 Then
                If headers(c) Like "####-##-##" Then
                    Dim v As Variant
                    v = ws.Cells(r, c).Value
                    If IsNumeric(v) And Not IsEmpty(v) Then
                        If CDbl(v) > 0 Then
                            rowJson = rowJson & "," & Q & headers(c) & Q & ":" & CStr(CDbl(v))
                        End If
                    End If
                End If
            End If
        Next c

        rowJson = rowJson & "}"
        If Not firstRow Then json = json & ","
        json = json & rowJson
        firstRow = False
NextRow:
    Next r
    json = json & "]}"

    Dim http As Object
    Set http = CreateObject("MSXML2.ServerXMLHTTP.6.0")
    http.setTimeouts 30000, 30000, 60000, 60000
    http.Open "POST", API_URL, False
    http.setRequestHeader "Content-Type", "application/json; charset=utf-8"
    http.setRequestHeader "X-Api-Key", API_KEY
    http.Send json

    Application.StatusBar = False
    If http.Status = 200 Then
        Application.StatusBar = "Plan uploaded (" & mode & ") " & Format(Now, "hh:mm:ss")
    Else
        MsgBox "Upload failed: HTTP " & http.Status, vbCritical
    End If
    Set http = Nothing
End Sub

Private Function EscapeJson(ByVal s As String) As String
    s = Replace(s, "\", "\\")
    s = Replace(s, Chr(34), "\" & Chr(34))
    s = Replace(s, vbCr, "\r")
    s = Replace(s, vbLf, "\n")
    EscapeJson = s
End Function
