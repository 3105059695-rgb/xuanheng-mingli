<p align="center">
  <img src="assets/hero.svg" alt="玄衡 · 命理推演 — 先核历，再推演。让判断有依据，让表达有分寸。" width="100%">
</p>

<p align="center">
  <strong>一套能核历、能排盘、能说明依据的中文命理 Skill</strong><br>
  <sub>方木出品 · 调用名 <code>mingli</code> · v2.8.1 · Python 3.9+</sub>
</p>

<p align="center">
  <a href="#开始使用">开始使用</a> ·
  <a href="#能力一览">能力一览</a> ·
  <a href="#看看交付样例">交付样例</a> ·
  <a href="REVIEW.md">检查记录</a>
</p>

---

**玄衡**让支持 Skill 的 AI 助手先核对输入、运行计算，再根据明确的传统规则给出有条件的白话判断。规则、计算和解释各有来源，重要分歧与资料缺项会保留下来。

你得到的是一套可安装的技能：**指令 + 参考资料 + Python 工具 + 测试**。使用环境需要能读取 Skill 并执行 Python。

> **如何理解它的结果**<br>
> 传统命理判断不是已验证的事实预测。脚本负责可复算的结构；测试和教学样例说明实现与流程，不代表预测命中率。

## 能力一览

| 方向 | 可以完成什么 | 详细说明 |
| :--- | :--- | :--- |
| **八字** | 公农历核验、四柱、藏干十神、大运与流年标签、格局条件审查 | [八字内核](mingli/references/bazi.md) |
| **六爻** | 三钱装卦、纳甲六亲、世应、动变、旬空及日月关系 | [六爻内核](mingli/references/liuyao.md) |
| **梅花** | 时间、数物与两段声音起卦，体用、本互变结构 | [梅花规则](mingli/references/meihua.md) |
| **民俗** | 小六壬、报数、筊杯，以及指定寺庙的求签记录 | [民间手法](mingli/references/folk.md) |
| **特殊时制** | IANA 时区、历史夏令时、重叠与缺失时刻、太阳钟面敏感性对照 | [时间核验](mingli/references/time-normalization.md) |
| **双人关系** | 两人分别排盘、共同期限按节分段、条件比较与白话报告 | [关系专题](mingli/references/relationships.md) |

## 开始使用

### 1 · 取得完整技能

[**下载 v2.8.1 安装包 →**](https://github.com/3105059695-rgb/xuanheng-mingli/releases/download/v2.8.1/mingli-v2.8.1.zip)

解压后，将整个 **`mingli/` 文件夹**放入助手支持的 skills 目录，保留内部结构。安装目录由你使用的助手决定；`SKILL.md`、`scripts/` 和 `references/` 需要一同保留。

也可以在仓库页面选择 **Code → Download ZIP**，取得完整源码、说明和测试。

### 2 · 准备 Python 环境

在下载或克隆得到的目录中打开终端，按所用系统执行。下列命令先进入 `mingli/`，再创建独立环境；如果终端已经在 `mingli/` 内，跳过第一行。

<details open>
<summary><strong>Windows · PowerShell</strong></summary>

```powershell
cd mingli
py -3 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

无需激活环境，也无需修改 PowerShell 执行策略。

</details>

<details>
<summary><strong>macOS / Linux · Terminal</strong></summary>

```bash
cd mingli
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

</details>

首次安装依赖需要联网。脚本最低要求 Python 3.9；本次实际验证环境为 **Windows / Python 3.12**。更多命令见 [历法与运行说明](mingli/references/calendar.md#运行)。

### 3 · 向助手提出问题

安装后，可以直接复制这一段：

```text
请使用 $mingli。

我的问题：【写清楚这次最想问的一件事】
检查期限：【起止时间及时区】
已知情况：【目前能够确认的事实】

请实际运行计算，先给有条件的判断，再解释关键依据、
会改变结论的限制，以及有事实依据的现实建议。
```

| 所用方法 | 再补充这些信息 |
| :--- | :--- |
| 八字 | 历别、出生年月日时、时间口径与误差；农历注明是否闰月，需要校时再补出生地 |
| 六爻 | 六次原始记录，按初爻到上爻排列；起卦时间与地点 |
| 双人关系 | 双方各自的资料，以及共同问题和期限 |

资料不清楚时直接写“未知”。不能补造时辰，也不能把未评估的误差写成零。

## 看看交付样例

| 样例 | 重点看什么 |
| :--- | :--- |
| [**八字咨询 →**](mingli/references/consultation-example.md) | 从命局依据到具体问题，怎样解释条件与限制 |
| [**六爻问事 →**](mingli/references/liuyao-example.md) | 怎样保留原始卦象、用神选择、支持与反证 |
| [**双人关系 →**](mingli/references/relationship-example.md) | 怎样分别排盘，并比较同一段期限内的变化 |

以上为教学与合成样例，用来展示方法，不作为真实客户实绩。正式交付的表达要求见 [白话报告规范](mingli/references/reporting.md)。

## 计算与验证

| 本次实际检查 | 结果 |
| :--- | :--- |
| 自动测试 | **154 项通过，无跳过** |
| Skill 结构 | 校验通过 |
| Python 依赖 | `pip check` 通过 |
| Windows 兼容性 | 已修复时区依赖缺失与卦象输出编码报错 |

完整复现、修复清单与未验证范围见 [**检查记录 →**](REVIEW.md)。

<details>
<summary><strong>依赖、编码与各平台的运行约定</strong></summary>

- 历法依赖固定为 `lunar-python==1.4.8`，时区数据依赖固定为 `tzdata==2026.4`。
- 时区工具优先使用系统 IANA 数据，没有系统数据时使用 `tzdata`，结果记录实际来源与版本。
- 计算脚本运行时不联网，标准输出与标准错误统一为 **UTF-8**；通过子进程调用时指定 `encoding="utf-8"`。
- 参考文档中的多行命令主要采用 macOS/Linux shell 写法。Windows 需换用 `.venv/Scripts/python.exe` 并合成单行，不使用反斜杠续行。
- 本次未在 macOS/Linux 或所有支持的 Python 版本实际执行测试。

</details>

## 深入阅读

| 想了解什么 | 从这里开始 |
| :--- | :--- |
| 技能如何选择方法、组织推演 | [Skill 入口](mingli/SKILL.md) · [核验与推演](mingli/references/core.md) |
| 规则出自哪里、采用哪个版本 | [来源台账](mingli/references/sources.md) |
| 如何写清楚依据与期限 | [咨询交付](mingli/references/consultation.md) · [白话报告](mingli/references/reporting.md) |
| 如何保存原断与后续结果 | [复核空表](mingli/assets/review-record.md) · [结果验证](mingli/references/validation.md) |

<details>
<summary><strong>查看目录结构</strong></summary>

```text
xuanheng-mingli/
├── README.md                 项目首页
├── REVIEW.md                 本次检查与修复记录
├── assets/                   首页视觉素材
└── mingli/
    ├── SKILL.md              技能入口
    ├── agents/               助手界面元数据
    ├── references/           传统规则、来源与教学样例
    ├── scripts/              7 个计算入口 + 输出辅助模块
    ├── tests/                8 个测试文件
    ├── assets/               单案复核空表
    └── requirements.txt      固定依赖
```

</details>

## 使用边界

完整平太阳时/视太阳时四柱与起运、后续每步大运精确交接尚未完成；不提供自动喜用神评分、婚配适配分或保证婚期。预测准确率、真人专业审阅与真实客户体验仍未验证。

个人出生资料、真实客户记录与生成报告请保存在仓库以外。`.gitignore` 已为 `cases/`、`private/` 和 `output/` 提供本地排除项。

---

<p align="center">
  <sub>玄衡 · 方木出品<br>原交付包未附项目许可证，本次保留该状态。</sub>
</p>
