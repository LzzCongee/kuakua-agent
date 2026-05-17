"""
Prompt 模板管理模块

从 templates.toml 加载所有 prompt 内容，本文件只保留加载和组装逻辑。
模板在进程启动时加载一次并常驻内存，修改 templates.toml 后需重启服务生效。
开发调试时可调用 reload() 热重载。

基于心理学研究设计的夸赞生成 Prompt 体系：
- Carol Dweck 成长型思维：过程性夸赞（努力/策略）> 人格性夸赞（天赋/聪明）
- 具体性原则：越具体的观察越容易被感知为真诚
- 情绪验证优先：先承认感受，再给予肯定
- SBI 框架：情境(Situation) → 行为(Behavior) → 影响(Impact)
"""

from __future__ import annotations

import tomllib
from enum import StrEnum
from pathlib import Path
from typing import Literal

from ..models.schemas import PromptContent

TOML_PATH = Path(__file__).parent / "templates.toml"


class SceneType(StrEnum):
    """
    夸赞场景类型枚举

    Attributes:
        GENERAL: 通用场景，适合日常随机夸赞
        CAREER: 事业搞钱场景，适合工作、面试、创业等
        BEAUTY: 颜值气质场景，适合自拍、打扮、提升自信
        LOVE: 甜蜜恋爱场景，适合和伴侣相处、表达爱意
        DAILY: 日常治愈场景，适合生活小确幸、坚持、心态调整
    """
    GENERAL = "general"
    CAREER = "career"
    BEAUTY = "beauty"
    LOVE = "love"
    DAILY = "daily"


def _load_toml() -> dict:
    """加载 TOML 模板文件（模块级加载，进程生命周期内只读一次）"""
    with open(TOML_PATH, encoding="utf-8") as f:
        return tomllib.loads(f.read())


# 模块加载时读取一次，进程内常驻内存
_data: dict = _load_toml()


def reload() -> None:
    """热重载模板（用于开发调试，生产环境建议重启）"""
    global _data
    _data = _load_toml()


def _build_system_prompt(role: str, task: str, notes: list[str]) -> str:
    """
    组装完整的 system prompt

    结构: role + task + 核心方法论 + 场景注意事项
    """
    methodology = _data["methodology"]["content"]
    notes_block = "\n".join(f"- {n}" for n in notes)
    return f"{role}\n{task}\n\n{methodology}\n\n【本场景特别注意】\n{notes_block}\n"


def get_prompt(scene: SceneType) -> PromptContent:
    """获取指定场景的 Prompt 模板"""
    scene_data = _data["scenes"][scene.value]
    return {
        "system": _build_system_prompt(
            role=scene_data["role"],
            task=scene_data["task"],
            notes=scene_data["notes"],
        ),
        "user": scene_data["user"],
    }


def get_all_scenes() -> list[SceneType]:
    """获取所有支持的场景类型列表"""
    return list(SceneType)


def get_scene_by_value(value: str) -> SceneType:
    """
    根据字符串值获取场景类型

    Raises:
        ValueError: 当传入的值不匹配任何场景时抛出
    """
    try:
        return SceneType(value.lower())
    except ValueError:
        available = ", ".join([s.value for s in SceneType])
        raise ValueError(f"未知的场景类型: {value}。可用场景: {available}")


def get_chat_prompt(input_type: Literal["text_only", "image_only", "mixed"]) -> PromptContent:
    """
    获取多模态聊天场景的 Prompt 模板

    Args:
        input_type: "text_only" | "image_only" | "mixed"
    """
    multimodal = _data["multimodal"]
    if input_type not in multimodal:
        available = ", ".join(multimodal.keys())
        raise ValueError(f"未知的输入类型: {input_type}。可用类型: {available}")

    data = multimodal[input_type]
    return {
        "system": _build_system_prompt(
            role=data["role"],
            task=data["task"],
            notes=data["notes"],
        ),
        "user": data.get("user", ""),
    }
