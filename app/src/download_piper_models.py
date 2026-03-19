from huggingface_hub import snapshot_download

snapshot_download(
    repo_id="rhasspy/piper-voices",
    allow_patterns=["en/en_US/*"],
    local_dir="piper-voices"
)