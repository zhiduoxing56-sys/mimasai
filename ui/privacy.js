"use strict";
(()=>{
 const v=JSON.parse(document.getElementById("safety-data").textContent),D=PGNNDisplay,mib=x=>x===null?"未知":(x/1048576).toFixed(2)+" MiB",count=x=>x.toLocaleString("zh-CN"),names={success:"成功验收",failure:"输入故障验收"};
 const total=v.audit.roles.reduce((s,r)=>s+r.checks,0);document.getElementById("permission-total").textContent=`${total} / ${total} 项通过`;
 D.table("permission-roles",["角色","检查","秘密与结果读取范围"],v.audit.roles.map(r=>[D.roles[r.role],`${r.passed} / ${r.checks}`,({s0:"仅本方秘密与账本",s1:"仅本方秘密与账本",dealer:"仅公共计划与本方随机材料",receiver:"仅当前授权最终份额",coordinator:"公开状态与会话元数据",page:"公开状态与授权最终结果"})[r.role]]));
 v.audit.roles.forEach(r=>document.getElementById("uid-detail").append(D.el("p",D.roles[r.role]+" · 账户标识 pgnn-"+r.role+" · 用户编号 "+r.uid)));
 document.getElementById("audit-version").textContent="验收冻结版本："+v.audit.runtime_commit+"；源码摘要："+v.audit.source_sha256;
 D.table("acceptance-requests",["记录","交付","总耗时","在线通信量","交互"],v.requests.map(r=>[names[r.kind],r.has_result?"完整结果":"无完整结果",r.cost.wall_seconds.toFixed(2)+" 秒",mib(r.cost.wire_bytes),r.cost.rounds===null?"未知":count(r.cost.rounds)+" 轮"]));
 D.table("cleanup-records",["记录","删文件","删除块 / 最后链接块","预览上界","内部变化","宿主变化"],v.cleanup.map(r=>[names[r.kind],count(r.removed_files),mib(r.deleted_file_allocated_bytes)+" / "+mib(r.unlinked_last_link_allocated_bytes),mib(r.reclaimable_upper_bytes),mib(r.space_after.internal_available_bytes-r.space_before.internal_available_bytes),r.space_before.host_available_bytes===null||r.space_after.host_available_bytes===null?"未知":mib(r.space_after.host_available_bytes-r.space_before.host_available_bytes)]));
 D.table("space-details",["记录","内部可用：前 → 后（字节）","宿主可用：前 → 后（字节）","宿主探针"],v.cleanup.map(r=>[names[r.kind],count(r.space_before.internal_available_bytes)+" → "+count(r.space_after.internal_available_bytes),r.space_before.host_available_bytes===null||r.space_after.host_available_bytes===null?"未知":count(r.space_before.host_available_bytes)+" → "+count(r.space_after.host_available_bytes),r.space_after.host_status==="READABLE"?"可读":"未知"]));
 const labels={real_uid:"真实身份权限矩阵",query_success:"既有成功查询",query_failure:"既有输入故障",independence:"新材料独立性"};v.sources.forEach(r=>document.getElementById("safety-sources").append(D.el("p",labels[r.report]+" · SHA-256 "+r.sha256)));
})();
