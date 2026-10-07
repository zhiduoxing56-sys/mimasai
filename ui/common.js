"use strict";
const PGNNDisplay=(()=>{
  const names={Case_Based:"基于案例",Genetic_Algorithms:"遗传算法",Neural_Networks:"神经网络",Probabilistic_Methods:"概率方法",Reinforcement_Learning:"强化学习",Rule_Learning:"规则学习",Theory:"理论"};
  const roles={s0:"在线服务器一",s1:"在线服务器二",dealer:"可信离线方",receiver:"授权接收端",coordinator:"协调器",page:"页面服务"};
  const sampling={stratified_frontier:"标签分层邻域抽样",uniform:"标签无关均匀抽样",multi_start:"标签无关多起点抽样"};
  const errors={INTERNAL_SPACE_LOW:"子系统内部空间不足，已拒绝或停止执行。",HOST_SPACE_LOW:"虚拟磁盘所在宿主盘余量不足，已拒绝或停止执行。",HOST_SPACE_UNKNOWN:"无法读取宿主余量，不能启动新材料生成。",INJECTED_INPUT_PREPARATION_FAILURE:"输入准备失败，本次没有完整交付。",QUERY_BUSY:"已有请求运行，请等待该请求结束。",LOCAL_AUTHORIZATION_REQUIRED:"请先使用本机授权链接登录。",LOCAL_AUTHORIZATION_REJECTED:"本机授权未通过，请检查访问链接。",REQUEST_CAPABILITY_REJECTED:"无权查看该请求，或当前浏览器没有本请求的查看权限。",REAL_UID_PERMISSIONS_NOT_ACCEPTED:"本版本真实身份权限尚未验收。",REAL_BACKEND_NOT_CONNECTED:"真实后端尚未连接。",RESTART_REQUIRES_STOP_CONFIRMATION:"服务重启后停止状态待确认，本次没有完整结果。",STOP_UNCONFIRMED:"相关进程停止尚未确认，后端暂不可用。",ROLE_OPERATION_FAILED:"角色执行失败，本次没有完整交付。",WORKER_FAILED:"在线执行失败，本次没有完整交付。",ONLINE_TIMEOUT:"在线执行超时，正在按停止规则收尾。",PUBLIC_INTERFACE_NOT_CONNECTED:"公开状态接口不可用，请稍后刷新查看原请求。"};
  const context=JSON.parse(document.getElementById("display-context").textContent);
  if(context.mode!=="live"){
    const banner=document.getElementById("deployment-notice");banner.hidden=false;
    banner.textContent=context.mode==="record_validation"?"独立展示测试 · 待部署。只读取既有授权验收记录，不连接密码后端，不生成材料。":"新版界面预览 · 待管理员部署。当前预览未连接查询后端，不生成材料；公开成果和验收记录来自已有报告。";
  }
  const page=document.body.dataset.page;
  document.querySelectorAll(".navigation a").forEach(a=>{if(a.dataset.page===page){a.classList.add("selected");a.setAttribute("aria-current","page");}});
  function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
  function pct(x){return (x*100).toFixed(2)+"%";}
  function table(target,headers,rows){const t=el("table"),h=el("thead"),tr=el("tr");headers.forEach(v=>tr.append(el("th",v)));h.append(tr);t.append(h);const b=el("tbody");rows.forEach(row=>{const r=el("tr");row.forEach(v=>r.append(el("td",v)));b.append(r);});t.append(b);document.getElementById(target).replaceChildren(t);}
  return Object.freeze({names,roles,sampling,context,el,pct,table,error:code=>errors[code]||"本次请求未完成，请查看本机运行记录。"});
})();
