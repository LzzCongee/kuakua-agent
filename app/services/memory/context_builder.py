"""
记忆上下文构建器

将多层记忆聚合为结构化对象，替代 format_memory_for_prompt() 的字符串拼接。
使用 Pydantic 校验确保字段完整性和类型安全。
"""

from pydantic import BaseModel, Field
from typing import Optional


class SemanticMemory(BaseModel):
    """单条语义记忆（类型安全）"""
    memory_id: str = ""
    content: str
    timestamp: Optional[str] = None


class MemoryContext(BaseModel):
    """
    记忆上下文（最终注入 Prompt 的结构）

    替换 format_memory_for_prompt() 的字符串拼接，
    使用 Pydantic 校验确保字段完整性和类型安全。
    """
    prefer_scene: Optional[str] = Field(default=None, description="偏好场景")
    prefer_style: Optional[str] = Field(default=None, description="喜欢风格")
    user_tags: list[str] = Field(default_factory=list, max_length=5, description="用户标签")
    avoid_words: list[str] = Field(default_factory=list, max_length=10, description="避免词")
    last_emotion: Optional[str] = Field(default=None, description="最近情绪")
    milestones: list[str] = Field(default_factory=list, max_length=3, description="高光里程碑")
    recent_messages: list[dict[str, str]] = Field(default_factory=list, max_length=5, description="最近消息")
    semantic_memories: list[SemanticMemory] = Field(default_factory=list, max_length=3, description="语义记忆")

    def to_prompt_string(self) -> str:
        """
        转换为 Prompt 注入字符串

        Returns:
            str: 格式化的记忆字符串，用于注入到 system prompt
        """
        parts: list[str] = []

        if self.prefer_scene:
            parts.append(f"- 偏好场景：{self.prefer_scene}")
        if self.prefer_style:
            parts.append(f"- 喜欢风格：{self.prefer_style}")
        if self.user_tags:
            parts.append(f"- 用户标签：{', '.join(self.user_tags[:5])}")
        if self.last_emotion:
            parts.append(f"- 当前情绪：{self.last_emotion}")

        if self.recent_messages:
            msg_parts: list[str] = []
            for m in self.recent_messages[-3:]:
                role = "用户" if m.get("role") == "user" else "夸夸"
                content = str(m.get("content", ""))[:50]
                msg_parts.append(f"{role}：{content}")
            if msg_parts:
                parts.append(f"- 最近对话：{' | '.join(msg_parts)}")

        if self.milestones:
            parts.append(f"- 高光时刻：{'; '.join(self.milestones[:3])}")

        if self.semantic_memories:
            semantic_contents = [m.content for m in self.semantic_memories[:2]]
            parts.append(f"- 相关记忆：{'; '.join(semantic_contents)}")

        if not parts:
            return ""

        return "【用户个性化信息】\n" + "\n".join(parts)

    def is_empty(self) -> bool:
        """判断记忆上下文是否为空（无有效信息）"""
        return not (
            self.prefer_scene
            or self.prefer_style
            or self.user_tags
            or self.last_emotion
            or self.milestones
            or self.recent_messages
            or self.semantic_memories
        )

    @classmethod
    def from_memory_summary(cls, memory_summary) -> "MemoryContext":
        """
        从 MemorySummary 创建 MemoryContext

        Args:
            memory_summary: MemorySummary 实例（来自 MemoryService.get_memory_summary）

        Returns:
            MemoryContext: 记忆上下文对象
        """
        # 处理 semantic_memories（可能是字符串列表或 SemanticMemory 列表）
        semantic_memories: list[SemanticMemory] = []
        if memory_summary.semantic_memories:
            for mem in memory_summary.semantic_memories:
                if isinstance(mem, SemanticMemory):
                    semantic_memories.append(mem)
                elif isinstance(mem, str):
                    semantic_memories.append(SemanticMemory(content=mem))
                elif isinstance(mem, dict):
                    semantic_memories.append(SemanticMemory(
                        memory_id=mem.get("memory_id", ""),
                        content=mem.get("content", mem.get("memory", "")),
                        timestamp=mem.get("timestamp")
                    ))

        return cls(
            prefer_scene=memory_summary.prefer_scene,
            prefer_style=memory_summary.prefer_style,
            user_tags=memory_summary.user_tags or [],
            avoid_words=getattr(memory_summary, 'avoid_words', []) or [],
            last_emotion=memory_summary.last_emotion,
            milestones=memory_summary.milestones or [],
            recent_messages=memory_summary.recent_messages or [],
            semantic_memories=semantic_memories,
        )