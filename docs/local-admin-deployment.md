# 本机管理员部署步骤

从工程终端执行以下命令。密码仅由 sudo 在该终端提示输入，不传给页面、服务或聊天；不要使用 `sudo -S` 或把密码写入配置。服务用专用系统账户，不为这些账户设置登录密码。

```sh
cd /home/tenggn/projects/privacy_gnn
sudo --preserve-env=WSL_DISTRO_NAME /usr/bin/python3 scripts/install_local_roles.py --check &&
sudo --preserve-env=WSL_DISTRO_NAME /usr/bin/python3 scripts/install_local_roles.py --install &&
sudo --preserve-env=WSL_DISTRO_NAME /usr/bin/python3 scripts/install_local_roles.py --verify
```

`--check`检查固定64节点/160轮已发布模型、检查点、同态资产和原消费账本，查找仍打开待迁移状态文件的进程，验证同一文件系统及部署目标安全性；失败不启动服务。

也在任何账户/组改动前逐项核验管理员辅助程序：仅从管理员持有且其他身份不可写的系统目录查找，检查可执行权限和所有权，不使用调用者PATH。当前系统的`gpasswd`为`/usr/bin/gpasswd`。上面的`&&`保证检查或安装失败后不继续验证。

`--install`建立 pgnn-s0、pgnn-s1、pgnn-dealer、pgnn-receiver、pgnn-coordinator、pgnn-page 六个非登录系统账户；安装管理员持有的只读代码/公共配置，迁移原状态文件并保留旧路径链接，链接现有发布模型和持久输入/同态资产，记录权限及内容校验。不会重建账本、恢复模型、训练、扩大图或清理历史会话。

安装三个服务：管理员角色执行器、受限协调器和只监听127.0.0.1的页面。页面初始为未连接，后端只有真实身份权限验证通过后才接受密码查询；未连接不产生概率或虚构成本。协调器不能读双方秘密或调用任意命令；执行器固定角色、动作、模型、授权目标和接收端。

`--verify`检查账户实际UID、服务身份、代码/配置所有权及只读属性、账本迁移校验记录。完成后保留终端输出，并在聊天里回复“部署完成”。我会通过受限执行器继续真实UID权限矩阵、连接门控和查询验证。无需发送密码。

```sh
systemctl status pgnn-role-broker pgnn-coordinator pgnn-page --no-pager
curl --fail http://127.0.0.1:8765/api/overview
```

前一命令查看三个服务运行状态；后一命令只读取允许字段的公开概览。页面地址为 `http://127.0.0.1:8765/`。服务未运行或验收未通过时显示未连接。

`--preserve-env=WSL_DISTRO_NAME`保留宿主盘绑定所需的发行版名称；探针无法确认宿主余量时拒绝启动新材料。安装会把访问链接写入仅工程所有者可读的`results/page/access-link.json`。链接中的随机能力令牌用于本机结果授权，不是管理员密码；不要将该文件纳入审阅包或贴到聊天中。权限验收后在本机浏览器打开该文件中的`url`即可登录；页面从地址栏移除令牌，不写请求日志。

安装失败先停止，不手工清空state或角色目录，不执行新训练补资产；提供不含密码的错误信息。安装器保留进度/迁移凭据，用相同命令核查恢复，不批量删除持久资产。管理员仍有访问所有材料的权限；本机部署隔离不改变两方半诚实、可信非串谋离线方等已有协议限制。

2026-10-06首次安装因旧代码错误指定`/usr/sbin/gpasswd`而在组配置阶段失败。六个账户和空`pgnn-gate`已创建，尚未建立迁移记录或移动数据库；修复版本直接复用这些账户，接续组配置。无须`userdel`、删除目录或重置数据库。`--verify`在缺少/未完成迁移记录时明确报告`INSTALLATION_NOT_COMPLETE`，不会将此状态判为已部署。程序错误报告包含当前阶段及原因。

## 已部署后的只读故障诊断

用户随后成功安装、验证`1c8f376`，六身份128项实测矩阵通过。首次真实请求在准入/准备阶段失败，旧会话已终止清理，禁止重跑。当前操作员没有有效sudo缓存，固定角色接口暂未导出完整失败阶段记录。请只执行下面的已测试诊断命令，并提供JSON输出：

```sh
cd /home/tenggn/projects/privacy_gnn &&
sudo --preserve-env=WSL_DISTRO_NAME /usr/bin/python3 scripts/diagnose_local_query.py --session c3c435f768cd4c6c9a0ef99421dc96eb
```

命令只读既有中央状态、事件、协调器请求文档和准备目录文件元数据；它不打开双方消费账本，不读取模型/输入/输出份额，不启动子进程、不生成材料、不修改数据库或权限。输出包括失败阶段/错误码、停止证明、协议是否已申领、准备文件数量及同inode链接数量；清理空间数据分别提供内部/宿主前后余量、删除文件分配块和可回收上界。输出不含查询令牌、cookie或最终概率。缺少会话或数据库时明确拒绝，不创建替代数据库。密码仅由sudo在本地终端提示输入。

目前不需要再次运行`--install`、`validate`或任何训练。先取得故障证据再确定修复和部署；后续源码与冻结运行代码分别标明版本，不把未部署的修改当作实际服务已修复。
