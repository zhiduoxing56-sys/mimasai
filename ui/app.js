"use strict";
const model=JSON.parse(document.getElementById("public-model").textContent),byId=id=>document.getElementById(id),D=PGNNDisplay;
byId("source").textContent="共享训练第 160 轮检查点 · 保留现有权重份额，无需重训";
byId("dimensions").textContent=model.dimensions.slice(1).join(" → ");byId("sampling").textContent=D.sampling[model.sampling]||"公开抽样";
byId("model-id").textContent=model.model_id;byId("source-id").textContent=model.source_training_session;byId("sampling-id").textContent=`${model.sampling} · 种子 ${model.sampling_seed}`;
byId("target").textContent=model.allowed_targets.join(", ");byId("receiver").textContent=model.receiver_id;byId("class-ids").textContent=model.classes.join(" → ");
let connected=false,csrf=null,current=null,busy=false,timer=null,clock=null,recordView=false;
const phaseOrder=["admission","offline","input","online","export","receiver","complete"];
const phases={admission:"磁盘准入",offline:"离线材料生成",input:"角色输入准备",online:"真实后端运行",export:"最终份额交付",receiver:"授权接收端恢复",complete:"持久保存与自动清理",failed:"失败 / 未完成交付",stopping:"停止待确认"};
function clearResult(){byId("prediction").hidden=true;byId("empty-result").hidden=false;byId("probabilities").replaceChildren();for(const id of ["wall-time","wire-bytes","rounds"])byId(id).textContent="—";}
function resetClock(){clock=null;byId("elapsed").textContent="—";}
function tickClock(){if(!clock)return;const s=clock.seconds+(clock.running?(performance.now()-clock.mark)/1000:0);byId("elapsed").textContent=(clock.running?"约 ":"")+s.toFixed(1)+" 秒";}
setInterval(tickClock,250);
function codeError(code){const err=new Error(D.error(code));err.code=code;return err;}
async function api(path,body){const options={credentials:"same-origin",cache:"no-store"};if(body){options.method="POST";options.headers={"Content-Type":"application/json","X-PGNN-CSRF":csrf};options.body=JSON.stringify(body);}const response=await fetch(path,options);const value=await response.json();if(!response.ok)throw codeError(value.error||"PUBLIC_INTERFACE_NOT_CONNECTED");return value;}
function validateView(value){
 if(!value||!Object.hasOwn(phases,value.phase)||typeof value.terminal!=="boolean"||!['pending','complete','incomplete'].includes(value.delivery_state))throw codeError("PUBLIC_STATE");
 if(value.result!==null){
  const r=value.result;
  if(!value.terminal||value.phase!=="complete"||value.delivery_state!=="complete"||r.model_id!==model.model_id||r.request_id!==value.request_id||JSON.stringify(r.classes)!==JSON.stringify(model.classes)||r.results.length!==1||r.results[0].node_id!=="936")throw codeError("PUBLIC_INCOMPLETE_RESULT");
  const row=r.results[0],p=row.probabilities;
  if(!Array.isArray(p)||p.length!==7||!p.every(v=>Number.isFinite(v)&&v>=0&&v<=1)||row.predicted_class!==model.classes[p.indexOf(Math.max(...p))])throw codeError("PUBLIC_PROBABILITIES");
 }
 if(value.delivery_state==="complete"&&value.result===null)throw codeError("PUBLIC_MISSING_RESULT");
}
function render(value,context=D.context.mode==="record_validation"?"acceptance":"current"){
 clearTimeout(timer);clearResult();validateView(value);recordView=context==="acceptance";
 if(recordView){connected=false;const n=byId("deployment-notice");n.hidden=false;n.textContent="验收记录渲染检查 · 待部署界面。这里显示既有授权请求，不是新查询，不生成材料。";byId("request-label").textContent="验收请求";byId("wall-label").textContent="验收记录总耗时";byId("wire-label").textContent="验收记录在线通信量";byId("cost-note").textContent="仅为既有验收记录，本页未执行新查询；不计作当前请求进度或成本。";byId("connection").textContent="验收记录 · 待部署";byId("connection").className="badge neutral";}
 byId("request-id").textContent=value.request_id;byId("phase-name").textContent=value.terminal&&value.delivery_state==="complete"?"完整交付":phases[value.phase];
 const index=phaseOrder.indexOf(value.phase);document.querySelectorAll("#phases li").forEach((item,i)=>{item.classList.toggle("done",index>=0&&(i<index||value.terminal&&value.delivery_state==="complete"));item.classList.toggle("active",i===index&&!value.terminal);});
 busy=!value.terminal;byId("submit").disabled=busy||!connected||recordView||D.context.mode!=="live";byId("submit").textContent=recordView?"验收记录，不执行查询":busy?"本次请求正在运行":"发起新的授权查询";
 const delivered=value.delivery_state==="complete"&&value.result&&value.terminal;
 byId("delivery-badge").textContent=delivered?(recordView?"验收记录：完整交付":"本次完整交付"):value.terminal?(recordView?"验收记录：未完成交付":"失败 / 未完成交付"):"等待完整交付";
 byId("delivery-badge").className="badge "+(delivered?"connected":value.terminal?"failed":"neutral");
 byId("error-details").hidden=!value.error;byId("error-code").textContent=value.error||"";
 if(delivered){const row=value.result.results[0];byId("empty-result").hidden=true;byId("prediction").hidden=false;byId("predicted-class").textContent=D.names[row.predicted_class];byId("top-probability").textContent=D.pct(Math.max(...row.probabilities));value.result.classes.forEach((name,i)=>{const line=D.el("div",undefined,"prob-row"+(name===row.predicted_class?" winner":""));const label=D.el("span",D.names[name]),bar=D.el("div",undefined,"bar"),fill=D.el("span"),number=D.el("b",D.pct(row.probabilities[i]));fill.style.width=(row.probabilities[i]*100)+"%";bar.append(fill);line.append(label,bar,number);byId("probabilities").append(line);});}
 else byId("result-message").textContent=value.terminal?(D.error(value.error)+" 没有可显示的最终概率。"):"正在执行本次请求，仅在双方最终份额完整交付后展示结果。";
 if(value.cost){const c=value.cost;if(Number.isFinite(c.wall_seconds)){byId("wall-time").textContent=c.wall_seconds.toFixed(2);const now=performance.now();let seconds=c.wall_seconds;if(clock&&clock.sid===value.request_id&&clock.running&&!value.terminal)seconds=Math.max(seconds,clock.seconds+(now-clock.mark)/1000);clock={sid:value.request_id,seconds,mark:now,running:!value.terminal&&!recordView};tickClock();}else resetClock();if(Number.isFinite(c.wire_bytes))byId("wire-bytes").textContent=(c.wire_bytes/1048576).toFixed(2);if(Number.isFinite(c.rounds))byId("rounds").textContent=c.rounds.toLocaleString("zh-CN");}else resetClock();
 if(!value.terminal&&!recordView)timer=setTimeout(poll,800);
}
function disconnected(code){connected=false;busy=false;clearTimeout(timer);resetClock();clearResult();byId("connection").textContent="未连接";byId("connection").className="badge disconnected";byId("phase-name").textContent="未连接";byId("submit").disabled=true;byId("submit").textContent=D.context.mode==="pending_deployment"?"预览未连接查询后端":"后端未连接";byId("gate-message").textContent=D.error(code);byId("delivery-badge").textContent="无本次完整结果";byId("delivery-badge").className="badge neutral";byId("result-message").textContent="状态未确认，不显示示例预测或旧结果。请刷新读取原请求状态。";document.querySelectorAll("#phases li").forEach(n=>n.classList.remove("done","active"));byId("error-code").textContent=code;byId("error-details").hidden=false;}
async function poll(){if(!current||recordView)return;try{render(await api("/api/status",{token:current}));}catch(error){disconnected(error.code||"PUBLIC_INTERFACE_NOT_CONNECTED");}}
byId("submit").addEventListener("click",async()=>{if(busy||!connected||recordView||D.context.mode!=="live")return;busy=true;clearResult();resetClock();byId("submit").disabled=true;current=crypto.randomUUID().replaceAll("-","");sessionStorage.setItem("pgnn-current-request",current);try{render(await api("/api/submit",{token:current}));}catch(error){disconnected(error.code||"PUBLIC_INTERFACE_NOT_CONNECTED");}});
(async()=>{if(location.protocol==="file:"||D.context.mode==="pending_deployment"){disconnected("PUBLIC_INTERFACE_NOT_CONNECTED");byId("gate-message").textContent="展示预览未连接真实查询，不生成材料。正式服务固定授权目标与接收端。";return;}try{const overview=await api("/api/overview");csrf=overview.csrf;const access=new URLSearchParams(location.hash.slice(1)).get("access");if(access){history.replaceState(null,"",location.pathname);await api("/api/login",{access});const authorized=await api("/api/overview");overview.connected=authorized.connected;overview.connection_reason=authorized.connection_reason;}connected=overview.connected===true;if(!connected){disconnected(overview.connection_reason||"REAL_UID_PERMISSIONS_NOT_ACCEPTED");return;}byId("connection").textContent="真实后端已连接";byId("connection").className="badge connected";byId("gate-message").textContent="真实身份权限已验收，每次新查询使用独立材料；刷新只读原请求。";byId("phase-name").textContent="待发起查询";byId("submit").disabled=false;byId("submit").textContent="发起授权查询";current=sessionStorage.getItem("pgnn-current-request");if(current)await poll();}catch(error){disconnected(error.code||"PUBLIC_INTERFACE_NOT_CONNECTED");}})();
