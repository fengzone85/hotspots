# 🌐 三站热点日报（Hotspots Daily）

自动抓取 [V2EX](https://v2ex.com)、[NodeSeek](https://nodeseek.com)、[Linux.do](https://linux.do) 三个社区的热门话题，生成结构化 Markdown 报告。

## 📁 项目结构

```
hotspots/
├── fetch_hotspots.py              # 主脚本：抓取 + 生成报告
├── requirements.txt               # Python 依赖
├── deploy_cron.sh                 # VPS cron 部署脚本
├── reports/                       # 报告输出目录
│   └── 2025-05-24.md             # 按日期命名的报告
├── .github/
│   └── workflows/
│       └── daily-hotspots.yml     # GitHub Actions 定时工作流
└── README.md                      # 本文件
```

## 🚀 快速开始

### 方式一：GitHub Actions（推荐，免费免服务器）

1. **Fork 或创建仓库**
   ```bash
   # 将本项目推送到你的 GitHub 仓库
   git init
   git add .
   git commit -m "feat: 三站热点日报"
   git remote add origin https://github.com/<你的用户名>/hotspots.git
   git push -u origin main
   ```

2. **启用 GitHub Actions**
   - 进入仓库 → Settings → Actions → General
   - 确保 "Allow all actions" 被选中
   - 工作流会自动在每天 **北京时间 09:00** 执行

3. **手动触发**
   - 进入仓库 → Actions → 三站热点日报 → Run workflow

4. **查看报告**
   - 每日报告自动提交到 `reports/` 目录
   - 也可在 Actions → 对应运行记录 → Summary 中查看

### 方式二：VPS / 服务器部署

1. **上传项目到服务器**
   ```bash
   scp -r hotspots/ user@your-server:/opt/hotspots/
   ```

2. **一键安装定时任务**
   ```bash
   cd /opt/hotspots
   chmod +x deploy_cron.sh
   ./deploy_cron.sh install
   ```

3. **常用命令**
   ```bash
   ./deploy_cron.sh status    # 查看任务状态
   ./deploy_cron.sh run       # 手动执行一次
   ./deploy_cron.sh remove    # 移除定时任务
   ```

4. **修改执行时间**
   编辑 `deploy_cron.sh` 中的 `CRON_SCHEDULE` 变量：
   ```bash
   # 默认每天9点
   CRON_SCHEDULE="0 9 * * *"
   # 改为每天8点30分
   CRON_SCHEDULE="30 8 * * *"
   ```

### 方式三：本地手动运行

```bash
cd hotspots
pip install -r requirements.txt
python fetch_hotspots.py
# 报告保存在 reports/ 目录下
```

## 📊 报告格式

每日报告为 Markdown 格式，包含：

- 🟢 **V2EX 热门话题** - 标题、节点、回复数、链接
- 🟡 **NodeSeek 热门帖子** - 标题、分类、回复数、链接
- 🔵 **Linux.do 热门话题** - 标题、回复数、浏览数、点赞数、链接
- 🎯 **趋势速览** - 高频关键词、跨站话题交叉分析

## ⚙️ 数据源说明

| 站点 | 数据获取方式 | 备注 |
|------|-------------|------|
| V2EX | 官方 API (`/api/topics/hot.json`) | 稳定可靠，含备用页面抓取 |
| Linux.do | Discourse API (`/top.json`) | 稳定可靠，含备用方案 |
| NodeSeek | 页面抓取 | 该站无公开API，可能因反爬导致获取失败 |

## ⚠️ 注意事项

1. **NodeSeek** 无公开 API，依赖页面抓取，成功率可能不稳定
2. 如遇频率限制，可在脚本中调整请求间隔（`fetch_with_retry` 中的 `time.sleep`）
3. GitHub Actions 的 cron 调度可能有几分钟延迟，属正常现象
4. 如需推送到微信/钉钉等，可自行在脚本末尾添加 webhook 通知

## 📝 License

MIT
