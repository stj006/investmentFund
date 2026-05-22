# 外部定时触发 GitHub Actions（cron-job.org）

GitHub 仓库自带的 `schedule` 在公共仓库上**经常延迟或漏跑**。改用 [cron-job.org](https://cron-job.org) 每天准时调用 GitHub API 触发 `workflow_dispatch`，更稳定。

---

## 一、创建 GitHub Personal Access Token（只做一次）

1. 打开：https://github.com/settings/tokens  
2. **Generate new token** → 选 **Fine-grained token**（推荐）或 Classic  
3. 权限：
   - **Repository access**：Only select → `stj8888/investmentFund`
   - **Permissions → Actions**：Read and write  
   - **Permissions → Contents**：Read（workflow 需要读代码）
4. 生成后**复制 Token**（只显示一次），保存到密码管理器  
5. **不要**把 Token 提交到 Git 或发给他人

本地测试时可写入 `.env`（勿提交）：

```env
GITHUB_PAT=github_pat_xxxxxxxx
```

---

## 二、在 cron-job.org 注册（免费）

1. 打开 https://cron-job.org 注册并登录  
2. 左侧 **Cronjobs** → **Create cronjob**

### 任务 1：每日持仓日报

| 字段 | 值 |
|------|-----|
| Title | investmentFund daily report |
| URL | `https://api.github.com/repos/stj8888/investmentFund/actions/workflows/daily_report.yml/dispatches` |
| Schedule | 每天 **20:35** |
| Timezone | **Asia/Shanghai** |

**Request settings**（展开 Advanced）：

| 项 | 值 |
|----|-----|
| Method | **POST** |
| Request body | `{"ref":"master"}` |
| Content-Type | `application/json` |

**Headers**（添加两行）：

```
Accept: application/vnd.github+json
Authorization: Bearer 你的GITHUB_PAT
```

可选第三行（推荐）：

```
X-GitHub-Api-Version: 2022-11-28
```

保存后点 **Test run**，应返回 **HTTP 204**（无内容即成功）。

### 任务 2：每周选基（可选）

再建一条 Cronjob：

| 字段 | 值 |
|------|-----|
| Title | investmentFund weekly recommend |
| URL | `https://api.github.com/repos/stj8888/investmentFund/actions/workflows/weekly_recommend.yml/dispatches` |
| Schedule | 每周日 **10:00** |
| Timezone | **Asia/Shanghai** |

Method / Body / Headers 与任务 1 相同。

---

## 三、验证是否成功

1. cron-job.org 点 **Test run** → History 里看到 **204**  
2. GitHub → [Actions](https://github.com/stj8888/investmentFund/actions) → 出现新的 **workflow_dispatch** 运行且绿色 ✓  
3. 邮箱收到 `【持仓】` 或 `【选基】` 邮件  

本地也可用脚本试触发（需 `.env` 里配 `GITHUB_PAT`）：

```powershell
cd d:\visual\makeMoney\investmentFund
powershell -ExecutionPolicy Bypass -File scripts/trigger_github_workflow.ps1 -Workflow daily
```

---

## 四、与本仓库 workflow 的关系

- 工作流已**关闭** GitHub 内置 `schedule`，只保留 `workflow_dispatch`  
- 定时完全由 cron-job.org 负责，避免双触发  
- GitHub Actions 里仍可手动 **Run workflow** 补跑  

---

## 五、常见问题

| 现象 | 处理 |
|------|------|
| HTTP 401 | PAT 错误或过期，重新生成 |
| HTTP 404 | URL 拼错，或 workflow 文件名不对 |
| HTTP 422 | body 里 `ref` 不是 `master` |
| 204 但无邮件 | 看 Actions 日志，多为净值/SMTP，与 cron 无关 |
| cron-job 显示失败 | 检查 Headers 是否含 `Bearer ` 前缀 |

---

*仓库：stj8888/investmentFund · 日报 20:35 · 选基 周日 10:00（北京时间）*
