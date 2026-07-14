# -*- coding: utf-8 -*-
"""
tools — Casting-Workflow 工具包

包含熔铸管道、质量控制、反朱雀检测、叙事分析等核心模块。
"""
import logging

__all__ = [
    "advisory_reporter",
    "anti_ai_reporter",
    "anti_pattern",
    "audit",
    "bloom_guard",
    "browser_ctl",
    "build_quality_baseline",
    "check_padding",
    "clean_commas",
    "cover_gen",
    "deslop_reporter",
    "dna_distiller",
    "fusion",
    "human_feature_injector",
    "human_profile",
    "humanity_scorer",
    "inject_punctuation",
    "local_discriminator",
    "methodology_weaver",
    "narrative_features",
    "quality_matrix",
    "rag_retriever",
    "story_analyze",
    "story_capture",
    "workflow_hooks",
]

# 包级 logger（供内部模块共用，避免各模块重复配置）
_package_logger = logging.getLogger(__name__)
