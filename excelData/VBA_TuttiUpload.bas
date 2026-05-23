' ============================================================
' 放在 Qbi製程記錄表 的 ThisWorkbook 模組
' 存檔時自動上傳到 EC2 → 解析 ow sheet → push to RDS
' ============================================================

Private Sub Workbook_AfterSave(ByVal Success As Boolean)
    If Not Success Then Exit Sub
    Call UploadTuttiForm
End Sub

Private Sub UploadTuttiForm()
    Const API_URL As String = "https://52-192-28-39.sslip.io/api/tutti-production/upload-excel"
    
    Dim fileName As String
    fileName = ThisWorkbook.Name
    
    ' --- 複製一份暫存檔避免檔案鎖定 ---
    Dim tmpPath As String
    tmpPath = Environ("TEMP") & "\" & fileName
    ThisWorkbook.SaveCopyAs tmpPath
    
    ' --- 讀取暫存檔為 binary ---
    Dim fileStream As Object
    Set fileStream = CreateObject("ADODB.Stream")
    fileStream.Type = 1
    fileStream.Open
    fileStream.LoadFromFile tmpPath
    
    ' --- 刪除暫存檔 ---
    Kill tmpPath
    
    ' --- 組裝 multipart boundary ---
    Dim boundary As String
    boundary = "----VBABoundary" & Format(Now, "yyyymmddhhnnss")
    
    Dim preFile As String
    preFile = "--" & boundary & vbCrLf & _
              "Content-Disposition: form-data; name=""file""; filename=""" & fileName & """" & vbCrLf & _
              "Content-Type: application/octet-stream" & vbCrLf & vbCrLf
    
    Dim postFile As String
    postFile = vbCrLf & "--" & boundary & "--" & vbCrLf
    
    ' --- 轉換 header 為 binary ---
    Dim preStream As Object
    Set preStream = CreateObject("ADODB.Stream")
    preStream.Type = 2: preStream.Charset = "ascii"
    preStream.Open
    preStream.WriteText preFile
    preStream.Position = 0
    preStream.Type = 1
    
    ' --- 轉換 footer 為 binary ---
    Dim postStream As Object
    Set postStream = CreateObject("ADODB.Stream")
    postStream.Type = 2: postStream.Charset = "ascii"
    postStream.Open
    postStream.WriteText postFile
    postStream.Position = 0
    postStream.Type = 1
    
    ' --- 合併為完整 body stream ---
    Dim bodyStream As Object
    Set bodyStream = CreateObject("ADODB.Stream")
    bodyStream.Type = 1
    bodyStream.Open
    
    preStream.Position = 0
    bodyStream.Write preStream.Read
    preStream.Close
    
    fileStream.Position = 0
    bodyStream.Write fileStream.Read
    fileStream.Close
    
    postStream.Position = 0
    bodyStream.Write postStream.Read
    postStream.Close
    
    ' --- 發送 HTTP ---
    bodyStream.Position = 0
    
    Dim http As Object
    Set http = CreateObject("MSXML2.ServerXMLHTTP.6.0")
    http.setTimeouts 5000, 10000, 30000, 60000
    http.Open "POST", API_URL, False
    http.setRequestHeader "Content-Type", "multipart/form-data; boundary=" & boundary
    http.send bodyStream.Read
    
    bodyStream.Close
    
    ' --- 確認結果 ---
    If http.Status = 200 Then
        Dim resp As String
        resp = http.responseText
        If InStr(resp, """ok""") > 0 And InStr(resp, "true") > 0 Then
            MsgBox Chr(9989) & " 製程記錄表上傳成功！" & vbCrLf & fileName, vbInformation, "Tutti Upload"
        Else
            MsgBox Chr(9888) & " 伺服器回應異常：" & vbCrLf & resp, vbExclamation, "Tutti Upload"
        End If
    Else
        MsgBox Chr(10060) & " 上傳失敗！" & vbCrLf & _
               "HTTP " & http.Status & vbCrLf & _
               http.responseText, vbCritical, "Tutti Upload"
    End If
    
    Set http = Nothing
End Sub
