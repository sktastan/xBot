# ---------------------------------------------------------------------
#   SQLite database manager for chat history and conversations.
# -------------------------------------------------------------------
import sqlite3
import os
import time
from rich.console import Console

console = Console()

# ---------------------------------------------------------------------
#   Manages SQLite database for conversations and messages.
# -------------------------------------------------------------------
class ChatDatabase:
    def __init__(self, db_path="chat_history.db"):
        self.db_path = db_path
        self._init_db()

    # ---------------------------------------------------------------------
    #   Creates and returns a new database connection.
    # -------------------------------------------------------------------
    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    # ---------------------------------------------------------------------
    #   Initializes the database schema (tables).
    # -------------------------------------------------------------------
    def _init_db(self):
        """Initializes the database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Conversations table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # Messages table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
                )
            ''')
            conn.commit()
        console.print(f"[bold green][DB][/bold green] Database initialized at {self.db_path}")

    # ---------------------------------------------------------------------
    #   Creates a new conversation record.
    # -------------------------------------------------------------------
    def create_conversation(self, title="New Conversation"):
        """Creates a new conversation and returns its ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO conversations (title) VALUES (?)", (title,))
            conn.commit()
            return cursor.lastrowid

    # ---------------------------------------------------------------------
    #   Retrieves all conversations.
    # -------------------------------------------------------------------
    def get_conversations(self):
        """Returns all conversations ordered by updated_at."""
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM conversations ORDER BY updated_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    # ---------------------------------------------------------------------
    #   Retrieves messages for a specific conversation.
    # -------------------------------------------------------------------
    def get_messages(self, conversation_id):
        """Returns all messages for a specific conversation."""
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM messages WHERE conversation_id = ? ORDER BY timestamp ASC", (conversation_id,))
            return [dict(row) for row in cursor.fetchall()]

    # ---------------------------------------------------------------------
    #   Adds a message to a conversation.
    # -------------------------------------------------------------------
    def add_message(self, conversation_id, role, content):
        """Adds a message to a conversation and updates the updated_at timestamp."""
        if conversation_id is None:
            return
        try:
            conv_id = int(conversation_id)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
                    (conv_id, role, content)
                )
                # Update the conversation timestamp
                cursor.execute(
                    "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (conv_id,)
                )
                conn.commit()
            console.print(f"[bold green][DB][/bold green] Message added to conv {conv_id} ({role})")
        except Exception as e:
            console.print(f"[bold red][DB Error][/bold red] Failed to add message: {e}")

    # ---------------------------------------------------------------------
    #   Deletes a conversation and its messages.
    # -------------------------------------------------------------------
    def delete_conversation(self, conversation_id):
        """Deletes a conversation and its messages."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
            conn.commit()

    # ---------------------------------------------------------------------
    #   Updates the title of a conversation.
    # -------------------------------------------------------------------
    def update_conversation_title(self, conversation_id, title):
        """Updates the title of a conversation."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE conversations SET title = ? WHERE id = ?",
                (title, conversation_id)
            )
            conn.commit()
