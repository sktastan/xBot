# ---------------------------------------------------------------------
#   Utility functions for CUDA info, SSE streaming, and concurrency.
# -------------------------------------------------------------------
import torch
from queue import Queue
from threading import Thread, Event
import asyncio
import json
import io
import wave
import base64
import re

# ---------------------------------------------------------------------
#   Prints available CUDA device information to the console.
# -------------------------------------------------------------------
def cuda_info():
    print("\n--- CUDA Information ---")
    if torch.cuda.is_available():
        print(f"CUDA is available. Device count: {torch.cuda.device_count()}")
        for i in range(torch.cuda.device_count()):
            print(f"Device {i}: {torch.cuda.get_device_name(i)}")
    else:
        print("CUDA is not available.")

# ---------------------------------------------------------------------
#   Formats a dictionary into a Server-Sent Events (SSE) string.
# -------------------------------------------------------------------
def _sse_line(obj: dict) -> bytes:
    return (json.dumps(obj) + "\n").encode()

# ---------------------------------------------------------------------
#   Wraps an async generator task into a Flask stream response.
# -------------------------------------------------------------------
def _make_stream(async_task_fn):
    """Run an async task in a background thread; yield items placed in the queue."""
    q = Queue()

    stop_event = Event()
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(async_task_fn(q.put, stop_event))
        except Exception as e:
            print(f"[Stream error] {e}")
        finally:
            q.put(None)
        loop.close()

    t = Thread(target=run, daemon=True)
    t.start()
    try:
        while True:
            item = q.get()
            if item is None:
                break
            yield item
    finally:
        stop_event.set() # Signal background thread to stop
        t.join(timeout=1.0)

# ---------------------------------------------------------------------
#   Generates audio for a single sentence and emits an SSE event.
# -------------------------------------------------------------------
async def _tts_sentence_events(put, tts_model, sentence: str, full_wav_file, index: int):
    """
    Generate TTS for one sentence, write PCM to the shared WAV file,
    and emit a single {"type":"audio_chunk","data":"<base64_wav>", "index": index} event.
    """
    if not tts_model.enabled:
        return

    buf = io.BytesIO()
    with wave.open(buf, "wb") as sent_wav:
        sent_wav.setnchannels(1)
        sent_wav.setsampwidth(2)
        sent_wav.setframerate(22050)
        async for pcm in tts_model.generate_audio_stream(sentence):
            sent_wav.writeframes(pcm)
            full_wav_file.writeframes(pcm)

    wav_b64 = base64.b64encode(buf.getvalue()).decode()
    put(_sse_line({"type": "audio_chunk", "data": wav_b64, "index": index}))

# ---------------------------------------------------------------------
#   Processes LLM stream, handles TTS generation, and saves output.
# -------------------------------------------------------------------
async def _stream_llm_tts(put, tts_model, llm_chunks, output_path, db=None, conv_id=None, stop_event=None):
    """
    Buffer LLM text into sentences, emit text chunks and per-sentence audio.
    Writes a complete WAV to output_path as a side-effect.
    """
    sentence_index = 0
    sentence_buffer = ""
    full_response = ""
    with wave.open(output_path, "wb") as full_wav:
        full_wav.setnchannels(1)
        full_wav.setsampwidth(2)
        full_wav.setframerate(22050)

        for chunk in llm_chunks:
            if stop_event and stop_event.is_set():
                break
            # Stream the text token to the client with the current sentence index
            put(_sse_line({"type": "chunk", "text": chunk, "index": sentence_index}))
            # print(chunk, end="", flush=True)
            sentence_buffer += chunk
            full_response += chunk

            # Sentence boundary detected → synthesise completed sentences immediately
            if re.search(r'[.!?](\s|$)', sentence_buffer):
                parts = re.split(r'(?<=[.!?])\s+', sentence_buffer)
                if len(parts) > 1:
                    to_process, sentence_buffer = parts[:-1], parts[-1]
                    for s in to_process:
                        if s.strip():
                            if stop_event and stop_event.is_set():
                                break
                            await _tts_sentence_events(put, tts_model, s, full_wav, sentence_index)
                            sentence_index += 1

        # Synthesise any remaining text that didn't end with punctuation
        if sentence_buffer.strip():
            await _tts_sentence_events(put, tts_model, sentence_buffer, full_wav, sentence_index)
    
    # Save the full AI response to the DB
    if db and conv_id and full_response:
        db.add_message(conv_id, "ai", full_response)