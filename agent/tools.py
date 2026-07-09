import asyncio
import json
from typing import Any

import httpx


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "搜索网络获取最新信息，适合查找最新课程、工具、资讯等",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_cloud_computer",
            "description": "推荐云电脑方案，当用户没有自己的电脑时需要这个功能",
            "parameters": {
                "type": "object",
                "properties": {
                    "budget": {
                        "type": "string",
                        "description": "预算范围：free/low/mid/high",
                        "enum": ["free", "low", "mid", "high"]
                    },
                    "purpose": {
                        "type": "string",
                        "description": "用途：chat/run_code/training"
                    }
                },
                "required": ["budget", "purpose"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_learning_path",
            "description": "根据用户水平和目标生成个性化学习路径",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "description": "学习方向"
                    },
                    "current_level": {
                        "type": "string",
                        "description": "当前水平：beginner/intermediate/advanced"
                    },
                    "target_level": {
                        "type": "string",
                        "description": "目标水平：L1/L2/L3/L4"
                    },
                    "weekly_hours": {
                        "type": "integer",
                        "description": "每周可投入小时数"
                    }
                },
                "required": ["direction", "current_level", "target_level"]
            }
        }
    }
]


async def search_web(query: str) -> str:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(
                "https://cn.bing.com/search",
                params={"q": query, "mkt": "zh-CN"},
                headers=headers,
            )
            resp.raise_for_status()
            text = resp.text

        results = []
        import re
        blocks = re.findall(r'<li class="b_algo"[^>]*>.*?</li>', text, re.DOTALL)
        for block in blocks:
            h2 = re.search(r'<h2[^>]*><a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a></h2>', block, re.DOTALL)
            if not h2:
                continue
            url = h2.group(1)
            title = re.sub(r'<[^>]+>', '', h2.group(2)).strip()
            p = re.search(r'<p[^>]*class="b_lineclamp[^"]*"[^>]*>(.*?)</p>', block, re.DOTALL)
            snippet = re.sub(r'<[^>]+>', '', p.group(1)).strip() if p else ""
            results.append(f"**{title}**\n{url}\n{snippet}")

        if not results:
            return f"未找到关于「{query}」的相关信息，建议用户自行搜索。"

        return "\n\n---\n\n".join(results[:5])
    except Exception as e:
        return f"搜索失败：{str(e)}"


def recommend_cloud_computer(budget: str, purpose: str) -> str:
    recommendations = {
        "free": {
            "chat": "推荐使用 Poe.com / Claude.ai / ChatGPT 免费版，手机就能用",
            "run_code": "推荐使用 Google Colab（免费 GPU）+ Kaggle Notebooks",
            "training": "推荐使用 Google Colab（免费 T4 GPU）或 Kaggle（免费 P100）"
        },
        "low": {
            "chat": "推荐开通 ChatGPT Plus（$20/月）或 Claude Pro",
            "run_code": "阿里云 PAI / 腾讯云 TI-ONE，按量付费，每小时几块钱",
            "training": "AutoDL / 恒源云，按小时租 GPU，几块钱一小时"
        },
        "mid": {
            "chat": "ChatGPT Team 或企业版",
            "run_code": "买一台带 4060 显卡的笔记本（约 6000-8000 元）",
            "training": "买一台带 4090 的台式机（约 2-3 万），或租用专业 GPU 服务器"
        },
        "high": {
            "chat": "部署本地开源模型（需要 GPU 服务器）",
            "run_code": "采购专业工作站或多卡 GPU 服务器",
            "training": "采购 A100/H100 集群或使用 AWS/GCP 云服务"
        }
    }
    result = recommendations.get(budget, {}).get(purpose, "自定义方案")
    return f"根据预算「{budget}」和用途「{purpose}」，推荐方案：\n{result}"


def generate_learning_path(direction: str, current_level: str, target_level: str, weekly_hours: int = 5) -> str:
    PATH_TEMPLATES = {
        "AI应用": {
            "L1": ["了解主流 AI 工具（ChatGPT/Claude/Midjourney）",
                    "学习提示词工程基础",
                    "用 AI 完成实际工作任务",
                    "分享你的使用心得"],
            "L2": ["掌握提示词高级技巧（思维链/角色扮演）",
                    "学习使用 AI Agent 工具（Dify/Coze）",
                    "搭建自己的 AI 工作流",
                    "了解 RAG 基本概念"],
            "L3": ["学习 Python 基础 + AI API 调用",
                    "搭建自己的 AI Agent（接入微信/飞书）",
                    "学习微调和 RAG 实践",
                    "参与开源 AI 项目"],
            "L4": ["深入学习 Transformer/LLM 原理",
                    "掌握 AI 产品设计和评估方法论",
                    "能够独立设计和交付 AI 解决方案",
                    "关注前沿论文和开源社区"]
        },
        "机器学习": {
            "L1": ["了解 ML 基本概念（监督/无监督/强化学习）",
                    "用 Google Teachable Machine 体验 ML",
                    "理解过拟合、欠拟合等核心概念",
                    "看清 ML 能解决什么问题、不能解决什么"],
            "L2": ["学习 Python + NumPy/Pandas 基础",
                    "用 Scikit-learn 跑第一个 ML 模型",
                    "理解训练集/验证集/测试集",
                    "参加 Kaggle 入门比赛"],
            "L3": ["深入学习线性代数/概率论/微积分",
                    "从零实现简单神经网络",
                    "掌握 PyTorch/TensorFlow 基础",
                    "复现经典论文的模型"],
            "L4": ["深入研究 SOTA 论文",
                    "掌握分布式训练/模型优化",
                    "有自己的研究或工程产出",
                    "参与顶会投稿/开源贡献"]
        },
        "深度学习": {
            "L1": ["了解神经网络基本概念（神经元/层/激活函数）",
                    "理解 CNN/RNN/Transformer 的区别",
                    "用 Hugging Face 体验预训练模型",
                    "了解 GPU 为什么重要"],
            "L2": ["学习 PyTorch 基础",
                    "用预训练模型做迁移学习",
                    "理解损失函数/优化器/学习率",
                    "跑通一个完整的训练流程"],
            "L3": ["深入理解 Transformer 架构",
                    "学习分布式训练基础",
                    "实现模型微调（LoRA/QLoRA）",
                    "阅读并复现顶会论文"],
            "L4": ["研究前沿方向（多模态/具身智能等）",
                    "掌握模型压缩/量化/部署",
                    "有能力改进现有架构",
                    "产出高水平论文或开源项目"]
        },
        "AI产品": {
            "L1": ["了解 AI 能做什么、不能做什么",
                    "体验 50+ 主流 AI 产品",
                    "培养 AI 产品 sense",
                    "学习用 AI 提效产品工作流"],
            "L2": ["学习 AI 产品设计方法论",
                    "掌握 Prompt Engineering",
                    "了解 RAG/Agent 等技术的产品形态",
                    "设计一个 AI 产品原型"],
            "L3": ["学习 AI 技术基础（能和技术团队沟通）",
                    "掌握 AI 产品评估和测试方法",
                    "了解数据标注/模型评估流程",
                    "推动 AI 产品从 0 到 1"],
            "L4": ["理解 AI 商业模式和成本结构",
                    "掌握 AI 产品合规/伦理/安全",
                    "能够制定 AI 产品战略",
                    "领导 AI 产品团队"]
        }
    }
    paths = PATH_TEMPLATES.get(direction, PATH_TEMPLATES["AI应用"])
    level = target_level
    if level not in paths:
        level = "L2"
    steps = paths[level]
    weeks_estimate = len(steps) * 2 * (40 // max(weekly_hours, 1))
    path_text = f"?? {direction} 学习路径（目标：{target_level}）\n\n"
    path_text += f"预计需要约 {weeks_estimate} 周（按每周 {weekly_hours} 小时计算）\n\n"
    for i, step in enumerate(steps, 1):
        path_text += f"**第{i}步**：{step}\n"
    return path_text


TOOL_FUNCTIONS = {
    "search_web": search_web,
    "recommend_cloud_computer": recommend_cloud_computer,
    "generate_learning_path": generate_learning_path,
}


async def execute_tool(name: str, arguments: str) -> str:
    if name not in TOOL_FUNCTIONS:
        return f"未知工具：{name}"
    func = TOOL_FUNCTIONS[name]
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
        if name == "search_web":
            return await func(**args)
        return func(**args)
    except Exception as e:
        return f"工具执行出错：{str(e)}"
