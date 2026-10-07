# 本机演示启动与操作稿（2026-10-08）

新版三页界面与独立展示验收已完成，**冻结部署仍为 e7e5436，新版待管理员更新**。现有真实服务保持运行；本轮没有新密码查询、训练或材料生成。七项展示短测及浏览器三页/中文/计时/失败/刷新检查通过；此前真实身份与真实查询证据复用，不能代替新版实际部署验收。逐项状态见 [验收清单](demo-final-acceptance.md)。

## 页面访问与预览

正式入口是 `http://127.0.0.1:8765/`，训练页 `/training`，保障页 `/privacy`。**后两页在当前旧冻结服务中尚未部署**。首次登录在本机读取仅操作员可读的 `results/page/access-link.json`，用其中的 `url` 打开浏览器；令牌在URL片段中，登录后移除。它不是sudo密码，不应贴到聊天或复制进审阅包。

不需要管理员权限的新版只读预览：

```sh
cd /home/tenggn/projects/privacy_gnn
python3 scripts/demo_preview.py
```

打开 `http://127.0.0.1:8766/`，三个页面均可导航。首页明确“待部署/未连接”，查询按钮禁用，服务拒绝POST；成果与保障页只展示经审核的既有公开记录。此进程是操作员预览，**不作为真实页面UID权限验收**。结束在该终端按Ctrl-C。本轮验收使用的预览和记录适配器已关闭，不留过夜测试负载。

离线备选：用浏览器打开 `results/demo-final/static-review/index.html`；同目录的training.html、privacy.html自带样式、脚本与允许列表数据，无需联网或后端，均标明待部署。源码包不包含这些生成HTML，公开证据包包含它们。

## 更新冻结部署

当前非交互探针 `sudo -n /usr/bin/id` 返回“需要密码”。以下步骤由操作员在本地终端执行；密码仅交给sudo，不传给脚本、页面或聊天。项目源码已提交，工作树应干净。

```sh
cd /home/tenggn/projects/privacy_gnn &&
sudo --preserve-env=WSL_DISTRO_NAME /usr/bin/python3 scripts/install_local_roles.py --check &&
sudo --preserve-env=WSL_DISTRO_NAME /usr/bin/python3 scripts/install_local_roles.py --install &&
sudo --preserve-env=WSL_DISTRO_NAME /usr/bin/python3 scripts/install_local_roles.py --verify &&
python3 scripts/local_deployment.py audit &&
python3 scripts/check_demo_deployment.py
```

`--check`验证公共展示资产、现有64节点/160轮模型、状态文件未打开、原inode及宿主探针；`--install`更新管理员只读代码/公共资产并重启三服务，复用账户、模型和账本；`--verify`验证实际身份及只读部署。**不重建或重置账本，不恢复模型，不生成材料或重训。** 新运行源码哈希使旧权限证据失效，需随后audit重新绑定六身份140项；该审计只运行权限、空间和公开参数准备探针，不执行密码协议。

`check_demo_deployment.py`核对新版公共文件字节和root只读属性、源码绑定的权限门控以及正式服务三页与公共JSON；只GET，不submit。未部署时返回PENDING_ADMIN_DEPLOYMENT及退出码2，本轮已独立核实；不会把预览当作已部署。不运行`local_deployment.py validate`，本轮没有需要再次执行的密码链变更。

新版实际页面浏览器空闲核对（无新查询）：

```sh
/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -ExecutionPolicy Bypass -File '\\wsl.localhost\GNN-Project\home\tenggn\projects\privacy_gnn\scripts\capture_local_page.ps1' -ReadyOnly
```

该既有工具只授权并展示空闲首页，不提交查询。三页实际浏览器导航、接收授权绑定和页面真实UID的新版验收在管理员更新后接续；本轮已交付的是独立待部署预览证据。当前管理员阻塞不影响已完成的源码/公共资产/说明/截图。

## 正常启动、状态检查与停止

部署已安装并验收的前提下：

```sh
# 在WSL的项目终端按服务依赖顺序启动；不会自动创建密码请求
sudo /usr/bin/systemctl start pgnn-role-broker pgnn-coordinator pgnn-page
# 实际版本、身份和三服务状态
readlink -f /opt/privacy-gnn/code
/usr/bin/systemctl status pgnn-role-broker pgnn-coordinator pgnn-page --no-pager
# 仅公开概览；没有授权cookie时connected=false是正常的
curl --fail --silent http://127.0.0.1:8765/api/overview
# 正常停止前确认没有运行/停止待确认请求，再停止三服务
sudo /usr/bin/systemctl stop pgnn-page pgnn-coordinator pgnn-role-broker
```

systemd使用KillMode=control-group和15秒停止超时；停机不是材料恢复入口。紧急停止或异常重启若留下停止待确认，后端会拒绝新查询，保留墓碑/账本/材料ID，由固定诊断接口核对，不重跑旧会话、不清理未知状态。不要手动改状态库或删除账本。宿主未知/不足时保持拒绝；不为演示关闭范围守卫或磁盘保护。

本轮实际三服务active/running，root执行器、协调器与页面仍按既有角色身份工作。预览测试与服务完全分开，服务没有新查询负载。

## 三至五分钟演示稿

默认使用已有记录，**无需新密码查询**。若尚未更新部署，先明确说“新版界面是待部署预览，真实后端的既有验收另行展示”。

| 时间 | 页面 / 操作 | 讲述要点 |
| --- | --- | --- |
| 0:00—0:45 | 隐私推理首页 | 论文主题七分类、64节点、模型来自160轮共享检查点；固定目标936和授权接收端，展示状态不是完成百分比 |
| 0:45—1:30 | 打开既有真实成功截图及新版验收记录渲染截图 | 既有结果为“基于案例”，71.875%；72.31秒、在线发送92.31 MiB，完整交付才有结果。这是验收记录，不冒充现场新查询 |
| 1:30—2:45 | 训练与效果 | 28/14/22划分，18/22测试正确、宏F1 0.8201；160点真实更新前损失。标签参与抽样、小图范围、验证神经网络类召回0。词特征与浮点/共享条件分别列出 |
| 2:45—3:45 | 隐私与运行保障 | 六角色公开流程、140项既有真实身份验收，可信离线方处理相关随机材料；本机OS保障不是主动密码安全 |
| 3:45—4:30 | 保障页的故障/清理记录及故障截图 | 输入失败没有完整结果，刷新不重跑；删除块、最后链接块、上界和两层余量分别报告，宿主变化0 |

截图：`results/local-page/connected-success.png`是既有真实部署结果；`results/demo-final/inference-acceptance-pending.png`是新版界面通过独立HTTP适配器渲染同一真实结果，标明验收记录/待部署，**不是新版服务真实UID验收**。故障对应既有和新版两张截图同样区分。新增三页截图均标记待部署。

已更新并通过新版部署验收后，如确实需要现场执行新查询，可在首页点击一次“发起授权查询”；约一分钟内的耗时只作既有记录参考，实际值取当前后端。页面运行时显示真实阶段与“约”经过时间，不显示虚构完成百分比；完整交付才显示概率。不要反复点击、运行故障注入或用刷新制造重复会话。浏览器刷新恢复本请求令牌并只取状态；读状态失败清空本次预测，服务状态未确认时不自动重试。此现场新查询是操作员后续选择，本轮为展示验收没有执行它。

## 可审阅交付

[源码包](../review/privacy-gnn-source-review.tar.gz)、[公开证据包](../review/local-page-evidence.tar.gz)、[文件哈希和版本清单](../review/delivery.json)。证据包明确列出允许文件，包含三页离线HTML、截图、短测、公共资产审计和当前空间/版本记录，保留此前真实查询及权限矩阵。访问能力、cookie、浏览器配置、秘密材料、消费账本及完整验证状态均不打包。

半诚实双方、可信非串谋离线方、管理员可访问及可信持久状态等限制保持；64节点22测试例不等于完整Cora效果。原协议、数值、模型、检查点、账本及历史证据保留。
