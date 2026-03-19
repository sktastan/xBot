# ---------------------------------------------------------------------
#   Large Language Model (LLM) wrapper for text generation.
# -------------------------------------------------------------------

# Set environment variables to force offline mode for Hugging Face libraries.
HG_TRANSFORMERS_OFFLINE = "0"
haggingface_hub_local_files_only = False

import os
os.environ["TRANSFORMERS_OFFLINE"] = HG_TRANSFORMERS_OFFLINE
os.environ["HF_HUB_OFFLINE"] = HG_TRANSFORMERS_OFFLINE

from threading import Thread
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer, GenerationConfig, StoppingCriteria, StoppingCriteriaList
from huggingface_hub import try_to_load_from_cache, REPO_TYPE_MODEL

# ---------------------------------------------------------------------
#   Custom stopping criteria to handle cancellation events.
# -------------------------------------------------------------------
class CancellationToken(StoppingCriteria):
    def __init__(self, stop_event):
        self.stop_event = stop_event

    def __call__(self, input_ids, scores, **kwargs):
        return self.stop_event.is_set() if self.stop_event else False

# ---------------------------------------------------------------------
#   Wrapper for the Large Language Model (Qwen/HuggingFace).
# -------------------------------------------------------------------
class LLM:
    # ---------------------------------------------------------------------
    #   Initializes the model and tokenizer from local cache.
    # -------------------------------------------------------------------
    def __init__(self):
        self.repo_id = "Qwen/Qwen3.5-0.8B"
        self.model_path = self.get_local_model_path(self.repo_id)
        
        # Use the resolved absolute path to bypass network-dependent metadata checks
        self.tokenizer = AutoTokenizer.from_pretrained(self.repo_id, local_files_only=haggingface_hub_local_files_only)
        self.model = AutoModelForCausalLM.from_pretrained(
            self.repo_id,
            dtype="auto",
            device_map="auto",
            local_files_only=haggingface_hub_local_files_only
        )

    # ---------------------------------------------------------------------
    #   Resolves the absolute local path for a HuggingFace model.
    # -------------------------------------------------------------------
    def get_local_model_path(self, repo_id):
        """
        Attempts to find the local cache directory for a given repository ID.
        Returns the absolute path to the snapshot directory if found, 
        otherwise returns the original repo_id.
        """
        try:
            # try_to_load_from_cache returns the path to a specific file in the snapshot
            file_path = try_to_load_from_cache(repo_id, "config.json", repo_type=REPO_TYPE_MODEL)
            if file_path:
                return os.path.dirname(file_path)
        except Exception:
            pass
        return repo_id

    # ---------------------------------------------------------------------
    #   Switches the active model to the specified model_name.
    # -------------------------------------------------------------------
    def setModel(self, model_name):
        self.repo_id = model_name
        self.model_path = self.get_local_model_path(self.repo_id)
        
        self.tokenizer = AutoTokenizer.from_pretrained(self.repo_id, local_files_only=haggingface_hub_local_files_only)
        self.model = AutoModelForCausalLM.from_pretrained(
            self.repo_id,
            dtype="auto",
            device_map="auto",
            local_files_only=haggingface_hub_local_files_only
        )

    # ---------------------------------------------------------------------
    #   Returns the current model repository ID.
    # -------------------------------------------------------------------
    def get_model_name(self):
        return self.repo_id

    # ---------------------------------------------------------------------
    #   Generates a streaming response from the model given a prompt.
    # -------------------------------------------------------------------
    def generate_stream(self, prompt, stop_event=None):
        """
        Generates a stream of text. 'prompt' can be a string or a list of message dicts.
        """
        if isinstance(prompt, str):
            messages = [{"role": "user", "content": prompt}]
        else:
            messages = prompt

        text = self.tokenizer.apply_chat_template(
            messages,
            max_input_length=32768,
            tokenize=False,
            add_generation_prompt=True, # Adjust if thinking mode is needed
            enable_thinking=False
        )
        model_inputs = self.tokenizer([text], return_tensors="pt").to(self.model.device)

        # Initialize the iterator streamer
        streamer = TextIteratorStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True)

        # Define tokens to ban during generation
        # bad_chars = ["#", "*"]
        # bad_words_ids = [self.tokenizer.encode(c, add_special_tokens=False) for c in bad_chars]
    
        stopping_criteria = StoppingCriteriaList()
        if stop_event:
            stopping_criteria.append(CancellationToken(stop_event))

        gen_config = GenerationConfig(
            max_new_tokens=32768,
            do_sample=True,
            temperature=0.7,
            top_p=0.9,
            repetition_penalty=1.1
        )

        generation_kwargs = dict(
            **model_inputs,
            streamer=streamer,
            generation_config=gen_config,
            stopping_criteria=stopping_criteria
        )

        # Start generation in a separate thread so the main thread can yield chunks
        thread = Thread(target=self.model.generate, kwargs=generation_kwargs)
        thread.start()

        for new_text in streamer:
            if stop_event and stop_event.is_set():
                break
            yield new_text.replace("*", "").replace("#", "")