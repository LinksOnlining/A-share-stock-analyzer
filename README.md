# 📊 A股智能股票分析工具

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![GitHub Release](https://img.shields.io/github/v/release/A-share-stock-analyzer/A-share-stock-analyzer)](https://github.com/A-share-stock-analyzer/A-share-stock-analyzer/releases)

基于 **DeepSeek 大模型 + 新浪财经实时行情** 的 A 股多维度智能分析系统。支持全市场搜索选股、六大维度深度分析、潜力股量化筛选。

> ⚠️ **风险警示**：本工具仅用于技术学习研究，AI 分析内容不构成任何投资建议，股市有风险，投资需谨慎。

---

## 📜 更新日志（Changelog）

### v5.0.0（2026-08-02）
- 🎯 **支持 PyInstaller 打包 exe**：单文件 exe + 控制台窗口 + 自动打开浏览器
- 📦 **新增 GitHub Actions 自动构建**：推送 git tag 即云端打包 exe 并发布到 Releases
- 🔧 打包兼容：缓存目录、`.env` 重定向到 exe 同级目录（单文件模式不丢数据）
- 🔧 打包后禁用 uvicorn reload（源码模式才需要）

### v4.0.0（2026-08-01）
- 🚀 **新增「潜力股筛选」功能**：量化初筛 + AI 深度分析双输出
  - 筛选条件：PE、总市值、换手率、涨跌幅、排除 ST、候选数量、排序方式
  - 综合得分模型：动量 30% + 流动性 20% + 低估值 30% + 市值适中 20%
  - 结果展示：量化候选表格 + AI《潜力候选分析报告》
- 数据源升级：全市场快照缓存 6 小时，筛选结果缓存 24 小时

### v3.0.0（2026-08-01）
- 🔄 **数据源切换为新浪财经**：解决东方财富接口被墙（502）问题
  - 并发 12 线程分页拉取，约 5 秒加载全市场 5533 只 A 股
  - 移除 akshare 依赖，改用 Python 标准库 urllib
- 🛡️ **三级降级兜底**：新浪 → 过期缓存 → 内置股票列表
- 🔎 搜索支持代码 / 名称 / 拼音首字母（如 `gzmt` → 贵州茅台）

### v2.0.0（2026-08-01）
- 🔎 **新增全市场股票搜索**：不再预置固定股票列表
  - 后端 `GET /api/stock/search` 接口，akshare 拉取沪深京全部 A 股
  - 前端实时防抖搜索 + 下拉建议 + 交易所徽章（SH/SZ/BJ）+ 键盘导航
  - 搜索不可用时自动降级为手动输入

### v1.1.0（2026-08-01）
- 📋 **新增快捷选股面板**：7 大行业 70+ 预置标的，点击即选
  - 单只模式：点击标签填入输入框
  - 批量模式：点击多选（再次点击取消），标签与 textarea 双向同步

### v1.0.0（2026-08-01）
- 🎉 **首个版本**：单只深度分析 + 批量横向对比
  - 后端 FastAPI + DeepSeek API，六大维度分析（基本面/估值/行业/资金/技术/风险）
  - 内置系统提示词，禁止前端篡改；内容过滤屏蔽买卖指令词汇
  - 前端原生 HTML + Tailwind CSS + marked.js，Markdown 渲染
  - 顶部固定红色风险警示横幅，本地 JSON 缓存 24 小时

---

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| 🔍 **单只深度分析** | 六大维度分析报告：基本面 / 估值 / 行业景气 / 资金面 / 技术面 / 风险排查 |
| 📋 **批量横向对比** | 最多 10 只股票横向对比 |
| 🚀 **潜力股筛选** | 量化初筛（动量+流动性+低估值+市值） + AI 深度分析 |
| 🔎 **全市场搜索** | 新浪财经实时数据，支持代码 / 名称 / 拼音首字母 |
| 🛡️ **内容安全过滤** | 自动屏蔽买卖指令词汇 |
| 💾 **本地缓存** | 分析结果缓存 24 小时，重复查询秒回 |

---

## 🔧 详细操作步骤

### 方式 A：GitHub Releases 直接下载 exe（推荐 · 普通用户）

1. 打开 Releases 页面：`https://github.com/A-share-stock-analyzer/A-share-stock-analyzer/releases`
2. 找到最新版本，下载 **`A-share-stock-analyzer.exe`**
3. 在 exe **同目录** 新建 `.env` 文件，填入你的 DeepSeek API Key：
   ```ini
   DEEPSEEK_API_KEY=sk-你的密钥
   ```
4. 双击 exe 启动：
   - 弹出黑色控制台窗口显示日志
   - 浏览器自动打开 `http://127.0.0.1:8000`
   - 关闭黑色窗口即停止服务

> **获取 DeepSeek API Key**：访问 [platform.deepseek.com](https://platform.deepseek.com) 注册 → 创建 API Key → 复制 `sk-` 开头的密钥

### 方式 B：源码本地运行（开发者）

```bash
# 1. 克隆仓库
git clone https://github.com/A-share-stock-analyzer/A-share-stock-analyzer.git
cd A-share-stock-analyzer

# 2. 安装依赖
pip install -r requirements.txt --break-system-packages

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY=sk-你的密钥

# 4. 启动服务
python main.py
# 浏览器自动打开 http://127.0.0.1:8000
```

### 配置说明（.env）

```ini
DEEPSEEK_API_KEY=your-deepseek-api-key-here   # 必填
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1/chat/completions  # 默认
DEEPSEEK_MODEL=deepseek-chat                  # 模型选择
REQUEST_TIMEOUT=120                            # 请求超时（秒）
CACHE_ENABLED=true                             # 是否启用缓存
HOST=127.0.0.1                                 # 监听地址
PORT=8000                                      # 监听端口
```

---

## 📦 打包方法

### 方法一：GitHub Actions 云端自动打包（推荐）

无需本机 Windows 环境，GitHub 云端 Windows 服务器自动构建 exe 并发布到 Releases。

**工作原理**：`.github/workflows/build-release.yml` 工作流在推送 git tag 时自动执行：
检出代码 → 安装 Python → 安装依赖 → PyInstaller 打包 → 上传 exe 到 Release。

**操作步骤**：

```bash
# 1. 推送到 GitHub
git add .
git commit -m "v5.0.0 release"
git push origin main

# 2. 打版本标签（触发自动构建）
git tag v5.0.0
git push origin v5.0.0

# 3. 等待 3-5 分钟，打开 Actions 页查看进度
# 4. 完成后 Releases 页出现可下载的 exe
```

**手动触发**（不想打 tag 时）：GitHub 仓库 → Actions → `Build Windows exe` → 右上角 **Run workflow** → 绿色按钮。

### 方法二：本地 Windows 手动打包

在 Windows 电脑上（需 Python 3.9+）：

```bash
# 方式 1：双击一键脚本
build_exe.bat

# 方式 2：手动命令
pip install -r requirements.txt --break-system-packages
pip install -r build_requirements.txt --break-system-packages
pyinstaller --clean --noconfirm stock_analyzer.spec
```

产物在 `dist\A股智能股票分析工具.exe`。

### 打包特性

| 特性 | 实现 |
|------|------|
| 单文件 exe | PyInstaller onefile 模式，static 资源打进 exe |
| 控制台窗口 | `console=True`，显示启动日志 |
| 自动开浏览器 | 启动后延迟 2 秒 `webbrowser.open` |
| 缓存目录 | 放 exe 同目录 `cache/`，不丢失 |
| .env 读取 | 读 exe 同目录 `.env`，便于改 Key |

---

## 🌐 API 接口文档

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/stock/search?q=关键词` | GET | 全市场股票搜索 |
| `/api/stock/analyze` | POST | 单只深度分析 |
| `/api/stock/batch` | POST | 批量横向对比 |
| `/api/stock/screen` | POST | 潜力股筛选 |
| `/api/health` | GET | 健康检查 |

**请求示例**：
```bash
# 单只分析
curl -X POST http://127.0.0.1:8000/api/stock/analyze \
  -H "Content-Type: application/json" \
  -d '{"stock_code":"600519.SH 贵州茅台"}'

# 批量对比
curl -X POST http://127.0.0.1:8000/api/stock/batch \
  -H "Content-Type: application/json" \
  -d '{"stock_list":["600519.SH 贵州茅台","000858.SZ 五粮液"]}'
```

---

## ⚠️ 免责声明

1. 本工具仅供**技术学习研究**，所有 AI 生成内容**不构成任何投资建议**
2. 分析基于公开信息推理，可能存在偏差，请以官方公告为准
3. 量化筛选结果仅代表技术/估值特征，**不代表基本面确认**
4. 股市有风险，投资需谨慎。使用者应自行承担决策责任

---

## 🛠 常见问题（FAQ）

**Q1：exe 被杀毒软件误报？**
单文件 exe 偶发误报，可添加信任，或改用 GitHub Actions 打包后下载（云端构建更接近正常编译）。

**Q2：启动后浏览器没自动打开？**
手动访问 `http://127.0.0.1:8000` 即可。若端口被占用，在 `.env` 修改 `PORT=8001`。

**Q3：改了 .env 不生效？**
确认 `.env` 在 exe 同目录（不是源码目录），修改后需重启 exe。

**Q4：搜索不到股票？**
新浪财经接口偶发限流，等待几秒重试。若持续失败，程序自动降级为手动输入模式。

**Q5：如何更新到新版本？**
GitHub Releases 下载最新 exe，覆盖旧的即可（`.env` 和 `cache/` 目录保留）。

---

## 📄 License

本项目采用 [MIT License](LICENSE)，可自由使用、修改、分发。

---

## 📁 项目结构

```
A-share-stock-analyzer/
├── .github/
│   └── workflows/
│       └── build-release.yml      # GitHub Actions 自动打包 exe 并发布 Release
├── main.py                         # 后端主程序（v5.0，支持打包）
├── static/
│   └── index.html                  # 前端网页
├── requirements.txt                # 运行依赖
├── build_requirements.txt          # 打包依赖
├── stock_analyzer.spec             # PyInstaller 配置
├── build_exe.bat                   # 本地手动打包脚本
├── .env.example                    # 环境变量模板
├── .gitignore                      # 忽略敏感/临时文件
├── LICENSE                         # MIT 许可证
└── README.md                       # 本文件
```
