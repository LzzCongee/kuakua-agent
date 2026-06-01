"""
数据库迁移脚本：旧版 sessions 表 → 新版 schema

旧版 schema:
  sessions: id, session_id, user_id, scene, messages(TEXT/JSON), created_at, updated_at

新版 schema:
  sessions: id, session_id, user_id, message_count, last_message_at, created_at, updated_at
  messages: id, session_id, trace_id, role, content, message_type, has_image, image_desc, scene, emotion, token_usage, created_at

迁移步骤:
  1. 将 sessions.messages JSON 中的消息迁移到 messages 表
  2. 添加 message_count 和 last_message_at 列
  3. 更新 message_count 和 last_message_at
  4. 删除旧的 scene 和 messages 列（SQLite 不支持 DROP COLUMN，需重建表）
"""

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "kuakua.db"


def migrate():
    if not DB_PATH.exists():
        print(f"数据库不存在: {DB_PATH}")
        return

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")  # 避免锁冲突
    c = conn.cursor()

    # 检查当前 schema
    c.execute("PRAGMA table_info(sessions)")
    session_cols = {row[1] for row in c.fetchall()}
    print(f"当前 sessions 列: {session_cols}")

    # ========== Step 1: 迁移 JSON 消息到 messages 表 ==========
    has_old_messages_col = "messages" in session_cols
    migrated_count = 0

    if has_old_messages_col:
        c.execute("SELECT session_id, messages FROM sessions WHERE messages IS NOT NULL AND messages != '[]'")
        rows = c.fetchall()
        print(f"找到 {len(rows)} 个有消息的 session 需要迁移")

        for session_id, messages_json in rows:
            try:
                msgs = json.loads(messages_json)
            except (json.JSONDecodeError, TypeError):
                print(f"  跳过无效 JSON: session_id={session_id}")
                continue

            for msg in msgs:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                timestamp = msg.get("timestamp")

                # 检查是否已存在（避免重复迁移）
                c.execute(
                    "SELECT COUNT(*) FROM messages WHERE session_id = ? AND role = ? AND content = ?",
                    (session_id, role, content)
                )
                if c.fetchone()[0] > 0:
                    continue

                c.execute(
                    """INSERT INTO messages (session_id, trace_id, role, content, message_type, has_image, image_desc, scene, emotion, token_usage, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        session_id,
                        "migrated",
                        role,
                        content,
                        "text",
                        0,
                        None,
                        "general",
                        None,
                        None,
                        timestamp or datetime.utcnow().isoformat(),
                    )
                )
                migrated_count += 1

        print(f"迁移了 {migrated_count} 条消息到 messages 表")
    else:
        print("sessions 表没有 messages 列，跳过消息迁移")

    # ========== Step 2: 添加新列 ==========
    if "message_count" not in session_cols:
        c.execute("ALTER TABLE sessions ADD COLUMN message_count INTEGER DEFAULT 0")
        print("添加 message_count 列")

    if "last_message_at" not in session_cols:
        c.execute("ALTER TABLE sessions ADD COLUMN last_message_at DATETIME")
        print("添加 last_message_at 列")

    # ========== Step 3: 更新 message_count 和 last_message_at ==========
    c.execute("""
        UPDATE sessions SET
            message_count = (SELECT COUNT(*) FROM messages WHERE messages.session_id = sessions.session_id),
            last_message_at = (SELECT MAX(created_at) FROM messages WHERE messages.session_id = sessions.session_id)
    """)
    print(f"更新了 {c.rowcount} 个 session 的 message_count 和 last_message_at")

    # ========== Step 4: 删除旧列（重建表） ==========
    if has_old_messages_col:
        print("重建 sessions 表（移除旧的 scene 和 messages 列）...")
        c.execute("""
            CREATE TABLE sessions_new (
                id INTEGER PRIMARY KEY,
                session_id VARCHAR(100) NOT NULL UNIQUE,
                user_id VARCHAR(100) NOT NULL,
                message_count INTEGER DEFAULT 0,
                last_message_at DATETIME,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            INSERT INTO sessions_new (id, session_id, user_id, message_count, last_message_at, created_at, updated_at)
            SELECT id, session_id, user_id, message_count, last_message_at, created_at, updated_at FROM sessions
        """)
        c.execute("DROP TABLE sessions")
        c.execute("ALTER TABLE sessions_new RENAME TO sessions")
        print("sessions 表重建完成")

    conn.commit()

    # ========== 验证 ==========
    print("\n=== 迁移后验证 ===")
    c.execute("PRAGMA table_info(sessions)")
    print(f"sessions 列: {[row[1] for row in c.fetchall()]}")

    c.execute("SELECT COUNT(*) FROM sessions")
    print(f"sessions 数量: {c.fetchone()[0]}")

    c.execute("SELECT COUNT(*) FROM messages")
    print(f"messages 数量: {c.fetchone()[0]}")

    c.execute("SELECT session_id, message_count, last_message_at FROM sessions LIMIT 5")
    print("最近 sessions:")
    for r in c.fetchall():
        print(f"  {r[0]} | count={r[1]} | last_msg={r[2]}")

    c.execute("SELECT session_id, role, substr(content, 1, 40), created_at FROM messages ORDER BY created_at DESC LIMIT 5")
    print("最近 messages:")
    for r in c.fetchall():
        print(f"  {r[0]} | {r[1]} | {r[2]} | {r[3]}")

    conn.close()
    print("\n迁移完成!")


def upgrade_topic_preference() -> None:
    """
    迁移:为话题偏好个性化功能添加表/列/索引。

    新增/变更:
      1. messages.topic: VARCHAR(50) DEFAULT 'general' — LLM 自报的回复 topic
      2. messages.ix_messages_role_content(role, content) 复合索引 — 收藏反查用
      3. user_topic_preferences 表:user × topic × like_count 聚合
      4. user_topic_preferences.ix_user_topic_pref_count(user_id, like_count) 索引 — 排序用
      5. user_topic_preferences.uq_user_topic_pref(user_id, topic) 唯一约束
      6. user_profiles.topic_preference_snapshot: TEXT NULL — topic 偏好 JSON 缓存

    幂等:可重复执行,已存在的列/表/索引自动跳过。

    设计依据: docs/greeting-topic-personalization-design-v2.md 第四章
    """
    if not DB_PATH.exists():
        print(f"数据库不存在: {DB_PATH}")
        print("新数据库通过 init_db() 的 create_all 自动建表,无需迁移。")
        return

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    c = conn.cursor()

    def column_exists(table: str, column: str) -> bool:
        c.execute(f"PRAGMA table_info({table})")
        return any(row[1] == column for row in c.fetchall())

    def table_exists(table: str) -> bool:
        c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
        return c.fetchone() is not None

    def index_exists(index_name: str) -> bool:
        c.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
            (index_name,),
        )
        return c.fetchone() is not None

    # ========== 1. messages.topic ==========
    if column_exists("messages", "topic"):
        print("  [skip] messages.topic 已存在")
    else:
        c.execute("ALTER TABLE messages ADD COLUMN topic VARCHAR(50) DEFAULT 'general'")
        print("  [add]  messages.topic")

    # ========== 2. messages.ix_messages_role_content ==========
    if index_exists("ix_messages_role_content"):
        print("  [skip] ix_messages_role_content 已存在")
    else:
        c.execute("CREATE INDEX ix_messages_role_content ON messages (role, content)")
        print("  [add]  ix_messages_role_content 索引")

    # ========== 3-5. user_topic_preferences 表 ==========
    if table_exists("user_topic_preferences"):
        print("  [skip] user_topic_preferences 表已存在")
    else:
        c.execute("""
            CREATE TABLE user_topic_preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id VARCHAR(100) NOT NULL,
                topic VARCHAR(50) NOT NULL,
                like_count INTEGER NOT NULL DEFAULT 0,
                last_liked_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                first_liked_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("  [add]  user_topic_preferences 表")

        c.execute("""
            CREATE UNIQUE INDEX uq_user_topic_pref
            ON user_topic_preferences (user_id, topic)
        """)
        print("  [add]  uq_user_topic_pref 唯一索引")

        c.execute("""
            CREATE INDEX ix_user_topic_pref_count
            ON user_topic_preferences (user_id, like_count DESC)
        """)
        print("  [add]  ix_user_topic_pref_count 排序索引")

        c.execute("""
            CREATE INDEX ix_user_topic_pref_user
            ON user_topic_preferences (user_id)
        """)
        print("  [add]  ix_user_topic_pref_user 单列索引")

    # ========== 6. user_profiles.topic_preference_snapshot ==========
    if column_exists("user_profiles", "topic_preference_snapshot"):
        print("  [skip] user_profiles.topic_preference_snapshot 已存在")
    else:
        c.execute("ALTER TABLE user_profiles ADD COLUMN topic_preference_snapshot TEXT")
        print("  [add]  user_profiles.topic_preference_snapshot")

    conn.commit()

    # ========== 验证 ==========
    print("\n=== 迁移后验证 ===")
    if table_exists("messages"):
        c.execute("PRAGMA table_info(messages)")
        cols = {row[1] for row in c.fetchall()}
        print(f"  messages.topic 存在: {'topic' in cols}")
    if table_exists("user_topic_preferences"):
        c.execute("PRAGMA table_info(user_topic_preferences)")
        cols = {row[1] for row in c.fetchall()}
        print(f"  user_topic_preferences 列: {sorted(cols)}")
        c.execute("PRAGMA index_list(user_topic_preferences)")
        idx = [row[1] for row in c.fetchall()]
        print(f"  user_topic_preferences 索引: {idx}")
    if table_exists("user_profiles"):
        c.execute("PRAGMA table_info(user_profiles)")
        cols = {row[1] for row in c.fetchall()}
        print(f"  user_profiles.topic_preference_snapshot 存在: {'topic_preference_snapshot' in cols}")

    conn.close()
    print("\n[ok] topic_preference 迁移完成")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "upgrade_topic_preference":
        upgrade_topic_preference()
    else:
        migrate()
