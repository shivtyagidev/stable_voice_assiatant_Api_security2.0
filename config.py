# ─────────────────────────────────────────────────────────────
#  API CONFIG
# ─────────────────────────────────────────────────────────────

# Active model — change to switch provider
# Options: "gemini" | "nvidia" | "groq" | "openrouter" | "openai" | "grok" | "claude"
ACTIVE_MODEL = "gemini"

# ── OpenAI (GPT-4o) ──────────────────────────────────────────
OPENAI_API_KEY  = "sk-your-openai-key-here"
OPENAI_MODEL    = "gpt-4o"

# ── Google Gemini ─────────────────────────────────────────────
GEMINI_API_KEY  = "AIzaSyAeQFO0ATwD28etPVsuV65kA1i6bSXV-Ys"
GEMINI_MODEL    = "gemini-1.5-pro"

# ── xAI Grok ─────────────────────────────────────────────────
GROK_API_KEY    = "xai-your-grok-key-here"
GROK_MODEL      = "grok-beta"

# ── Nvidia NIM (Llama / Mistral free) ────────────────────────
NVIDIA_API_KEY  = "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"
NVIDIA_MODEL    = "meta/llama-3.1-70b-instruct"

# ── Groq (ultra fast, free) ───────────────────────────────────
GROQ_API_KEY    = "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"
GROQ_MODEL      = "llama-3.3-70b-versatile"

# ── OpenRouter (many models, free tier) ──────────────────────
OPENROUTER_API_KEY  = "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"
OPENROUTER_MODEL    = "meta-llama/llama-3.1-70b-instruct:free"

# ── Anthropic Claude ─────────────────────────────────────────
CLAUDE_API_KEY  = "sk-ant-your-claude-key-here"
CLAUDE_MODEL    = "claude-sonnet-4-6"

# ── Answer settings ───────────────────────────────────────────
MAX_TOKENS      = 1024
TEMPERATURE     = 0.3
SYSTEM_PROMPT   = (
    "You are an expert exam assistant. "
    "Give concise, accurate answers. "
    "For MCQ: state the answer letter first, then brief reason. "
    "For descriptive: clear structured answer in 3-5 sentences max."
)
