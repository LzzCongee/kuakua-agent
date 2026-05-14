"""
CloudBase 记忆服务 - 使用 CloudBase NoSQL Database

提供三层记忆管理的统一封装：
1. 短期会话记忆（sessions）
2. 用户偏好记忆（user_profiles）
3. 高光里程碑记忆（milestones）

使用 CloudBase NoSQL Database HTTP API
"""

import json
import time
import hmac
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


class CloudBaseDBClient:
    """CloudBase NoSQL Database HTTP API 客户端"""
    
    def __init__(self, env_id: str, secret_id: str, secret_key: str, region: str = "ap-shanghai"):
        self.env_id = env_id
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.region = region
        # 使用腾讯云 API v3 的标准端点（不区分地域）
        self.base_url = "https://tcb.tencentcloudapi.com"
        self._client = httpx.AsyncClient(timeout=30.0)
    
    def _sign(self, params: dict[str, Any]) -> dict[str, str]:
        """生成腾讯云 API v3 签名"""
        
        # 构建规范请求字符串
        http_request_method = "POST"
        canonical_uri = "/"
        canonical_query_string = ""
        host = self.base_url.replace("https://", "").replace("http://", "")
        canonical_headers = f"content-type:application/json; charset=utf-8\nhost:{host}\n"
        signed_headers = "content-type;host"
        
        # 请求体
        payload = json.dumps(params, ensure_ascii=False, separators=(',', ':'))
        hashed_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        
        canonical_request = (
            f"{http_request_method}\n{canonical_uri}\n{canonical_query_string}\n"
            f"{canonical_headers}\n{signed_headers}\n{hashed_payload}"
        )
        
        # 构建待签名字符串
        algorithm = "TC3-HMAC-SHA256"
        request_timestamp = int(time.time())
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        credential_scope = f"{date}/tcb/tc3_request"
        hashed_canonical_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
        string_to_sign = f"{algorithm}\n{request_timestamp}\n{credential_scope}\n{hashed_canonical_request}"
        
        # 计算签名
        secret_date = hmac.new(f"TC3{self.secret_key}".encode("utf-8"), date.encode("utf-8"), hashlib.sha256).digest()
        secret_service = hmac.new(secret_date, b"tcb", hashlib.sha256).digest()
        secret_signing = hmac.new(secret_service, b"tc3_request", hashlib.sha256).digest()
        signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        
        # 构建 Authorization
        authorization = (
            f"{algorithm} "
            f"Credential={self.secret_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )
        
        headers = {
            "Authorization": authorization,
            "Content-Type": "application/json; charset=utf-8",
            "Host": host,
            "X-TC-Action": params.get("Action", ""),
            "X-TC-Timestamp": str(request_timestamp),
            "X-TC-Version": "2018-06-08",
            "X-TC-Region": self.region,
        }
        
        return headers
    
    async def call_api(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        """调用 CloudBase API"""
        payload = {
            "Action": action,
            "EnvId": self.env_id,
            **params
        }
        
        headers = self._sign(payload)
        
        response = await self._client.post(
            self.base_url,
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        
        result = response.json()
        if "Response" in result:
            if "Error" in result["Response"]:
                raise Exception(f"API Error: {result['Response']['Error']}")
            return result["Response"]
        
        return result


class CloudBaseMemoryService:
    """CloudBase 记忆服务"""
    
    def __init__(self, env_id: str, secret_id: str, secret_key: str):
        self.client = CloudBaseDBClient(env_id, secret_id, secret_key)
        self.env_id = env_id
    
    # ==================== 短期会话记忆 ====================

    async def get_or_create_session(
        self, user_id: str, session_id: str
    ) -> dict:
        """获取或创建会话"""
        # 查询现有会话
        query = {"session_id": session_id}
        result = await self._query("sessions", query)

        if result and result.get("Documents"):
            docs = json.loads(result["Documents"])
            if docs:
                return docs[0]

        # 创建新会话
        now = datetime.now(timezone.utc).isoformat()
        session_data = {
            "session_id": session_id,
            "user_id": user_id,
            "message_count": 0,
            "last_message_at": now,
            "created_at": now,
            "updated_at": now
        }

        await self._insert("sessions", json.dumps(session_data))
        return session_data
    
    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        """获取会话"""
        query = {"session_id": session_id}
        result = await self._query("sessions", query)
        
        if result and result.get("Documents"):
            docs = json.loads(result["Documents"])
            return docs[0] if docs else None
        
        return None
    
    async def update_session(self, session_id: str, messages: list[dict[str, Any]]) -> dict[str, Any] | None:
        """更新会话消息"""
        session = await self.get_session(session_id)
        if session:
            update_data = {
                "$set": {
                    "messages": messages,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            }
            
            query = {"session_id": session_id}
            await self._update("sessions", query, json.dumps(update_data))
            
            return await self.get_session(session_id)
        
        return None
    
    async def get_recent_sessions(self, user_id: str, limit: int = 5) -> list[dict[str, Any]]:
        """获取用户最近的会话"""
        query = {"user_id": user_id}
        result = await self._query("sessions", query)
        
        if result and result.get("Documents"):
            docs = json.loads(result["Documents"])
            # 按 updated_at 排序
            docs.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
            return docs[:limit]
        
        return []
    
    async def cleanup_expired_sessions(self, hours: int = 2) -> int:
        """清理过期会话"""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        query = {"created_at": {"$lt": cutoff.isoformat()}}
        
        result = await self._query("sessions", query)
        count = 0
        
        if result and result.get("Documents"):
            docs = json.loads(result["Documents"])
            for doc in docs:
                await self._delete("sessions", {"_id": doc["_id"]})
                count += 1
        
        return count
    
    # ==================== 用户偏好记忆 ====================
    
    async def get_user_profile(self, user_id: str) -> dict[str, Any] | None:
        """获取用户偏好"""
        query = {"user_id": user_id}
        result = await self._query("user_profiles", query)
        
        if result and result.get("Documents"):
            docs = json.loads(result["Documents"])
            return docs[0] if docs else None
        
        return None
    
    async def get_or_create_profile(self, user_id: str) -> dict[str, Any]:
        """获取或创建用户偏好"""
        profile = await self.get_user_profile(user_id)
        
        if not profile:
            now = datetime.now(timezone.utc).isoformat()
            profile_data = {
                "user_id": user_id,
                "prefer_scene": None,
                "prefer_style": None,
                "user_tags": [],
                "avoid_words": [],
                "last_emotion": None,
                "conversation_count": 0,
                "favorite_count": 0,
                "last_active": now,
                "created_at": now,
                "updated_at": now
            }
            
            await self._insert("user_profiles", json.dumps(profile_data))
            return profile_data
        
        return profile
    
    async def update_user_profile(self, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """更新用户偏好"""
        profile = await self.get_or_create_profile(user_id)
        
        update_data: dict[str, Any] = {"$set": {"updated_at": datetime.now(timezone.utc).isoformat()}}
        
        for key, value in data.items():
            if value is not None:
                update_data["$set"][key] = value
        
        # 增加对话计数
        update_data["$inc"] = {"conversation_count": 1}
        
        query = {"user_id": user_id}
        await self._update("user_profiles", query, json.dumps(update_data))
        
        return await self.get_user_profile(user_id)
    
    async def increment_favorite_count(self, user_id: str) -> dict[str, Any]:
        """增加收藏次数"""
        profile = await self.get_or_create_profile(user_id)
        
        update_data = {
            "$inc": {"favorite_count": 1},
            "$set": {"last_active": datetime.now(timezone.utc).isoformat()}
        }
        
        query = {"user_id": user_id}
        await self._update("user_profiles", query, json.dumps(update_data))
        
        return await self.get_user_profile(user_id)
    
    async def update_prefer_scene(self, user_id: str, scene: str) -> dict[str, Any]:
        """更新用户偏好场景（根据使用频率自动调整）"""
        profile = await self.get_or_create_profile(user_id)
        
        now = datetime.now(timezone.utc).isoformat()
        update_data = {
            "$set": {
                "prefer_scene": scene,
                "last_active": now,
                "updated_at": now
            }
        }
        
        query = {"user_id": user_id}
        await self._update("user_profiles", query, json.dumps(update_data))
        
        return await self.get_user_profile(user_id)
    
    # ==================== 高光里程碑记忆 ====================
    
    async def get_milestones(self, user_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """获取用户的高光里程碑"""
        query = {"user_id": user_id}
        result = await self._query("milestones", query)
        
        if result and result.get("Documents"):
            docs = json.loads(result["Documents"])
            # 按 importance 排序
            docs.sort(key=lambda x: (-x.get("importance", 0), x.get("created_at", "")))
            return docs[:limit]
        
        return []
    
    async def add_milestone(
        self, user_id: str, content: str, source: str = "user_input", importance: int = 1
    ) -> dict[str, Any]:
        """添加高光里程碑"""
        now = datetime.now(timezone.utc).isoformat()
        milestone_data = {
            "user_id": user_id,
            "content": content,
            "source": source,
            "importance": importance,
            "is_achieved": False,
            "created_at": now,
            "updated_at": now
        }
        
        await self._insert("milestones", json.dumps(milestone_data))
        return milestone_data
    
    async def extract_and_add_milestone(self, user_id: str, content: str) -> dict[str, Any] | None:
        """
        从对话内容中提取并添加里程碑
        
        检测内容是否包含成就类关键词，如果是则自动创建里程碑。
        
        Args:
            user_id: 用户ID
            content: 对话内容
            
        Returns:
            Optional[dict]: 新增的里程碑（如果没有提取到成就则返回 None）
        """
        achievement_keywords = [
            "完成", "达成", "通过", "拿到", "获得",
            "坚持", "成功", "突破", "进步", "提升"
        ]
        
        # 简单检测是否有成就相关关键词
        has_achievement = any(kw in content for kw in achievement_keywords)
        
        if has_achievement:
            return await self.add_milestone(
                user_id=user_id,
                content=content[:200],  # 截取前200字符
                source="user_input",
                importance=2
            )
        
        return None
    
    # ==================== 记忆汇总 ====================
    
    async def get_memory_summary(self, user_id: str, session_id: str | None = None) -> dict[str, Any]:
        """获取用户记忆汇总"""
        profile = await self.get_user_profile(user_id)
        
        recent_messages = []
        if session_id:
            session = await self.get_session(session_id)
            if session and session.get("messages"):
                recent_messages = session["messages"][-3:]
        
        milestones = await self.get_milestones(user_id, limit=5)
        milestone_contents = [m["content"] for m in milestones]
        
        return {
            "prefer_scene": profile.get("prefer_scene") if profile else None,
            "prefer_style": profile.get("prefer_style") if profile else None,
            "user_tags": profile.get("user_tags", []) if profile else [],
            "recent_messages": recent_messages,
            "milestones": milestone_contents,
            "last_emotion": profile.get("last_emotion") if profile else None
        }
    
    def format_memory_for_prompt(self, memory: dict[str, Any]) -> str:
        """格式化记忆为 Prompt 注入字符串"""
        parts = []
        
        if memory.get("prefer_scene"):
            parts.append(f"偏好场景：{memory['prefer_scene']}")
        if memory.get("prefer_style"):
            parts.append(f"喜欢风格：{memory['prefer_style']}")
        if memory.get("user_tags"):
            tags = memory["user_tags"][:5]
            parts.append(f"用户标签：{', '.join(tags)}")
        if memory.get("last_emotion"):
            parts.append(f"当前情绪：{memory['last_emotion']}")
        
        if memory.get("recent_messages"):
            msg_str = "; ".join([
                f"{m.get('role', 'user')}: {m.get('content', '')[:50]}"
                for m in memory["recent_messages"][-3:]
            ])
            parts.append(f"最近对话：{msg_str}")
        
        if memory.get("milestones"):
            parts.append(f"高光时刻：{'; '.join(memory['milestones'][:3])}")
        
        if not parts:
            return ""
        
        return "【用户记忆】\n" + "\n".join(parts)
    
    # ==================== 内部方法 ====================
    
    async def _query(self, collection: str, query: dict[str, Any]) -> dict[str, Any]:
        """查询文档"""
        params = {
            "CollectionName": collection,
            "Query": json.dumps(query)
        }
        return await self.client.call_api("QueryDocument", params)
    
    async def _insert(self, collection: str, documents: str) -> dict[str, Any]:
        """插入文档"""
        params = {
            "CollectionName": collection,
            "Documents": documents
        }
        return await self.client.call_api("InsertDocument", params)
    
    async def _update(self, collection: str, query: dict[str, Any], update: str) -> dict[str, Any]:
        """更新文档"""
        params = {
            "CollectionName": collection,
            "Query": json.dumps(query),
            "Updates": update
        }
        return await self.client.call_api("UpdateDocument", params)
    
    async def _delete(self, collection: str, query: dict[str, Any]) -> dict[str, Any]:
        """删除文档"""
        params = {
            "CollectionName": collection,
            "Query": json.dumps(query)
        }
        return await self.client.call_api("DeleteDocument", params)
