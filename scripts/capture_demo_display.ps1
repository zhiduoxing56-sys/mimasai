# Independent presentation verification; public retained records only.
param([string]$Project='\\wsl.localhost\GNN-Project\home\tenggn\projects\privacy_gnn')
$ErrorActionPreference='Stop'
$Out=Join-Path $Project 'results\demo-final'
$Port=19377
$Profile=Join-Path $env:TEMP ('privacy-gnn-display-'+[guid]::NewGuid().ToString('N'))
$Edge='C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
$Process=Start-Process -FilePath $Edge -ArgumentList @('--headless=new','--disable-gpu','--disable-extensions','--no-first-run','--no-default-browser-check','--disable-background-networking',"--remote-debugging-port=$Port",'--remote-debugging-address=127.0.0.1',"--user-data-dir=`"$Profile`"",'about:blank') -PassThru
$Socket=$null;$Serial=0;$RequestLog=@()
function Invoke-CDP([string]$Method,$Parameters){
 $script:Serial++
 $id=$script:Serial
 $bytes=[Text.Encoding]::UTF8.GetBytes((@{id=$id;method=$Method;params=$Parameters}|ConvertTo-Json -Depth 30 -Compress))
 $cancel=[Threading.CancellationTokenSource]::new(20000)
 try{
  $script:Socket.SendAsync([ArraySegment[byte]]::new($bytes),[Net.WebSockets.WebSocketMessageType]::Text,$true,$cancel.Token).GetAwaiter().GetResult() | Out-Null
  do{
   $memory=[IO.MemoryStream]::new();$buffer=New-Object byte[] 65536
   do{$received=$script:Socket.ReceiveAsync([ArraySegment[byte]]::new($buffer),$cancel.Token).GetAwaiter().GetResult();$memory.Write($buffer,0,$received.Count)}while(-not $received.EndOfMessage)
   $message=[Text.Encoding]::UTF8.GetString($memory.ToArray())|ConvertFrom-Json;$memory.Dispose()
   if($message.method -eq 'Network.requestWillBeSent'){
    $requestUri=[Uri]$message.params.request.url
    if($requestUri.Host -eq '127.0.0.1' -and $requestUri.Port -in @(8766,8767)){
     # Record method/path only, never headers, cookies, query, or request body.
     $script:RequestLog+=@{method=$message.params.request.method;path=$requestUri.AbsolutePath}
    }
   }
  }while($message.id -ne $id)
  if($message.error){throw ('CDP '+$Method+' failed: '+$message.error.code)}
  return $message.result
 }finally{$cancel.Dispose()}
}
function Evaluate([string]$Expression){
 $answer=Invoke-CDP 'Runtime.evaluate' @{expression=$Expression;awaitPromise=$true;returnByValue=$true}
 if($answer.exceptionDetails){throw 'Browser evaluation failed; capability values omitted.'}
 return $answer.result.value
}

function Check([string]$Expression,[string]$Message){if(-not (Evaluate $Expression)){throw $Message}}
function Wait-Condition([string]$Expression){
 $deadline=[DateTime]::UtcNow.AddSeconds(20)
 do{try{if(Evaluate $Expression){return}}catch{if($_.Exception.Message -notlike 'Browser evaluation failed*'){throw}};Start-Sleep -Milliseconds 150}while([DateTime]::UtcNow -lt $deadline)
 throw 'Display condition timed out; no capability values logged.'
}
function Shot([string]$Name){
 $height=Evaluate 'document.documentElement.scrollHeight'
 $data=Invoke-CDP 'Page.captureScreenshot' @{format='png';captureBeyondViewport=$true;clip=@{x=0;y=0;width=1440;height=$height;scale=1}}
 [IO.File]::WriteAllBytes((Join-Path $Out ($Name+'.png')),[Convert]::FromBase64String($data.data))
}
try{
 $until=[DateTime]::UtcNow.AddSeconds(25)
 do{try{$targets=Invoke-RestMethod "http://127.0.0.1:$Port/json/list";$target=$targets|Where-Object {$_.type -eq 'page'}|Select-Object -First 1}catch{$target=$null};if(-not $target){Start-Sleep -Milliseconds 150}}while(-not $target -and [DateTime]::UtcNow -lt $until)
 if(-not $target){throw 'Loopback browser endpoint unavailable.'}
 $Socket=[Net.WebSockets.ClientWebSocket]::new();$Socket.ConnectAsync([Uri]$target.webSocketDebuggerUrl,[Threading.CancellationToken]::None).GetAwaiter().GetResult()|Out-Null
 Invoke-CDP 'Page.enable' @{}|Out-Null;Invoke-CDP 'Network.enable' @{}|Out-Null
 Invoke-CDP 'Emulation.setDeviceMetricsOverride' @{width=1440;height=1280;deviceScaleFactor=1;mobile=$false}|Out-Null
 Invoke-CDP 'Page.navigate' @{url='http://127.0.0.1:8766/'}|Out-Null
 Wait-Condition 'document.readyState==="complete"&&document.body&&document.body.dataset.page==="inference"&&document.getElementById("submit")&&document.getElementById("submit").disabled'
 Check 'document.querySelectorAll(".prob-row").length===0&&document.getElementById("prediction").hidden&&!document.getElementById("deployment-notice").hidden' 'Pending inference view contained a prediction or missed deployment label.'
 Shot 'inference-pending'
 foreach($page in @('training','privacy')){
  Invoke-CDP 'Page.navigate' @{url=('http://127.0.0.1:8766/'+$page)}|Out-Null
  Wait-Condition ('document.readyState==="complete"&&document.body&&document.body.dataset.page==="'+$page+'"&&document.querySelector(".navigation .selected")')
  Check 'document.documentElement.scrollWidth<=innerWidth' 'Desktop display overflowed horizontally.'
  Check 'document.querySelectorAll("button").length===0' 'Readonly report page exposed a button.'
  if($page -eq 'training'){
   Check 'document.querySelector(".loss-line").getAttribute("points").split(" ").length===160' 'Curve did not have 160 recorded points.'
   Check 'document.getElementById("correct-count").textContent==="18 / 22"&&document.getElementById("test-accuracy").textContent==="81.82%"' 'Training metrics differed from existing record.'
  }else{Check 'document.getElementById("permission-total").textContent.startsWith("140 / 140")&&document.querySelectorAll("#permission-roles tbody tr").length===6' 'Permission summary did not match existing matrix.'}
  Shot ($page+'-pending')
 }
 $initialization=Invoke-CDP 'Page.addScriptToEvaluateOnNewDocument' @{source='sessionStorage.setItem("pgnn-current-request","aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");'}
 Invoke-CDP 'Page.navigate' @{url=('http://127.0.0.1:8767/#access='+('0'*64))}|Out-Null
 Wait-Condition 'document.querySelectorAll(".prob-row").length===7&&document.getElementById("prediction").hidden===false'
 Check 'document.getElementById("predicted-class").textContent==="\u57fa\u4e8e\u6848\u4f8b"' 'Class display was not the required Chinese name.'
 Check 'JSON.stringify([...document.querySelectorAll(".prob-row>span")].map(n=>n.textContent))===JSON.stringify(["\u57fa\u4e8e\u6848\u4f8b","\u9057\u4f20\u7b97\u6cd5","\u795e\u7ecf\u7f51\u7edc","\u6982\u7387\u65b9\u6cd5","\u5f3a\u5316\u5b66\u4e60","\u89c4\u5219\u5b66\u4e60","\u7406\u8bba"])' 'Seven class display names or order differed.'
 Check 'document.getElementById("wall-time").textContent==="72.31"&&document.getElementById("wire-bytes").textContent==="92.31"&&document.getElementById("submit")&&document.getElementById("submit").disabled' 'Retained acceptance costs or readonly state differed.'
 Shot 'inference-acceptance-pending'
 Invoke-CDP 'Page.removeScriptToEvaluateOnNewDocument' @{identifier=$initialization.identifier}|Out-Null
 Evaluate '(async()=>{window.retained=await api("/api/status",{token:"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"});return true})()'|Out-Null
 Check '(()=>{const v=structuredClone(window.retained);v.delivery_state="incomplete";try{render(v)}catch(e){disconnected(e.code)}return document.getElementById("prediction").hidden&&document.querySelectorAll(".prob-row").length===0})()' 'Partial delivery retained a prediction.'
 Evaluate 'current=null;const v=structuredClone(window.retained);v.phase="online";v.terminal=false;v.delivery_state="pending";v.result=null;v.cost={wall_seconds:10,wire_bytes:null,rounds:null};render(v,"current");window.firstElapsed=parseFloat(document.getElementById("elapsed").textContent.replace(/[^0-9.]/g,""));true'|Out-Null
 Start-Sleep -Milliseconds 400
 Check 'parseFloat(document.getElementById("elapsed").textContent.replace(/[^0-9.]/g,""))>window.firstElapsed&&document.getElementById("prediction").hidden&&document.querySelectorAll("#phases li.active").length===1' 'Stage clock did not advance or displayed a result before delivery.'
 Evaluate '(async()=>{render(window.retained,"acceptance");window.savedFetch=window.fetch;window.fetch=()=>Promise.reject(new TypeError("synthetic transport failure"));recordView=false;current="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";await poll();window.fetch=window.savedFetch;return true})()'|Out-Null
 Check 'document.getElementById("prediction").hidden&&document.querySelectorAll(".prob-row").length===0&&document.getElementById("wall-time").textContent==="\u2014"' 'Status transport failure retained the old probability or cost.'
 Evaluate '(async()=>{recordView=false;current="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";sessionStorage.setItem("pgnn-current-request",current);await poll();return true})()'|Out-Null
 Wait-Condition 'document.getElementById("request-id").textContent==="0cce9d0b2e93b1e7b03afe683baae8d3"&&document.getElementById("delivery-badge").classList.contains("failed")'
 Check 'document.getElementById("prediction").hidden&&document.querySelectorAll(".prob-row").length===0' 'Failed record retained a prediction.'
 Shot 'failure-acceptance-pending'
 $before=Evaluate 'performance.timeOrigin'
 Invoke-CDP 'Page.reload' @{ignoreCache=$true}|Out-Null
 Wait-Condition ('performance.timeOrigin!=='+$before+'&&document.getElementById("request-id")&&document.getElementById("request-id").textContent==="0cce9d0b2e93b1e7b03afe683baae8d3"&&document.getElementById("delivery-badge").classList.contains("failed")')
 Check 'document.getElementById("prediction").hidden&&document.querySelectorAll(".prob-row").length===0' 'Reload retained an old prediction.'
 $proof=Invoke-RestMethod 'http://127.0.0.1:8767/test-evidence'
 if($proof.calls.submit -ne 0 -or $proof.calls.status -lt 3 -or $proof.real_backend_connected){throw 'Display fixture attempted a query or missed status refresh.'}
 $submits=@($RequestLog|Where-Object {$_.path -eq '/api/submit'})
 if($submits.Count -ne 0){throw 'Browser sent a submit during retained-record verification.'}
 Invoke-CDP 'Emulation.setDeviceMetricsOverride' @{width=390;height=844;deviceScaleFactor=1;mobile=$true}|Out-Null
 Invoke-CDP 'Page.navigate' @{url='http://127.0.0.1:8766/'}|Out-Null
 Wait-Condition 'document.readyState==="complete"&&document.body&&document.body.dataset.page==="inference"&&document.getElementById("submit")&&document.getElementById("submit").disabled'
 Check 'document.documentElement.scrollWidth<=innerWidth' 'Mobile inference display overflowed horizontally.'
 @{kind='INDEPENDENT_PENDING_UI_BROWSER_ACCEPTANCE';status='PASS';screenshots=@('inference-pending.png','training-pending.png','privacy-pending.png','inference-acceptance-pending.png','failure-acceptance-pending.png');deployment='PENDING_ADMIN_UPDATE';new_crypto_queries=0;training_executed=$false;materials_generated=$false;record_rendering='Existing authorized success/failure HTTP records through isolated test adapter, not deployed page UID';chinese_classes_in_order=$true;curve_recorded_points=160;stage_clock_synthetic_check=$true;partial_delivery_clears=$true;status_failure_clears=$true;refresh_new_document_same_failure=$true;mobile_no_horizontal_overflow=$true;fixture_evidence=$proof;submit_requests=$submits.Count;request_methods_and_paths=$RequestLog;capabilities_in_evidence=$false}|ConvertTo-Json -Depth 12|Set-Content -Encoding UTF8 (Join-Path $Out 'browser-display-evidence.json')
 Write-Output 'PASS: three pending pages, retained real result rendering, Chinese names, clock, partial/status failure clearing, reload status only. No new query.'
}finally{
 if($Socket){$Socket.Dispose()}
 # taskkill can report a child that exited during traversal. Check the
 # unique fixture profile after stopping instead of treating that stderr
 # race as a presentation failure. Never stop the operator's normal Edge.
 $previousError=$ErrorActionPreference;$ErrorActionPreference='Continue'
 & "$env:SystemRoot\System32\taskkill.exe" /PID $Process.Id /T /F 2>$null|Out-Null
 $ErrorActionPreference=$previousError
 $remaining=@(Get-CimInstance Win32_Process -Filter "Name = 'msedge.exe'"|Where-Object {$_.CommandLine -like "*$Profile*"})
 foreach($child in $remaining){Stop-Process -Id $child.ProcessId -Force -ErrorAction SilentlyContinue}
 Start-Sleep -Milliseconds 200
 $remaining=@(Get-CimInstance Win32_Process -Filter "Name = 'msedge.exe'"|Where-Object {$_.CommandLine -like "*$Profile*"})
 if($remaining.Count -ne 0){throw 'Fixture browser processes remained after stop.'}
 $global:LASTEXITCODE=0
}
