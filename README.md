# 币安合约仓位监控 - GitHub Actions 部署指南

把这个监控部署到 GitHub Actions 上，电脑关机也照样 24 小时运行，仓位平仓自动微信通知。

## 原理

- GitHub 每 5 分钟自动运行一次检查脚本（免费、无需电脑开机）
- GitHub 服务器在海外，直连币安 API，**不需要代理**
- 用 `state.json` 记录持仓快照，每次运行对比快照检测平仓
- API 密钥存在 GitHub Secrets 里，代码仓库中不含任何敏感信息

## 部署步骤（约 10 分钟）

### 第 1 步：创建 GitHub 账号 / 登录

打开 https://github.com ，没有账号就注册一个（免费）。

### 第 2 步：创建仓库

1. 点右上角 **+** → **New repository**
2. Repository name 填：`crypto-monitor`
3. 可见性选 **Public**（重要！Public 仓库 Actions 完全免费不限时长；Private 仓库每月只有 2000 分钟免费额度，每 5 分钟跑一次会超）
   - 代码里没有密钥，公开是安全的
4. 勾选 **Add a README file**
5. 点 **Create repository**

### 第 3 步：添加密钥（Secrets）

进入仓库页面 → **Settings** → 左侧 **Secrets and variables** → **Actions** → 点 **New repository secret**，添加 3 个：

| Name（必须完全一致） | Secret 值从哪来 |
|---|---|
| `BINANCE_API_KEY` | 本地 config.json 里 `binance_futures.api_key` 的值 |
| `BINANCE_API_SECRET` | 本地 config.json 里 `binance_futures.api_secret` 的值 |
| `PUSHPLUS_TOKEN` | 本地 config.json 里 `notification.pushplus.token` 的值 |

### 第 4 步：上传代码文件

在仓库页面点 **Add file** → **Create new file**，逐个创建：

**文件 1**：文件名框输入 `action_monitor.py`，把本地 `action_monitor.py` 的全部内容粘贴进去 → 点 **Commit changes**

**文件 2**：文件名框输入 `requirements.txt`，内容一行：`requests` → **Commit changes**

**文件 3**（workflow，路径必须一字不差）：
文件名框输入 `.github/workflows/monitor.yml`（输入 `/` 会自动变成文件夹层级），
把本地 `.github/workflows/monitor.yml` 的全部内容粘贴进去 → **Commit changes**

### 第 5 步：手动触发测试

1. 仓库顶部点 **Actions** 标签
2. 左侧选 **Crypto Monitor**
3. 右侧点 **Run workflow** → **Run workflow**
4. 等约 1 分钟，出现绿色 ✓ 表示运行成功
5. 点进这次运行可以看详细日志（当前持仓、检查结果）

### 第 6 步：验证

- 运行成功后仓库里会多出 `state.json`（记录了当前持仓快照）
- 平仓后 5~10 分钟内微信会收到通知

## 注意事项

- GitHub 定时任务有 1~5 分钟延迟，实际检查间隔约 5~10 分钟
- 通知延迟换来的是：电脑关机、不开代理也照常监控
- 想改检查频率：编辑 `.github/workflows/monitor.yml` 里的 cron：
  - `*/5 * * * *` = 每 5 分钟（默认）
  - `*/15 * * * *` = 每 15 分钟
- 想停止监控：Actions 页面左侧选 Crypto Monitor → 点 `...` → **Disable workflow**

## 本地文件对照

| 要上传的文件 | 本地位置 |
|---|---|
| `action_monitor.py` | `crypto-monitor/github-deploy/action_monitor.py` |
| `requirements.txt` | `crypto-monitor/github-deploy/requirements.txt` |
| `.github/workflows/monitor.yml` | `crypto-monitor/github-deploy/.github/workflows/monitor.yml` |
