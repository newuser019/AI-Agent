import json
import requests
from langgraph.graph import StateGraph, END
from typing import TypedDict, List
import moviepy.editor as mp
from pathlib import Path

# ====================== Ollama 本地模型 ======================
from langchain_ollama import ChatOllama
llm = ChatOllama(model="qwen2.5:1.5b", temperature=0.1)

# ====================== Pexels API Key ======================
PEXELS_API_KEY = "P9hWpc0HY6ievPhbHh1MT17Y3GvOrQ9vPrrY4jgib1etzaXdtTbh0jn3"

# ====================== 状态定义 ======================
class VideoState(TypedDict):
    topic: str
    script: str
    storyboard: list
    material_paths: List[str]
    final_video_path: str

# ====================== 1. 生成脚本 ======================
def generate_script(state: VideoState):
    prompt = f"""你是专业短视频编剧，根据主题生成15秒短视频脚本。
    主题：{state['topic']}
    输出：时长、台词、镜头要求。简洁清晰。"""
    response = llm.invoke(prompt)
    print("\n📝 生成脚本：")
    print(response.content)
    return {"script": response.content}

# ====================== 2. 生成分镜 ======================
def generate_storyboard(state: VideoState):
    storyboard = [
        {"scene":1, "content":"sunset beach", "duration":3, "subtitle":"海边日落"},
        {"scene":2, "content":"ocean waves", "duration":3, "subtitle":"海浪拍岸"}
    ]
    print("\n🎬 生成分镜：")
    print(storyboard)
    return {"storyboard": storyboard}

# ====================== 3. 下载 Pexels 素材 ======================
def search_materials(state: VideoState):
    paths = []
    headers = {"Authorization": PEXELS_API_KEY}
    print("\n📥 开始下载素材...")

    for i, scene in enumerate(state["storyboard"]):
        try:
            res = requests.get(
                "https://api.pexels.com/videos/search",
                headers=headers,
                params={"query": scene["content"], "per_page": 1}
            )
            data = res.json()
            if data.get("videos"):
                video_url = data["videos"][0]["video_files"][0]["link"]
                save_path = f"material_{i}.mp4"

                with open(save_path, "wb") as f:
                    f.write(requests.get(video_url).content)

                paths.append(save_path)
                print(f"✅ 已下载：{save_path}")
        except Exception as e:
            print(f"❌ 下载失败：{e}")
            continue

    print(f"📦 共下载 {len(paths)} 个素材")
    return {"material_paths": paths}

# ====================== 4. 剪辑视频 ======================
def edit_video(state: VideoState):
    paths = state["material_paths"]
    if not paths:
        print("\n⚠️ 无素材，无法生成真实视频")
        return {"final_video_path": ""}

    clips = []
    for p in paths:
        if Path(p).exists():
            clip = mp.VideoFileClip(p).subclip(0, 3)
            clips.append(clip)

    final_path = "ai_generated_video.mp4"
    final_video = mp.concatenate_videoclips(clips)
    final_video.write_videofile(final_path, fps=24)
    return {"final_video_path": final_path}

# ====================== 工作流（已修复）======================
workflow = StateGraph(VideoState)
workflow.add_node("script_agent", generate_script)
workflow.add_node("storyboard_agent", generate_storyboard)
workflow.add_node("material_agent", search_materials)
workflow.add_node("edit_agent", edit_video)  # 这里是对的

workflow.set_entry_point("script_agent")
workflow.add_edge("script_agent", "storyboard_agent")
workflow.add_edge("storyboard_agent", "material_agent")
workflow.add_edge("material_agent", "edit_agent")  # 这里修复了！
workflow.add_edge("edit_agent", END)
app = workflow.compile()

# ====================== 运行 ======================
if __name__ == "__main__":
    print("🚀 开始运行 AI 视频创作助手...")
    result = app.invoke({
        "topic": "治愈系海边日出短视频",
        "script": "",
        "storyboard": [],
        "material_paths": [],
        "final_video_path": ""
    })
    print("\n🎉 全部完成！")
    print("最终视频：", result["final_video_path"])