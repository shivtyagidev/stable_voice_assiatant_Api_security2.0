# -*- coding: utf-8 -*-
"""
Multi-model API client.
Supports: OpenAI, Gemini, Grok, Nvidia NIM, Claude
Switch model in config.py — no code change needed.
"""
import config


def ask(question: str) -> str:
    model = config.ACTIVE_MODEL.lower().strip()
    if model == "openai":
        return _ask_openai(question)
    elif model == "gemini":
        return _ask_gemini(question)
    elif model == "grok":
        return _ask_grok(question)
    elif model == "nvidia":
        return _ask_nvidia(question)
    elif model == "groq":
        return _ask_groq(question)
    elif model == "openrouter":
        return _ask_openrouter(question)
    elif model == "claude":
        return _ask_claude(question)
    else:
        return f"[ERROR] Unknown model: {model}. Check config.py ACTIVE_MODEL"


# ── OpenAI ───────────────────────────────────────────────────
def _ask_openai(question: str) -> str:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": config.SYSTEM_PROMPT},
                {"role": "user",   "content": question},
            ],
            max_tokens=config.MAX_TOKENS,
            temperature=config.TEMPERATURE,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"[OpenAI Error] {e}"


# ── Google Gemini ─────────────────────────────────────────────
def _ask_gemini(question: str) -> str:
    try:
        import google.generativeai as genai
        genai.configure(api_key=config.GEMINI_API_KEY)
        model = genai.GenerativeModel(
            model_name=config.GEMINI_MODEL,
            system_instruction=config.SYSTEM_PROMPT,
        )
        resp = model.generate_content(
            question,
            generation_config=genai.GenerationConfig(
                max_output_tokens=config.MAX_TOKENS,
                temperature=config.TEMPERATURE,
            ),
        )
        return resp.text.strip()
    except Exception as e:
        return f"[Gemini Error] {e}"


# ── xAI Grok ─────────────────────────────────────────────────
def _ask_grok(question: str) -> str:
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=config.GROK_API_KEY,
            base_url="https://api.x.ai/v1",
        )
        resp = client.chat.completions.create(
            model=config.GROK_MODEL,
            messages=[
                {"role": "system", "content": config.SYSTEM_PROMPT},
                {"role": "user",   "content": question},
            ],
            max_tokens=config.MAX_TOKENS,
            temperature=config.TEMPERATURE,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"[Grok Error] {e}"


# ── Nvidia NIM ────────────────────────────────────────────────
def _ask_nvidia(question: str) -> str:
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=config.NVIDIA_API_KEY,
            base_url="https://integrate.api.nvidia.com/v1",
        )
        resp = client.chat.completions.create(
            model=config.NVIDIA_MODEL,
            messages=[
                {"role": "system", "content": config.SYSTEM_PROMPT},
                {"role": "user",   "content": question},
            ],
            max_tokens=config.MAX_TOKENS,
            temperature=config.TEMPERATURE,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"[Nvidia Error] {e}"


# ── Groq (OpenAI-compatible, ultra fast) ─────────────────────
def _ask_groq(question: str) -> str:
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=config.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )
        resp = client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[
                {"role": "system", "content": config.SYSTEM_PROMPT},
                {"role": "user",   "content": question},
            ],
            max_tokens=config.MAX_TOKENS,
            temperature=config.TEMPERATURE,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"[Groq Error] {e}"


# ── OpenRouter ────────────────────────────────────────────────
def _ask_openrouter(question: str) -> str:
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=config.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
        )
        resp = client.chat.completions.create(
            model=config.OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": config.SYSTEM_PROMPT},
                {"role": "user",   "content": question},
            ],
            max_tokens=config.MAX_TOKENS,
            temperature=config.TEMPERATURE,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"[OpenRouter Error] {e}"


# ── Anthropic Claude ─────────────────────────────────────────
def _ask_claude(question: str) -> str:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=config.CLAUDE_API_KEY)
        resp = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=config.MAX_TOKENS,
            system=config.SYSTEM_PROMPT,
            messages=[{"role": "user", "content": question}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        return f"[Claude Error] {e}"
