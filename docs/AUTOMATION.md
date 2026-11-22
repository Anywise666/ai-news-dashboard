# AI 晨报播客自动化配置与维护文档

> 最后更新：2026-11-22  
> 仓库：<https://github.com/Anywise666/ai-news-dashboard>  
> GitHub Pages：<https://anywise666.github.io/ai-news-dashboard/>

本文档是仓库内关于"AI 晨报双语播客生成与推送"的配置基线。**以后任何脚本、定时规则、路径、依赖或仓库变更，都必须同步更新本文档并推送到 GitHub。**

---

## 1. 当前主方案概览

当前主方案使用 **GitHub Actions**（2026-11-21 由 WorkBuddy 本地自动化迁移而来）。不再依赖任何常开服务器或本机在线。

```text
aihot API → GitHub Actions (ubuntu-latest) → gen_audio.py → audio/YYYY-MM-DD/ → GitHub main → GitHub Pages
```

核心原则：

- 页面本身在浏览器端实时拉取 `https://aihot.news/api/v1`，所以新闻内容每天会更新。
- 预生成的中英双语 mp3 和 `manifest.json` 由 GitHub Actions 每日定时任务生成。
- GitHub `main` 分支上的 `audio/YYYY-MM-DD/manifest.json` 是"当天已完成"的唯一事实源。
- 任务幂等：当天 manifest 已存在且有效就跳过生成与推送。
- 公共仓库的 GitHub Actions 永久免费、不限分钟数，无需信用卡，也不受本机在线状态影响。
- 服务器部署方案（第 6 节）为历史备用，**当前未启用**。
- WorkBuddy 本地自动化作为**最后一道防线**（第 2.4 节）：每天 20:00 检查线上当天音频，缺失才补跑，正常情况不产生任何操作。

---

## 2. 自动化配置

### 2.1 GitHub Actions（当前主方案）

| 字段 | 值 |
|---|---|
| 名称 | `AI晨报双语播客每日更新` |
| 文件 | `.github/workflows/daily-podcast.yml` |
| 状态 | `ACTIVE` |
| 调度 | 三个错峰 cron：`'17 0 * * *'`（北京 08:17 主）、`'23 5 * * *'`（北京 13:23 午后兜底）、`'41 11 * * *'`（北京 19:41 晚间兜底） |
| 兜底触发 | `push` 到 `main`（`paths-ignore: audio/**`、`feed.xml`），任何非音频提交都会触发一次幂等检查，防止 schedule 被丢弃时整天不生成 |
| 手动入口 | `workflow_dispatch`，可选 `target_date`（`YYYY-MM-DD`，留空=北京时间当天），用于指定日期验证或补跑 |
| 运行器 | `ubuntu-latest` |
| Python | `3.11`（actions/setup-python@v5） |
| 依赖 | `edge-tts` |
| 推送方式 | `GITHUB_TOKEN`（需仓库 Settings → Actions → General → Workflow permissions 设为 **Read and write**） |
| 并发控制 | `concurrency.group = podcast-daily`，`cancel-in-progress: false` |

流程：checkout → 计算北京时间日期 → 检查当天 manifest → 未完成则 `python tools/gen_audio.py <日期>` → 每次都运行 `python tools/gen_feed.py` 重建播客 RSS → `git add audio/ feed.xml` → `git commit` + `git push origin HEAD:main`。

> feed 与音频在同一提交中推送：即使当天音频已完成（幂等跳过），feed 步骤仍会运行，可在 feed 缺失/损坏时自愈；无变化时输出 `NO_CHANGES_SKIP`。

关键输出标记：

- `ALREADY_DONE`：当天已完成，幂等跳过。
- `NO_CHANGES_SKIP`：生成后无文件变化，跳过提交。
- `PUSH_OK`：本次成功推送。

> 注意：GitHub Actions 的 `schedule` 只接受 UTC。2026-11-22 故障复盘：原单点 cron `'30 0 * * *'`（UTC 整点半高峰）自建仓以来 **0 次触发**，GitHub 页面显示 "0 workflow runs"，而手动 `workflow_dispatch` 正常——即云端 cron 被丢弃，非脚本问题。
>
> 修复策略（2026-11-22）：
> 1. **多时点错峰**：三个 cron 分散在全天，避开 UTC 整点/半点拥堵窗口，任一触发即可，幂等检查保证当天只生成一次。
> 2. **push 兜底**：任何 push 到 `main`（排除 `audio/**`、`feed.xml` 自身）都会触发一次幂等运行。即便 schedule 全部失效，只要有日常代码/文档提交就会补上当天生成；`GITHUB_TOKEN` 推送的音频/feed 提交被 `paths-ignore` 排除，无递归风险。
>
> 其他约束：公共仓库若连续 60 天无提交，GitHub 会自动停用定时任务；本修复的 push 兜底也规避了这一点。用 `GITHUB_TOKEN` 推送的 commit 不会再次触发本 workflow。

### 2.2 权限配置（一次性）

仓库页面 → **Settings** → 左侧 **Actions → General** → 底部 **Workflow permissions** → 选 **Read and write permissions** → Save。（URL：`<repo>/settings/actions`）

### 2.3 手动验证

Actions 页 → 左侧选 `AI晨报双语播客每日更新` → 右侧 **Run workflow**：

- **幂等分支**：`target_date` 留空直接跑，因当天 manifest 已存在，日志出现 `ALREADY_DONE` 即通。
- **完整生成+推送分支**：在 `target_date` 填一个尚无音频的日期（如 `2026-11-20`），跑完日志应出现 `PUSH_OK`，随后 main 上出现 `audio/2026-11-20/`，Pages 自动重新部署。

绿色对勾 + 对应标记即为验证通过。

### 2.4 WorkBuddy 本地自动化（最后一道防线）

迁移前使用两个 WorkBuddy 本地任务，在 GitHub Actions 接管后一度停用：

| 名称 | 原 ID | 原调度 | 状态 |
|---|---|---|---|
| `AI晨报双语播客每日更新` | `a31fad70-e425-4dc2-b2ab-e8ee0ee1bd43` | `FREQ=DAILY;BYHOUR=8;BYMINUTE=30` | 已停用（历史） |
| `AI晨报双语播客上线补跑检查` | `af8c52b6-579e-411d-9e6e-e802312cdb6e` | `FREQ=HOURLY;INTERVAL=1` | 已停用（历史） |

二者原执行命令均为 `bash "./audio-pipeline/daily_update.sh"`。原提示词约定：只运行一次脚本，`ALREADY_DONE_*` / `REMOTE_LOCK_SKIP` / `NO_REPORT_SKIP` / `NO_CHANGES_SKIP` / `ANOTHER_MACHINE_DONE` 视为正常跳过，仅 `PUSH_OK` / `PUSH_OK_AFTER_REBASE` 表示成功，`PUSH_FAILED` 报错。

**2026-11-22 新增兜底任务（当前启用）**：

| 名称 | ID | 调度 | 执行命令 | 状态 |
|---|---|---|---|---|
| `AI晨报播客兜底检查` | `ee5e56ac-3f26-4798-a237-2ded5165a435` | `FREQ=DAILY;BYHOUR=20;BYMINUTE=0`（每天北京时间 20:00） | `bash "D:/Python Work/AI汇报/ai-news-dashboard/tools/ensure_today.sh"` | ACTIVE |

定位：GitHub Actions 三个错峰 cron + push 兜底之后的**最后一道防线**，专门覆盖「当天零提交 + 三个 cron 全部被 GitHub 丢弃」的边缘场景。脚本 `tools/ensure_today.sh` 以线上 `audio/<今天>/brief_zh.mp3` 的 HTTP 状态为唯一事实源：

- 线上 200 → 输出 `ALREADY_OK` 直接退出（绝大多数情况，不做任何写操作，不干扰云端任务）。
- 线上 404 → 本地 `gen_audio.py` + `gen_feed.py` 生成，commit 后带 6 次重试 push 到 main（应对本机代理对 github.com 的间歇性握手失败），再轮询复核上线，成功输出 `PUSH_OK`。
- 失败标记：`GEN_FAILED` / `FEED_FAILED` / `PUSH_FAILED`。

> 依赖提醒：该任务需要本机在 20:00 在线且已装 `edge-tts`。它只在云端两道防线都失效时才真正干活，是「最后保险」而非主链路；即便某天本机不在线，也只是回到无兜底状态，不影响云端正常工作。

---

## 3. 脚本与布局

### 3.1 仓库内文件

| 路径 | 说明 |
|---|---|
| `.github/workflows/daily-podcast.yml` | **当前主方案**：GitHub Actions 每日定时生成并推送播客音频 |
| `tools/daily_update.sh` | 跨机器幂等补跑脚本（原 WorkBuddy 任务使用，现备用）：生成音频 → 克隆仓库 → 拷贝页面与音频 → commit → push |
| `tools/gen_audio.py` | 音频生成脚本，使用 `edge-tts`（Actions 直接复用）；同时生成 90 秒速览 `brief_zh.mp3` |
| `tools/gen_feed.py` | 播客 RSS 生成脚本（纯标准库），扫描 audio/ 生成 feed.xml，Actions 每次运行后重建 |
| `index.html` | GitHub Pages 首页，日历档案 + 双语播客 + 90 秒速览 + 播客订阅 + 阅读工具 |
| `audio/YYYY-MM-DD/` | 每日预生成的中英双语 mp3 + `brief_zh.mp3`(速览) + `manifest.json`(含 `brief` 字段) |
| `feed.xml` | 播客订阅源（RSS 2.0 + iTunes），每期 enclosure 指向 brief_zh.mp3，保留最近 60 期 |
| `README.md` | 仓库总说明 |
| `docs/AUTOMATION.md` | 本文档，自动化配置与维护基线 |

### 3.2 本地工作区布局

```text
G:/Python Work/AI汇报/
├── audio-pipeline/
│   ├── daily_update.sh
│   └── gen_audio.py
├── ai-daily-live/
│   ├── index.html
│   └── audio/
└── docs/
    └── AUTOMATION.md
```

### 3.3 双布局兼容

`tools/daily_update.sh` 和 `tools/gen_audio.py` 都兼容两种目录布局：

| 场景 | 页面目录 | 音频目录 | 生成脚本目录 |
|---|---|---|---|
| 本地工作区 | `ai-daily-live/` | `ai-daily-live/audio/` | `audio-pipeline/` |
| GitHub 仓库 / 服务器 | 仓库根目录 | 根目录 `audio/` | `tools/` |

脚本通过“从自身位置推导工作目录”实现兼容，不依赖固定的 Windows 绝对路径。

---

## 4. 补跑脚本流程

`tools/daily_update.sh` 的流程：

1. 计算北京时间当天日期 `YYYY-MM-DD`。
2. 通过公开 raw 地址快速检查：
   - `https://raw.githubusercontent.com/Anywise666/ai-news-dashboard/main/audio/YYYY-MM-DD/manifest.json`
   - 若已存在且含 `items`，直接输出 `ALREADY_DONE_REMOTE_RAW` 并退出。
3. 临时克隆 GitHub 仓库，用 Git 状态再次检查 `origin/main:audio/YYYY-MM-DD/manifest.json`，避免 raw CDN 缓存误判。
4. 获取跨机器锁：
   - 锁分支：`automation-lock/YYYY-MM-DD`
   - 若其他机器持锁，输出 `REMOTE_LOCK_SKIP` 并退出。
   - 若锁超过 2 小时未释放，视为过期锁并尝试接管。
   - 任务结束或失败时自动删除锁分支。
5. 本地准备音频：
   - 本地已有有效 `manifest.json` 时复用，避免重复 TTS。
   - 否则调用 `gen_audio.py` 生成。
6. 拷贝 `index.html` 和 `audio/` 到临时仓库，commit 并 push 到 `main`。
7. 若首次 push 失败：
   - 再次检查远端是否已有当天 manifest；
   - 若已有，输出 `ANOTHER_MACHINE_DONE`；
   - 否则尝试 rebase 后重试一次。

---

## 5. 多机器生效前提

要让“所有登录本账号的机器上线后补跑”真正生效，每台机器需要满足：

1. 登录同一个 WorkBuddy 账号。
2. 打开同一个工作区 / 项目。
3. 本地具备 Python 3，并安装 `edge-tts`。
4. 本机 SSH key 已绑定 GitHub 账号 `Anywise666`，具备仓库写权限。
5. 能访问 `aihot.news` API 和 GitHub。

如果某台机器只上线 WorkBuddy，但没有打开该工作区或缺少依赖，自动化即使触发也无法完成补跑。

---

## 6. 备用方案：CentOS 8 服务器 cron（未执行）

当本机不可长期在线时，可切换到常开服务器方案。以下为备用部署基线。

### 6.1 依赖准备

```bash
sudo yum install -y python3 python3-pip git cronie
sudo pip3 install edge-tts
sudo systemctl enable --now crond
sudo timedatectl set-timezone Asia/Shanghai
```

### 6.2 部署目录

```bash
sudo mkdir -p /opt/ai-news-dashboard/logs
```

将仓库内容部署到：

```text
/opt/ai-news-dashboard/
├── index.html
├── tools/
│   ├── daily_update.sh
│   └── gen_audio.py
├── audio/
├── README.md
└── docs/
    └── AUTOMATION.md
```

### 6.3 SSH 部署密钥

在服务器生成 SSH key，并将公钥作为 GitHub 仓库 `Anywise666/ai-news-dashboard` 的 Deploy Key 添加，需勾选写权限。

```bash
ssh-keygen -t ed25519 -C "ai-news-dashboard-server"
cat ~/.ssh/id_ed25519.pub
```

测试：

```bash
ssh -T git@github.com
```

### 6.4 cron 配置

```bash
crontab -e
```

加入：

```cron
30 8 * * * cd /opt/ai-news-dashboard && /usr/bin/bash ./tools/daily_update.sh >> /opt/ai-news-dashboard/logs/daily_update.log 2>&1
```

如果系统时区不是 `Asia/Shanghai`，可使用：

```cron
CRON_TZ=Asia/Shanghai
30 8 * * * cd /opt/ai-news-dashboard && /usr/bin/bash ./tools/daily_update.sh >> /opt/ai-news-dashboard/logs/daily_update.log 2>&1
```

> 注意：部分 cron 实现不完全支持 `CRON_TZ`。更稳妥的方式是先把服务器系统时区设置为 `Asia/Shanghai`。

### 6.5 systemd timer 替代方案

服务文件 `/etc/systemd/system/ai-news-dashboard.service`：

```ini
[Unit]
Description=AI News Dashboard Daily Podcast Update

[Service]
Type=oneshot
WorkingDirectory=/opt/ai-news-dashboard
ExecStart=/usr/bin/bash /opt/ai-news-dashboard/tools/daily_update.sh
```

定时器 `/etc/systemd/system/ai-news-dashboard.timer`：

```ini
[Unit]
Description=Run AI News Dashboard update daily at 08:30

[Timer]
OnCalendar=*-*-* 08:30:00
Persistent=true
Unit=ai-news-dashboard.service

[Install]
WantedBy=timers.target
```

启用：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ai-news-dashboard.timer
sudo systemctl list-timers | grep ai-news-dashboard
```

其中 `Persistent=true` 支持机器关机错过时间后，开机时补跑一次。

---

## 7. 维护约定（必须执行）

**从 2026-11-21 起，本文档是自动化配置的仓库内唯一基线。以后同步更新维护本文档。**

发生以下任一变更时，必须更新本文档并提交到 GitHub：

- 修改 `.github/workflows/daily-podcast.yml`（调度、权限、步骤、并发等）
- 修改 `tools/daily_update.sh` 或 `audio-pipeline/daily_update.sh`
- 修改 `tools/gen_audio.py` 或 `audio-pipeline/gen_audio.py`
- 修改 `tools/gen_feed.py` 或 `feed.xml` 的字段 / 期数 / 站点地址
- 修改 GitHub Actions / WorkBuddy 自动化的名称、ID、调度规则、提示词、状态或工作目录
- 修改 GitHub 仓库名、分支、Pages 地址、Workflow permissions 或 SSH 部署方式
- 修改音频保留天数、TTS 音色、API 域名或数据源
- 启用 / 禁用服务器备用方案
- 新增或取消跨机器锁机制

### 7.1 标准维护流程

```text
1. 修改本地脚本或自动化配置
2. 本地校验语法
3. 同步脚本到 GitHub 仓库 tools/
4. 更新 docs/AUTOMATION.md
5. 必要时更新 README.md 的链接或简述
6. commit + push 到 main
7. 核验 GitHub 远端文件与最新提交
8. 如自动化配置变化，重新核对 WorkBuddy 中的实际配置
```

### 7.2 校验命令

本地脚本：

```bash
bash -n "./audio-pipeline/daily_update.sh"
python -m py_compile "./audio-pipeline/gen_audio.py"
```

幂等补跑测试：

```bash
bash "./audio-pipeline/daily_update.sh"
```

若当天已完成，预期输出：

```text
ALREADY_DONE_REMOTE_RAW audio/YYYY-MM-DD/manifest.json
```

GitHub 端核验：

```text
https://github.com/Anywise666/ai-news-dashboard/commits/main
https://github.com/Anywise666/ai-news-dashboard/blob/main/docs/AUTOMATION.md
```

---

## 8. 已知限制

- GitHub Actions `schedule` 只认 UTC，且有数分钟延迟，高峰时段可能被直接丢弃（见 2.1 故障复盘）；已用多时点 + push 兜底缓解，但无法保证 100% 准点。
- 英文原题来自 `/api/v1/items`，仅覆盖近 7 天；历史日期音频会降级为中文。
- GitHub Pages CDN 更新通常约 20 秒生效。
- 公共仓库连续 60 天无提交会被自动暂停定时任务（本仓库日常推送不会触发）。
- 原多机器锁机制随 WorkBuddy 任务停用而不再参与主链路；`daily_update.sh` 保留备用时仍可用。
- 服务器 cron / systemd 方案与 WorkBuddy 本地任务均为历史备用，当前未启用。
