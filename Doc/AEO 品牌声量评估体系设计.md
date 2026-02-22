# **指标说明**

### ---

**一、 核心指标：品牌加权声量指数 (Brand Weighted SOV)**

你提到的“提及次数+正向情感”是基础，但在大模型场景下，\*\*“回答的顺位（Rank）”\*\*同样致命重要。如果品牌被提及，但排在竞品之后，或者只是作为陪衬，声量价值会打折。

因此，建议将该指标升级为 **Brand Weighted Visibility Score (BWVS)**。

#### **1\. 定义**

综合衡量品牌在目标问题集中的**出现频率**、**情感倾向**以及**展示顺位**的复合指标。

#### **2\. 计算公式 (LaTeX)**

$$BWVS \= \\sum\_{i=1}^{N} (M\_i \\times S\_i \\times P\_i)$$  
其中：

* $N$: 总问题数量。  
* $M\_i$ (**Mention**): 提及状态。提及=1，未提及=0。  
* $S\_i$ (**Sentiment**): 情感系数。建议设定：正向=1.2，中性=1.0，负向=-1.0（直接扣分）。  
* $P\_i$ (**Position**): 顺位衰减系数。模型回答通常分点作答，越靠前越重要。建议公式：$1 / \\log\_2(Rank \+ 1)$ 或简单的 $1/Rank$。如果未分点，则设为 1。

#### **3\. 开发逻辑**

* **输入**: LLM 回答文本。  
* **NLP 任务**:  
  1. NER（实体识别）提取品牌名。  
  2. SA（情感分析）判断该段落情感。  
  3. List Extraction（列表提取）判断品牌出现的行号/段落位次。

### ---

**二、 详细指标拆解表 (可供开发参考)**

以下表格将你要求的其余 5 个指标进行了工程化定义：

| 指标名称 | 英文标识 | 定义描述 | 计算逻辑 / 伪代码思路 | 业务价值 |
| :---- | :---- | :---- | :---- | :---- |
| **1\. 提及率** | Mention Rate | 品牌在选定问题集中被 AI 提及的概率（不分情感与排名）。 |  $$\\frac{\\text{含品牌关键词的回答数}}{\\text{总问题数}} \\times 100\\%$$ | 衡量基础曝光广度（Top of Mind）。 |
| **2\. 答案正确率** | Accuracy Score | AI 回答中关于品牌的事实性描述（价格、参数、Slogan）与品牌“事实库”的匹配程度。 | **需预设 \[Ground Truth\] ，用户录入**。 1\. 提取回答中的 Claim（如“价格是500元”）。 2\. 与预设库比对。 $$\\frac{\\text{符合事实的 Claim 数}}{\\text{总提取 Claim 数}}$$ | 监控“AI 幻觉”风险，防止错误信息误导用户。 |
| **3\. 官网引用占比** | Official Domain Share | 大模型给出的“参考链接/引用源”中，直接指向品牌官网（如 apple.com）的比例。 | **输入**: 品牌主域名列表。 $$\\frac{\\text{引用中含主域名的数量}}{\\text{该回答总引用链接数}}$$ | 衡量 SEO 资产向 AEO 的转化效率，直接导流能力。 |
| **4\. 官方矩阵引用占比** | Authority Matrix Share | 引用源中包含官网、官方社媒、官方新闻稿、白名单合作媒体的比例。 | **输入**: 域名白名单 (Domain Whitelist)。 逻辑：遍历所有 citation URL，匹配 Whitelist。 $$\\frac{\\text{白名单引用数}}{\\text{总引用链接数}}$$ | 衡量品牌在大模型眼中的“权威信源”覆盖广度。 |
| **5\. 引用来源分布** | Citation Distribution | 引用链接的域名属性分类统计（媒体、UGC、竞品、无关）。 | **输入**: 域名分类库 (Map\<Domain, Category\>)。 输出：JSON 对象，如 {"Media": 40%, "UGC": 30%, "Official": 20%}。 | 诊断内容短板（如：缺知乎讨论？还是缺权威报道？）。 |

### ---

**三、 系统逻辑架构图**

为了让你的技术团队更清晰地理解数据流向，以下是该评估系统的架构图：

代码段

graph TD  
    subgraph Input\_Layer \[输入层\]  
        Q\[Prompt/问题库\] \--\> Crawler\[跨平台抓取引擎\]  
        Platform\[平台: DeepSeek/Kimi/GPT\] \--\> Crawler  
        FactBase\[品牌事实库 (Ground Truth)\] \--\> Validator  
        DomainList\[官方域名/白名单\] \--\> LinkParser  
    end

    subgraph Processing\_Layer \[处理层\]  
        Crawler \--\>|Raw Answer HTML/Markdown| NLP\_Engine\[NLP 分析引擎\]  
          
        NLP\_Engine \--\>|NER: 提取品牌| Metric\_Mention\[计算: 提及率\]  
        NLP\_Engine \--\>|Sentiment: 情感分析| Metric\_SOV\[计算: 加权声量\]  
        NLP\_Engine \--\>|Ranking: 顺位识别| Metric\_SOV  
        NLP\_Engine \--\>|Claim Extraction: 事实提取| Validator\[校验: 正确率\]  
          
        Crawler \--\>|Citations: 提取引用链接| LinkParser\[链接解析器\]  
        LinkParser \--\>|Match Domain| Metric\_Official\[计算: 官网/官方占比\]  
        LinkParser \--\>|Classify Domain| Metric\_Dist\[计算: 来源分布\]  
    end

    subgraph Data\_Layer \[数据沉淀\]  
        Metric\_Mention & Metric\_SOV & Validator & Metric\_Official & Metric\_Dist \--\> DB\[(AEO 指标数据库)\]  
    end

    subgraph Output\_Layer \[应用层\]  
        DB \--\> Dashboard\[可视化仪表盘\]  
        Dashboard \--\> GapAnalysis\[差距分析 \-\> 生成内容稿\]  
    end

### **四、 关键指标的技术实现难点与对策**

在开发这套模式时，请注意以下三个“坑”：

1. **正确率（Accuracy）的判定难度**：  
   * *问题*：机器很难判断语义上的“正确”。例如“性价比高”是主观的。  
   * *对策*：将正确率考核**仅限于“硬指标”**（Hard Facts），如：价格、发布时间、核心功能点。主观评价归类到“情感分析”中，不要混淆。  
2. **引用来源的清洗（URL Cleaning）**：  
   * *问题*：大模型给出的引用链接经常带有复杂的参数（UTM、Session ID）或者是重定向链接。  
   * *对策*：在计算占比前，必须有一个 URL Normalization 步骤，提取 Root Domain（根域名）进行比对。  
3. **情感分析的语境依赖**：  
   * *问题*：在对比类问题中，“A比B便宜”对A是正向，对B可能也是正向（如果B主打高端）。  
   * *对策*：使用 LLM 本身进行二次评估（LLM-as-a-Judge）。即：把抓取到的答案投喂给一个通用大模型，Prompt 为：“在这段文字中，针对 \[品牌A\] 的评价是正向、中性还是负向？请输出 JSON。”

