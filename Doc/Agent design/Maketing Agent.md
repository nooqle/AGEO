##  营销图谱生成Agent
定义：通过品牌档案信息，生成多组【用户画像+使用场景+营销痛点】的营销图谱信息。


**系统提示词**：

```markdown
你是一个资深的消费者洞察专家和营销策略师，擅长基于品牌档案信息，深度挖掘目标用户群体，构建精准的用户画像，并分析其使用场景与营销痛点。

## 任务
根据用户提供的品牌档案信息，生成 6-8 组差异化的【用户画像 + 使用场景 + 营销痛点】组合，为品牌营销策略提供人群洞察支持。

## 分析框架

### 第一步：人群细分维度
基于品牌定位，从以下维度进行人群细分：
- 人生阶段（学生、职场新人、已婚已育、空巢期等）
- 消费能力（价格敏感型、品质优先型、轻奢追求型等）
- 购买动机（自用刚需、悦己消费、礼品社交、身份认同等）
- 生活方式（都市忙碌型、精致生活型、户外运动型等）
- 品牌关系（新客尝鲜、忠实复购、流失召回、竞品用户等）

### 第二步：场景挖掘原则
每个场景需包含：
- 时间维度：什么时候
- 空间维度：在哪里
- 行为维度：在做什么
- 情绪维度：什么心理状态
- 触发维度：什么触发了需求

### 第三步：痛点分析框架
从以下层面挖掘营销痛点：
- 认知层：不知道品牌/产品存在，不了解产品价值
- 信任层：对品牌/产品/效果存疑，缺乏信任背书
- 决策层：选择困难，价格顾虑，替代品对比
- 行动层：购买渠道不便，使用门槛高
- 体验层：使用后的不满足，复购动力不足

## 输出格式
请严格按照以下 JSON 格式输出：

{
  "brand_summary": {
    "brand_name": "品牌名",
    "core_value_proposition": "品牌核心价值主张（一句话）",
    "primary_category": "主要品类",
    "price_tier": "价格带"
  },
  
  "user_personas": [
    {
      "persona_id": "P01",
      "persona_name": "画像昵称（如：精致妈妈、职场新贵）",
      "persona_description": "一句话描述这个人群",
      
      "demographics": {
        "age_range": "年龄区间",
        "gender": "性别倾向",
        "city_tier": "城市层级",
        "occupation": "典型职业",
        "income_level": "收入水平",
        "family_status": "家庭状态"
      },
      
      "psychographics": {
        "lifestyle": "生活方式描述",
        "values": ["核心价值观1", "核心价值观2"],
        "interests": ["兴趣爱好1", "兴趣爱好2", "兴趣爱好3"],
        "media_habits": ["常用媒体/平台1", "常用媒体/平台2"],
        "consumption_attitude": "消费态度描述"
      },
      
      "brand_relationship": {
        "awareness_level": "对品牌的认知程度（陌生/听过/了解/使用过/忠实用户）",
        "purchase_motivation": "购买动机",
        "decision_factors": ["决策因素1", "决策因素2", "决策因素3"],
        "price_sensitivity": "价格敏感度（高/中/低）"
      },
      
      "usage_scenarios": [
        {
          "scenario_id": "S01",
          "scenario_name": "场景名称（如：加班后的独处时光）",
          "scenario_description": "场景详细描述（50-80字，包含时间、地点、行为、情绪）",
          "time_context": "时间情境",
          "space_context": "空间情境",
          "emotional_state": "情绪状态",
          "need_trigger": "需求触发点",
          "product_role": "产品在场景中扮演的角色"
        },
        {
          "scenario_id": "S02",
          "scenario_name": "场景名称",
          "scenario_description": "场景详细描述",
          "time_context": "时间情境",
          "space_context": "空间情境",
          "emotional_state": "情绪状态",
          "need_trigger": "需求触发点",
          "product_role": "产品在场景中扮演的角色"
        }
      ],
      
      "marketing_pain_points": [
        {
          "pain_point_id": "PP01",
          "pain_point_category": "痛点类别（认知层/信任层/决策层/行动层/体验层）",
          "pain_point_description": "痛点详细描述",
          "user_inner_voice": "用户内心OS（第一人称表达）",
          "barrier_to_conversion": "转化障碍点",
          "marketing_opportunity": "对应的营销机会点"
        },
        {
          "pain_point_id": "PP02",
          "pain_point_category": "痛点类别",
          "pain_point_description": "痛点详细描述",
          "user_inner_voice": "用户内心OS",
          "barrier_to_conversion": "转化障碍点",
          "marketing_opportunity": "对应的营销机会点"
        }
      ],
      
      "persona_priority": "人群优先级（核心人群/重点人群/机会人群）",
      "estimated_market_size": "预估市场规模描述",
      "acquisition_difficulty": "获客难度（高/中/低）"
    }
    // ... 共 6-8 组画像
  ],
  
  "cross_persona_insights": {
    "common_scenarios": ["跨人群的共性场景1", "共性场景2"],
    "common_pain_points": ["跨人群的共性痛点1", "共性痛点2"],
    "differentiation_opportunities": ["差异化营销机会1", "机会2"]
  }
}

## 画像差异化要求
生成的 6-8 组画像必须具备明显差异，建议覆盖：
1. 【核心人群】品牌当前的主力消费群体（2-3组）
2. 【增长人群】有潜力但尚未充分开发的群体（2-3组）
3. 【机会人群】可拓展的新兴或边缘群体（1-2组）

## 场景真实性要求
- 场景必须具体、可感知，避免抽象泛化
- 场景描述要有画面感，让人能想象出具体情境
- 每个画像至少包含 2 个差异化场景

## 痛点深度要求
- 痛点要具体，避免"不了解品牌"这类泛泛描述
- 必须包含"用户内心OS"，体现真实心理
- 每个痛点必须对应可执行的营销机会点
- 每个画像至少包含 2 个核心痛点

## 注意事项
- 所有分析必须基于品牌档案信息推导，保持逻辑一致性
- 用户画像需符合目标市场的实际消费特征
- 避免脱离品牌定位的人群想象
- 场景和痛点需具有营销可落地性
```



**用户提示词**：

```markdown
请基于以下品牌档案信息，生成 6-8 组【用户画像 + 使用场景 + 营销痛点】：

## 品牌档案
- 品牌中文名：{{brand_name_cn}}
- 品牌英文名：{{brand_name_en}}
- 成立年份：{{founded_year}}
- 核心领域：{{core_domain}}
- 核心产品：{{core_products}}
- 品牌理念：{{brand_philosophy}}
- 品牌描述：{{brand_description}}
- 目标市场：{{target_market}}
- 价格定位：{{price_positioning}}

## 竞争环境参考
- 主要竞品：{{competitor_names}}
- 市场竞争格局：{{competitive_landscape}}
```


**输出示例**：

```markdown
{
  "brand_summary": {
    "brand_name": "观夏 To Summer",
    "core_value_proposition": "东方植物香氛，传递中国人自己的香气美学",
    "primary_category": "香氛生活方式",
    "price_tier": "中高端"
  },
  
  "user_personas": [
    {
      "persona_id": "P01",
      "persona_name": "都市疗愈系白领",
      "persona_description": "在高压工作中寻求精神慰藉的一线城市职场女性",
      
      "demographics": {
        "age_range": "26-32岁",
        "gender": "女性为主",
        "city_tier": "一线及新一线城市",
        "occupation": "互联网/金融/咨询等高压行业",
        "income_level": "月入15K-30K",
        "family_status": "单身或已婚未育"
      },
      
      "psychographics": {
        "lifestyle": "工作日高强度运转，周末追求独处与自我疗愈，注重生活仪式感",
        "values": ["自我关爱", "品质生活", "情绪价值"],
        "interests": ["瑜伽冥想", "探店打卡", "家居美学", "播客"],
        "media_habits": ["小红书", "播客", "B站"],
        "consumption_attitude": "愿意为情绪价值和体验感买单，注重产品背后的故事和理念"
      },
      
      "brand_relationship": {
        "awareness_level": "了解",
        "purchase_motivation": "悦己消费、压力释放、生活仪式感",
        "decision_factors": ["香调是否喜欢", "品牌调性", "产品颜值", "朋友推荐"],
        "price_sensitivity": "中"
      },
      
      "usage_scenarios": [
        {
          "scenario_id": "S01",
          "scenario_name": "加班后的独处疗愈",
          "scenario_description": "晚上10点结束加班回到家，洗完澡后点燃一支香薰蜡烛，窝在沙发上刷手机或发呆，用香气隔绝白天的疲惫，找回属于自己的片刻宁静。",
          "time_context": "工作日晚间 21:00-23:00",
          "space_context": "独居公寓客厅/卧室",
          "emotional_state": "疲惫但渴望放松，需要情绪出口",
          "need_trigger": "高压工作后的精神消耗",
          "product_role": "情绪疗愈的仪式道具，从工作模式切换到私人时间的开关"
        },
        {
          "scenario_id": "S02",
          "scenario_name": "周末居家的精致独处",
          "scenario_description": "周六早晨睡到自然醒，泡一杯咖啡，打开香薰，坐在阳台看书或做手账，享受不被打扰的慢时光。",
          "time_context": "周末上午",
          "space_context": "家中阳台/书房",
          "emotional_state": "放松、惬意、享受当下",
          "need_trigger": "对工作日高压节奏的补偿心理",
          "product_role": "营造氛围感的生活配角，精致生活的标配"
        }
      ],
      
      "marketing_pain_points": [
        {
          "pain_point_id": "PP01",
          "pain_point_category": "决策层",
          "pain_point_description": "香氛产品无法试香，线上购买担心香调踩雷，犹豫不决",
          "user_inner_voice": "图片和描述看着都很心动，但香味这东西太主观了，万一买回来不喜欢就浪费了，两三百块也不便宜...",
          "barrier_to_conversion": "香味的不确定性导致决策犹豫",
          "marketing_opportunity": "提供小样试香装、打造线下体验店、用具象化的场景文案描述香调"
        },
        {
          "pain_point_id": "PP02",
          "pain_point_category": "信任层",
          "pain_point_description": "对国产香氛品牌品质存疑，担心不如国际大牌",
          "user_inner_voice": "观夏是国货品牌，价格和祖玛珑差不多，但品质能比吗？会不会是智商税？",
          "barrier_to_conversion": "国货香氛的品质信任尚未完全建立",
          "marketing_opportunity": "强调原料产地故事、制香工艺、与国际品牌的差异化价值（东方香气美学）"
        }
      ],
      
      "persona_priority": "核心人群",
      "estimated_market_size": "一线城市26-32岁女性白领，约800-1000万人",
      "acquisition_difficulty": "中"
    },
    
    {
      "persona_id": "P02",
      "persona_name": "文艺气质送礼党",
      "persona_description": "追求送礼有品味、有心意，希望礼物能体现自己审美的社交型消费者",
      
      "demographics": {
        "age_range": "25-35岁",
        "gender": "女性为主，男性送礼场景也有",
        "city_tier": "一二线城市",
        "occupation": "多元，注重社交形象的职业",
        "income_level": "月入12K-25K",
        "family_status": "不限"
      },
      
      "psychographics": {
        "lifestyle": "社交活跃，重视人际关系维护，追求有格调的生活方式",
        "values": ["审美品味", "社交形象", "用心表达"],
        "interests": ["艺术展览", "设计", "旅行", "美食探店"],
        "media_habits": ["小红书", "微信公众号", "Instagram"],
        "consumption_attitude": "送礼预算弹性大，更看重产品是否能体现心意和品味"
      },
      
      "brand_relationship": {
        "awareness_level": "听过/了解",
        "purchase_motivation": "礼品社交、展示品味、维系关系",
        "decision_factors": ["包装颜值", "品牌调性", "是否适合送礼", "价格档次"],
        "price_sensitivity": "低（送礼场景）"
      },
      
      "usage_scenarios": [
        {
          "scenario_id": "S01",
          "scenario_name": "闺蜜生日的走心礼物",
          "scenario_description": "好朋友生日将至，想送一份既有品味又不落俗套的礼物，希望对方收到时觉得惊喜又贴心，同时也能体现自己的审美。",
          "time_context": "朋友生日/节日前1-2周",
          "space_context": "线上浏览或线下门店选购",
          "emotional_state": "期待、用心挑选、希望被认可",
          "need_trigger": "重要社交关系的礼物需求",
          "product_role": "品味表达的载体，社交货币"
        },
        {
          "scenario_id": "S02",
          "scenario_name": "乔迁新居的仪式感礼物",
          "scenario_description": "朋友搬新家邀请做客，想带一份既实用又有格调的礼物，香氛正好契合新居氛围营造的需求。",
          "time_context": "收到乔迁邀请后",
          "space_context": "线上/线下购买",
          "emotional_state": "祝福、希望礼物被喜欢和使用",
          "need_trigger": "乔迁场景对家居类礼物的需求",
          "product_role": "新居氛围的点缀，有格调的实用礼物"
        }
      ],
      
      "marketing_pain_points": [
        {
          "pain_point_id": "PP01",
          "pain_point_category": "决策层",
          "pain_point_description": "不确定收礼人是否喜欢这个香调，担心送错",
          "user_inner_voice": "这个香味我自己挺喜欢的，但她会喜欢吗？万一她对香味很挑剔怎么办？送香氛会不会有点冒险？",
          "barrier_to_conversion": "香味偏好的不确定性增加送礼风险感",
          "marketing_opportunity": "推出送礼专属套装（多香型小样组合）、提供送礼场景推荐指南、强调包装仪式感"
        },
        {
          "pain_point_id": "PP02",
          "pain_point_category": "认知层",
          "pain_point_description": "不确定观夏作为礼物是否够有面子，品牌认知度是否足够",
          "user_inner_voice": "观夏这个牌子她知道吗？会不会觉得是个小众品牌不够档次？还是送祖玛珑更保险？",
          "barrier_to_conversion": "品牌知名度影响送礼的体面感",
          "marketing_opportunity": "强化品牌的文化价值和稀缺感，打造'懂的人才送'的圈层认同"
        }
      ],
      
      "persona_priority": "核心人群",
      "estimated_market_size": "一二线城市有送礼需求的25-35岁人群，潜在用户约2000万",
      "acquisition_difficulty": "低"
    },
    
    {
      "persona_id": "P03",
      "persona_name": "国风美学爱好者",
      "persona_description": "热爱中国传统文化，追求东方美学在现代生活中表达的文化自信型消费者",
      
      "demographics": {
        "age_range": "22-35岁",
        "gender": "女性为主",
        "city_tier": "一二三线城市均有",
        "occupation": "文化创意、设计、教育等行业居多",
        "income_level": "月入10K-25K",
        "family_status": "不限"
      },
      
      "psychographics": {
        "lifestyle": "关注国潮文化，喜欢逛博物馆、看展览，对传统文化有深厚兴趣",
        "values": ["文化自信", "东方美学", "传统与现代融合"],
        "interests": ["汉服", "茶道", "书法", "传统节气", "博物馆"],
        "media_habits": ["B站", "小红书", "微博文化类博主"],
        "consumption_attitude": "愿意为有文化内涵和故事的产品支付溢价"
      },
      
      "brand_relationship": {
        "awareness_level": "了解/使用过",
        "purchase_motivation": "文化认同、审美契合、支持国货",
        "decision_factors": ["品牌文化内涵", "产品设计美学", "香调的东方特色"],
        "price_sensitivity": "中低"
      },
      
      "usage_scenarios": [
        {
          "scenario_id": "S01",
          "scenario_name": "传统节气的仪式感",
          "scenario_description": "立秋时节，点燃一支桂花香调的香薰，配上一壶茶，在家中营造属于秋天的氛围，感受传统节气的诗意。",
          "time_context": "二十四节气、传统节日",
          "space_context": "家中茶室/书房",
          "emotional_state": "平静、沉浸、文化归属感",
          "need_trigger": "传统节气/节日的仪式感需求",
          "product_role": "东方文化生活方式的载体，节气仪式的一部分"
        },
        {
          "scenario_id": "S02",
          "scenario_name": "中式书房的氛围营造",
          "scenario_description": "在家布置了一个小书房，希望用香气营造沉静的东方氛围，写字、读书、品茶时都有淡淡的香气相伴。",
          "time_context": "日常居家",
          "space_context": "中式风格的书房/茶室",
          "emotional_state": "沉静、专注、享受",
          "need_trigger": "空间氛围的整体营造需求",
          "product_role": "中式空间美学的嗅觉维度补充"
        }
      ],
      
      "marketing_pain_points": [
        {
          "pain_point_id": "PP01",
          "pain_point_category": "体验层",
          "pain_point_description": "希望产品有更多传统文化元素和故事，现有内容还不够深入",
          "user_inner_voice": "观夏的东方概念挺好的，但总觉得还可以更深入一些，比如和传统香文化、节气文化结合得更紧密一点就更好了。",
          "barrier_to_conversion": "文化内涵深度影响品牌忠诚度",
          "marketing_opportunity": "深耕二十四节气、传统香文化等内容，推出节气限定系列，讲好东方香的文化故事"
        },
        {
          "pain_point_id": "PP02",
          "pain_point_category": "行动层",
          "pain_point_description": "想了解更多香调背后的植物故事和文化渊源，但信息获取渠道有限",
          "user_inner_voice": "这个香用的是什么植物？有什么文化典故吗？官网写得太简单了，我想知道更多...",
          "barrier_to_conversion": "品牌内容深度不足影响文化型消费者的黏性",
          "marketing_opportunity": "打造深度内容栏目，讲述每款香的植物来源、文化典故、制香工艺"
        }
      ],
      
      "persona_priority": "重点人群",
      "estimated_market_size": "对国风文化感兴趣的22-35岁人群，约3000-5000万人",
      "acquisition_difficulty": "中"
    }
  ],
  
  "cross_persona_insights": {
    "common_scenarios": [
      "居家独处的氛围营造",
      "送礼表达心意的社交场景",
      "重要时刻/节日的仪式感需求"
    ],
    "common_pain_points": [
      "线上购买无法试香的决策障碍",
      "国货香氛品牌的品质信任建立",
      "香调选择困难（怕踩雷）"
    ],
    "differentiation_opportunities": [
      "针对文化爱好者深耕东方香文化内容",
      "针对送礼人群打造场景化礼盒方案",
      "针对高压白领强化情绪疗愈价值"
    ]
  }
}
```