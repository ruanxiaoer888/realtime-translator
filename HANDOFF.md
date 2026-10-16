# HANDOFF —— 实时翻译助手 · 双机协作交接

> 两台电脑（公司 / 家里）都用 DeepSeek Harness、都在本地跑、互相看不见，
> 靠这个公开仓库 + GitHub API 交换进度。
> 最后更新：2026-10-16（公司电脑）

---

# 👤 给人看的一页（回家照这个做，30 秒读完）

> 下面从「🤖 给家里的 AI 助手」开始，是给**家里的 DSH 助手**看的。你只需要读这一页。

## 第 1 步：拉到最新代码

**如果家里项目目录已经是 git 仓库**（做过下面那次设置），只要一条：

```powershell
cd <家里项目目录>
git pull
```

**如果从没设置过**，在这个目录里整段粘贴（一次性，约 1 分钟）：

```powershell
cd <家里项目目录>
git init
git remote add origin https://github.com/ruanxiaoer888/realtime-translator.git
git fetch origin main
git reset --hard origin/main
git branch -M main
git branch --set-upstream-to=origin/main main
git config user.name  "xiaoer"
git config user.email "203290839+ruanxiaoer888@users.noreply.github.com"
git status
```

- 这会把**全部代码更新 + 本文件 + `tools/dsh_pull.py`** 一次性拉下来
- **`libs\`、`tmp\models\`、`记录\`、`settings.json` 不会被碰**（已实测：它们不在仓库里）
- 最后 `git status` 应该是干净的（有报错就先记下来）

## 第 2 步：把这句话发给家里的 AI（复制即可）

> 项目在 `<家里项目目录>`。请先读仓库根目录的 `HANDOFF.md`
> （https://raw.githubusercontent.com/ruanxiaoer888/realtime-translator/main/HANDOFF.md ），
> 然后按里面的指示继续。你在沙箱里跑不了 git，拉取用 `py -3.12 tools/dsh_pull.py --apply`。

（就算第 1 步没做成功、项目里还没有 `HANDOFF.md`，上面那个网址也能直接看到全文 ——
把网址和这句话一起发给它就行。）

## 第 3 步：收工，让 AI 提交、你只跑一条 push

对 AI 说「把改动提交好并写好进度记录」。它会复制文件、`git add`、`git commit`
（**本地 git 它能用，只有联网的 fetch/push 不行**），然后给你一条命令，
你在**你自己的** PowerShell 里执行：

```powershell
git -C <家里项目目录> push
```

> 为什么这条必须你做：推送需要你的 GitHub 身份，AI 不应该去读你的凭据。

## 你回家总共只有三个动作

| 时机 | 你要做什么 | 耗时 |
|---|---|---|
| 到家 | `git pull`（或上面的 8 条初始化） | 5 秒 |
| 开工 | 把第 2 步那句话发给 AI | 10 秒 |
| 收工 | `git push` | 5 秒 |

**其余全部（读文档、拉代码、比对、改代码、跑测试、写进度记录）都是 AI 的活。**

---

# 🤖 给家里的 AI 助手（DSH）

> **接手顺序**：读完本文件 → `py -3.12 tools/dsh_pull.py --apply` 对齐代码
> → 按第 5 节挑任务开工 → 收工在最后一节「进度记录」最上面加一条。
>
> **首次引导**：如果 `tools/dsh_pull.py` 还不存在，用 web_fetch 读
> `https://raw.githubusercontent.com/ruanxiaoer888/realtime-translator/main/tools/dsh_pull.py`
> 再用 write 写到本地即可（Python 访问 GitHub 是通的，见第 6 节）。

## 0. 先知道这 5 件事，能省你半小时

1. **沙箱里的 git 用不了，但 Python 的网络完全正常。**
   `git clone/fetch/pull/push` 全都会失败（详见第 6 节），
   而 `urllib` 访问 `api.github.com` / `raw.githubusercontent.com` / `codeload.github.com`
   实测都是 200。**所以"拉取"这件事你自己就能做**，用 `tools/dsh_pull.py`，不要麻烦人。
2. **"推送"必须请人执行** —— 那不是能力问题，是凭据边界：推送需要用户的 GitHub 身份，
   你不应该去读他的凭据。你自己能做到的是：**把本地文件对齐、把 commit 做好**，
   然后请人跑一条 `git push`（命令见第 9 节）。
3. **项目目录可能在 DSH 工作区之外**（例如 `D:\Michael\DSHProjects\TikTokBR-Translator`
   而工作区是 `D:\Michael\DSHProjects\Tiktok`）→ 写文件需要
   `sandbox_permissions: danger-full-access`。
4. **永远用 `py -3.12`**。`libs\` 是 cp312 编译的，3.13/3.14 加载会报
   `Error importing numpy ... source directory` 这种极具误导性的错。
5. **验收标准是现成的**，别自己发明：第 8 节列了作者自带的测试套件和期望值。

---

## 1. 这个项目是什么

TikTok Shop 巴西/墨西哥直播用的**实时翻译助手**（Windows 桌面程序，Tkinter）：
抓系统声音 → faster-whisper 识别葡语/西语 → 在线接口翻中文 → 悬浮窗 + 自动写 srt。
完全离线可跑（除翻译接口），不需要 API Key。

**用户是跨境电商运营**，用途是看巴西直播时同步看中文字幕。

---

## 2. 两台机器的差异（你接手时先确认自己在哪台）

| | 公司电脑 | 家里电脑 |
|---|---|---|
| 项目路径 | `D:\Michael\DSHProjects\TikTokBR-Translator` | 待确认（找含 `启动翻译助手.bat` 的目录） |
| GPU | **GTX 1650 4GB**（TU117，**无张量核心**） | **RTX 3060 Ti 8GB**（**有张量核心**） |
| CUDA 运行库 | 在 `libs\nvidia\`（1.5 GB，12 个 DLL，随文件夹走） | 系统级（本来就有），**不要拷公司的过去** |
| 项目体积 | 4.47 GB（含 CUDA 库 1.5 GB） | 约 3 GB |

**为什么家里不要拷 `libs\nvidia\`**：家里 GPU 本来就能跑（README 的 GPU 实测就是在那里测的），
拷过去会把 `libs\nvidia\*\bin` 插到 `PATH` 最前面，等于用 9.1.0.70 盖住家里原来的 cuDNN。

---

## 3. 当前状态：主要问题已解决并验证

一句话：公司电脑从「识别跟不上、一场丢 27 句」变成「识别 2.11 秒、0 丢句、实时率 0.41x」，
模型同时从 small 升到 medium（更准）。**家里（3060 Ti）还没验证。**

### 3.1 两场真实直播对比（来源 `记录\运行日志.txt`）

| 指标 | 第 2 场（CPU small） | 第 3 场（GPU medium） | 结论 |
|---|---|---|---|
| 算力 | `cpu/int8` | `cuda/int8_float16` | GPU 生效 |
| 丢弃句数 | **27 次** | **0 次** | ✅ |
| 识别 中位 / 最大 | 4.61 s / **47.82 s** | **2.11 s / 2.44 s** | ✅ 尖峰消失 |
| 队列等待 中位 / 最大 | 6.10 s / 11.20 s | **0.00 s / 1.50 s** | ✅ 不积压 |
| 翻译 中位 | 0.17 s | 0.15 s | 翻译从来不是瓶颈 |
| **实时率** | **1.28×（过载）** | **0.41×（余量 2.4 倍）** | ✅ |

### 3.2 GPU 速度实测（GTX 1650，**关掉 VAD** 的真实编码）

| 配置 | 6 秒音频 | 显存 |
|---|---|---|
| cpu int8 small | 3.109 s | — |
| cuda float16 small | 1.321 s | 1.7 GB |
| **cuda int8_float16 small** | **0.433 s** | 1.4 GB |
| cuda float16 medium | 4.327 s | 3.1 GB |
| **cuda int8_float16 medium** | **1.154 s** | 2.1 GB |

### 3.3 准确度（真实字幕回放）

有明显错译的句子：**修复前 18/18 → 修复后 1/18**。
术语资产：五金工具/pt 术语 **61 条**、`TERM_FIXES` **58 个词**、`PT_ASR_FIXES` **11 条**。

### 3.4 测试套件现状（作者自带）

| 测试 | 结果 |
|---|---|
| `tools/check_termfixes.py` | OK |
| `tools/verify_p0.py` | **22 通过 / 0 失败** |
| `tools/verify_e2e.py` | 5/5 无污染 |
| `check_deploy.py` | 11 项 OK |

---

## 4. 未决问题

| # | 问题 | 怎么推进 |
|---|---|---|
| 1 | **分句上限刚从 6 s 收到 4.5 s，还没有真实数据** | 跑一场直播看日志 |
| 2 | **家里 3060 Ti 未验证**（CUDA 环境、精度选择） | 第 5 节 P0 |
| 3 | `libs\nvidia\` 不入库，换机不带 | 靠文件夹整体拷贝 |
| 4 | `verify_p0` 的「单帧 OCR < 2 s」偶发失败 | 环境相关（没装葡语语言包），不用管 |
| 5 | 同类错译会反复出现（真实直播里总有新口语） | 每次直播后把新错译补进 `TERM_FIXES`/术语表 |

---

## 5. 你的任务清单

### P0 —— 家里电脑验证（如果你在家里）

1. **先确认 GPU 被认到**：
   ```
   py -3.12 check_deploy.py
   ```
   看「算力」行，应为 `cuda/int8_float16（CUDA可用=True）`。
   **如果是 `cpu/int8`**：家里的 CUDA 库没被找到 —— 先别改代码，
   把这一行和 `libs\nvidia` 是否存在记进「进度记录」，回公司一起看。
2. **确认两项设置**（`settings.json` 被 gitignore，`git reset` 不会覆盖它）：
   识别模型 = **medium**、翻译引擎 = **仅在线接口**（NLLB 是 CC-BY-NC-4.0 禁止商用）。
3. **测这台机器的精度选择**（3060 Ti 有张量核心，结论可能和 GTX 1650 相反）：
   ```
   py -3.12 tools/dsh_bench.py
   ```
   看输出里的实时率排序。**如果 `float16` 明显好于 `int8_float16`**，
   就把 `asr_engine.py` 里 `get_model()` 的 `order` 改成 `("cuda","float16")` 优先
   （改完要跑第 8 节的测试套件）。**更彻底的做法**：做成界面可选项，
   两台机器各用各的最优值 —— 这是 P1。
4. **跑一场 5~10 分钟真实直播**，看 `记录\运行日志.txt`：
   识别 1.5~2.5 s、队列等待 ≈0、没有「丢弃最旧的一句」。
5. 把结果写进第 10 节，然后按第 9 节请用户推送。

### P1 —— 让两台机器各用各自最优的精度
把计算精度做成可配置（界面下拉或按 GPU 名自动判断），避免"为一台机器写死的参数拖累另一台"。

### P2 —— 继续榨性能（公司那台实时率只有 0.41x，余量 2.4 倍）
- 分句上限再收到 3.5~4 s（字幕更跟手）
- medium + 更大 `beam_size`（质量换一点速度）
- 屏幕 OCR 装葡语语言包：1300 ms/帧 → 约 14 ms/帧（要 `DISM /RestoreHealth` + 重启）

### P3 —— 工程化
- 把公司 DSH 工作区的辅助脚本（`compare.py`、`replay_e2e.py`、`verify_protect.py`、
  `download_cuda.py`、`extract_cuda.py`）也搬进 `tools/`，这样两台机器都有
- 写一个用 GitHub API **更新本地 clone** 的脚本（现在 `git fetch` 只能请人跑）

---

## 6. 沙箱能力清单（实测，别浪费时间去试）

| 能力 | 可用? | 现象 / 替代方案 |
|---|---|---|
| Python urllib → api / raw / codeload | ✅ | 200，0.4~0.6 s |
| `git clone/fetch/pull/push`（HTTPS） | ❌ | `schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS` |
| `git -c http.sslBackend=openssl` | ❌ | `Unsupported SSL backend 'openssl'. Supported: schannel` |
| git 本地操作（init/add/commit/reset/log/status/diff） | ✅ | 本地提交可以，**fetch 不行** |
| `git fetch <本地路径>`（当远端用） | ❌ | 沙箱禁命名管道：`sh.exe: couldn't create signal pipe, Win32 error 5` |
| `py_compile`（会写 `__pycache__`） | ❌ | 项目目录不可写 → 报 Permission denied（**不是语法错误**）。用 `ast.parse` + `PYTHONDONTWRITEBYTECODE=1` |
| `pip download` | ❌ | 索引解析会挂死。改用 PyPI JSON API 拿直链 + urllib |
| 写项目目录（项目在工作区外时） | ⚠️ | 需要 `danger-full-access` 提权 |
| `Get-CimInstance` / `tasklist` | ❌ | 拒绝访问。用 `Get-Process`（需提权） |
| 控制台里的中文 | ⚠️ | GBK 控制台会乱码，**不代表文件坏了**；判断内容要写到 UTF-8 文件再读 |

---

## 7. 你会撞上的坑（按代价排序）

### 编码 / 环境
1. **`start.ps1` 和 `启动翻译助手.bat` 必须保持纯 ASCII。** PowerShell 5.1 按 GBK 解析
   UTF-8 无 BOM 文件，中文注释会导致解析错乱、变量变空、启动静默失败
   （表现是 `START FAILED: app.py exited with code`，退出码还是空的）。中文提示只写在
   `app.py` / `check_deploy.py` 里。
2. **一律 `py -3.12`。** 用 3.14 会报 `Error importing numpy: you should not try to import
   numpy from its source directory` —— 看着像"文件没拷全"，其实是版本不对。
3. 装 3.12 会把它的目录插到用户 PATH 最前面，于是裸 `python` 从 3.14 变成 3.12。
   **是"加装"不是"降级"**，诊断时别被继承来的旧环境骗了。

### git / 网络
4. 公司网络封了 `github.com` 解析到的那个 IP（`20.205.243.166`），但其它 GitHub IP 通。
   **不是 DNS 污染**。修法（在**人**的终端里执行）：
   `git config --global http.curloptResolve "github.com:443:20.27.177.113"`
   —— 需要管理员、不改 hosts、可 `--unset` 撤销。**这条线路时通时断，失败就重试；
   可用 IP 会用 `tools/dsh_pull.py` 之外的方式探测（api.github.com 一直通）。**
5. **GH007**：commit 作者邮箱必须是
   `203290839+ruanxiaoer888@users.noreply.github.com`，否则 GitHub 拒收。
6. **CRLF/LF 假差异**：Windows clone 出来是 CRLF、本地是 LF，按字节比对会显示
   "26 个文件都改了"。**以 `git status` 为准**；脚本里设 `core.autocrlf=false`。
7. 用 blob SHA 比对时，**基准值要跟着每次推送更新**，否则误报差异。

### ASR / GPU（技术含量最高，别重蹈覆辙）
8. **`ctranslate2.get_cuda_device_count() > 0` 不代表 GPU 能用。** ct2 加载 CUDA 模型时
   **不校验** cublas/cudnn，缺库要等**第一次真正编码**才炸
   （`Library cublas64_12.dll is not found or cannot be loaded`）。
   `asr_engine` 里已有"0.3 秒静音真跑一次"的验证，别删。
9. **Whisper 每次固定编码一个 30 秒窗口 → 识别成本与音频长度无关。**
   1.4 秒的短句和 6 秒的长句一样贵。所以"句子切长一点"是纯赚；
   判断跟不跟得上要看**实时率**，不是单句耗时。
10. **测 ASR 速度必须关 `vad_filter`。** 用噪声/静音测时 VAD 会把音频整段滤掉，
    编码根本不发生，得到 0.01 秒的假数据（踩过两次）。用 `tools/dsh_bench.py`。
11. **faster-whisper 默认解码回退极贵**：`temperature` 6 档，且每档 `best_of=5` →
    一次完整回退 = **26 次解码**，实测造成 47.8 s / 62.7 s 尖峰。
    现在固定为 `best_of=1` + `temperature=[0,0.2,0.4]`，别改回去。
12. **GTX 1650 没有张量核心 → fp16 反而慢**，int8_float16 快 3 倍。
    **换到 3060 Ti 这个结论不一定成立**，所以要实测（P0-3）。
13. **单线程流水线是延迟的元凶**：识别+翻译在录制循环里同步跑，期间不取音频 →
    每句积压 3 s+ 且只增不减。现在改成后台线程 + 有界队列（满 2 丢最旧），
    **宁可丢句也要追上实时**，别改回同步。

### 术语 / 准确度
14. **`TERM_FIXES` 的键必须同时存在于术语表里**才会触发（漏登记 = 规则静默失效）。
15. **加规则必须拿真实数据验证**：曾加过 `aproveita → 抓紧`，实测有害
    （"正在享受"变"正在抓紧"），已撤销。
16. **术语保护集不能"保护整张表的译文"**，否则 `broca` 的"钻头"会把
    `furadeira→电钻` 的修正护死（真实字幕 9 处全没修对）。
    现在的规则是"**只保护原文里真的出现过的词**"，改动前先看 `apply_glossary` 的注释。
17. **ASR 听错 ≠ 翻译错译**：`fideira`（应为 `furadeira`）术语表救不了，因为原文里
    根本没有正确的词 → 用原文级的 `PT_ASR_FIXES` 在**翻译之前**修原文。

---

## 8. 工具与验证命令

### 拉取更新（你自己就能做）
```
py -3.12 tools/dsh_pull.py                  # 预览差异（默认不写盘）
py -3.12 tools/dsh_pull.py --apply          # 真正写入（改项目目录需提权）
py -3.12 tools/dsh_pull.py --apply --tools  # 连 tools/ 也更新
```
它用 GitHub API 取文件树、算本地 blob SHA、只从 raw 下载有变化的文件。
**不碰 `libs/`、`tmp/`、`记录/`、`settings.json`**（它们不在仓库里）。

### 测速（决定精度）
```
py -3.12 tools/dsh_bench.py
```

### 验收套件（改完代码必跑）
```
py -3.12 check_deploy.py                                    # 期望 11 项 OK
py -3.12 tools\check_termfixes.py                           # 期望 结果: OK
$env:PYTHONPATH="$PWD\libs"; py -3.12 tools\verify_p0.py     # 期望 22/22
py -3.12 tools\verify_e2e.py                                # 期望 5/5
```

### 跑真实直播后看这个
```
记录\运行日志.txt     # 每句一行：队列等待0.0s 识别2.11s 翻译0.15s 音频5.5s 队列0
```
| 字段 | 健康值 | 含义 |
|---|---|---|
| `识别` | 1~2 s（GPU medium） | CPU small 是 4~5 s |
| `队列等待` | ≈0 | 持续变大 = 识别跟不上 |
| `队列` / 「丢弃最旧的一句」 | 不应出现 | 出现 = 过载，会掉句 |

---

## 9. 需要人类配合的动作（只有两条）

你在沙箱里做不到的只有"需要用户 GitHub 身份"的那一步。请人执行时，把命令**原样**给他：

| 时机 | 给人的命令 | 说明 |
|---|---|---|
| 会话开始（可选） | `git -C <clone目录> pull` | 你也可以直接用 `tools/dsh_pull.py` 对齐代码，不一定需要他 |
| 会话结束（必须） | `git -C <clone目录> push origin main` | 推送必须有凭据，这一步只能人做 |

公司电脑的 clone 目录是 `D:\Michael\DSHProjects\_gh_sync\realtime-translator`；
家里如果没有，请人跑一次（在**他自己的** PowerShell 里，不是沙箱）：
```
git clone https://github.com/ruanxiaoer888/realtime-translator.git D:\_gh_sync\realtime-translator
```

**你（AI）在推送前要做的**：把改动的文件复制进 clone、`git add`、`git commit`
（本地 git 可用），并确认作者是 noreply 邮箱。然后只请人跑 `git push` 一句话。

---

## 10. 进度记录（AI 每次收工在最上面加一条）

### 2026-10-16（公司电脑）
- **做了什么**：诊断延迟根因（单线程 + 实时率 1.28x 过载）→ 识别/翻译移入后台线程 +
  有界队列 + 运行日志；修 faster-whisper 解码回退尖峰（26 次 → 3 次）；
  装 GPU（cuBLAS 12.4.5.8 / cuDNN 9.1.0.70 / cudart 12.4.127 → `libs\nvidia\`，1.5 GB）；
  GPU 首选精度定为 `int8_float16`；模型 small → medium；
  术语 38 → 61 条 + `PT_ASR_FIXES` 11 条；修术语保护集冲突（改为"只保护原文出现过的词"）；
  分句上限 6 s → 4.5 s；文档更新（含 `部署到另一台电脑.md` 第四节整节重写）；
  新增 `tools/dsh_pull.py`、`tools/dsh_bench.py`
- **实测数据**：识别中位 4.61 → **2.11 s**；识别最大 47.82 → **2.44 s**；
  队列等待 6.10 → **0.00 s**；丢弃 27 → **0 次**；实时率 1.28 → **0.41x**；
  错译 18/18 → 1/18；`verify_p0` 21/1 → **22/0**
- **卡在哪**：分句 4.5 s 还没真实数据；家里 3060 Ti 环境与精度未验证；
  沙箱不能 git push（需人执行）
- **下次先做什么**：家里先 `check_deploy.py` 看算力行 → `tools/dsh_bench.py` 定精度 →
  跑一场 5~10 分钟看运行日志三个指标 → 结果写进本节并推送

### （模板）
```
### YYYY-MM-DD（哪台电脑）
- 做了什么：
- 实测数据：
- 卡在哪：
- 下次先做什么：
```
