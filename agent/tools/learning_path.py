"""学习路径生成工具。"""

from agent.tools.base import BaseTool


class LearningPathTool(BaseTool):
    def get_definition(self):
        return {
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

    async def execute(self, direction: str, current_level: str, target_level: str, weekly_hours: int = 5, **kwargs) -> str:
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
        path_text = f"## {direction} 学习路径（目标：{target_level}）\n\n"
        path_text += f"预计需要约 {weeks_estimate} 周（按每周 {weekly_hours} 小时计算）\n\n"
        for i, step in enumerate(steps, 1):
            path_text += f"**第{i}步**：{step}\n"
        return path_text
