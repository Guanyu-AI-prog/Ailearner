"""云电脑推荐工具。"""

from agent.tools.base import BaseTool


class CloudComputerTool(BaseTool):
    def get_definition(self):
        return {
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
        }

    async def execute(self, budget: str, purpose: str, **kwargs) -> str:
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
