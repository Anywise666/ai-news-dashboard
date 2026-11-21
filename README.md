# AI 晨报仪表盘 (ai-news-dashboard)

每日 AI 新闻的静态 HTML 仪表盘。单文件自包含(内联 CSS/JS),无需构建。**页面在浏览器端实时拉取 aihot 当天日报**,链接固定不变、内容每天自动更新。

## 在线访问链接

| 平台 | 链接 | 说明 |
|------|------|------|
| **GitHub Pages(固定地址,推荐)** | https://anywise666.github.io/ai-news-dashboard/ | 地址永久不变,源 main/root |
| 内置发布(会变) | 见聊天记录最新分享链接 | 每次重新发布会换新 sandboxId,管理入口:设置—数据管理—应用 |

> 内置发布链接每次重新发布都会变化,长期分享请优先用 GitHub Pages 固定地址。

## 更新原理

托管方只提供静态 HTML,不跑任何定时任务。访客每次打开页面,浏览器实时请求 `https://aihot.news/api/v1/dailies/{今天}` 渲染当天数据;当天未生成时自动回退最近一期。数据源 CORS 为 `*`,因此任意托管域名均可跨域拉取。

## 文件说明

| 文件 | 说明 |
|------|------|
| `index.html` | 日历档案 + 双语播客版(默认首页) |
| `audio/YYYY-MM-DD/` | 每日预生成的双语 mp3 + manifest.json(最近30天) |
| `.github/workflows/daily-podcast.yml` | **当前主方案**：GitHub Actions 每日定时生成并推送音频(北京时间 8:30) |
| `tools/gen_audio.py` | 音频生成脚本(edge-tts)，由 Actions 直接复用 |
| `tools/daily_update.sh` | 跨机器幂等补跑脚本(原 WorkBuddy 任务使用，现备用) |
| `docs/AUTOMATION.md` | 自动化配置与维护基线(含 GitHub Actions 配置与备用服务器方案) |
| `ai-daily-2026-08-01.html` | 2026-08-01 单文件日报归档快照 |

## 功能

### 日历档案
- 默认展示今日日报;顶部日历可切换月份、点击任意有数据的日期回看当天日报。
- **重大事件高亮**:基于当天头条标题+摘要的重大关键词评分(IPO/发布/突破/融资/GPT/Gemini 等),得分 ≥5 的日期标金色,约占近半年 21% 的天数。
- 日历数据来自 `/dailies?limit=180` 索引(约 180 天历史),每日报告在点击时按需加载。

### 双语播客(听播客按钮)
- 每张新闻卡片与今日头条都有「▶ 听播客」按钮,点击用浏览器语音合成(Web Speech API)朗读。
- **中英双语串读**:先读中文(标题+摘要),再读英文原题(originalTitle);底部有播放控制条可停止。
- 英文原题来自 `/api/v1/items`(仅覆盖近 7 天,约 77% 条目有英文原题),历史日期无英文原题时自动降级为纯中文朗读。
- **预生成音频(微信可用)**:每天自动生成并托管在仓库 `audio/` 目录,页面优先播放 mp3,微信内可直接听;微软神经音色,音质优于浏览器 TTS。仅保留最近 30 天。
- 无预生成音频时(如历史日期)回退浏览器 TTS;微信内不支持则提示在浏览器中打开。
- 生成由 `tools/gen_audio.py` 完成(edge-tts 免费)；由 **GitHub Actions** 每天北京时间 8:30 自动运行并推送 main，当天已完成会自动跳过。整条链路在 GitHub 云端完成，不依赖任何机器在线（原 WorkBuddy 本地任务与每小时补跑已停用，改为备用）。

### 阅读工具(顶部工具栏)
- **全局搜索**:跨全部档案的头条/摘要/关键词即时检索，命中高亮，点击跳到对应日期。
- **收藏 / 稍后读**:卡片点 ☆ 收藏，顶部「收藏」进入集中列表，可跳转/分享/移除/清空。
- **已读标记**:点击标题或「阅读全文」自动标记已读，卡片淡化并显示「✓ 已读」。
- **分享**:每条支持复制文案 + Canvas 生成日报卡片图下载；「分享本日」汇总当天头条与各板块。
- **深色/浅色 + 字号**:主题切换与三档字号(小/中/大)。
- 以上偏好(收藏、已读、主题、字号)均存浏览器 `localStorage`，无后端、刷新不丢。

## 技术说明

- 纯静态单文件,深色主题,响应式布局,无外部依赖、无后端。
- API 直连最终域名 `aihot.news`,规避旧域名跨域 301;CORS 全开。
- 日期以接口 `report.date` 为准;逐日尝试最近 5 天,再兜底索引最近一期。
- 徽章说明:「今日实时」=当天数据;「历史回看」=正在查看历史日报。

## 维护

更新 `index.html` 后:
- GitHub Pages:push 到 main 自动部署(约 20 秒生效)。
- 内置发布:在「设置—数据管理—应用」中重新发布目录(链接会变)。

### 自动化（GitHub Actions）
完整配置与维护基线见 [`docs/AUTOMATION.md`](docs/AUTOMATION.md)。

- **主方案**：`.github/workflows/daily-podcast.yml`，`schedule` 每天北京时间 08:30（cron `30 0 * * *`）在 `ubuntu-latest` 运行，用 `GITHUB_TOKEN` 推送；仓库需开启 Workflow permissions 的 Read and write。
- 幂等：以 `audio/YYYY-MM-DD/manifest.json` 是否有效作为当天已完成标记，已完成跳过生成与推送。
- 手动验证/补跑：Actions 页面 → `AI晨报双语播客每日更新` → Run workflow，可填 `target_date`(YYYY-MM-DD) 指定日期。
- `tools/daily_update.sh` 与跨机器锁 `automation-lock/YYYY-MM-DD` 为原 WorkBuddy 方案的备用实现，当前主链路不再使用，但脚本保留可用。
- 脚本从自身位置推导工作目录，不依赖固定 Windows 路径。
- 以后自动化配置发生任何变更，必须同步更新 `docs/AUTOMATION.md` 并推送。
