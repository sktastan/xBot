# ---------------------------------------------------------------------
#   Main application entry point initializing models and server.
# -------------------------------------------------------------------
import os
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

from app.src.stt import STT
from app.src.llm import LLM
from app.src.tts import TTS
from app.src.lts import LongTermMemory
from app.src.flask_server import FlaskServer
from app.src.database import ChatDatabase
from app.src.stm import ShortTermMemory
from app.src.flask_server import request, jsonify, send_file, Response
from rich import print
import asyncio
from app.src.misc import cuda_info, _sse_line, _make_stream, _stream_llm_tts

# ---------------------------------------------------------------------
#   Main Application Entry Point. Configures and starts the server.
# -------------------------------------------------------------------
def main():
    cuda_info()

    print("--- Initializing models ---")
    llmModel = LLM()
    print(f"[bold green]Loaded model: {llmModel.get_model_name()}[/bold green]")
    sttModel = STT()

    ttsModel = TTS()
    ltm = LongTermMemory(llmModel)
    db = ChatDatabase()
    stm = ShortTermMemory()

    server = FlaskServer(processor=None, db=db)

    # ---------------------------------------------------------------------------------------------
    # Serve Audio
    # ---------------------------------------------------------------------------------------------
    # ---------------------------------------------------------------------
    #   Route: Serves the generated audio file.
    # -------------------------------------------------------------------
    @server.app.route('/audio', methods=['GET'])
    def serve_audio():
        audio_path = os.path.abspath("response.wav")
        return send_file(audio_path, mimetype="audio/wav")

    # ---------------------------------------------------------------------------------------------
    # Process Audio
    # ---------------------------------------------------------------------------------------------
    # ---------------------------------------------------------------------
    #   Route: Processes uploaded audio, transcribes, and generates response.
    # -------------------------------------------------------------------
    @server.app.route('/process_audio', methods=['POST'])
    def process_audio():
        print("Received request at /process_audio")

        if not getattr(sttModel, 'enabled', True):
             return jsonify({"error": "Speech-to-Text is disabled."}), 403

        if 'audio' not in request.files:
            return jsonify({"error": "No audio file part in the request"}), 400
        audio_file = request.files['audio']
        if audio_file.filename == '':
            return jsonify({"error": "No selected file"}), 400
        
        # Use a standardized filename to prevent path traversal/injection risks
        file_path = "temp_recording.wav"
        audio_file.save(file_path)
        print(f"Audio file '{file_path}' saved.")

        conv_id = request.args.get('conv_id', type=int)

        print(f"\n--- Transcribing from: {file_path} ---")
        try:
            text = sttModel.transcribe(file_path)
        except RuntimeError as e:
            if "cublas" in str(e) or "cudnn" in str(e):
                error_msg = f"STT Engine Error: Missing CUDA/cuDNN libraries ({str(e)}). Please ensure NVIDIA CUDA 12 is installed and added to your system PATH."
                print(f"[bold red]{error_msg}[/bold red]")
                return jsonify({"error": error_msg}), 500
            raise e
            
        text = text.strip()
        print("Transcribed text: " + text)

        # Save user message to DB
        if db and conv_id:
            db.add_message(conv_id, "user", text)

        async def task(put, stop_event):
            put(_sse_line({"type": "transcribed", "text": text}))
            
            # Fetch Short-Term Memory (Context)
            history = stm.get_context(db, conv_id, current_query=text)
            
            final_prompt = await ltm.get_final_prompt(text, history=history)
            chunks = llmModel.generate_stream(final_prompt, stop_event=stop_event)
            await _stream_llm_tts(put, ttsModel, chunks, os.path.abspath("response.wav"), db=db, conv_id=conv_id, stop_event=stop_event)

        return Response(_make_stream(task), mimetype='application/x-ndjson')

    # ---------------------------------------------------------------------------------------------
    # Process Prompt
    # ---------------------------------------------------------------------------------------------
    # ---------------------------------------------------------------------
    #   Route: Processes text prompt and generates response.
    # -------------------------------------------------------------------
    @server.app.route('/process_prompt', methods=['POST'])
    def process_prompt():
        print("Received request at /process_prompt")
        data = request.get_json()
        user_prompt = data.get('text', '')
        conv_id = data.get('conv_id')
        print(f"User prompt: {user_prompt}")

        # Save user message to DB
        if db and conv_id:
            db.add_message(conv_id, "user", user_prompt)

        async def task(put, stop_event):
            # Fetch Short-Term Memory (Context)
            history = stm.get_context(db, conv_id, current_query=user_prompt)
            
            final_prompt = await ltm.get_final_prompt(user_prompt, history=history)
            chunks = llmModel.generate_stream(final_prompt, stop_event=stop_event)
            await _stream_llm_tts(put, ttsModel, chunks, os.path.abspath("response.wav"), db=db, conv_id=conv_id, stop_event=stop_event)

        return Response(_make_stream(task), mimetype='application/x-ndjson')

    # ---------------------------------------------------------------------------------------------
    # Get Conversations
    # ---------------------------------------------------------------------------------------------
    # ---------------------------------------------------------------------
    #   Route: Returns list of conversations.
    # -------------------------------------------------------------------
    @server.app.route('/api/conversations', methods=['GET'])
    def get_conversations():
        if not db: return jsonify([]), 200
        return jsonify(db.get_conversations()), 200

    # ---------------------------------------------------------------------------------------------
    # Create Conversation
    # ---------------------------------------------------------------------------------------------
    # ---------------------------------------------------------------------
    #   Route: Creates a new conversation.
    # -------------------------------------------------------------------
    @server.app.route('/api/conversations', methods=['POST'])
    def create_conversation():
        if not db: return jsonify({"error": "No DB"}), 500
        data = request.get_json() or {}
        title = data.get('title', 'New Conversation')
        conv_id = db.create_conversation(title)
        return jsonify({"id": conv_id, "title": title}), 201

    # ---------------------------------------------------------------------------------------------
    # Get Messages
    # ---------------------------------------------------------------------------------------------
    # ---------------------------------------------------------------------
    #   Route: Returns messages for a specific conversation.
    # -------------------------------------------------------------------
    @server.app.route('/api/conversations/<int:conv_id>', methods=['GET'])
    def get_messages(conv_id):
        if not db: return jsonify([]), 200
        return jsonify(db.get_messages(conv_id)), 200
    
    # ---------------------------------------------------------------------------------------------
    # Delete Conversation
    # ---------------------------------------------------------------------------------------------
    # ---------------------------------------------------------------------
    #   Route: Deletes a conversation.
    # -------------------------------------------------------------------
    @server.app.route('/api/conversations/<int:conv_id>', methods=['DELETE'])
    def delete_conversation(conv_id):
        if not db: return jsonify({"error": "No DB"}), 500
        db.delete_conversation(conv_id)
        return jsonify({"status": "deleted"}), 200
    
    # ---------------------------------------------------------------------------------------------
    # Update Conversation
    # ---------------------------------------------------------------------------------------------
    # ---------------------------------------------------------------------
    #   Route: Updates conversation title.
    # -------------------------------------------------------------------
    @server.app.route('/api/conversations/<int:conv_id>', methods=['PUT'])
    def update_conversation(conv_id):
        if not db: return jsonify({"error": "No DB"}), 500
        data = request.get_json()
        title = data.get('title')
        db.update_conversation_title(conv_id, title)
        return jsonify({"status": "updated"}), 200

    # ---------------------------------------------------------------------------------------------
    # TTS Voice Management
    # ---------------------------------------------------------------------------------------------
    # ---------------------------------------------------------------------
    #   Route: Returns available TTS voices.
    # -------------------------------------------------------------------
    @server.app.route('/api/tts/voices', methods=['GET'])
    def get_voices():
        voices = ttsModel.get_voices()
        current = ttsModel.get_current_voice()
        return jsonify({"voices": voices, "current": current}), 200

    # ---------------------------------------------------------------------
    #   Route: Sets the active TTS voice.
    # -------------------------------------------------------------------
    @server.app.route('/api/tts/voice', methods=['POST'])
    def set_voice():
        data = request.get_json()
        voice_name = data.get('voice')
        if not voice_name:
            return jsonify({"error": "No voice specified"}), 400
        ttsModel.setVoice(voice_name)
        return jsonify({"status": "success", "voice": voice_name}), 200

    # ---------------------------------------------------------------------------------------------
    # Settings APIs (STT/TTS Toggles)
    # ---------------------------------------------------------------------------------------------
    # ---------------------------------------------------------------------
    #   Route: Manages STT enabled state.
    # -------------------------------------------------------------------
    @server.app.route('/api/settings/stt', methods=['GET', 'POST'])
    def handle_stt_settings():
        if request.method == 'POST':
            data = request.get_json()
            sttModel.enabled = data.get('enabled', True)
            return jsonify({"status": "success", "enabled": sttModel.enabled})
        return jsonify({"enabled": getattr(sttModel, 'enabled', True)})

    # ---------------------------------------------------------------------
    #   Route: Manages TTS enabled state.
    # -------------------------------------------------------------------
    @server.app.route('/api/settings/tts', methods=['GET', 'POST'])
    def handle_tts_settings():
        if request.method == 'POST':
            data = request.get_json()
            ttsModel.enabled = data.get('enabled', True)
            return jsonify({"status": "success", "enabled": ttsModel.enabled})
        return jsonify({"enabled": ttsModel.enabled})

    server.run()

if __name__ == "__main__":
    print("--- .......... ---")
    try:
        main()
    except KeyboardInterrupt:
        print("\n[bold yellow]Server shutting down gracefully.[/bold yellow]")
