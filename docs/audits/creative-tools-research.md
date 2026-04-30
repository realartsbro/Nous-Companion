# Creative Tools Research — Nous Companion Demo Video

**Date:** 2026-04-30  
**Scope:** ComfyUI Probe, Character Generation Workflows, Waifu-Sprites Analysis  
**Status:** Research Complete  

---

## Part 1: ComfyUI Probe

### 1.1 Installation Location

ComfyUI is installed at `D:\ComyBackup\ComfyUI-Easy-Install\` (Windows path).

**WSL Note:** Drive D: was not auto-mounted in this WSL session (only C:\ and E:\ are mounted by default). The installation was probed via `powershell.exe` from WSL to enumerate files.

**Installation structure:**
```
D:\ComyBackup\ComfyUI-Easy-Install\
├── python_embeded/          # Bundled Python environment
├── ComfyUI/                 # Main ComfyUI application
│   ├── main.py              # Entry point (EXISTS)
│   ├── server.py
│   ├── comfyui_version.py   # __version__ = "0.8.2"
│   ├── models/              # Model directories
│   ├── custom_nodes/        # Custom nodes
│   ├── input/
│   └── output/
├── update/
├── Add-ons/
│   ├── Nunchaku.bat
│   └── SageAttention.bat
├── run_nvidia_gpu.bat
├── run_nvidia_gpu_SageAttention.bat
├── Update All and RUN.bat
└── Update Comfy and RUN.bat
```

**Version:** ComfyUI 0.8.2 (from `comfyui_version.py`)

### 1.2 Runtime Status

- **ComfyUI Server:** NOT running (curl to `http://127.0.0.1:8188/system_stats` failed)
- **Entry point:** `main.py` exists at `ComfyUI/main.py` — can be started
- **Launcher:** Batch files present for NVIDIA GPU runs (`run_nvidia_gpu.bat`, etc.)

### 1.3 Installed Models

#### Checkpoints (25GB+ each — LTX Video models)
| File | Size |
|------|------|
| `ltx-2-19b-dev-fp8.safetensors` | ~25.2 GB |
| `ltx-2-19b-distilled-fp8.safetensors` | ~25.3 GB |
| `put_checkpoints_here` | (placeholder) |
| `Unconfirmed 211414.crdownload` | (partial download) |

#### LoRAs
| File | Notes |
|------|-------|
| `ltx-2-19b-lora-camera-control-dolly-left.safetensors` | Camera pan control |
| `ltx-2-19b-distilled-lora-384.safetensors` | Lower resolution variant |
| `ltx-2-19b-ic-lora-detailer.safetensors` | Detail enhancement |
| `put_loras_here` | (placeholder) |

#### VAE
- No VAE models installed (`put_vae_here` placeholder only)

#### ControlNet
- No ControlNet models installed (`put_controlnets_and_t2i_here` placeholder only)

#### Text Encoders
- `gemma_3_12B_it.safetensors` — Google Gemma 3 12B text encoder

#### CLIP
- No CLIP models installed (`put_clip_or_text_encoder_models_here` placeholder only)

#### CLIP Vision
- No CLIP Vision models installed (`put_clip_vision_models_here` placeholder)

#### Diffusion Models
- `MelBandRoformer_fp32.safetensors` — audio separation model (not image diffusion)

#### IP-Adapter
- **NOT installed** (directory does not exist)

#### PhotoMaker
- **NOT installed** (`put_photomaker_models_here` placeholder only)

#### Upscale Models
- None installed (placeholder only)

#### Style Models
- None installed (placeholder only)

#### UNET
- None installed (`put_unet_files_here` placeholder only)

#### LLM Models
- `Florence-2-large-PromptGen-v2.0` — Florence-2 prompt generation model

#### Key Takeaway
The installation is **primarily LTX Video-focused**. The two checkpoint models are both LTX Video 2 19B models (FP8). LoRAs are all LTX-related. This machine appears to be set up specifically for **video generation** rather than image generation. There are no standard SDXL, Flux, or SD 1.5 checkpoint models installed. No IP-Adapter, PhotoMaker, or ControlNet models — all of which would be needed for character-consistent workflows.

### 1.4 Custom Nodes (61 installed)

**Core/Infrastructure:**
- `ComfyUI-Manager`
- `cg-use-everywhere`
- `rgthree-comfy`
- `comfyui-essentials` / `comfyui-essentials_mb`
- `comfyui-custom-scripts`
- `comfyui-kjnodes`
- `comfyui-various`
- `comfyui-mxtoolkit`
- `kaytool`
- `RES4LYF`
- `comfyui-logicutils`
- `was-node-suite-comfyui`
- `comfyui-rvtools_v2`
- `teacache`

**Video/Animation:**
- `ComfyUI-LTXVideo` — LTX Video native nodes
- `comfyui-ltxvideolora` — LTX Video LoRA loader
- `ComfyUI-WanVideoWrapper` — WAN Video support
- `comfyui-frame-interpolation` — Frame interpolation
- `ComfyUI-FramePackWrapper` — Frame packing
- `comfyui-dream-video-batches` — Batch video processing
- `ComfyUI-SeedVR2_VideoUpscaler` — Video upscaling
- `comfyui-videohelpersuite` — Video helper tools

**Image Generation/Editing:**
- `ComfyUI-Easy-Use` — All-in-one image gen nodes
- `ComfyUI-AdvancedRefluxControl` — Advanced Flux control
- `ComfyUI-GGUF` — GGUF model support
- `ComfyUI-nunchaku` — Nunchaku acceleration
- `ComfyUI-TiledDiffusion` — Tiled diffusion for large images
- `comfyui-fluxtrainer` — Flux model training
- `comfyui-seamless-tiling` — Seamless texture generation
- `ComfyUI-ToSVG` — Image to SVG

**Control/Spatial:**
- `comfyui_controlnet_aux` — ControlNet auxiliary preprocessors (installed but no models)
- `comfyui-depthanythingv2` — Depth estimation
- `cg-use-everywhere` — Node wiring helpers

**Inpainting/Image Editing:**
- `comfyui-inpaint-cropandstitch` — Inpainting crop & stitch
- `comfyui-inspyrenet-rembg` — Background removal (RMBG)

**Audio/TTS:**
- `ComfyUI-Sonic` — Sonic audio generation
- `ComfyUI-MegaTTS` / `ComfyUI-ChatterBox_SRT_Voice`
- `ComfyUI-HiggsAudio_2` / `comfyui-kokoro` (Kokoro TTS)
- `ComfyUI-MelBandRoFormer` — Audio separation
- `ComfyUI-Vaja-Ai4thai`
- `tts_audio_suite` / `VibeVoice-ComfyUI` / `megatts3-mw`
- `ComfyUI-MegaTTS` (standalone in root)
- `audio-separation-nodes-comfyui`

**Vision/LLM:**
- `ComfyUI-Florence2` — Florence-2 vision-language
- `ComfyUI-Searge_LLM` — LLM integration
- `comfyui-ollama` — Ollama LLM
- `comfyui-omnigen` — OmniGen
- `janus-pro` — Janus Pro multimodal

**Other:**
- `ComfyUI-Chibi-Nodes` — Utility nodes
- `ComfyUI-Crystools` — Monitoring/settings
- `comfyui-image-saver` — Image saving
- `comfyui-lora-manager` / `comfyui-lora-auto-trigger-words`
- `comfyui-multigpu` — Multi-GPU support
- `comfyui-itools` — iTools
- `ComfyUI-AdvancedLivePortrait` — Live Portrait
- `canvas_tab` — Canvas UI
- `cocotools_io`
- `ComfyUI_Comfyroll_CustomNodes`
- `comfyui_layerstyle`
- `ComfyUI_Sonic`
- `controlaltai-nodes`
- `websocket_image_save.py`

### 1.5 AnimateDiff Status

**AnimateDiff is NOT installed.** No AnimateDiff nodes or variants were found in the custom_nodes directory. The closest video/animation capabilities come from:
- `ComfyUI-LTXVideo` — LTX Video 2 generation
- `ComfyUI-WanVideoWrapper` — WAN Video
- `comfyui-frame-interpolation` — Interpolation
- `comfyui-dream-video-batches` — Batch processing

### 1.6 LTX Video Models

**LTX Video is the primary installed model family.** Found in multiple directories:

| Location | File |
|----------|------|
| `models/checkpoints/` | `ltx-2-19b-dev-fp8.safetensors` (25.2 GB) |
| `models/checkpoints/` | `ltx-2-19b-distilled-fp8.safetensors` (25.3 GB) |
| `models/loras/` | `ltx-2-19b-lora-camera-control-dolly-left.safetensors` |
| `models/loras/` | `ltx-2-19b-distilled-lora-384.safetensors` |
| `models/loras/` | `ltx-2-19b-ic-lora-detailer.safetensors` |
| `models/latent_upscale_models/` | `ltx-2-spatial-upscaler-x2-1.0.safetensors` |

This is a strong foundation for **video generation** but the machine lacks the image generation models (SDXL, Flux, SD1.5) needed for sprite/character sheet creation pipelines.

---

## Part 2: Character Generation Workflows Research

### 2.1 Current SOTA for Local Inpainting (April 2026)

Based on web research:

**Top contenders:**
1. **Flux Fill Dev** — Still considered the "meta" for ComfyUI inpainting as of 2026. High quality, but slower than alternatives. Works well with GGUF quantized versions for lower VRAM. Best when combined with Redux for style matching.
   
2. **Flux Fill Pro** — Proprietary version with better prompt adherence but limited to API access. Outperforms SDXL inpainting across quality metrics.

3. **SDXL Inpainting** — Still viable, faster than Flux, good for 8GB VRAM. Lower quality than Flux but more accessible.

4. **Legacy SD 1.5 Inpainting** — Fastest option, runs on 4GB VRAM, but noticeably lower quality.

**Key workflow patterns:**
- Flux Fill + ControlNet (inpaint) for structure guidance
- Flux Fill + Redux for reference/style matching
- Inpaint Crop & Stitch (custom node already installed) for memory efficiency

**Relevance to Nous Companion:** For generating character sprite assets, inpainting would primarily be used for fixing/editing generated sprites, not for the core generation pipeline. The installed `comfyui-inpaint-cropandstitch` node is available but requires Flux or SDXL checkpoint models to function.

### 2.2 ComfyUI Workflows for Sprite Sheet / Character Generation

**Found resources:**

1. **Sprite Sheet Generator (Comfy.org workflow):**
   - Template: `comfy.org/workflows/templates-sprite_sheet-...`
   - Designed for game developers to generate sprite animations
   - Useful for producing multiple frames from a single character

2. **Reddit — "One image in, 2D animated + customizable character out":**
   - r/comfyui thread `1sve5id`
   - Animation-ready rigged character generation workflow
   - Mentions Blender ComfyUI Wrapper for pipeline integration

3. **"Consistent Characters: Low VRAM (2026 Update)" (YouTube):**
   - Building consistent character workflows from scratch
   - Focus on low-VRAM techniques (relevant since this machine lacks typical image gen models)

4. **ThinkDiffusion Guide — Consistent Characters with Flux:**
   - Uses IP-Adapter + Flux for character consistency
   - Character sheet generation from reference images
   - Requires IP-Adapter models (not currently installed)

5. **"Create a consistent character animation sprite using ComfyUI" (itch.io):**
   - Step 1: Generate character in T-pose/A-pose using Pose ControlNet
   - Step 2: Use Qwen Image Edit and Flux for refinement
   - Step 3: Rig and animate

**Workflow architecture pattern for character sheets:**
```
Input Image (single ref)
  → IP-Adapter / Reference ControlNet → Extract face/features
  → Pose ControlNet → Set character pose (T-pose, A-pose)
  → Multi-view prompt → Generate front/back/side views
  → Inpainting → Fix inconsistencies
  → Up scaling → Final sheet
```

**Key finding:** Most modern character consistency workflows (2026) rely on a combination of:
- **IP-Adapter** for face/feature preservation
- **Flux or SDXL** as the backbone model
- **ControlNet (OpenPose)** for pose control
- **LoRA** for character-specific fine-tuning

**None of these are currently installed** on this ComfyUI instance (no IP-Adapter, no SDXL/Flux checkpoints, no ControlNet models, no pose models).

### 2.3 Tools for Generating Animated Character Assets from Reference

| Tool | Approach | Relevance |
|------|----------|-----------|
| **AutoSprite (autosprite.io)** | Upload sprite → pick moveset → export spritesheet | Commercial, not local |
| **PixelLab (pixellab.ai)** | Text/prompt-based pixel art generator | Pixel art focused |
| **Ludo.ai** | Text → animated spritesheet | Game asset focused |
| **fofr/cog-consistent-character** | Reference → multiple poses via IP-Adapter | Open source, 2yo |
| **ComfyUI IMG2Rig workflow** | Single image → rigged animation | Experimental |

### 2.4 Cutout Sprite Animation Generation

No dedicated "cutout sprite" animation ComfyUI workflows were found via web search. This appears to be a niche gap. The closest approaches:
- Frame interpolation between keyframes (via `comfyui-frame-interpolation`)
- Video generation from reference (via LTX Video or WAN Video)
- Manual posing with ControlNet across multiple frames

---

## Part 3: Waifu-Sprites Comparison

### 3.1 Repository Overview

**Repo:** `github.com/waifuai/waifu-sprites`  
**Stars:** 9  
**Last commit:** 4 hours ago (Apr 30, 2026) — actively maintained  
**License:** Not specified (public repository)

### 3.2 Architecture

```
┌─────────────────────────────────────────────────┐
│ waifu-sprites (Windows native)                  │
│                                                  │
│ server.js (:8000)    tts_server.py (:8001)       │
│ ┌─────────────────┐  ┌────────────────────────┐ │
│ │ Sprite display   │  │ Kokoro TTS server      │ │
│ │ POST /state      │  │ POST /tts              │ │
│ │ GET /current_state│  │ POST /clear            │ │
│ │ GET /sets        │  │ POST /skip             │ │
│ │ GET /display_stats│  │                       │ │
│ └────────┬────────┘  └────────┬───────────────┘ │
│          │                    │                   │
│    index.html (browser)       │                   │
│    ┌──────────────────┐       │                   │
│    │ Sprite display    │       │                   │
│    │ TTS controls      │       │                   │
│    └──────────────────┘       │                   │
└──────────────────────────────────────────────────┘
          ▲                           ▲
          │ HTTP :8000                │ file queue
          │                           │
┌─────────┴───────────────────────────┴───────────┐
│ WSL2 / hermes-agent                              │
│                                                   │
│ src/waifu_hook.py (symlink → src/)                │
│ ├─ set_waifu_state() → HTTP POST to :8000         │
│ ├─ on_agent_reply() → queues TTS file              │
│ ├─ emotion detection + TTS chunking                │
│ └─ sprite usage tracking → stats.json              │
│                                                   │
│ src/waifu.py                                      │
│ └─ Monkey-patches HermesCLI to inject hooks       │
└───────────────────────────────────────────────────┘
```

### 3.3 Key Features

**Sprite System (3 modes):**
1. **Directory Mode** — Individual PNG files per state (`1.png` = idle, `2.png` = listening, etc.)
2. **Spritesheet Mode** — Single 4×3 grid PNG, auto-cropped via CSS `background-position`
3. **MP4 Mode** — Hardware-accelerated H.264 video per state (higher priority than PNG)

**12 Action States:** idle, listening, speaking, thinking, typing, searching, calculating, fixing, success, error, alert, sleeping

**12 Emotion States (e1-e12):** happy, amused, empathetic, curious, confused, surprised, embarrassed, confident, annoyed, overwhelmed, determined, affectionate

**TTS Integration:** Kokoro TTS server with chunk queuing, skip back/forward, stop controls

**Tool→State Mapping:** Comprehensive mapping of 50+ hermes-agent tools to sprite states (e.g., `web_search` → searching, `terminal` → fixing, `read_file` → typing)

**Agent Integration via Monkey-Patching:**
- `waifu.py` wraps `HermesCLI._init_agent` and `HermesCLI.chat`
- Tool callbacks wrapped to trigger sprite state changes
- Emotion detection from agent responses
- Background notification on reply (taskbar flash)

**Display Tracking:** Stats persistence (`display_stats.json`) for tracking which states were actually shown

### 3.4 Comparison with Nous Companion

| Dimension | Waifu-Sprites | Nous Companion (current) |
|-----------|---------------|--------------------------|
| **Purpose** | Face/UI for agentic LLM orchestrators | Demo video for Nous Research |
| **Platform** | Web-based (Node.js server + browser) | TBD (demo video concept) |
| **Character System** | 2D sprite sheets / MP4 videos | TBD (likely animated character) |
| **States** | 12 action + 12 emotion states | TBD |
| **TTS** | Kokoro TTS with chunk queuing | TBD |
| **Agent Integration** | Monkey-patches hermes-agent CLI | TBD |
| **Asset Format** | PNG spritesheets / MP4 video loops | TBD |
| **Emotion Detection** | Rule-based keyword matching | TBD |
| **Usage Tracking** | Full state duration stats | TBD |
| **Multi-Character** | Multiple sets via assets/ folder | TBD |
| **Launch Time** | Instant | TBD |
| **Hardware Requirements** | Minimal (browser does rendering) | TBD |

### 3.5 Architecture Lessons for Nous Companion

1. **Decoupled Brain/Face architecture:** The separation of the LLM agent (brain) from the sprite display (face) via HTTP is elegant. The agent never blocks on rendering.

2. **Simple state protocol:** A single `POST /state` endpoint with a string state identifier is all that's needed for full sprite control.

3. **Multi-format fallback:** Supporting PNG (fallback) → Spritesheet (efficient) → MP4 (best) gives flexibility.

4. **Display tracking:** Telemetry on what's actually displayed vs. what was requested is useful for debugging and optimization.

5. **Manual browse mode:** Pause auto-follow to browse states manually — useful for demo recording.

6. **Cached video selection:** Random video selection per state with caching avoids flickering.

7. **Symlink-based hot-reload:** `src/` is symlinked into hermes-agent so edits take effect immediately.

8. **Kokoro TTS integration:** On-device TTS with fine-grained control (skip, stop, chunk display).

9. **File queue for cross-OS communication:** WSL2 ↔ Windows communication via file queue for TTS, HTTP for sprite state.

### 3.6 Gap Analysis for Nous Companion

**What Waifu-Sprites has that Nous Companion might want:**
- Battle-tested agent hook architecture
- Comprehensive tool→state mapping
- Emotion detection from LLM responses
- TTS chunk queuing with skip controls

**What Waifu-Sprites lacks that Nous Companion might need:**
- 3D/VRM character support (wireframe only for 2D)
- No character generation pipeline (expects hand-crafted sprites)
- No integrated ComfyUI workflow for asset generation
- No lip-sync (TTS plays but sprite doesn't auto-lip-sync)
- No animation blending between states
- Single monologue/reply mode (no persistent chat UI)

---

## Summary & Recommendations

### ComfyUI Status
- **Running:** No (can be started via batch files)
- **Primary capability:** LTX Video 2 (video generation)
- **Missing for character work:** SDXL/Flux checkpoints, IP-Adapter, ControlNet models, AnimateDiff, LoRA character models
- **Installed base to leverage:** LTX Video nodes, video helpers, inpainting utilities, frame interpolation

### Character Generation Pipeline (Recommended Approach)
Based on current SOTA research, a character generation workflow for the demo video would need:
1. **Backbone model** — Flux or SDXL (needs to be installed)
2. **IP-Adapter** — For face/feature consistency across poses (needs to be installed)
3. **ControlNet (OpenPose)** — For pose guidance in sprite sheets (needs to be installed)
4. **LTX Video** — Already installed, could be used for animating generated sprites
5. **Post-processing** — Frame interpolation, upscaling (tools already available)

### Waifu-Sprites Integration Potential
For the Nous Companion demo video, waifu-sprites provides a proven reference for:
- Agent-visual-state architecture
- Lightweight web-based character display
- Multi-character/emotion system
- TTS integration patterns

The repo is actively maintained (commit 4 hours ago) and directly integrates with hermes-agent, making it a strong reference implementation for the companion's visual layer.

---

*End of research report. No images were generated or ComfyUI started — this is a research-only audit.*
