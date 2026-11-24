# HPC_Style_For_AI

_面向各类 HPC 项目的通用设计与评审原则，0.3.1。_

目标不是让新代码“长得像某个成熟库”，而是让 AI 能从计算契约、资源约束和工程代价推导设计。框架、模板、布局、并行模型和平台适配，都应是这个推导的结果，而非预设答案。

## 从原则进入，而非从案例进入

[通用原则](<skills/hpc-style-for-ai/references/rules.md>)是主文档，不依赖 AMReX、C++、网格或 CUDA。它按设计问题组织：

| 设计问题 | 原则 |
| --- | --- |
| 什么才算正确，代价主要在哪里 | G01 计算契约；G02 主导成本与关键路径 |
| 数据与程序怎样组织 | G03 表示、访问、放置与生命周期；G04 稳定语义与抽象边界 |
| 信息和工作何时、如何执行 | G05 绑定时机；G06 粒度与局部性；G07 依赖与完成；G08 整体完成时间 |
| 如何控制长期工程成本 | G09 特化预算；G10 可推理的代码结构；G11 验证闭环；G12 可移植性契约 |

例如，“为什么使用模板元编程”先转化为“哪些信息值得提前确定”。之后才比较编译期特化、运行时计划、JIT、批量分派和普通动态执行。这样既保留模板的设计动机，也让原则适用于其他语言和算法。

## 内容分成三个层次

```mermaid
flowchart TB
    accTitle: Principles Mechanisms And Evidence
    accDescr: 通用原则独立组织设计问题，实施说明解释可选机制，案例提供具体证据和限制。案例不决定原则正文的章节与接口要求。
    principles["通用原则：约束、成本与取舍"] --> mechanisms["实施说明：按任务选择机制"]
    evidence["案例论据：具体机制与适用限制"] -.-> principles
    evidence -.-> mechanisms
```

- **原则层**：[十二条通用原则](<skills/hpc-style-for-ai/references/rules.md>)。AI 默认读取，不要求复制任何项目的架构。
- **补充说明层**：[绑定策略](<skills/hpc-style-for-ai/references/binding-strategies.md>)，以及[数据独立性、一致性与工作完成](<skills/hpc-style-for-ai/references/execution-memory-contracts.md>)。按设计问题加载，说明决策条件、可选办法、代价和验证方法，不按某个库的功能清单组织。
- **论据层**：[原则与证据的联系](<docs/principle-evidence.md>)、[AMReX Base 案例](<docs/base-study.md>)及其[账本](<evidence/base-evidence.json>)，还有新增的[Kokkos 案例](<docs/kokkos-study.md>)及其[账本](<evidence/kokkos-evidence.json>)。支持和限定设计解释，不充当规范目录。

0.3.1 保留 G01–G12，把上一轮较贴近实现的段落改为通用问题：数据需要怎样的共享或隔离，不同表示何时有效，每份工作应贡献几次，结果何时可以消费，以及测试是否触及实际条件。独立性不预设全量物理复制，协调也不预设某种并行模型。

具体库的术语、API 行为、固定源码与探针结论留在案例和证据层；它们用于支持或限制判断，不决定原则的章节和技能的加载条件。两轮源码阅读分别固定到 AMReX `7802c6ef997f8350c26d07a2e7326a4fe0c77fb8` 与 Kokkos 5.3.0 `dc826b0fad122b57fee60223e86154aecb8e60f4`，原有证据和适用限制保持独立。

本轮只审阅指定实现与测试片段，并运行原创 Serial/OpenMP 契约探针；不是两份库的全量审计，也没有跨设备或性能验收。源码机制、上游测试源码阅读和本仓库实测结果在案例中分别记录。

## 给 AI 使用

读取[技能入口](<skills/hpc-style-for-ai/SKILL.md>)及其默认引用的原则，随后提交具体任务。例如：

```text
使用 hpc-style-for-ai 设计这个稀疏迭代求解流程。
先确定数值契约、重复使用的结构、数据运动与关键路径，
再选择预处理计划、数据表示和并行粒度。不要预设模板或某种执行框架。
说明每个重要选择的收益、代价和验证方法。
```

```text
使用 hpc-style-for-ai 评审这段 Fortran/Python 科学计算流程。
从端到端成本、隐式复制、工作粒度、依赖与数值验证入手。
不要为了套用案例而更换语言或引入网格对象体系。
```

对稠密计算，可以从复用和计算强度切入；对稀疏或图任务，可以从不规则访问、预处理摊销和长尾切入；对重复变换，可以从计划构建、重排和通信切入。这些只是原则应用的假设场景，不是已经实施的优化成果。

支持 skill 目录的工具可复制整个 `skills/hpc-style-for-ai/`，保留入口和 references 的相对布局。其核心内容不依赖外部源码仓库或证据附录即可加载。

### DSH 插件

插件按需注册 `hpc-style-for-ai`，不向全局提示词强制注入规则。适配目标是 DSH skills 服务 `0.2.1-rc.5`，Node.js 22+。

```bash
# 安装固定版本发行包；将 web 换成实际使用的 profile。
dsh plugin --profile web add https://github.com/WangZW928/HPC_Style_For_AI/releases/download/v0.3.1/dsh-hpc-style-for-ai-0.3.1.tgz

# 从源码检查和打包。
git clone https://github.com/WangZW928/HPC_Style_For_AI.git
cd HPC_Style_For_AI
npm run check
npm pack
```

发行包也可下载后通过宿主插件管理器安装。按宿主提示启用、刷新会话并检查技能目录；安装是否生效以实际加载为准。包名为 `dsh-hpc-style-for-ai`，技能名为 `hpc-style-for-ai`。

## 检查范围

```bash
# 文档、原则和 provider 契约检查
npm run check
# 可选：核对 AMReX 案例的固定提交、26 条引文与源文件状态
python3 scripts/validate.py --source ../amrex
# 可选：核对 Kokkos 固定提交、24 条逐字引文和完整源文件 SHA256
python3 scripts/validate.py --kokkos-source /absolute/path/to/kokkos-5.3.0
# 可选：隔离环境中的真实 DSH registry 发现、加载与资源定位
node scripts/host-smoke.mjs /absolute/path/to/dsh-runtime
```

结构检查验证原则层与案例层的依赖方向、编号、链接和技能加载，不证明 AI 在所有任务中都会正确应用原则。Mermaid 仅做结构检查，没有可视化验收。

保留的[独立 C++ 示例](<examples/owner_view.cpp>)只演示一组类型与执行边界，不是规范蓝图。它已有 Serial/OpenMP 正确性和标量 sanitizer 检查；空域、尺寸不匹配、const、同址 alias 等测试不代表所有 HPC 机制已覆盖。其[构建入口](<CMakeLists.txt>)支持以下命令：

```bash
cmake -S . -B build-serial -DCMAKE_BUILD_TYPE=Release
cmake --build build-serial
ctest --test-dir build-serial --output-on-failure
# OpenMP：另用 -DHPC_STYLE_OPENMP=ON 配置。
```

案例层的[契约探针](<examples/kokkos_contracts.cpp>)依赖已安装的 Kokkos 5.3，默认关闭且不自动下载源码。上一轮以固定源码运行的两项主机探针和原有示例测试共三项通过，具体编译配置、检查内容与未覆盖条件见[案例运行记录](<docs/kokkos-study.md#本轮真正运行了什么>)。它们验证有限的实现契约，不是新项目必须实现的规范清单；本次抽象化修订不改变探针代码或源码证据。

复现时先在外部安装同一提交的 Serial/OpenMP Kokkos，再运行：

```bash
cmake -S . -B build-kokkos -DCMAKE_BUILD_TYPE=Release -DHPC_STYLE_KOKKOS=ON -DCMAKE_PREFIX_PATH=/absolute/path/to/kokkos-install
cmake --build build-kokkos
ctest --test-dir build-kokkos --output-on-failure
```

通用文档与 provider 检查不需要 Kokkos；源码校验使用 `--kokkos-source` 才验证本地源码，省略该参数不宣称已核对源码。新增负控检查拒绝错误提交、引文漂移、被修改的源文件、缺失的证据字段、哈希差异与无效证据编号。CI 配置增加了固定 Kokkos 源码和主机探针任务；本轮未触发远端 CI。

没有运行上游完整测试套件、MPI、CUDA 或其他加速器后端，也没有真实异步时间线或性能基准。主机契约通过不证明跨设备依赖、浮点可复现性或普遍性能收益。

## 后续维护

先提出独立于具体项目的设计问题，再检查论据支持了什么、遗漏了什么。新增案例可以支持、限制或促使修改原则，但不因它使用某种 API，就把那种 API 的组织方式推广为所有项目的要求。

公开项目地址：[WangZW928/HPC_Style_For_AI](https://github.com/WangZW928/HPC_Style_For_AI)。原创代码、探针、图标和文档采用 [MIT 许可](<LICENSE>)；AMReX 引文与片段保留[BSD-3-Clause 许可](<third_party/AMReX-LICENSE>)，Kokkos 引文保留[Apache-2.0 with LLVM Exceptions 许可](<third_party/Kokkos-LICENSE>)。归属说明见 [NOTICE](<NOTICE>)，不代表这些项目官方认可。

发行包通过 GitHub Release 分发；npm 包名仅用于包标识，不代表已经发布到 npm。市场收录由各目录维护者审核，提交申请不等于已经上架。
