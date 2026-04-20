import streamlit as st
import json
import requests
import moviepy.editor as mp
from moviepy.editor import VideoFileClip, AudioFileClip, CompositeVideoClip, TextClip
from pathlib import Path
from langgraph.graph import StateGraph, END
from typing import TypedDict, List
from langchain_ollama import ChatOllama

# ==========================
# 模型 & API
# ==========================
llm = ChatOllama(model="qwen2.5:1.5b", temperature=0.1)
PEXELS_API_KEY = "P9hWpc0HY6ievPhbHh1MT17Y3GvOrQ9vPrrY4jgib1etzaXdtTbh0jn3"

# ==========================
# 状态定义
# ==========================
class VideoState(TypedDict):
    topic: str
    script: str
    storyboard: list
    material_paths: List[str]
    final_video_path: str

# ======================
# 1. AI生成视频脚本
# ======================
def generate_script(state: VideoState):
    prompt = f"""你是专业短视频编剧，生成15秒治愈系短视频脚本。
    主题：{state['topic']}
    输出格式：
    时长：15秒
    台词：
    - 镜头一：xxx
    - 镜头二：xxx
    - 镜头三：xxx
    镜头要求：画面温馨、节奏舒缓，适合竖屏播放
    """
    response = llm.invoke(prompt)
    return {"script": response.content}

# ======================
# 2. AI根据脚本自动生成英文分镜关键词（修复JSON解析错误）
# ======================
def generate_storyboard_from_script(script: str):
    prompt = f"""根据下面的短视频脚本，生成对应的英文分镜关键词，严格输出JSON数组，不要任何解释。
    每个镜头包含scene、content（英文关键词，单个词优先）、duration（3秒）、subtitle（中文字幕，简短）。
    脚本：{script}
    输出格式示例：
    [
        {{"scene":1,"content":"sunrise","duration":3,"subtitle":"日出晨光"}},
        {{"scene":2,"content":"bird flying","duration":3,"subtitle":"小鸟飞过"}}
    ]
    """
    response = llm.invoke(prompt)
    try:
        storyboard = json.loads(response.content.strip())
        # 兜底修复：如果返回不是列表，用默认分镜
        if not isinstance(storyboard, list):
            raise ValueError("AI返回的不是列表")
        return storyboard
    except Exception as e:
        st.warning(f"AI分镜解析失败，使用默认分镜：{e}")
        # 兜底默认分镜，确保流程不中断
        return [
            {"scene":1,"content":"sunrise","duration":3,"subtitle":"镜头1"},
            {"scene":2,"content":"bird flying","duration":3,"subtitle":"镜头2"},
            {"scene":3,"content":"mountain","duration":3,"subtitle":"镜头3"}
        ]

# ======================
# 3. 下载素材（仅点击按钮后执行）
# ======================
def search_materials(state: VideoState):
    paths = []
    headers = {"Authorization": PEXELS_API_KEY}
    failed_scenes = []

    for i, scene in enumerate(state["storyboard"]):
        try:
            st.info(f"🔍 搜索素材: {scene['content']}")
            res = requests.get(
                "https://api.pexels.com/videos/search",
                headers=headers,
                params={"query": scene["content"], "per_page": 1, "orientation": "portrait"}
            )
            data = res.json()

            if not data.get("videos"):
                failed_scenes.append(scene["content"])
                st.warning(f"⚠️ 未找到 '{scene['content']}' 相关素材")
                continue

            video_url = data["videos"][0]["video_files"][0]["link"]
            save_path = f"material_{i}.mp4"

            st.info(f"📥 下载中: {save_path}")
            with open(save_path, "wb") as f:
                f.write(requests.get(video_url).content)
            paths.append(save_path)
            st.success(f"✅ 下载完成: {save_path}")
        except Exception as e:
            failed_scenes.append(scene["content"])
            st.error(f"❌ 下载失败 ({scene['content']}): {e}")
            continue
    
    if failed_scenes:
        st.warning("💡 部分素材下载失败，建议使用更通用的关键词：")
        common = ["sunrise", "nature", "ocean", "forest", "city", "bird", "water", "sky"]
        st.write(" | ".join([f"`{kw}`" for kw in common]))
    return {"material_paths": paths}

# ======================
# 4. 剪辑视频（加字幕+背景音乐，修复中文字体）
# ======================
def add_subtitle_to_clip(clip, subtitle_text, duration, start_time):
    # 适配不同系统的字体，避免报错
    font_path = "SimHei" if Path("C:/Windows/Fonts/simhei.ttf").exists() else "DejaVu Sans"
    text_clip = TextClip(
        subtitle_text,
        fontsize=40,
        color="white",
        font=font_path,
        stroke_color="black",
        stroke_width=2
    ).set_position(("center", "bottom")).set_duration(duration).set_start(start_time)
    return CompositeVideoClip([clip, text_clip])

def edit_video(state: VideoState):
    paths = state["material_paths"]
    if not paths:
        st.error("❌ 没有可用素材，无法生成视频")
        return {"final_video_path": ""}

    clips = []
    total_duration = 0
    for i, p in enumerate(paths):
        if Path(p).exists():
            scene = state["storyboard"][i]
            clip = VideoFileClip(p).subclip(0, scene["duration"])
            clip_with_sub = add_subtitle_to_clip(clip, scene["subtitle"], scene["duration"], total_duration)
            clips.append(clip_with_sub)
            total_duration += scene["duration"]

    final_video = mp.concatenate_videoclips(clips, method="chain")
    
    # 背景音乐（可选）
    if Path("default_bg_music.mp3").exists():
        audio = AudioFileClip("default_bg_music.mp3").volumex(0.3)
        if audio.duration > final_video.duration:
            audio = audio.subclip(0, final_video.duration)
        final_video = final_video.set_audio(audio)

    final_path = "ai_generated_video.mp4"
    final_video.write_videofile(final_path, fps=24, codec="libx264", audio_codec="aac")
    st.success(f"✅ 视频剪辑完成：{final_path}")
    return {"final_video_path": final_path}

# ==========================
# Streamlit 界面（修复版）
# ==========================
st.set_page_config(page_title="AI 视频生成", layout="wide")
st.title("🎬 AI 全自动短视频生成工具")

# 初始化会话状态（修复空值问题）
if "step" not in st.session_state:
    st.session_state.step = 0
if "storyboard" not in st.session_state:
    st.session_state.storyboard = []
if "material_paths" not in st.session_state:
    st.session_state.material_paths = []
if "script" not in st.session_state:
    st.session_state.script = ""
if "final_video_path" not in st.session_state:
    st.session_state.final_video_path = ""

# 第一步：输入主题，生成脚本+AI自动分镜
topic = st.text_input("🎥 输入视频主题", value="海边日出")

if st.button("1️⃣ AI生成脚本+分镜关键词"):
    # 生成脚本
    script_result = generate_script({"topic": topic})
    st.session_state.script = script_result["script"]
    # AI根据脚本自动生成分镜关键词
    st.session_state.storyboard = generate_storyboard_from_script(st.session_state.script)
    st.session_state.step = 1
    st.success("✅ 脚本与AI分镜生成完成！")

# 第二步：固定渲染脚本+分镜编辑区域（无论step多少，只要有数据就显示）
if st.session_state.script:
    st.subheader("📝 生成的视频脚本")
    st.text(st.session_state.script)

if st.session_state.storyboard:
    st.subheader("✏️ 编辑AI生成的分镜关键词（必须修改后再下载素材）")
    edited_storyboard = []
    for i, scene in enumerate(st.session_state.storyboard):
        # 兜底处理：确保每个场景都有字段
        scene = scene or {}
        content = scene.get("content", "nature")
        duration = scene.get("duration", 3)
        subtitle = scene.get("subtitle", f"镜头{i+1}")

        col1, col2, col3 = st.columns(3)
        with col1:
            new_content = st.text_input(f"镜头{i+1} 搜索关键词（英文）", value=content, key=f"content_{i}")
        with col2:
            new_duration = st.number_input(f"镜头{i+1} 时长（秒）", min_value=1, max_value=10, value=duration, key=f"duration_{i}")
        with col3:
            new_subtitle = st.text_input(f"镜头{i+1} 字幕（中文）", value=subtitle, key=f"subtitle_{i}")
        
        edited_storyboard.append({
            "scene": i+1,
            "content": new_content,
            "duration": new_duration,
            "subtitle": new_subtitle
        })
    # 更新会话状态
    st.session_state.storyboard = edited_storyboard

    # 第三步：手动点击下载素材
    if st.button("2️⃣ 下载素材（仅点击后执行）"):
        with st.spinner("正在下载素材..."):
            result = search_materials({"storyboard": st.session_state.storyboard})
            st.session_state.material_paths = result["material_paths"]
            st.session_state.step = 2

# 第四步：生成视频（素材下载完成后）
if st.session_state.step >= 2 and len(st.session_state.material_paths) > 0:
    if st.button("3️⃣ 生成最终视频（加字幕+背景音乐）"):
        with st.spinner("正在剪辑视频..."):
            result = edit_video({
                "storyboard": st.session_state.storyboard,
                "material_paths": st.session_state.material_paths
            })
            st.session_state.final_video_path = result["final_video_path"]
            st.session_state.step = 3

# 第五步：固定渲染最终视频区域（无论step多少，只要有文件就显示）
if st.session_state.final_video_path and Path(st.session_state.final_video_path).exists():
    st.subheader("🎥 最终成品视频")
    st.video(st.session_state.final_video_path)
    with open(st.session_state.final_video_path, "rb") as f:
        st.download_button("📥 下载成品视频", f, file_name=f"{topic}_成品视频.mp4")
else:
    if st.session_state.step >= 3:
        st.warning("⚠️ 视频生成失败，请检查素材是否下载成功")

# 清理临时文件
if st.sidebar.button("🧹 清理素材文件"):
    for file in Path(".").glob("material_*.mp4"):
        file.unlink()
    st.sidebar.success("✅ 素材文件已清理")