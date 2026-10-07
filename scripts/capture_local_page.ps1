# Operator browser validation. Reads only its own final-result capability file.
param([string]$Project='\\wsl.localhost\GNN-Project\home\tenggn\projects\privacy_gnn',[switch]$ReadyOnly)
$ErrorActionPreference='Stop'
$Out=Join-Path $Project 'results\local-page'
if($ReadyOnly){$Access=Get-Content -Raw (Join-Path $Project 'results\page\access-link.json') | ConvertFrom-Json}
else{$Private=Get-Content -Raw (Join-Path $Project 'results\page\browser-session.json') | ConvertFrom-Json}
$Port=19376
$Profile=Join-Path $env:TEMP ('privacy-gnn-browser-'+[guid]::NewGuid().ToString('N'))
$Edge='C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
$Process=Start-Process -FilePath $Edge -ArgumentList @('--headless=new','--disable-gpu','--disable-extensions','--no-first-run','--no-default-browser-check','--disable-background-networking',"--remote-debugging-port=$Port",'--remote-debugging-address=127.0.0.1',"--user-data-dir=`"$Profile`"",'about:blank') -PassThru
$Socket=$null;$Serial=0
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
function Wait-View([string]$Expected){
 $end=[DateTime]::UtcNow.AddSeconds(25)
 do{
  $ready=Evaluate '(document.getElementById("request-id")||{}).textContent'
  if($ready -eq $Expected){
   $terminal=Evaluate 'document.getElementById("delivery-badge").classList.contains("connected")||document.getElementById("delivery-badge").classList.contains("failed")'
   if($terminal){return}
  }
  Start-Sleep -Milliseconds 200
 }while([DateTime]::UtcNow -lt $end)
 throw 'Authorized result view did not reach the expected request.'
}
function Evidence([string]$Name){
 $value=Evaluate '({request_id:document.getElementById("request-id").textContent,connection:document.getElementById("connection").textContent,phase:document.getElementById("phase-name").textContent,delivery:document.getElementById("delivery-badge").textContent,prediction_visible:getComputedStyle(document.getElementById("prediction")).display!=="none",probability_rows:document.querySelectorAll(".prob-row").length,wall_seconds:document.getElementById("wall-time").textContent,wire_mib:document.getElementById("wire-bytes").textContent,rounds:document.getElementById("rounds").textContent})'
 $image=Invoke-CDP 'Page.captureScreenshot' @{format='png';captureBeyondViewport=$true}
 [IO.File]::WriteAllBytes((Join-Path $Out ($Name+'.png')),[Convert]::FromBase64String($image.data))
 return $value
}
try{
 $until=[DateTime]::UtcNow.AddSeconds(25)
 do{
  try{$targets=Invoke-RestMethod "http://127.0.0.1:$Port/json/list";$target=$targets|Where-Object {$_.type -eq 'page'}|Select-Object -First 1}catch{$target=$null}
  if(-not $target){Start-Sleep -Milliseconds 200}
 }while(-not $target -and [DateTime]::UtcNow -lt $until)
 if(-not $target){throw 'Loopback browser debugging endpoint unavailable.'}
 $Socket=[Net.WebSockets.ClientWebSocket]::new();$Socket.ConnectAsync([Uri]$target.webSocketDebuggerUrl,[Threading.CancellationToken]::None).GetAwaiter().GetResult()|Out-Null
 Invoke-CDP 'Page.enable' @{}|Out-Null
 Invoke-CDP 'Emulation.setDeviceMetricsOverride' @{width=1440;height=1280;deviceScaleFactor=1;mobile=$false}|Out-Null
 if($ReadyOnly){
  Invoke-CDP 'Page.navigate' @{url=$Access.url}|Out-Null
  $end=[DateTime]::UtcNow.AddSeconds(25)
  do{$connected=Evaluate 'document.getElementById("connection").classList.contains("connected")';if(-not $connected){Start-Sleep -Milliseconds 200}}while(-not $connected -and [DateTime]::UtcNow -lt $end)
  if(-not $connected){throw 'Authorized page did not reach connected idle state.'}
  $ready=Evidence 'connected-ready'
  $hasRequest=Evaluate '/^[a-f0-9]{32}$/.test(document.getElementById("request-id").textContent)'
  if($ready.prediction_visible -or $ready.probability_rows -ne 0 -or $hasRequest){throw 'Idle view unexpectedly showed a request or prediction.'}
  $url=Evaluate 'location.href'
  if($url -ne 'http://127.0.0.1:8765/'){throw 'Authorization fragment was not removed.'}
  @{kind='REAL_BROWSER_CONNECTED_IDLE_VIEW_ONLY';ready=$ready;new_protocol_runs=0;real_query_completed=$false;capabilities_in_evidence=$false}|ConvertTo-Json -Depth 10|Set-Content -Encoding UTF8 (Join-Path $Out 'browser-ready-evidence.json')
  Write-Output 'PASS actual authorized browser idle view; no query or prediction.'
  return
 }
 foreach($cookie in $Private.cookies){Invoke-CDP 'Network.setCookie' @{name=$cookie.name;value=$cookie.value;url='http://127.0.0.1:8765/';httpOnly=$true;sameSite='Strict'}|Out-Null}
 $token=$Private.success.token|ConvertTo-Json -Compress
 $initialization=Invoke-CDP 'Page.addScriptToEvaluateOnNewDocument' @{source=('sessionStorage.setItem("pgnn-current-request",'+$token+');')}
 Invoke-CDP 'Page.navigate' @{url='http://127.0.0.1:8765/'}|Out-Null
 Wait-View $Private.success.request_id
 $success=Evidence 'connected-success'
 if(-not $success.prediction_visible -or $success.probability_rows -ne 7){throw 'Success view did not show seven real probabilities.'}
 Invoke-CDP 'Page.removeScriptToEvaluateOnNewDocument' @{identifier=$initialization.identifier}|Out-Null
 $fault=$Private.failure.token|ConvertTo-Json -Compress
 Evaluate ('current='+$fault+';sessionStorage.setItem("pgnn-current-request",current);poll();true')|Out-Null
 Wait-View $Private.failure.request_id
 $failure=Evidence 'connected-failure'
 if($failure.prediction_visible -or $failure.probability_rows -ne 0){throw 'Failure view retained a prior prediction.'}
 # Initialization hook is removed. Reload retains the actual current nonce,
 # so this checks application refresh behavior without overriding view state.
 Invoke-CDP 'Page.reload' @{ignoreCache=$true}|Out-Null
 Wait-View $Private.failure.request_id
 $refresh=Evaluate '(document.getElementById("request-id")||{}).textContent'
 if($refresh -ne $Private.failure.request_id){throw 'Refresh did not retain the failed request.'}
 @{kind='REAL_BROWSER_AUTHORIZED_EXISTING_REQUEST_VIEWS';success=$success;failure=$failure;refresh_same_failed_request=$true;new_protocol_runs=0;view_url='http://127.0.0.1:8765/';capabilities_in_evidence=$false}|ConvertTo-Json -Depth 10|Set-Content -Encoding UTF8 (Join-Path $Out 'browser-evidence.json')
 Write-Output 'PASS actual browser: authorized success, failure clears previous prediction, refresh status only. No new query.'
}finally{
 if($Socket){$Socket.Dispose()}
 & "$env:SystemRoot\System32\taskkill.exe" /PID $Process.Id /T /F 2>$null|Out-Null
}
