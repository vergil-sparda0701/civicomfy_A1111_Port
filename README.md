# Civicomfy for Automatic1111 (Stable Diffusion WebUI)

A port of the [Civicomfy](https://github.com/MoonGoblinDev/Civicomfy.git) ComfyUI extension to **Stable Diffusion AUTOMATIC1111 WebUI**.

## Features

- 🔍 **Search** Civitai models directly from the WebUI (using Meilisearch for fast results)
- ⬇ **Download** models with multi-connection or single-connection support
- 📋 **Download Queue** — concurrent downloads with progress tracking, cancellation, and retry
- 💾 **Metadata saving** — saves `.cminfo.json` with model info and `.preview.jpeg` for each downloaded model
- 🗂 **Smart path detection** — automatically uses A1111's model directories (Stable-diffusion, Lora, VAE, etc.)
- ⚙️ **Settings** — API key, NSFW thresholds, default model type

## Installation

1. Open your A1111 WebUI
2. Go to **Extensions → Install from URL**
3. Paste: `https://github.com/vergil-sparda0701/civicomfy_A1111_Port`
4. Click **Install**, then **Apply and restart UI**

Or clone manually into your `extensions/` folder:

```bash
cd stable-diffusion-webui/extensions
git clone https://github.com/vergil-sparda0701/civicomfy_A1111_Port
```

## Usage

After installation, a **🎨 Civicomfy** button appears in the bottom-right corner of the WebUI (and in the tab bar). Click it to open the downloader overlay.

### Download Tab
1. Paste a Civitai model URL or just the model ID
2. Select the model type and optionally a subfolder
3. Optionally specify a custom filename
4. Click **Start Download** — the download is added to the queue

### Search Tab
1. Type a search query
2. Optionally filter by model type and base model
3. Click a result card to auto-fill the Download tab

### Status Tab
- View active, queued, and completed downloads
- Cancel active downloads
- Retry failed downloads
- Open the containing folder for completed downloads

### Settings Tab
- Set your Civitai API key (or use the `CIVITAI_API_KEY` environment variable)
- Configure NSFW blur level for search results
- Set default model type

## Model Directories

The extension automatically maps Civitai model types to A1111's directories:

| Civitai Type | A1111 Directory |
|---|---|
| Checkpoint | `models/Stable-diffusion/` |
| Lora / LoCon / LyCORIS | `models/Lora/` |
| VAE | `models/VAE/` |
| Embedding | `models/embeddings/` |
| Hypernetwork | `models/hypernetworks/` |
| ControlNet | `models/ControlNet/` |
| Upscaler | `models/ESRGAN/` |
| Motion Module | `models/motion_module/` |

## Environment Variables

| Variable | Description |
|---|---|
| `CIVITAI_API_KEY` | Your Civitai API key (fallback when not set in UI settings) |

## Requirements

- Stable Diffusion WebUI (AUTOMATIC1111 / Vladmandic / similar forks)
- Python 3.8+
- `requests` (already included in A1111's environment)
- `gradio` (already included)

## Differences from the ComfyUI version

| Feature | ComfyUI | A1111 |
|---|---|---|
| UI Integration | ComfyUI menu button | Floating button + tab bar button |
| Model paths | `folder_paths` module | `modules.paths` module |
| API framework | aiohttp routes | FastAPI routes |
| JavaScript | ES modules | Self-contained IIFE |
| Custom model roots | Supported via JSON | Uses A1111's paths |

## Credits

Based on [Civicomfy](https://github.com/MoonGoblinDev/Civicomfy.git) by its original authors.
