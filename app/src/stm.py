# ---------------------------------------------------------------------
#   Short-Term Memory manager for retrieving conversation context.
# -------------------------------------------------------------------
from rich.console import Console

console = Console()

# ---------------------------------------------------------------------
#   Manages Short-Term Memory (Conversation Context).
# -------------------------------------------------------------------
class ShortTermMemory:
    """
    Manages the short-term context of a conversation by retrieving
    past messages from the database.
    """
    def __init__(self, limit=10):
        self.limit = limit

    # ---------------------------------------------------------------------
    #   Retrieves recent conversation history from the DB.
    # -------------------------------------------------------------------
    def get_context(self, db, conv_id, current_query=None):
        """
        Fetches the last N messages and returns them as a single string.
        """
        if not db or not conv_id:
            return ""

        try:
            messages = db.get_messages(conv_id)
            
            # Skip current query if already in DB
            if current_query and messages and messages[-1]['role'] == 'user' and messages[-1]['content'].strip() == current_query.strip():
                messages = messages[:-1]

            recent_messages = messages[-self.limit:] if len(messages) > self.limit else messages
            
            if not recent_messages:
                return ""

            lines = []
            for i, msg in enumerate(recent_messages):
                # We use tags (U) for User and (A) for Assistant to help model IQ
                role_tag = "U" if msg['role'] == 'user' else "A"
                lines.append(f"[MSG_{i+1:02d} ({role_tag})]: {msg['content']}")

            context = "\n".join(lines)
            console.print(f"[bold blue][STM][/bold blue] Encoded {len(recent_messages)} messages with role hints.")
            return context
        except Exception as e:
            console.print(f"[bold red][STM Error][/bold red] {e}")
            return ""
