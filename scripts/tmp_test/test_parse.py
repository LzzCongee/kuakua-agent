"""单元测试 parse_chat_response 各种输入格式"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")
from app.services.chat_service import parse_chat_response, ALLOWED_TOPICS

tests = [
    # (input, expected_topic, expected_reply_substr)
    ('{"reply": "你好", "topic": "career"}', "career", "你好"),
    ('```json\n{"reply": "好的", "topic": "love"}\n```', "love", "好的"),
    ('好的,{"reply": "hello", "topic": "daily"}', "daily", "hello"),
    ("整段纯文本", "general", "整段纯文本"),
    ("", "general", ""),
    ('{"reply": "x", "topic": "unknown_topic"}', "general", "x"),
    ('{"reply": "x", "topic": "rebuild"}', "rebuild", "x"),
    ('前缀文字 {"reply":"r1","topic":"career"} 后缀', "career", "r1"),
    ('{"reply":"嵌套 {\"a\":1} 测试","topic":"daily"}', "daily", "嵌套"),
]
all_pass = True
for raw, exp_topic, exp_reply in tests:
    reply, topic = parse_chat_response(raw)
    reply_ok = (exp_reply in reply) if exp_reply else (reply == "")
    topic_ok = topic == exp_topic
    ok = reply_ok and topic_ok
    mark = "OK" if ok else "FAIL"
    print(f"  {mark}: topic={topic!r}, reply={reply!r}")
    if not ok:
        print(f"    raw: {raw!r}")
        print(f"    exp topic={exp_topic!r} reply~{exp_reply!r}")
        all_pass = False

print("\n" + ("all tests pass" if all_pass else "SOME FAILED"))
