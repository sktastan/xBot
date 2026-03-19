@ECHO OFF
ECHO Setup xbot
uv pip install huggingface_hub transformers faster_whisper piper-tts sentence_transformers chromadb accelerate bs4 aiohttp asyncio brotli flask 
uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130
uv run %~dp0app\src\download_piper_models.py
PAUSE
