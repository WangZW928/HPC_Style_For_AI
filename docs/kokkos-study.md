# Kokkos 5.3.0：从访问表示到完成契约

_案例层；2026-11-24。源码机制、测试源码阅读与本仓库契约探针的运行结果分别记录。_

本轮固定到 tag `5.3.0`、commit `dc826b0fad122b57fee60223e86154aecb8e60f4`。
证据编号、逐字引文、行号、源码文件 SHA256 与限制见[证据账本](<../evidence/kokkos-evidence.json>)；原则入口见[通用原则](<../skills/hpc-style-for-ai/references/rules.md>)。
这里关注访问表示、资源共享和执行完成如何组合，不把 Kokkos 的类结构当成新工程蓝图。

## View 不等于无所有权句柄

在 AMReX 案例中，无所有权访问描述是一个有用的边界；把它扩展为“所有 View 都不管理资源”，就会误读 Kokkos。
5.3.0 的 [BasicView 类型定义](<https://github.com/kokkos/kokkos/blob/dc826b0fad122b57fee60223e86154aecb8e60f4/core/src/View/Kokkos_BasicView.hpp#L119-L137>)使用 `mdspan` 的 extents、mapping、accessor 和 data handle 类型（KM01）。
这说明表示可以拆成若干变化轴，却不说明整个对象就是一个无所有权的标准 `mdspan`。

[ReferenceCountedDataHandle 构造](<https://github.com/kokkos/kokkos/blob/dc826b0fad122b57fee60223e86154aecb8e60f4/core/src/View/MDSpan/Kokkos_MDSpan_Accessor.hpp#L288-L320>)给出更直接的区别：
managed 句柄携带分配记录；子视图可以共享 tracker，同时改变访问指针；裸指针构造则保留空 tracker（KM02）。
所以“复制句柄”“复制元素”“延长资源生命周期”是三个不同动作。

| 情形 | 本轮源码支持的判断 | 留给调用方的问题 |
| --- | --- | --- |
| managed View 浅复制 | 共享分配记录，不复制元素 | 别名之间谁可写、何时读 |
| managed 子视图 | 共享记录，使用偏移后的访问映射 | 访问范围与 stride 是否匹配操作 |
| unmanaged 句柄 | 不因转回普通 View 类型而恢复所有权 | 原资源是否一直存活 |

[上游引用计数测试](<https://github.com/kokkos/kokkos/blob/dc826b0fad122b57fee60223e86154aecb8e60f4/core/unit_test/TestViewMapping_a.hpp#L601-L635>)明确检查浅复制后的计数，以及 unmanaged 转换后计数仍为零。
这是测试源码阅读，不是本轮执行该测试的记录；也不证明引用计数已经替异步消费者等待。
可推广的是 G03、G07：把访问权、别名与资源存活写清楚，而不是强制一个独立 owner 类。

## 映射决定 stride，分配还可能启动初始化

逻辑形状相同，不代表底层字节排列相同。
[View::span 与连续性查询](<https://github.com/kokkos/kokkos/blob/dc826b0fad122b57fee60223e86154aecb8e60f4/core/src/Kokkos_View.hpp#L459-L464>)分别使用 mapping 的 `required_span_size()` 和 `is_exhaustive()`（KM05）。
[显式 stride 测试](<https://github.com/kokkos/kokkos/blob/dc826b0fad122b57fee60223e86154aecb8e60f4/core/unit_test/TestViewAPI_b.hpp#L8-L35>)为 `LayoutLeft(10,20)` 设置 stride 15，为 `LayoutRight(10,20)` 设置 stride 25。
因此只保存 extent、随后按元素数乘积解释所有存储，已经漏掉了间隙和映射信息。
这支持 G03 的联合设计，不支持“某一种布局普遍更快”。

另一个容易被名字掩盖的动作是初始化。
[分配记录创建](<https://github.com/kokkos/kokkos/blob/dc826b0fad122b57fee60223e86154aecb8e60f4/core/src/View/Kokkos_ViewAlloc.hpp#L259-L270>)只在 `Initialize` 且分配非零时登记销毁 functor 并构造元素（KM03）。
[初始化执行路径](<https://github.com/kokkos/kokkos/blob/dc826b0fad122b57fee60223e86154aecb8e60f4/core/src/View/Kokkos_ViewAlloc.hpp#L109-L159>)区分 memset、逐元素构造及等待；默认执行实例的初始化带 fence，显式实例有所不同。
`WithoutInitializing` 在这里也跳过销毁 functor 的登记，涉及非平凡对象时需重新核对生命周期，不能只当成“省一次填零”。
对应 G02、G04：把初始化、等待和回收放入成本与副作用契约，再决定是否省略；本轮没有测这些成本。

## deep_copy 的完成语义属于具体重载与路径

[SpaceAccessibility 定义](<https://github.com/kokkos/kokkos/blob/dc826b0fad122b57fee60223e86154aecb8e60f4/core/src/Kokkos_Concepts.hpp#L366-L388>)计算的是执行空间与内存空间之间的类型关系（KM04）。
`accessible` 不等待生产者，也不使旧数据自动变新；`assignable` 又是另一关系。
只有明确了可达性，才有条件继续讨论在哪个实例上复制，以及何时能消费结果。

以下对照锁定非零秩 View→View 重载，不替代标量、rank-0 或其他接口的契约：

| 调用路径 | 公共实现的实际动作 | 对组合的影响 |
| --- | --- | --- |
| `deep_copy(dst, src)` | 字节路径及逐元素 fallback 都安排前后全局 fence | 不是只提交后立即返回的接口 |
| `deep_copy(exec, dst, src)`，指定实例可访问两端 | 把实例传给字节复制或逐元素复制，公共层没有末尾 fence | 消费与复用要满足相应实例的完成依赖 |
| 带实例，但逐元素复制须切换执行域 | 先等待指定实例，再在可达执行域复制并等待 | “带实例就绝不阻塞”不成立 |

这些分支分别见[无实例实现](<https://github.com/kokkos/kokkos/blob/dc826b0fad122b57fee60223e86154aecb8e60f4/core/src/Kokkos_CopyViews.hpp#L1313-L1339>)与[带实例实现](<https://github.com/kokkos/kokkos/blob/dc826b0fad122b57fee60223e86154aecb8e60f4/core/src/Kokkos_CopyViews.hpp#L2484-L2527>)（KM06、KM07）。
字节复制还要求元素、布局、连续性和 stride 满足条件；否则会尝试逐元素路径，或报告需要临时分配的失败。
在上述带实例的直接提交路径中，公共层没有末尾 fence，也不保证特定后端确实异步，更不保证发生计算与复制重叠。

别名也不是任意复制的许可。
[重叠处理](<https://github.com/kokkos/kokkos/blob/dc826b0fad122b57fee60223e86154aecb8e60f4/core/src/Kokkos_CopyViews.hpp#L1253-L1288>)区分相同连续 span 与连续部分重叠；后者报错（KM10）。
检测条件含双方连续，不能据此声称所有非连续交叠都被检测；同一 View 对象作两个参数还另有配置相关检查。
G01、G07 要保留这些失败条件和完成边界，而不是把所有复制都理解成 `memmove`。

## mirror 可能是别名，DualView 需要状态协议

[create_mirror_view](<https://github.com/kokkos/kokkos/blob/dc826b0fad122b57fee60223e86154aecb8e60f4/core/src/Kokkos_CopyViews.hpp#L3183-L3204>)按空间与类型条件返回源的浅构造，或创建独立 mirror（KM08）。
它既不总是分配，也不承诺复制源内容；需要独立快照时，要确认独立分配并完成复制。
[create_mirror_view_and_copy](<https://github.com/kokkos/kokkos/blob/dc826b0fad122b57fee60223e86154aecb8e60f4/core/src/Kokkos_CopyViews.hpp#L3282-L3306>)在同空间直接返回源；不给实例时先 fence，给实例时跳过该 fence；异空间才建立 mirror 并走相应复制重载（KM09）。
因此 `and_copy` 也不是“一定搬运一次”的证据。

DualView 解决的是表示之间的一致性协议，而不是自动截获每一次写入。
[modify_host / modify_device](<https://github.com/kokkos/kokkos/blob/dc826b0fad122b57fee60223e86154aecb8e60f4/containers/src/Kokkos_DualView.hpp#L781-L819>)更新 dirty 计数，双侧同时 dirty 时终止；sync 再根据标志选择复制和清零（KM11）。
浅复制和子视图还会共享修改标志，不能把它们当成各自独立的一致性状态。

这里尤其需要保留实现限定：
[sync 的分支](<https://github.com/kokkos/kokkos/blob/dc826b0fad122b57fee60223e86154aecb8e60f4/containers/src/Kokkos_DualView.hpp#L547-L580>)在相同 memory_space 的 sync_impl 中仍安排两个执行域的 fence，但 `impl_dualview_is_single_device` 分支直接返回，并留有 `FIXME_DUALVIEW_ASYNCHRONOUS_BACKENDS`（KM12）。
single-device 指 host/device 的 device_type 相同，不只是空间名相同。
[上游同步测试](<https://github.com/kokkos/kokkos/blob/dc826b0fad122b57fee60223e86154aecb8e60f4/containers/unit_tests/TestDualView.hpp#L485-L539>)也显式跳过 HPX。
本轮只读该测试，不把它写成所有配置已经通过，更不把 `sync` 一概描述为全局完成。

## 执行实例、结果载体与 Team 副作用

策略类型确定执行空间类别，[RangePolicy 构造](<https://github.com/kokkos/kokkos/blob/dc826b0fad122b57fee60223e86154aecb8e60f4/core/src/Kokkos_ExecPolicy.hpp#L153-L167>)仍保存运行时传入的实例和范围（KE01）。
这与静态选择并不矛盾：类型信息可以提前绑定，资源归属和数据规模继续动态确定；同类型实例也不等于天然独立队列。

结果载体本身会改变完成路径。
[parallel_reduce_needs_fence](<https://github.com/kokkos/kokkos/blob/dc826b0fad122b57fee60223e86154aecb8e60f4/core/src/Kokkos_Parallel_Reduce.hpp#L264-L304>)对 View 返回 false，对其他结果默认返回 true，reducer 可通过 `references_scalar()` 决定；需要时 fence 的是 policy 所持实例（KE04）。
所以 host scalar 与 rank-0 View 不是只换了一个存储容器；View 不触发这一层等待，也不证明后端一定异步。

Team 的另一个边界是副作用应执行几次。
[CUDA TeamThreadRange](<https://github.com/kokkos/kokkos/blob/dc826b0fad122b57fee60223e86154aecb8e60f4/core/src/Cuda/Kokkos_Cuda_Team.hpp#L463-L478>)按 `threadIdx.y` 分工，没有按 x lane 过滤（KE10）。
当 vector length 大于一时，未经 vector 语义组织的写入可能重复；Serial 的宽度一会掩盖这种错误。
这不是禁止 vector 协作，而是要求明确“每元素、每逻辑线程、每 team”各自的副作用重数，再选择 `ThreadVectorRange` 或合适作用域的 `single`。

[scratch 与 team_barrier](<https://github.com/kokkos/kokkos/blob/dc826b0fad122b57fee60223e86154aecb8e60f4/core/src/impl/Kokkos_HostThreadTeam.hpp#L422-L445>)区分 team 共享和 thread 切分，并提供 team rendezvous（KE11）。
嵌套循环结束不应被当成自动 team barrier；生产 scratch 后再由其他成员消费，需要匹配的集体依赖。
team barrier 也不完成其他 team、整个 league 或 host 的工作，scratch 更不是跨 kernel 的持久存储。

## 本轮真正运行了什么

原创[契约探针](<../examples/kokkos_contracts.cpp>)与上游测试源码阅读是两组证据。
主线使用 g++ 13.3、CMake 3.28.3、C++20、Release 构建 Kokkos Serial + OpenMP；每次探针运行都显式实例化 Serial 与 OpenMP。
CTest 在 OpenMP 线程数 1、4 的两项探针测试通过，既有 `owner_view` 测试也通过，共三项。测试同时固定环境与初始化参数，并核对 `concurrency()`；Serial 的实际 team size 为 1，4 线程 OpenMP 的实际 team size 为 2，不仅靠 `AUTO` 名称推断组内并行已经覆盖。

| 已运行的检查 | 能支持的范围 | 尚未由此证明 |
| --- | --- | --- |
| LayoutLeft/Right 转换、strided subview copy | 这组 HostSpace 数据的逻辑值保持 | 跨设备搬运、任意 accessor、布局性能 |
| host mirror alias 与独立分配后的快照 | 同空间别名及独立复制的区别 | 所有空间、const 组合、所有权失效边界 |
| scalar、rank-0 View 与空域 reduce | 本例整数求和、显式等待后的 View 结果、空和中性元 | View 结果的真实异步完成、浮点可复现性 |
| scan 最终阶段写入及原子计数 | 本例精确前缀值与每个索引的最终写入次数 | 所有后端的回调遍数与任意副作用 |
| TeamThreadRange + scratch + barrier + single | 核对实际 team 大小和每个 league 的单次结果写入计数；4 线程 OpenMP 显式 team size 2 | CUDA vector lane 重数及设备竞争 |

没有运行 CUDA、跨设备 copy 或真实异步时间线测试，也没有性能测量。
CUDA 的 Team 与实例完成相关结论来自执行 reviewer 的静态阅读，不是设备实测；HIP、SYCL、OpenACC、HPX、NextSilicon 等运行配置也未验收。
可继续用独立实例时间线、副作用原子计数、边界形状和后端测试反驳或收紧这些判断；当前结果不支持普遍加速比。

## 对通用规则的约束

这组案例补充的是 G03 的共享与表示契约、G04 的可发现副作用、G05 的绑定时机，以及 G07 的依赖和完成边界。
G11、G12 要求保留“读到实现”“读到测试”“原创探针已运行”“未覆盖后端”之间的区别。
它修正的是 View 必定无所有权、可达就已同步、带实例必定非阻塞、统一 API 就有统一完成语义这些过度简化。
迁移到别的算法或语言时，仍应先问谁持有数据、映射是否合适、谁完成哪项工作，再决定需要哪些函数、模块或描述符；不必重建 Kokkos 的对象体系。
