# Omics-GEM Studio 前端预览包使用指南

这个压缩包只包含前端，用来让别人试用页面结构、导航和操作逻辑。它不包含后端、数据库、case studies、user_runs 或资源缓存。

## 包内内容

- `dist/`：已经构建好的静态前端文件。
- `source/`：轻量前端源码，不含 `node_modules`。
- `FRONTEND_PREVIEW_GUIDE.md`：本说明。

## 最简单预览

如果只想看页面壳、路由和交互布局：

```powershell
cd dist
python -m http.server 4173
```

然后打开：

```text
http://127.0.0.1:4173
```

注意：这个模式没有后端数据。涉及资源搜索、case study、上传、Model Compare、Summary 等 API 的功能会提示后端不可达或加载失败。

## 连接真实后端预览

如果你提供了一个可访问的后端或反代地址，例如：

```text
https://your-demo.trycloudflare.com
```

对方可以用源码模式运行前端：

```powershell
cd source
npm install
$env:VITE_API_BASE_URL="https://your-demo.trycloudflare.com"
npm run dev
```

然后打开 Vite 提示的本地地址，一般是：

```text
http://127.0.0.1:5173
```

如果你的公网演示是“前端和 API 同一个域名”的反代模式，可以改用：

```powershell
$env:VITE_API_BASE_URL="same-origin"
```

## 重新构建静态版

如果需要把 API 地址写进静态构建：

```powershell
cd source
npm install
$env:VITE_API_BASE_URL="https://your-demo.trycloudflare.com"
npm run build
```

构建结果会出现在 `source/dist/`。

## 建议让同学重点试的页面

- `#/module-input`：Resource Atlas、树谱系、资源详情抽屉、上传数据入口。
- `#/module-generate`：Model Generator、Dossier、Method Workbench。
- `#/module-model-comparison`：左右模型网络对比。
- `#/module-analysis`：Analysis 方法工作台。
- `#/module-summary`：Summary、case story、QA matrix。

## 限制说明

- 这个包不能单独跑完整 workflow。
- 不包含任何后端 Python 代码或本地数据。
- 不包含登录密码配置；如果连接到你部署的后端，登录规则以后端为准。
- 如果对方只打开 `dist/`，适合评估 UI 和操作逻辑，不适合验证真实计算结果。
