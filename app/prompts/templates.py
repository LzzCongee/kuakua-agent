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
from pathlib import Path
from typing import Literal

from ..models.schemas import PromptContent

TOML_PATH = Path(__file__).parent / "templates.toml"


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

    结构: role + task + 核心方法论 + 输出格式(JSON+topic) + 场景注意事项
    """
    methodology = _data["methodology"]["content"]
    notes_block = "\n".join(f"- {n}" for n in notes)
    output_format = _data.get("output_format", {}).get("block", "")
    parts = [role, task, "", methodology]
    if output_format:
        parts.extend(["", output_format])
    parts.extend(["", "【本场景特别注意】", notes_block])
    return "\n".join(parts) + "\n"


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


def get_personality(personality: str) -> dict | None:
    """
    获取人格变体配置

    Args:
        personality: 人格类型 (default/witty/chill/enthusiastic)

    Returns:
        dict | None: 包含 role、tone、trigger_tags 的配置;未知人格返回 None
        (注意:不再回退到 default,调用方负责处理 default/未知场景)
    """
    personalities = _data.get("personalities", {})
    return personalities.get(personality)


def get_random_mode_config() -> dict:
    """
    获取随机模式配置

    Returns:
        dict: 包含 enabled、trigger_probability、categories 的配置
    """
    return _data.get("random_modes", {})


def get_random_mode_prompt(
    mode_type: str,
    user_input: str,
    personality: str = "default"
) -> str:
    """
    生成随机模式的 prompt 模板

    注入 SBI（Situation-Behavior-Impact）框架以保证回复质量，
    并加入对话钩子（conversation hook）引导用户延续对话。

    Args:
        mode_type: 随机模式类型 (witty_teasing/insightful/meme/ironic_warm)
        user_input: 用户输入的文本
        personality: 人格类型（影响语气）

    Returns:
        str: 渲染后的 prompt
    """
    random_modes = _data.get("random_modes", {})
    categories = random_modes.get("categories", {})

    if mode_type not in categories:
        mode_type = "ironic_warm"

    personality_data = get_personality(personality) or {}
    tone = personality_data.get("tone", "")

    mode_instructions = {
        "witty_teasing": (
            "方式：用调侃的方式回应，看似吐槽实则肯定（好一个嘴上说不要，身体很诚实）。\n"
            "结尾：抛一个略带挑衅的问题，给对方一个辩解的机会——辩解本身就是倾诉的开始。"
        ),
        "insightful": (
            "方式：说一句让人愣住的洞察，帮用户看到自己没注意到的情绪或模式。\n"
            "结尾：由此引申一个与对方情绪相关的开放式问题，把话语权交还给对方。"
        ),
        "meme": (
            "方式：用当前的梗或段子回应，贴合用户说的内容，让氛围轻松下来。\n"
            "结尾：接一个玩梗的问题，自然过渡到让对方分享更多。"
        ),
        "ironic_warm": (
            "方式：偏不按用户预期的方式回应，出乎意料但兜底温暖。\n"
            "结尾：用一句温柔的邀请收尾，制造安全的倾诉空间（让对方感到想说的话都有人听）。"
        ),
    }

    instruction = mode_instructions.get(mode_type, mode_instructions["ironic_warm"])

    return (
        f"【模式：随机互动 | 人格语气：{tone}】\n"
        f"用户说：{user_input}\n\n"
        f"【SBI 框架 —— 先找具体细节，再回应】\n"
        f"1. 锚定细节：从用户输入中找一个真实可观察的具体点\n"
        f"2. 识别品质：将细节映射到背后的品质或状态\n"
        f"3. 按下方方式回应，表达积极影响\n\n"
        f"{instruction}\n\n"
        f"【要求】\n"
        f"- 口语化，像朋友私聊，语气自然不刻意\n"
        f"- 30字以内\n"
        f"- 禁止：空洞套话、排比句、鸡汤句式、与他人比较\n"
        f"- **必须：以问句或邀请结尾，让对方愿意继续说下去**"
    )
