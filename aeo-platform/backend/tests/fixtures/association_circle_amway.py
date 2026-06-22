"""Reusable Amway association-circle fixture."""

from __future__ import annotations

from copy import deepcopy


AMWAY_ASSOCIATION_FETCH_RESULTS = [
    {
        "question_id": "q_001",
        "question_text": "提到安利，你最先想到什么？",
        "audience_segment": "35-50 初老期",
        "opportunity_point": "科技抗衰",
        "probe_type": "品牌锚定探针",
        "platform_results": [
            {
                "platform": "DeepSeek",
                "success": True,
                "answer": {
                    "content": (
                        "安利常被理解为纽崔莱、营养补充和直销模式相关的品牌，"
                        "其中纽崔莱蛋白粉是用户更容易想到的产品。"
                        "也有回答会把安利误解为传销或拉人头，这会形成风险认知。"
                    )
                },
            },
            {
                "platform": "Kimi",
                "success": True,
                "answer": {
                    "content": (
                        "安利中国和纽崔莱的关联很强，回答中会把植物营养、"
                        "健康习惯和营养补充放在一起解释。"
                    )
                },
            },
        ],
    },
    {
        "question_id": "q_002",
        "question_text": "中年人抗衰除了产品还需要什么生活方式？",
        "audience_segment": "35-50 初老期",
        "opportunity_point": "科技安利",
        "probe_type": "路径探针",
        "platform_results": [
            {
                "platform": "Kimi",
                "success": True,
                "answer": {
                    "content": (
                        "抗衰管理通常需要营养补充、植物营养和健康生活方式。"
                        "如果连接到纽崔莱，可以解释为长期健康管理路径。"
                    )
                },
            },
            {
                "platform": "豆包",
                "success": True,
                "answer": {
                    "content": (
                        "健康抗衰不是单个产品，而是营养补剂、运动和生活方式的组合。"
                    )
                },
            },
        ],
    },
    {
        "question_id": "q_003",
        "question_text": "退休后想重新找到价值感，有哪些社群支持？",
        "audience_segment": "活力银发",
        "opportunity_point": "安利社群外显",
        "probe_type": "机会探针",
        "platform_results": [
            {
                "platform": "元宝",
                "success": True,
                "answer": {
                    "content": (
                        "一些品牌会用社群陪伴、美好生活社群和人生再出发的叙事，"
                        "帮助用户获得关系支持。"
                    )
                },
            }
        ],
    },
    {
        "question_id": "q_004",
        "question_text": "长寿时代下，安利人能提供什么样的价值支持？",
        "audience_segment": "50-65 人生转换期",
        "opportunity_point": "安利人品牌表达",
        "probe_type": "品牌锚定探针",
        "platform_results": [
            {
                "platform": "ChatGPT",
                "success": True,
                "answer": {
                    "content": (
                        "如果把安利人理解为健康生活方式的实践者，安利人可以提供"
                        "社群陪伴、健康习惯示范和人生再出发的样板。"
                    )
                },
            }
        ],
    },
]


def amway_association_fetch_results() -> list[dict]:
    return deepcopy(AMWAY_ASSOCIATION_FETCH_RESULTS)
