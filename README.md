# XBot: Local Multimodal AI Assistant

## Overview

XBot is a sophisticated, locally-hosted AI assistant designed for privacy, performance, and multimodal interaction. It integrates state-of-the-art open-source models to provide a seamless voice and text chat experience. 

Unlike simple chatbots, XBot features a robust cognitive architecture comprising **Short-Term Memory** (conversation context) and **Long-Term Memory** (RAG + Vector Database). It can intelligently decide when to answer from its internal knowledge base, when to query your local documents, and when to browse the web for real-time information.

## Key Features

### 🧠 Advanced Intelligence
*   **Local LLM Inference:** Powered by **Qwen** (configured for Qwen3.5-0.8B/1.7B) for high-speed, local text generation without sending data to the cloud.
*   **RAG (Retrieval-Augmented Generation):** Automatically indexes local text documents into a **ChromaDB** vector store, allowing the AI to answer questions based on your personal data.
*   **Autonomous Web Search:** Detects when a user asks for current events or external facts and performs live web searches (via DuckDuckGo, Bing, or Google), summarizing the results and learning from them.

### 🗣️ Voice Interface
*   **Speech-to-Text (STT):** Utilizes **Faster-Whisper** running on CUDA for near-instant transcription of user audio.
*   **Text-to-Speech (TTS):** Integrated **Piper TTS** for fast, neural-quality voice synthesis.
*   **Gapless Playback:** A custom frontend audio queue system ensures the AI's voice flows naturally without stuttering between sentence chunks.

### 💾 Memory Systems
*   **Short-Term Memory (STM):** Retains recent conversation context using SQLite, allowing for coherent multi-turn conversations.
*   **Long-Term Memory (LTM):** 
    *   **Document Ingestion:** A background process watches the `app/src/documents/` folder, automatically chunking and embedding new `.txt` files.
    *   **Self-Learning:** When the AI searches the web, it can save valuable Q&A summaries back into its vector database for future recall.

### 🖥️ Modern UI
*   **Responsive Chat Interface:** A clean web interface supporting Markdown rendering for code and rich text.
*   **Voice Controls:** "Push-to-Talk" or keyboard shortcuts (`Ctrl+Space`) for voice input.
*   **Conversation Management:** Create, rename, delete, and switch between multiple conversation histories.
*   **Settings:** Toggle Microphone/Voice output and switch TTS voice models directly from the UI.

## System Architecture

*   **Backend:** Python 3.10+ using **Flask** (Async) for API handling.
*   **Frontend:** Vanilla JavaScript, HTML5, CSS3.
*   **Database:** 
    *   **SQLite:** Stores chat history and conversation metadata.
    *   **ChromaDB:** Stores vector embeddings for RAG (Long-Term Memory).
*   **AI Models:**
    *   **LLM:** `transformers` + `AutoModelForCausalLM` (Qwen).
    *   **Embeddings:** `sentence-transformers` (all-MiniLM-L6-v2).
    *   **STT:** `faster_whisper`.
    *   **TTS:** `piper`.

## Installation

### Prerequisites
*   Python 3.10 or higher.
*   NVIDIA GPU with CUDA support (strongly recommended for LLM and Whisper performance).

### Setup

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/sktastan/xbot.git
    cd xbot
    ```

2.  **Install Python Dependencies**
    ```bash
    uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130
    uv pip install huggingface_hub transformers faster_whisper piper-tts sentence_transformers chromadb accelerate bs4 aiohttp asyncio brotli flask
    uv run %~dp0app\src\download_piper_models.py
    ```
    or
    setup.bat

    *(Note: You may need specific versions of `torch` depending on your CUDA version).*

3.  **Model Configuration**
    *   The system is configured to use `Qwen/Qwen3.5-0.8B` by default. On first run, it will attempt to download this from Hugging Face if not cached.
    *   **TTS Models:** Ensure you have Piper ONNX voice models located in `tts-models/tts/`.

4.  **Directory Structure**
    Ensure the following directories exist:
    *   `app/src/documents/` (Place `.txt` files here for RAG)
    *   `chroma_db/` (Created automatically for vector storage)
    *   `chat_history.db` (Created automatically)

## Usage

1.  **Start the Server**
    ```bash
    uv run main.py
    ```
    or
    run.bat

    The server will initialize the models (this may take a moment) and start listening on port 5000.

2.  **Access the Interface**
    Open a web browser and navigate to: `http://localhost:5000`

3.  **Interact**
    *   **Text:** Type in the input box and hit Enter.
    *   **Voice:** Click the microphone icon or hold `Ctrl+Space` to speak.
    *   **Context:** To add knowledge, drop text files into `app/src/documents/`. The system processes them automatically.

## License
MIT
