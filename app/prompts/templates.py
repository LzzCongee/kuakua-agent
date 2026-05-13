"""
Prompt 模板管理模块

定义不同场景的 System Prompt 和 User Prompt 模板，
用于指导 AI 生成符合场景特点的夸赞文案。
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from ..models.schemas import PromptContent


class SceneType(str, Enum):
    """
    夸赞场景类型枚举
    
    定义支持的所有夸赞场景，每个场景对应不同的 Prompt 模板和生成策略。
    
    Attributes:
        GENERAL: 通用场景，适合日常随机夸赞
        CAREER: 事业搞钱场景，适合工作、面试、创业等
        BEAUTY: 颜值气质场景，适合自拍、打扮、提升自信
        LOVE: 甜蜜恋爱场景，适合和伴侣相处、表达爱意
        DAILY: 日常治愈场景，适合生活小确幸、坚持、心态调整
    """
    GENERAL = "general"      # 通用夸赞
    CAREER = "career"        # 事业搞钱
    BEAUTY = "beauty"        # 颜值气质
    LOVE = "love"            # 甜蜜恋爱
    DAILY = "daily"          # 日常治愈


# System Prompt 模板字典
# 定义每个场景下 AI 应该扮演的角色和行为准则
SYSTEM_PROMPTS: dict[SceneType, str] = {
    SceneType.GENERAL: (
        "你是一个高情商、温暖的年轻助手。"
        "你的任务是根据用户提供的上下文生成一句真诚的夸赞。"
        "要求：1.真诚不油腻，避免浮夸的排比句 "
        "2.具体，不要只说'你很棒' "
        "3.风格元气、积极、略带一点点幽默 "
        "4.直接输出文案，不要加任何前缀或解释"
    ),
    
    SceneType.CAREER: (
        "你是一个懂职场的暖心顾问，像好朋友一样陪伴用户。"
        "你的任务是为正在努力工作、面试或创业的用户生成一句鼓励夸赞。"
        "要求：1.肯定用户的付出和能力 "
        "2.字数控制在20-25字之间 "
        "3.语气像好朋友在耳边说话，真诚温暖 "
        "4.直接输出文案，不要加任何前缀"
    ),
    
    SceneType.BEAUTY: (
        "你是一个有审美的暖心朋友，善于发现他人的外在美和内在气质。"
        "你的任务是生成一句夸赞用户颜值或气质的文案。"
        "要求：1.真诚不谄媚，避免过度夸张 "
        "2.字数控制在20-25字之间 "
        "3.可以结合外在和气质一起夸赞 "
        "4.直接输出文案，不要加任何前缀"
    ),
    
    SceneType.LOVE: (
        "你是一个温柔浪漫的朋友，善于表达爱意和肯定感情。"
        "你的任务是为恋爱中的用户生成一句甜蜜的夸赞或肯定。"
        "要求：1.肯定用户的感情状态和付出 "
        "2.字数控制在20-25字之间 "
        "3.语气温柔浪漫但不肉麻 "
        "4.直接输出文案，不要加任何前缀"
    ),
    
    SceneType.DAILY: (
        "你是一个治愈系暖心朋友，善于发现生活中的小确幸。"
        "你的任务是为用户的日常生活生成一句温暖的夸赞或肯定。"
        "要求：1.肯定用户在日常小事中的坚持和用心 "
        "2.字数控制在20-25字之间 "
        "3.语气治愈、温暖、给人力量 "
        "4.直接输出文案，不要加任何前缀"
    ),
}

# User Prompt 模板字典
# 定义每个场景下发送给 AI 的用户提示词模板
USER_PROMPTS: dict[SceneType, str] = {
    SceneType.GENERAL: (
        "请根据当前时间和用户状态，生成一句不超过30字的夸赞。"
    ),
    
    SceneType.CAREER: (
        "请为正在努力工作的用户生成一句鼓励夸赞。"
    ),
    
    SceneType.BEAUTY: (
        "请为用户的外貌和气质生成一句真诚的夸赞。"
    ),
    
    SceneType.LOVE: (
        "请为恋爱中的用户生成一句甜蜜的夸赞。"
    ),
    
    SceneType.DAILY: (
        "请为用户的日常生活生成一句温暖的夸赞。"
    ),
}


def get_prompt(scene: SceneType) -> PromptContent:
    """
    获取指定场景的 Prompt 模板
    
    Args:
        scene: 场景类型，使用 SceneType 枚举
        
    Returns:
        包含 system 和 user 两个键的字典：
        - system: System Prompt，定义 AI 角色和行为准则
        - user: User Prompt，用户输入的具体提示
        
    Example:
        >>> prompt = get_prompt(SceneType.CAREER)
        >>> print(prompt["system"])  # 输出事业场景的系统提示词
        >>> print(prompt["user"])    # 输出事业场景的用户提示词
    """
    return {
        "system": SYSTEM_PROMPTS[scene],
        "user": USER_PROMPTS[scene]
    }


def get_all_scenes() -> list[SceneType]:
    """
    获取所有支持的场景类型列表
    
    Returns:
        SceneType 枚举成员列表
        
    Example:
        >>> scenes = get_all_scenes()
        >>> for scene in scenes:
        ...     print(scene.value, scene.name)
    """
    return list(SceneType)


def get_scene_by_value(value: str) -> SceneType:
    """
    根据字符串值获取场景类型
    
    Args:
        value: 场景类型字符串值（如 "career", "beauty" 等）
        
    Returns:
        对应的 SceneType 枚举成员
        
    Raises:
        ValueError: 当传入的值不匹配任何场景时抛出
        
    Example:
        >>> scene = get_scene_by_value("career")
        >>> print(scene)  # SceneType.CAREER
    """
    try:
        return SceneType(value.lower())
    except ValueError:
        available = ", ".join([s.value for s in SceneType])
        raise ValueError(f"未知的场景类型: {value}。可用场景: {available}")


# 多模态场景 System Prompt 模板
MULTIMODAL_SYSTEM_PROMPTS = {
    "text_only": (
        "你是一个高情商、温暖的夸夸助手。用户会分享他们的心情、经历或想法，"
        "请基于用户的输入内容，生成一句真诚、具体的夸赞或鼓励。"
        "要求：1.真诚不油腻 2.紧扣用户说的内容 3.不超过50字 4.直接输出文案"
    ),
    "image_only": (
        "你是一个高情商、温暖的夸夸助手。用户会发送一张图片，"
        "请仔细观察图片中的内容（人物、场景、物品等），生成一句真诚、具体的夸赞。"
        "要求：1.基于图片内容进行夸赞 2.真诚不油腻 3.不超过50字 4.直接输出文案"
    ),
    "mixed": (
        "你是一个高情商、温暖的夸夸助手。用户会发送文字和图片，"
        "请结合用户的文字描述和图片内容，生成一句真诚、具体的夸赞。"
        "要求：1.同时结合文字和图片 2.真诚不油腻 3.不超过50字 4.直接输出文案"
    ),
}


def get_chat_prompt(input_type: Literal["text_only", "image_only", "mixed"]) -> PromptContent:
    """
    获取多模态聊天场景的 Prompt 模板
    
    根据输入类型（纯文字、纯图片、图文混合）返回对应的 system prompt。
    用于多模态聊天场景，支持用户发送文字、图片或两者混合的输入。
    
    Args:
        input_type: 输入类型，可选值：
            - "text_only": 纯文字输入
            - "image_only": 纯图片输入
            - "mixed": 文字+图片混合输入
    
    Returns:
        包含 system 和 user 两个键的字典：
        - system: System Prompt，定义 AI 角色和行为准则
        - user: User Prompt，对于多模态场景为空字符串
                  （实际 user content 由 chat_service 组装）
    
    Raises:
        ValueError: 当传入的 input_type 不支持时抛出
    
    Example:
        >>> prompt = get_chat_prompt("text_only")
        >>> print(prompt["system"])  # 输出纯文字场景的 system prompt
        >>> 
        >>> prompt = get_chat_prompt("mixed")
        >>> print(prompt["system"])  # 输出图文混合场景的 system prompt
    """
    if input_type not in MULTIMODAL_SYSTEM_PROMPTS:
        available = ", ".join(MULTIMODAL_SYSTEM_PROMPTS.keys())
        raise ValueError(f"未知的输入类型: {input_type}。可用类型: {available}")
    
    return {
        "system": MULTIMODAL_SYSTEM_PROMPTS[input_type],
        "user": ""
    }
