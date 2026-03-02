# ================================================
# civicomfy_core/config.py
# Configuration for A1111 version of Civicomfy
# ================================================
import os

# --- Configuration ---
MAX_CONCURRENT_DOWNLOADS = 3
DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1MB
DEFAULT_CONNECTIONS = 4
DOWNLOAD_HISTORY_LIMIT = 100
DOWNLOAD_TIMEOUT = 60
HEAD_REQUEST_TIMEOUT = 25
METADATA_DOWNLOAD_TIMEOUT = 20

# --- Paths ---
PLUGIN_ROOT = os.path.dirname(os.path.realpath(__file__))
EXTENSION_ROOT = os.path.dirname(PLUGIN_ROOT)

# --- A1111 Model Directories ---
# These are resolved at runtime using A1111's paths
def get_a1111_model_dirs():
    """Get model directories from A1111's modules.paths"""
    try:
        from modules import paths as a1111_paths
        base = a1111_paths.models_path
    except Exception:
        base = os.path.join(os.path.dirname(EXTENSION_ROOT), "models")

    return {
        "checkpoint":       os.path.join(base, "Stable-diffusion"),
        "lora":             os.path.join(base, "Lora"),
        "locon":            os.path.join(base, "Lora"),
        "lycoris":          os.path.join(base, "Lora"),
        "vae":              os.path.join(base, "VAE"),
        "embedding":        os.path.join(base, "embeddings"),
        "hypernetwork":     os.path.join(base, "hypernetworks"),
        "controlnet":       os.path.join(base, "ControlNet"),
        "upscaler":         os.path.join(base, "ESRGAN"),
        "motionmodule":     os.path.join(base, "motion_module"),
        "diffusionmodels":  os.path.join(base, "Stable-diffusion"),
        "unet":             os.path.join(base, "Stable-diffusion"),
        "poses":            os.path.join(base, "Poses"),
        "wildcards":        os.path.join(base, "wildcards"),
        "other":            os.path.join(base, "other"),
    }

# Model type display names for the UI
MODEL_TYPE_DISPLAY = {
    "checkpoint":       "Checkpoint",
    "lora":             "Lora",
    "locon":            "LoCon",
    "lycoris":          "LyCORIS",
    "vae":              "VAE",
    "embedding":        "Embedding (Textual Inversion)",
    "hypernetwork":     "Hypernetwork",
    "controlnet":       "ControlNet",
    "upscaler":         "Upscaler",
    "motionmodule":     "Motion Module",
    "diffusionmodels":  "Diffusion Models",
    "unet":             "Unet",
    "poses":            "Poses",
    "wildcards":        "Wildcards",
    "other":            "Other",
}

# Civitai API type mapping (internal key -> Civitai API 'types' param value)
CIVITAI_API_TYPE_MAP = {
    "checkpoint":       "Checkpoint",
    "lora":             "LORA",
    "locon":            "LoCon",
    "lycoris":          "LORA",
    "vae":              "VAE",
    "embedding":        "TextualInversion",
    "hypernetwork":     "Hypernetwork",
    "controlnet":       "Controlnet",
    "motionmodule":     "MotionModule",
    "poses":            "Poses",
    "wildcards":        "Wildcards",
    "upscaler":         "Upscaler",
    "unet":             "UNET",
    "diffusionmodels":  "Checkpoint",
}

AVAILABLE_BASE_MODELS = [
    "AuraFlow", "CogVideoX", "Flux.1 D", "Flux.1 S", "Hunyuan 1", "Hunyuan Video",
    "Illustrious", "Kolors", "LTXV", "Lumina", "Mochi", "NoobAI", "ODOR", "Other",
    "PixArt E", "PixArt a", "Playground v2", "Pony", "SD 1.4", "SD 1.5",
    "SD 1.5 Hyper", "SD 1.5 LCM", "SD 2.0", "SD 2.0 768", "SD 2.1", "SD 2.1 768",
    "SD 2.1 Unclip", "SD 3", "SD 3.5", "SD 3.5 Large", "SD 3.5 Large Turbo",
    "SD 3.5 Medium", "SDXL 0.9", "SDXL 1.0", "SDXL 1.0 LCM", "SDXL Distilled",
    "SDXL Hyper", "SDXL Lightning", "SDXL Turbo", "SVD", "SVD XT", "Stable Cascade",
    "Wan Video"
]

# Filename suffixes for metadata/preview
METADATA_SUFFIX = ".cminfo.json"
PREVIEW_SUFFIX = ".preview.jpeg"
