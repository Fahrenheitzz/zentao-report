# 禅道迭代执行进展报告生成器

自动从禅道（Zentao）PM 系统拉取迭代数据，生成美观的静态 HTML 报告页面，无需服务器，直接浏览器打开即可查看。

## 功能特性

- 📊 **5 大统计卡片**：时间进度、系统进度、需求数、任务数、Bug 数
- 📈 **3 张可视化图表**：需求阶段分布、任务状态分布、任务类型分布（Chart.js）
- ⚠️ **风险预警 & 进展亮点**：自动识别延期任务、即将到期任务
- 👥 **任务按人分析**：按 5 大分类（产品/后端/前端/移动端/测试）Tab 切换，每人折叠面板，显示延期数量（红色高亮）
- 📋 **需求分析**：需求状态统计 + 可折叠的需求明细表（阶段显示中文）
- 🐛 **Bug 分析**：未关闭 / 全部 Bug 双 Tab 查看
- 🏠 **返回首页**：报告头部左上角"返回首页"按钮，跳转到迭代总览页

## 快速开始

### 1. 安装依赖

```bash
# 无需额外依赖，仅使用 Python 标准库
# Python 3.8+ 自带 ssl、json、urllib 等
```

### 2. 配置禅道账号

```bash
# 复制配置模板
cp zentao_config.example.json zentao_config.json

# 编辑 zentao_config.json，填入你的禅道账号信息
```

`zentao_config.json` 格式：

```json
{
  "url": "https://your-zentao-url.com",
  "username": "your_username",
  "password": "your_password"
}
```

### 3. 生成报告

```bash
# 生成所有迭代的执行进展报告
python generate_iteration_reports.py

# 生成首页 index.html（迭代总览）
python generate_index.py

# 一键运行以上两个脚本
python generate_all.py
```

### 4. 查看报告

直接用浏览器打开 `index.html`，或打开 `YYYY-MM-DD/迭代XXXX_执行进展报告.html`。

## 项目结构

```
zentao-report/
├── generate_iteration_reports.py   # 生成每个迭代的详细报告
├── generate_index.py               # 生成首页（迭代总览）
├── update_index.py                 # 更新首页数据
├── generate_all.py                 # 一键运行以上所有脚本
├── zentao_config.example.json     # 配置模板（不含真实账号）
├── .gitignore                    # Git 排除规则
├── index.html                     # 生成的首页（可提交到 Git）
└── 2026-06-18/                  # 生成的报告（可按日期归档）
    ├── 迭代4608_执行进展报告.html
    ├── 迭代4598_执行进展报告.html
    └── ...
```

## 配置说明

在脚本顶部可修改以下配置：

```python
PROJECT_IDS   = [1013, 4047]       # 禅道项目 ID 列表
PROJECT_NAMES  = {1013: '商城3.0', 4047: '格力官网'}  # 项目 ID → 名称映射
CATEGORIES    = ['产品', '后端开发', '前端开发', '移动端开发', '测试']  # 任务分类
```

## 自定义样式

报告使用纯 HTML + CSS + JS，无框架依赖。修改 `CSS_TEMPLATE` 和 `JS_TEMPLATE` 常量即可自定义样式。

## 部署到 GitHub Pages

1. 将项目推送到 GitHub 仓库
2. 在仓库设置中开启 GitHub Pages
3. 访问 `https://your-username.github.io/zentao-report/`

注意：`.gitignore` 已排除 `zentao_config.json`，请确保不要提交真实账号信息。

## 常见问题

**Q: 报告打不开 / 空白？**
A: 检查 `zentao_config.json` 中的 API 地址是否正确，禅道 REST API 需要开启。

**Q: 阶段显示英文？**
A: 脚本中已内置 `STAGE_LABEL_ZH` 映射，将 `wait` → `未开始`、`developing` → `开发中` 等。

**Q: 如何定时自动生成？**
A: 使用 crontab（Linux/macOS）或任务计划程序（Windows）定时运行 `generate_all.py`。

## 许可

MIT License
