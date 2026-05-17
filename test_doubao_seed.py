# coding:utf-8
"""
火山引擎 Doubao-Seed-2.0-mini 音频输入测试
支持 Chat Completions API 音频输入和情绪识别
"""
import requests
import json

VOLC_API_KEY = "c596006f-1c5d-4788-b425-9ec4a9f89b15"
MODEL = "doubao-seed-2-0-mini-260428"
BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

headers = {
    "Authorization": f"Bearer {VOLC_API_KEY}",
    "Content-Type": "application/json"
}


def test_audio_transcription():
    """测试音频内容识别"""
    print("\n=== 音频内容识别测试 ===")
    body = {
        "model": MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "input_audio",
                    "input_audio": {
                        "url": "https://ark-project.tos-cn-beijing.volces.com/doc_audio/ark_demo_audio.mp3",
                        "format": "mp3"
                    }
                },
                {
                    "type": "text",
                    "text": "请识别音频中的内容"
                }
            ]
        }]
    }
    resp = requests.post(f"{BASE_URL}/chat/completions", headers=headers, json=body, timeout=60)
    r = resp.json()
    if 'error' in r:
        print(f"Error: {r['error'].get('message')}")
        return None
    return r['choices'][0]['message']['content']


def test_audio_emotion_recognition():
    """测试音频情绪识别"""
    print("\n=== 音频情绪识别测试 ===")
    body = {
        "model": MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "input_audio",
                    "input_audio": {
                        "url": "https://ark-project.tos-cn-beijing.volces.com/doc_audio/ark_demo_audio.mp3",
                        "format": "mp3"
                    }
                },
                {
                    "type": "text",
                    "text": "请分析音频中的情绪"
                }
            ]
        }]
    }
    resp = requests.post(f"{BASE_URL}/chat/completions", headers=headers, json=body, timeout=60)
    r = resp.json()
    if 'error' in r:
        print(f"Error: {r['error'].get('message')}")
        return None
    return r['choices'][0]['message']['content']


def test_audio_multilingual():
    """测试多语种识别"""
    print("\n=== 多语种音频测试 ===")
    body = {
        "model": MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "input_audio",
                    "input_audio": {
                        "url": "https://ark-project.tos-cn-beijing.volces.com/doc_audio/ark_demo_audio.mp3",
                        "format": "mp3"
                    }
                },
                {
                    "type": "text",
                    "text": "请分析这段音频的语种和内容概要"
                }
            ]
        }]
    }
    resp = requests.post(f"{BASE_URL}/chat/completions", headers=headers, json=body, timeout=60)
    r = resp.json()
    if 'error' in r:
        print(f"Error: {r['error'].get('message')}")
        return None
    return r['choices'][0]['message']['content']


def test_audio_base64():
    """测试 base64 编码音频输入（通过 URL 获取音频后编码）"""
    import base64
    import io

    print("\n=== Base64 编码音频输入测试 ===")

    # 通过 URL 获取音频并转为 base64
    audio_url = "https://ark-project.tos-cn-beijing.volces.com/doc_audio/ark_demo_audio.mp3"
    try:
        audio_resp = requests.get(audio_url, timeout=30)
        audio_base64 = base64.b64encode(audio_resp.content).decode("utf-8")
        print(f"音频大小: {len(audio_resp.content) / 1024:.1f} KB")
    except Exception as e:
        print(f"获取音频失败: {e}")
        return None

    body = {
        "model": MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "input_audio",
                    "input_audio": {
                        "data": audio_base64,
                        "format": "mp3"
                    }
                },
                {
                    "type": "text",
                    "text": "请识别音频中的内容"
                }
            ]
        }]
    }
    resp = requests.post(f"{BASE_URL}/chat/completions", headers=headers, json=body, timeout=60)
    r = resp.json()
    if 'error' in r:
        print(f"Error: {r['error'].get('message')}")
        return None
    return r['choices'][0]['message']['content']


if __name__ == "__main__":
    print("=" * 50)
    print("Doubao-Seed-2.0-mini 音频输入测试")
    print("=" * 50)

    # 测试音频内容识别
    content = test_audio_transcription()
    if content:
        print(f"识别内容: {content[:200]}...")

    # 测试音频情绪识别
    emotion = test_audio_emotion_recognition()
    if emotion:
        print(f"情绪分析: {emotion[:200]}...")

    # 测试多语种
    multilingual = test_audio_multilingual()
    if multilingual:
        print(f"多语种分析: {multilingual[:200]}...")

    # 测试 base64 编码音频
    b64_result = test_audio_base64()
    if b64_result:
        print(f"Base64音频识别: {b64_result[:200]}...")

    print("\n=== 测试完成 ===")