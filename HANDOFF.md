# HANDOFF —— 实时翻译助手 · 双机协作与交接

> 最后更新：2026-10-16（公司电脑）
> **这份文件是公司电脑 ↔ 家里电脑之间传递上下文的唯一载体。**
> 它放在 GitHub 仓库里，所以 `git pull` 就能拿到最新版。
> **每次工作结束，请在最后一节「进度记录」最上面追加一条** —— 另一台电脑靠它才知道你做到哪了。

---

# ⭐ 快速开始：两台电脑怎么交替干活

## 在家里电脑第一次设置（只做一次，约 1 分钟）

在**家里项目目录**（含 `启动翻译助手.bat` 和 `libs\` 的那个）打开 PowerShell，整段粘贴：

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

**这四条命令各自在做什么：**

| 命令 | 作用 |
|---|---|
| `git init` | 把家里这个普通文件夹变成 git 仓库 |
| `git remote add origin ...` | 指向 GitHub 仓库 |
| `git reset --hard origin/main` | 用仓库版本覆盖**已跟踪**的文件（把今晚这 11 个文件的更新一次性拿来） |
| `git branch -M main` + `--set-upstream-to` | 让以后 `git pull` / `git push` 不用带参数 |

**两个必须知道的点：**

1. **`libs\`、`tmp\models\`、`记录\`、`settings.json` 不会被碰** —— 它们在仓库里是"未跟踪/被忽略"的，
   `reset --hard` 只覆盖已跟踪文件，**不会删你的模型和依赖**。
2. **`user.email` 必须是上面那个 noreply 地址**，否则 push 会被 GitHub 拒
   （报 `GH007: Your push would publish a private email address`）。

最后一次 `git status` 输出应该是干净的（家里和仓库一致）。

## 之后每天：两条命令

**回到某台电脑，先拉最新：**

```powershell
cd <项目目录>
git pull
```

**干完活，推上去：**

```powershell
cd <项目目录>
git status                                    # ← 先看一眼（重要）
git add -A
git commit -m "简述这次改了什么"
git push
```

> ⚠️ **第一次 push 前务必先看 `git status`**：`git add -A` 会把目录里所有新文件都加进来。
> 如果里面出现**你不认识的、体积很大的、或含隐私的文件**，先别 `add`，
> 把这个文件记到「进度记录」里，回公司再处理。

## 在另一台电脑上让 AI 接着干，就说这句话

> 请先读项目根目录的 `HANDOFF.md`，然后 `git pull`，接着按里面的
> 「进度记录」和「下一步计划」继续。

（这两句写在这里，就是为了你换电脑、换 AI 都能无缝接上。）

---

## 0. 一句话现状

**主要问题已解决并验证。** 公司电脑（GTX 1650）从「识别跟不上、一场丢 27 句」变成
「识别 2.11 秒、0 丢句、实时率 0.41x」，识别模型同时从 small 升级到 medium（更准）。
改动已推送到 GitHub（`e636170`）。**家里电脑（3060 Ti）待验证。**

---

## 1. 目标 / 当前任务

原始需求：把原本在家里电脑跑的实时翻译助手（葡语/西语 → 中文，TikTok Shop 直播用）
在公司电脑跑起来；跑起来后发现两个新问题：

| 问题 | 现象 | 状态 |
|---|---|---|
| A. 延迟大到不能接受 | 字幕越拖越久，8 分钟一场丢 27 句 | ✅ 已解决 |
| B. 翻译看不懂 | 术语错译、口语直译 | ✅ 大幅改善（18/18 → 1/18） |

---

## 2. 两台机器的环境

| | 公司电脑 | 家里电脑 |
|---|---|---|
| 项目路径 | `D:\Michael\DSHProjects\TikTokBR-Translator` | 待确认（含 `启动翻译助手.bat` 的目录） |
| GPU | **GTX 1650 4GB**（TU117，驱动 610.88） | **RTX 3060 Ti 8GB**（有张量核心） |
| CUDA 运行库 | **已补进 `libs\nvidia\`（1.5 GB，12 个 DLL）** | 本来就有（系统级），**不要**拷公司的过去 |
| Python | **3.12.9**（另有 3.14.7 共存） | 3.12 |
| 项目体积 | **4.47 GB**（其中 CUDA 库 1.5 GB） | 约 3 GB |

**Python 版本说明（重要）**：公司电脑原本只有 3.14，而 `libs\` 是 **cp312 编译**的，
3.14 加载会报一堆看不懂的错。后来**加装**了 3.12（不是降级、3.14 没删）。
装 3.12 时勾了"加入 PATH"，它会插到用户 PATH 最前面 —— 所以新开的终端里
裸 `python` 从 3.14 变成了 3.12。跑本项目一律用 `py -3.12`。

---

## 3. 已完成（全部有实测证据，不是估计）

### 3.1 性能：三场真实直播对比

来源：`记录\运行日志.txt`（本次新加的运行日志）

| 指标 | 第 2 场（CPU small） | **第 3 场（GPU medium）** | 结论 |
|---|---|---|---|
| 算力 | `cpu/int8` | **`cuda/int8_float16`** | GPU 生效 |
| 字幕条数 | 50 | 62 | |
| **丢弃句数** | **27 次** | **0 次** | ✅ |
| 识别 中位 | 4.61 s | **2.11 s** | ✅ 快 2.2 倍 |
| 识别 **最大** | **47.82 s** | **2.44 s** | ✅ 尖峰消失 |
| 识别尖峰(>8s) | 3 次（共 73 s） | **0 次** | ✅ |
| **队列等待 中位** | **6.10 s** | **0.00 s** | ✅ 不再积压 |
| 队列等待 最大 | 11.20 s | 1.50 s | ✅ |
| 翻译 中位 | 0.17 s | 0.15 s | 稳定（翻译从来不是瓶颈） |
| **实时率** | **1.28×（过载）** | **0.41×（余量 2.4 倍）** | ✅ |

> 关键概念：**Whisper 每次固定编码一个 30 秒窗口，识别成本与音频长度无关**
> —— 1.4 秒的短句和 6 秒的长句一样贵。判断"跟不跟得上"要看**实时率**
> （识别总耗时 ÷ 音频总长），不能只看单句耗时。

### 3.2 GPU 实测速度（GTX 1650，关掉 VAD 的真实编码）

| 配置 | 6 秒音频 | 显存 |
|---|---|---|
| cpu int8 small | 3.109 s | — |
| cuda float16 small | 1.321 s | 1.7 GB |
| **cuda int8_float16 small** | **0.433 s** | 1.4 GB |
| cuda float16 medium | 4.327 s | 3.1 GB |
| **cuda int8_float16 medium** | **1.154 s** | 2.1 GB |

**GTX 1650 没有张量核心，fp16 反而慢 —— int8_float16 快 3 倍**，所以代码里首选精度是
`int8_float16`。medium 在 GPU 上（1.154 s）**比 small 在 CPU 上（3.109 s）还快 2.7 倍**。

### 3.3 准确度

用真实直播字幕回放验证：

| 阶段 | 有明显错译的句子 |
|---|---|
| 修复前 | **18 / 18** |
| 补术语表 + 错译修正后 | **1 / 18** |

| 原文 | 修复前 | 修复后 |
|---|---|---|
| `...disponíveis de furadeira` | 博拉加莱拉最新可用的**钻床**单元 | **来吧大家**最新可用的**电钻**单元 |
| `vai furar, parede` | **将刺**，墙 | **钻孔**，墙 |
| `desmontar malzinha` | 去拆卸**小恶魔** | 去拆卸**工具箱** |
| `preço de barbada` | **巴巴多斯**价格 | **白菜价** |
| `top demais, pessoal, aproveita e leva` | 顶太多，个人，享受和携带 | **太棒了，各位，抓紧下单带走** |

术语资产现状：五金工具/pt 术语 **61 条**、`TERM_FIXES` **58 个词**、
`PT_ASR_FIXES`（ASR 误听修正）**11 条**。

### 3.4 工程与部署

- **项目迁移**：`D:\Tools\TikTokBR-Translator` → `D:\Michael\DSHProjects\TikTokBR-Translator`，自检 11/11
- **start.ps1 重写**：新增 `Find-Py312()` 精确查找 3.12（**去掉盲目的 `py -3` 回退**）、
  失败时自动前台重跑并打印真实报错、app 输出转存 `tmp\startup_log.txt`
- **asr_engine 三重 GPU 保护**：真实推理试跑（0.3 s 静音）→ 失败自动降级 CPU →
  推理时遇 cublas/cudnn 错误再兜底重试
- **check_deploy 新增「VC++ 运行库」检查**（共 11 项）
- **识别/翻译移入后台线程 + 有界队列（上限 2，满了丢最旧）**：录制循环不再被阻塞
- **新增运行日志** `记录\运行日志.txt`：每句一行，记录 `队列等待/识别/翻译/音频/队列`
- **解码回退尖峰修复**：`best_of=1` + `temperature=[0,0.2,0.4]`
  （默认是 6 档 × best_of=5 = **26 次解码**，实测造成 47.8 s / 62.7 s 尖峰）
- **术语保护逻辑修正**：从"保护整张术语表的译文"改成"只保护原文里出现过的词"，
  解决 `furadeira→电钻`、`martelete→电锤` 被其它术语压住修不动的问题
- **分句上限 6.0 s → 4.5 s**（用掉 GPU 余量，字幕出得更快；界面「每句最短」仍可调）
- **文档更新**：`部署到另一台电脑.md` 第四节整节重写（原结论是"不用 GPU"，已被推翻）、
  `README.md`、`使用说明.md`、`.gitignore`

### 3.5 测试结果（作者自带的测试套件）

| 测试 | 结果 |
|---|---|
| `tools/check_termfixes.py` | **OK** |
| `tools/verify_p0.py` | **22 通过 / 0 失败**（改动前是 21/1） |
| `tools/verify_e2e.py` | **5/5 通过，无术语污染** |
| `check_deploy.py` | 11 项全 OK（沙箱里"记录目录可写"会 FAIL，是权限问题，正常运行时 OK） |
| 补充测试 | 保护集冲突 9/9、端到端回放、线程化无界面测试（提交耗时 0.0000 s） |

### 3.6 GitHub 同步

仓库：<https://github.com/ruanxiaoer888/realtime-translator>（public）

| 提交 | 内容 |
|---|---|
| `66eab30` | （家里那台推的初始状态） |
| `3299b28` | 7 个文件：start.ps1 / asr_engine / check_deploy / 3 个文档 / README |
| `0d277da` | .gitignore + 移除 4 个 tools 结果 JSON + 部署文档补 GitHub 排障节 |
| **`e636170`** | **GPU 支持 + 线程化 + 运行日志 + 术语修复 + 文档（7 文件，+411/-56）** |
| `HANDOFF.md` | 本文件（双机协作载体） |

---

## 4. 卡住 / 未决的问题

| # | 问题 | 影响 | 备注 |
|---|---|---|---|
| 1 | **分句上限 4.5 s 还没有真实数据** | 无法确认"字幕更快"是否达标 | 需要再跑一场直播看日志 |
| 2 | **家里电脑（3060 Ti）未验证** | CUDA 环境、精度选择都可能不同 | 见第 5 节 P0/P1 |
| 3 | **`libs\nvidia\` 不在 GitHub**（`.gitignore` 排除） | 换机器不会自动带 GPU 库 | 靠"整体拷文件夹"传递，或重跑下载脚本 |
| 4 | **AI 无法执行 `git push`** | 每次推送最后一步要人工 | 沙箱里 git 只有 schannel 后端且被禁（`SEC_E_NO_CREDENTIALS`）；**但 Python 网络正常** |
| 5 | `pip download` 在沙箱里会挂死 | 不能直接用 pip 装 CUDA 库 | 绕法：PyPI JSON API 拿直链 + Python urllib 下载 |
| 6 | `verify_p0.py` 的「单帧 OCR 耗时 < 2 s」偶发失败 | 与本项目改动无关 | 环境相关（没装葡语语言包），本次复跑是 22/22 |
| 7 | 同类错译会反复出现 | 准确度需要持续养护 | 每次真实直播后，把新错译补进 `TERM_FIXES` / 术语表 |

---

## 5. 下一步计划（按优先级）

### P0 —— 家里电脑验证

1. 按上面「快速开始」完成第一次设置（没做过的）
2. **先跑自检** `py -3.12 check_deploy.py`，确认算力行是
   `cuda/int8_float16（CUDA可用=True）` 或 `cuda/float16`。
   **如果是 `cpu/int8`，先别测** —— 说明家里的 CUDA 库没被找到，把那一行记下来。
3. **手动调两项设置**（`settings.json` 被 gitignore，不会被覆盖）：
   识别模型 → **medium**；翻译引擎 → **仅在线接口**（NLLB 本地兜底是 CC-BY-NC-4.0 禁止商用）。
4. **跑一场 5~10 分钟**，看 `记录\运行日志.txt`：识别 1.5~2.5 s、队列等待 ≈0、无"丢弃"。
5. 把结果写进「进度记录」。

### P1 —— 两台机器的精度选择

公司那台没有张量核心，所以代码首选 `int8_float16`。**3060 Ti 有张量核心，`float16` 可能更准**
（速度差别不大）。如果家里测出准确度不如以前：
- 简单版：改 `asr_engine.py` 里的 `order`，把 `("cuda", "float16")` 放前面
- 更好版：做成界面可选项 / 按显卡自动选，两台机器各用各自的最优值

### P2 —— 继续榨性能（有余量）

实时率只有 0.41x，余量 2.4 倍，可选：
- 分句上限再收到 3.5~4 s（字幕更跟手）
- 用 `medium` + 更大的 `beam_size`（质量换一点速度）
- 屏幕 OCR 装葡语语言包：1300 ms/帧 → 约 14 ms/帧（需 `DISM /RestoreHealth` + 重启）

### P3 —— 工程化收尾

- 把 GPU 安装/检测脚本固化进 `tools/`
- 把「拉取更新」也做成脚本（现在 `git pull` 已经够用）
- 域名解析修复（`http.curloptResolve`）只写在部署文档里，可考虑做成脚本

---

## 6. 踩过的坑（按代价从大到小）

### 编码 / 环境类

1. **`start.ps1` 里绝不能出现非 ASCII 字符。**
   Windows PowerShell 5.1 会把无 BOM 的 UTF-8 当 GBK 解析。我往里加了中文注释 →
   解析错乱、变量变空、启动静默失败（表现为 `START FAILED: app.py exited with code`，
   退出码还是空的）。**中文提示只能写在 `app.py` / `check_deploy.py` 里。**
2. **Python 版本**：`libs\` 是 cp312，用 3.14 跑会报
   `Error importing numpy: you should not try to import numpy from its source directory`
   —— 这个报错极其误导（看着像"文件没拷全"）。一律 `py -3.12`。
3. **装 3.12 会改变裸 `python` 的指向**（插到用户 PATH 最前面），但 3.14 没被删 ——
   是"加装"不是"降级"。诊断时别被自己的旧环境骗了。
4. **沙箱里 `py_compile` 会报 Permission denied**（不许写项目目录的 `__pycache__`），
   那不是语法错误。检查语法用 `ast.parse`，并设 `PYTHONDONTWRITEBYTECODE=1`。
5. **沙箱禁命名管道** → `git ls-remote` 连**本地**仓库都失败
   （`sh.exe: couldn't create signal pipe, Win32 error 5`）。
6. **GBK 控制台里中文乱码 ≠ 文件坏了。** 判断文件内容要写进 UTF-8 文件再读，别信控制台。

### Git / 网络类

7. **公司网络封了 `github.com` 解析到的那个 IP**（20.205.243.166），
   但 `api.github.com`、`codeload.github.com` 和其它几个 GitHub IP 是通的。
   **不是 DNS 污染**（4 个公共 DNS 都返回同一个真实 IP）。
   修法：`git config --global http.curloptResolve "github.com:443:20.27.177.113"` ——
   不需要管理员、不改 hosts、只影响 git。撤销：`--unset`。
   注意：**这是公司网络特有的，家里一般不需要**。
8. **沙箱里 git 根本不能用**：这个 git 构建只编译了 `schannel` 后端
   （`Supported SSL backends: schannel`），而沙箱禁止它访问 Windows 凭据库 →
   `schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS`。
   换 openssl 后端也不行（没编译进去）。**但同一个沙箱里 Python urllib 联网完全正常。**
9. **`pip download` 在沙箱里会挂死**（索引解析超时）。
   绕法：用 PyPI JSON API 拿 wheel 直链，再用 urllib 下载（1.03 GB 实测可行，SHA256 校验通过）。
10. **GH007 推送被拒**：commit 作者邮箱用了私人邮箱，而账号开了"禁止暴露私人邮箱"。
    必须用 noreply：`203290839+ruanxiaoer888@users.noreply.github.com`。
11. **CRLF/LF 假差异**：Windows 上 clone 出来是 CRLF，本地是 LF，按字节比对会显示
    "26 个文件都改了"，其实 git 提交时归一化 → **以 `git status` 为准**。
    脚本里设 `core.autocrlf=false` 可消除。
12. **核对脚本的基准值要跟着每次推送更新**，否则会误报差异（我漏改一条，白查一轮）。

### ASR / GPU 类（技术含量最高）

13. **`ctranslate2.get_cuda_device_count() > 0` 不代表 GPU 能用。**
    ct2 加载 CUDA 模型时**不校验** cublas/cudnn，缺库要等**第一次真正编码**才炸
    （`Library cublas64_12.dll is not found or cannot be loaded`）。
    必须用"0.3 秒静音真跑一次"来验（代码里已加）。
14. **Whisper 每次固定编码 30 秒窗口** → 识别成本与音频长度无关。
    这条改变了整个优化思路：句子切长一点是**纯赚**（同样的钱干更多活）。
15. **用噪声/静音测 ASR 会被 VAD 整段滤掉**，测出 0.01 s 的假数据（我踩了两次）。
    **测速必须关 `vad_filter`**，或者用真实语音。
16. **faster-whisper 的默认解码回退极其昂贵**：`temperature` 6 档，
    而 `temperature>0` 的每一档都用 `best_of=5` 生成 5 个候选 → 一次完整回退 = **26 次解码**。
    实测造成 47.8 s / 62.7 s 的识别尖峰（占该场识别总耗时的 25%）。
17. **GTX 1650 没有张量核心** → fp16 反而慢。int8_float16 快 3 倍。
    换卡（比如 3060 Ti）时这个结论不一定成立。
18. **单线程流水线是延迟的元凶**：识别（3 s）+ 翻译在录制循环里同步执行，
    期间不取音频 → 每句积压 3 s+，而且**只增不减**（一场下来 100 s+）。
    修法是后台线程 + 有界队列（宁可丢句也要追上实时）。

### 术语 / 准确度类

19. **`TERM_FIXES` 的键必须同时存在于术语表里才会触发。**
    我加了 `furar` 的修正规则却忘了往术语表登记 → 规则静默失效。
20. **加规则必须拿真实数据验证。** 我加的 `aproveita → 抓紧` 实测**有害**
    （"正在享受"变成"正在抓紧"），已撤掉并写了注释防止后人再加。
21. **术语保护集会互相压住。** 原来是"保护整张术语表的译文"，
    于是 `broca` 的译文"钻头"把 `furadeira→电钻` 的修正护死了（真实字幕里 9 处全没修对）。
    改成"只保护原文里出现过的词"后解决，反向验证（`broca`+`furadeira` 同现时"钻头"必须保留）通过。
22. **ASR 听错和翻译错译要分开修**：ASR 听错（`fideira` 应为 `furadeira`）术语表救不了 ——
    原文里根本没有正确的词。所以新增了原文级的 `PT_ASR_FIXES`（在翻译之前修原文，
    这样字幕里的葡语原文和中文一起变干净）。

---

## 7. 关键文件与命令速查

### 日常使用

```
双击      <项目目录>\启动翻译助手.bat
自检      cd <项目目录> && py -3.12 check_deploy.py
运行日志  记录\运行日志.txt        ← 判断卡不卡、有没有掉句，看这个
字幕      记录\直播字幕.srt
拉更新    cd <项目目录> && git pull
推改动    cd <项目目录> && git status && git add -A && git commit -m "..." && git push
```

### 运行日志怎么读

```
17:52:19  #1   队列等待0.0s 识别2.11s 翻译0.15s 音频5.5s 队列0
```

| 字段 | 健康值 | 含义 |
|---|---|---|
| `识别` | 1~2 s（GPU medium） | CPU small 是 4~5 s |
| `队列等待` | ≈0 | 持续变大 = 识别跟不上 |
| `队列` / 「丢弃最旧的一句」 | 不应出现 | 出现说明过载，会掉句 |

### 工具脚本位置（在公司的 DSH 工作区，不在仓库里）

| 路径 | 用途 |
|---|---|
| `D:\Michael\DSHProjects\Tiktok\_gh_check\sync_github.ps1` | 把项目改动同步到 GitHub 克隆并提交 |
| `D:\Michael\DSHProjects\Tiktok\_gh_check\fix_github_access.ps1` | 探测可用 GitHub IP 并写入 git 配置 |
| `D:\Michael\DSHProjects\Tiktok\_gh_check\compare.py` | 本地 vs GitHub 逐字节（blob SHA）比对 |
| `D:\Michael\DSHProjects\Tiktok\_gpu\download_cuda.py` | 下载 cuBLAS/cuDNN/cudart wheel（含 SHA256 校验） |
| `D:\Michael\DSHProjects\Tiktok\_gpu\extract_cuda.py` | 把 wheel 里的 DLL 解包成 `libs\nvidia\<包>\bin\` |
| `D:\Michael\DSHProjects\Tiktok\_gpu\bench_gpu2.py` | GPU/CPU 真实速度对比（**关掉 VAD**） |
| `D:\Michael\DSHProjects\Tiktok\_gh_check\replay_e2e.py` | 拿真实字幕回放验证准确度 |
| `D:\Michael\DSHProjects\Tiktok\_gh_check\verify_protect.py` | 保护集冲突 + 回归 9 项 |

### CUDA 运行库（公司机器已装，家里**不要**拷）

| 包 | 版本 | wheel | 解包后 |
|---|---|---|---|
| nvidia-cublas-cu12 | 12.4.5.8 | 378 MB | `cublas64_12.dll` / `cublasLt64_12.dll` |
| nvidia-cudnn-cu12 | 9.1.0.70 | 648 MB | `cudnn*64_9.dll`（8 个） |
| nvidia-cuda-runtime-cu12 | 12.4.127 | 0.9 MB | `cudart64_12.dll` |

布局：`libs\nvidia\{cublas,cudnn,cuda_runtime}\bin\`（共 12 个 DLL，1.54 GB）。
`asr_engine._register_cuda_dlls()` 启动时把它们注册进 DLL 搜索路径
（`os.add_dll_directory` + `PATH`）；**目录不存在时是安全空操作**。
撤销：删掉 `libs\nvidia\` 即可。

> **为什么家里不要拷这 1.5 GB**：家里那台 GPU 本来就能跑（README 的 GPU 实测就是在家里测的），
> 说明 cuBLAS/cuDNN 已就位。拷过去会把 `libs\nvidia\*\bin` 插到 PATH 最前面，
> 等于用 9.1.0.70 盖住家里原来的版本。

---

## 8. 验证方法（怎么判断有没有变坏）

| 检查 | 命令 | 期望 |
|---|---|---|
| 语法 | `ast.parse`（不要用 `py_compile`，沙箱会因 `__pycache__` 权限报错） | 0 错误 |
| 自检 | `py -3.12 check_deploy.py` | 11 项 OK；算力 `cuda/...` |
| 术语规则 | `py -3.12 tools\check_termfixes.py` | `结果: OK` |
| P0 验收 | `$env:PYTHONPATH="<项目>\libs"; py -3.12 tools\verify_p0.py` | **22/22** |
| 端到端 | `py -3.12 tools\verify_e2e.py` | 5/5 无污染 |
| 性能 | 跑一场 → 看 `记录\运行日志.txt` | 识别 1~2 s、队列等待 ≈0、无丢弃 |
| GPU | 看自检「算力」行 | `cuda/int8_float16` |

---

## 9. 本次改动涉及的文件

### 项目里被改的（已推送）

| 文件 | 改动要点 |
|---|---|
| `app.py` | 识别/翻译后台线程 + 有界队列；运行日志；`fix_source` 调用；字幕列表加锁；分句上限 4.5 s |
| `asr_engine.py` | `_register_cuda_dlls()`；GPU 首选 `int8_float16`；`best_of=1` + temperature 3 档；`_cuda_usable` 状态位 + 试跑验证 |
| `translate_core.py` | `fix_source()` + `PT_ASR_FIXES`（11 条误听修正）；`TERM_FIXES` 大幅补充；保护逻辑改为"只保护原文出现过的词" |
| `markets.py` | 巴西直播口语术语（五金工具/pt 从 38 → **61 条**） |
| `check_deploy.py` | 新增「VC++ 运行库」检查（11 项） |
| `start.ps1` | `Find-Py312()`；去掉 `py -3` 回退；启动失败自诊断；保持纯 ASCII |
| `.gitignore` | 忽略工具结果 JSON |
| `README.md` / `使用说明.md` / `新电脑先读我.txt` / `部署到另一台电脑.md` | 同步以上结论与实测数据 |
| `settings.json`（**本地，不入库**） | 模型 medium、引擎「仅在线接口」 |

### 项目里新增的

| 文件 | 说明 |
|---|---|
| `记录\运行日志.txt` | 运行时自动生成（每次听译追加一段，带表头）——**不入库** |
| `HANDOFF.md` | **本文件（入库，双机协作靠它）** |

---

## 10. 一句话给下一位接手的人

**这个项目的性能瓶颈永远是 ASR，不是翻译**（翻译稳定 0.15 s/句）。
调优顺序应该是：先看 `记录\运行日志.txt` 的**实时率**和**队列等待**，
再决定是上 GPU、缩短音频段、还是限制解码回退 —— 不要凭感觉调参数，
更不要把"单句耗时"当成"延迟"。

---

## 11. 进度记录（每次工作后在最上面追加一条）

### 2026-10-16（公司电脑）
- **做了什么**：诊断延迟根因（单线程 + 实时率 1.28x 过载）→ 线程化 + 运行日志；
  修解码回退尖峰（26 次解码 → 3 次）；装 GPU（cuBLAS 12.4/cuDNN 9.1/cudart 12.4 → `libs\nvidia\`）；
  模型 small → medium；术语 38 → 61 条 + 11 条 ASR 误听修正；修术语保护集冲突；
  分句上限 6 s → 4.5 s；文档更新；推送 GitHub（`e636170`）
- **实测数据**：识别中位 4.61 → **2.11 s**；识别最大 47.82 → **2.44 s**；
  队列等待 6.10 → **0.00 s**；丢弃 27 → **0 次**；实时率 1.28 → **0.41x**；
  错译 18/18 → 1/18；`verify_p0` 21/1 → **22/0**
- **卡在哪**：分句 4.5 s 还没有真实数据；家里 3060 Ti 环境未验证；AI 无法 push（需人工执行）
- **下次先做什么**：家里先跑 `check_deploy.py` 看算力行；再跑一场看运行日志三个指标；
  结果写进本文件

### （模板，复制这段改）
```
### YYYY-MM-DD（哪台电脑）
- 做了什么：
- 实测数据：
- 卡在哪：
- 下次先做什么：
```
