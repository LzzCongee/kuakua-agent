"""
记忆上下文构建器

将多层记忆聚合为结构化对象，替代 format_memory_for_prompt() 的字符串拼接。
使用 Pydantic 校验确保字段完整性和类型安全。
"""

from typing import Optional

from pydantic import BaseModel, Field


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
    recent_messages: list[dict[str, str]] = Field(default_factory=list, max_length=6, description="最近消息")
    semantic_memories: list[SemanticMemory] = Field(default_factory=list, max_length=3, description="语义记忆")

    # 人格偏好
    personality_prefer: str = Field(
        default="default",
        description="喜欢的人格类型：default/witty/chill/enthusiastic"
    )
    humor_taste: Optional[str] = Field(
        default=None,
        description="喜欢的幽默类型：teasing/insightful/meme/ironic"
    )
    tone_shift: bool = Field(
        default=False,
        description="是否接受语气转变（有时正经有时搞笑）"
    )
    interaction_count: int = Field(
        default=0,
        description="累计交互次数，用于判断用户是否活跃"
    )

    # topic 偏好(新增)— 来自收藏聚合的衰减权重结果
    # 结构: {"topics": [{topic, weight, count, last_days_ago, intensity}, ...],
    #        "total_likes": int, "generated_at": iso str}
    topic_preference: Optional[dict] = Field(
        default=None,
        description="topic 偏好(lead topics + 强度标签),供 prompt 注入"
    )

    def to_prompt_string(self) -> str:
        """
        转换为结构化 Prompt 字符串（放在 user message 中）

        按优先级从高到低分区块：
        1. 当前状态（情绪、最近对话）
        2. 交互设定（人格、幽默偏好）
        3. 个人档案（场景、风格、标签）
        4. 深度记忆（里程碑、语义记忆）

        Returns:
            str: 结构化的记忆字符串，空区块被跳过
        """
        blocks: list[str] = []

        # === 区块 1：当前状态（最时效相关） ===
        state_lines: list[str] = []
        if self.last_emotion:
            state_lines.append(f"情绪：{self.last_emotion}")
        if self.recent_messages:
            msg_parts: list[str] = []
            for m in self.recent_messages[-6:]:
                role = "用户" if m.get("role") == "user" else "夸夸"
                content = str(m.get("content", ""))[:80]
                msg_parts.append(f"{role}：{content}")
            if msg_parts:
                state_lines.append(f"最近对话：{' | '.join(msg_parts)}")
        if state_lines:
            blocks.append("【当前状态】")
            blocks.extend(state_lines)

        # === 区块 2：交互设定（影响语气和行为） ===
        style_lines: list[str] = []
        if self.personality_prefer and self.personality_prefer != "default":
            style_lines.append(f"人格模式：{self.personality_prefer}")
        if self.humor_taste:
            style_lines.append(f"幽默偏好：{self.humor_taste}")
        if self.tone_shift:
            style_lines.append("接受语气变化")
        if style_lines:
            if blocks:
                blocks.append("")
            blocks.append("【交互设定】")
            blocks.extend(style_lines)

        # === 区块 3：个人档案（静态偏好） ===
        profile_lines: list[str] = []
        if self.prefer_scene:
            profile_lines.append(f"偏好场景：{self.prefer_scene}")
        if self.prefer_style:
            profile_lines.append(f"喜欢风格：{self.prefer_style}")
        if self.user_tags:
            profile_lines.append(f"用户标签：{', '.join(self.user_tags[:5])}")
        if profile_lines:
            if blocks:
                blocks.append("")
            blocks.append("【个人档案】")
            blocks.extend(profile_lines)

        # === 区块 4：深度记忆（长期背景） ===
        memory_lines: list[str] = []
        if self.milestones:
            memory_lines.append(f"高光时刻：{'; '.join(self.milestones[:3])}")
        if self.semantic_memories:
            semantic_contents = [m.content for m in self.semantic_memories[:2]]
            memory_lines.append(f"相关记忆：{'; '.join(semantic_contents)}")
        if memory_lines:
            if blocks:
                blocks.append("")
            blocks.append("【深度记忆】")
            blocks.extend(memory_lines)

        # === 区块 5：话题偏好(衰减权重 + 强度) ===
        # 注入 lead topic + 强度标签,让 LLM 在生成时主动倾向这些方向
        # 强度说明:
        #   strong(weight>=5): 明显偏好,可以放心地往这个方向靠
        #   medium(weight>=2): 中等偏好,可适度倾斜
        #   weak(weight<2):   弱偏好,作为软提示,不要过度
        topic_lines: list[str] = []
        if self.topic_preference:
            topics = self.topic_preference.get("topics") or []
            total = self.topic_preference.get("total_likes") or 0
            has_declared = bool(self.topic_preference.get("declared_topics"))
            for t in topics[:3]:  # 最多 3 个,设计上 MAX_INJECTED_TOPICS
                intensity = t.get("intensity", "weak")
                topic = t.get("topic", "")
                weight = t.get("weight", 0)
                if topic and topic != "general":
                    # count=0 表示纯主动声明,弱化显示
                    if t.get("count", 0) == 0 and t.get("declared"):
                        topic_lines.append(f"{topic}({intensity}, 主动声明)")
                    else:
                        topic_lines.append(f"{topic}({intensity}, weight={weight})")
            # 仅在有真实收藏数据时显示"基于 X 次收藏"
            if topic_lines and total > 0:
                topic_lines.insert(0, f"基于 {total} 次收藏")
            elif topic_lines and has_declared and total == 0:
                topic_lines.insert(0, "基于用户主动声明")

        if topic_lines:
            if blocks:
                blocks.append("")
            blocks.append("【话题偏好】")
            blocks.append("用户在以下话题上有明显偏好,生成内容时可自然往这些方向靠:")
            blocks.extend(f"- {line}" for line in topic_lines)

        if not blocks:
            return ""

        return "\n".join(blocks)

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
            or self.topic_preference
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
            personality_prefer=getattr(memory_summary, 'personality_prefer', 'default') or 'default',
            humor_taste=getattr(memory_summary, 'humor_taste', None),
            tone_shift=getattr(memory_summary, 'tone_shift', True),
            interaction_count=getattr(memory_summary, 'interaction_count', 0) or 0,
            topic_preference=getattr(memory_summary, 'topic_preference', None),
        )
