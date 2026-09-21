# -*- coding: utf-8 -*-
"""
QubitClient Service - LLM/VLM 图像分析服务

集成 QubitClient 的量子实验图像分析能力：
- Q1: describe_plot - 描述图表
- Q2: classify_outcome - 分类实验结果
- Q3: scientific_reasoning - 科学推理
- Q4: assess_fit - 评估拟合
- Q5: extract_params - 提取参数
- Q6: evaluate_status - 评估状态
"""

from .server import QubitClientService

__all__ = ["QubitClientService"]
