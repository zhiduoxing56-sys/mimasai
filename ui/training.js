"use strict";
(()=>{
 const v=JSON.parse(document.getElementById("training-data").textContent),D=PGNNDisplay,p=D.pct,metric=r=>[p(r.accuracy),p(r.macro_precision),p(r.macro_recall),r.macro_f1.toFixed(4)],split={train:"训练",validation:"验证",test:"测试"};
 document.getElementById("correct-count").textContent=`${Math.round(v.actual.metrics.test.accuracy*22)} / 22`;
 document.getElementById("test-accuracy").textContent=p(v.actual.metrics.test.accuracy);document.getElementById("test-f1").textContent=v.actual.metrics.test.macro_f1.toFixed(4);
 D.table("split-metrics",["划分 / 例数","准确率","宏精确率","宏召回率","宏 F1"],Object.entries(v.actual.metrics).map(([k,r])=>[split[k]+" / "+r.count,...metric(r)]));
 const kinds={word_matched:"词特征 · 匹配条件",gcn_float:"图模型 · 浮点参考",word_selected:"词特征 · 验证所选"},conditions=r=>`浮点，隐层 ${r.hidden}，学习率 ${r.learning_rate}，${r.iterations} 轮`;
 const main=v.comparisons.filter(r=>r.seed===v.seed);
 D.table("comparison-metrics",["模型 / 条件","测试准确率","宏精确率","宏召回率","宏 F1"],[...main.map(r=>[kinds[r.kind]+"\n"+conditions(r),...metric(r.metrics.test)]),["图模型 · 实际共享\n定点，隐层 6，学习率 0.5，160 轮",...metric(v.actual.metrics.test)]]);
 D.table("other-seeds",["对照","种子","测试准确率","宏 F1"],v.comparisons.map(r=>[kinds[r.kind],r.seed,p(r.metrics.test.accuracy),r.metrics.test.macro_f1.toFixed(4)]));
 D.table("class-recall",["论文主题","测试例数","测试召回","验证召回"],v.actual.metrics.test.classes.map((r,i)=>[D.names[v.classes[i]],r.support,p(r.recall),p(v.actual.metrics.validation.classes[i].recall)]));
 D.table("label-free",["抽样 / 种子","边对","无原始邻居","测试准确率 / 宏 F1"],v.label_free.map(r=>[D.sampling[r.strategy]+"\n"+r.seed,r.edge_pairs,r.isolated,p(r.test.accuracy)+" / "+r.test.macro_f1.toFixed(4)]));
 const holder=document.getElementById("learning-curve"),curve=v.actual.loss_curve;
 if(curve.length){
  const ns="http://www.w3.org/2000/svg",svg=document.createElementNS(ns,"svg");svg.setAttribute("viewBox","0 0 640 240");svg.setAttribute("aria-hidden","true");
  function shape(tag,attrs,text){const n=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,x])=>n.setAttribute(k,x));if(text)n.textContent=text;svg.append(n);return n;}
  const high=Math.ceil(Math.max(...curve.map(r=>r.preupdate_loss))*2)/2;
  for(let i=0;i<5;i++){const y=20+i*42;shape("line",{x1:46,x2:612,y1:y,y2:y,class:"chart-grid"});shape("text",{x:37,y:y+4,"text-anchor":"end",class:"chart-label"},(high*(1-i/4)).toFixed(1));}
  shape("polyline",{points:curve.map(r=>`${46+r.iteration/159*566},${188-r.preupdate_loss/high*168}`).join(" "),class:"loss-line"});
  for(const i of [1,40,80,120,160])shape("text",{x:46+(i-1)/159*566,y:211,"text-anchor":"middle",class:"chart-label"},String(i));
  shape("text",{x:329,y:233,"text-anchor":"middle",class:"chart-label"},"共享训练轮次（每轮更新前）");holder.append(svg);
  document.getElementById("curve-note").textContent=`真实记录 ${curve.length} 点：${v.actual.first_loss.toFixed(6)} → ${v.actual.last_preupdate_loss.toFixed(6)}。仅显示实际共享训练，没有混入浮点或更长参考曲线。`;
 }else{holder.textContent="未提供已保存曲线；以下汇总指标与流程来自既有报告。";document.getElementById("curve-note").textContent="没有生成替代曲线。";}
 document.getElementById("training-model").textContent=v.model_id;
 const labels={representative:"代表性验收公开汇总",storage_delivery:"词特征与数值解释公开汇总"};v.sources.forEach(r=>document.getElementById("training-sources").append(D.el("p",labels[r.report]+" · SHA-256 "+r.sha256)));
})();
