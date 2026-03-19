# ---------------------------------------------------------------------
#   Long-Term Memory manager for RAG, web search, and decision logic.
# -------------------------------------------------------------------
import json
import time
from rich.console import Console
# from src.llm import LLM
from app.src.rag import RAG
from app.src.web_search import WebSearch

console = Console()

# ---------------------------------------------------------------------
#   Manages Long-Term Memory, RAG, and Web Search decision logic.
# -------------------------------------------------------------------
class LongTermMemory:
    """
    Orchestrates a smart long-term memory system for the AI.
    It decides when to use its internal knowledge (RAG), when to search the web
    for new information, and when to update its knowledge base.
    """
    def __init__(self, llm_model):
        # self.llm = LLM()
        self.llm = llm_model    
        self.rag = RAG()

    # ---------------------------------------------------------------------
    #   Helper to generate a complete string response from the LLM.
    # -------------------------------------------------------------------
    async def _generate_full_response(self, prompt: str) -> str:
        """Helper to get a full string response from the LLM stream."""
        chunks_iterator = self.llm.generate_stream(prompt)
        full_response_parts = []
        for chunk in chunks_iterator:
            full_response_parts.append(chunk)
        return "".join(full_response_parts)

    # ---------------------------------------------------------------------
    #   Determines action (Search, RAG, or Chat) based on keywords.
    # -------------------------------------------------------------------
    def _get_decision_by_keywords(self, user_query: str, rag_context: str) -> dict:
        """
        Decides the action using fast keyword/pattern matching instead of LLM routing.
        This is reliable regardless of model size, and much faster.
        """
        import re
        q = user_query.lower()

        # Explicit search triggers
        SEARCH_PATTERNS = [
            r'\b(search|look up|look it up|find|google|browse)\b',
            r'\b(latest|newest|current|recent|today|now|right now)\b',
            r'\b(news|headline|update|happening|going on)\b',
            r'\b(price|stock|market|weather|forecast)\b',
            r'\b(who is|who are|what is|what are).{0,30}(now|today|currently|president|prime minister|ceo|leader)\b',
            r'\b(20(2[5-9]|[3-9]\d))\b',  # years 2025 and beyond (future/current)
        ]
        for pattern in SEARCH_PATTERNS:
            if re.search(pattern, q):
                return {"action": "needs_web_search", "reason": f"Keyword match: '{pattern}'"}

        # If RAG has context, prefer it
        if rag_context:
            return {"action": "use_rag", "reason": "RAG context available."}

        return {"action": "use_initial_llm", "reason": "General knowledge question."}

    # ---------------------------------------------------------------------
    #   Executes web search, summarizes results, and updates RAG.
    # -------------------------------------------------------------------
    async def _perform_web_search_and_update(self, user_query: str) -> str:
        """Performs a web search, summarizes the results, and returns the summary."""
        console.print("[LTM]   - Performing web search...")
        web_search = WebSearch(user_query)
        results = await web_search.search()

        if not results:
            console.print("[LTM]   - Web search returned no results.")
            return "I couldn't find any information on the web to answer your question."

        web_context_parts = [f"Source [{i+1}]: {res.get('title', 'N/A')}\nSnippet: {res.get('snippet', 'N/A')}" for i, res in enumerate(results)]
        web_context = "\n\n".join(web_context_parts)

        console.print("[LTM]   - Summarizing web search results...")
        summary_prompt = (
            "You are a helpful assistant. Please provide a concise summary of the following web search results to answer the user's question.\n\n"
            f"--- Web Search Results ---\n{web_context}\n\n"
            f"--- User's Question ---\n{user_query}"
        )
        
        new_summary = await self._generate_full_response(summary_prompt)
        console.print(f"[LTM]   - Generated Summary: {new_summary[:100].strip()}...")
        
        # Save the new, valuable information to the knowledge base
        await self.save_qna_to_rag(user_query, new_summary)
        
        return new_summary

    # ---------------------------------------------------------------------
    #   Constructs the final prompt with Context, History, and RAG data.
    # -------------------------------------------------------------------
    async def get_final_prompt(self, user_query: str, history: str = "") -> list:
        """Orchestrates research and returns a Mega-Prompt message list."""
        console.print(f"[bold magenta]LTM: Processing query: '{user_query}' [/bold magenta]")

        # 1. RAG Search
        rag_context = self.rag.query(user_query)
        
        # 2. Decision logic
        decision = self._get_decision_by_keywords(user_query, rag_context)
        action = decision.get("action", "use_initial_llm")

        # 3. Supplemental Research
        research_block = ""
        if action == "needs_web_search":
            summary = await self._perform_web_search_and_update(user_query)
            research_block = f"\n\n[Web Search Result]: {summary}"
        elif action == "use_rag" and rag_context:
            research_block = f"\n\n[Internal Knowledge]: {rag_context}"

        # 4. Construct Refined Tactical Mega-Prompt
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        
        # We frame this for a 'Tactical Assistant' who is human-like but efficient.
        knowledge_block = f"\n\n<SATELLITE_DATA>\n{research_block}\n</SATELLITE_DATA>" if research_block else ""
        log_block = f"\n\n<MISSION_LOG>\n{history}\n</MISSION_LOG>" if history else ""

        mega_prompt = (
            f"SYSTEM_ID: XBot-7_Professional_Representative\n"
            f"TIME: {current_time} | LANG: en\n"
            "--- MISSION_LOG ---"
            f"{log_block}{knowledge_block}\n"
            "--- END_DATA ---\n\n"
            "INSTRUCTION: You are a professional analytical representative. Review the log above for context. "
            "Respond in a formal, informative, yet natural conversational style. "
            "CRITICAL: Do NOT include labels like 'Question:' or 'Answer:' in your response. "
            "Speak directly and professionally to the user based on the latest MISSION_LOG data.\n\n"
            f"USER_REQUEST: {user_query}"
        )

        return [
            {"role": "user", "content": mega_prompt}
        ]

    # ---------------------------------------------------------------------
    #   Saves a Question/Answer pair to the vector database.
    # -------------------------------------------------------------------
    async def save_qna_to_rag(self, question: str, answer: str):
        """Saves a new question-answer pair to the RAG, checking for duplicates first."""
        if not answer or not answer.strip() or "couldn't find any information" in answer:
            return

        console.print("\n[LTM] Checking for duplicates before saving to RAG...")
        if not self.rag.check_for_duplicate(question):
            console.print("[LTM] No duplicate found. Saving new Q&A to knowledge base...")
            new_entry_text = f"Question: {question}\nAnswer: {answer.strip()}"
            document_id = f"ltm_entry_{int(time.time())}"
            self.rag.add_entry(new_entry_text, document_id)