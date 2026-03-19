# ---------------------------------------------------------------------
#   RAG (Retrieval-Augmented Generation) module using ChromaDB.
# -------------------------------------------------------------------

# Set environment variables to force offline mode for Hugging Face libraries.
HG_TRANSFORMERS_OFFLINE = "0"
haggingface_hub_local_files_only = False

import os
os.environ["TRANSFORMERS_OFFLINE"] = HG_TRANSFORMERS_OFFLINE
os.environ["HF_HUB_OFFLINE"] = HG_TRANSFORMERS_OFFLINE

from sentence_transformers import SentenceTransformer
from chromadb import Client
from chromadb.config import Settings
from huggingface_hub import try_to_load_from_cache, REPO_TYPE_MODEL

# ---------------------------------------------------------------------
#   Resolves the absolute local path for a HuggingFace model.
# -------------------------------------------------------------------
def get_local_model_path(repo_id):
    """
    Attempts to find the local cache directory for a given repository ID.
    Returns the absolute path to the snapshot directory if found, 
    otherwise returns the original repo_id.
    """
    try:
        file_path = try_to_load_from_cache(repo_id, "config.json", repo_type=REPO_TYPE_MODEL)
        if file_path:
            return os.path.dirname(file_path)
    except Exception:
        pass
    return repo_id

# ---------------------------------------------------------------------
#   Retrieval-Augmented Generation (RAG) system using ChromaDB.
# -------------------------------------------------------------------
class RAG:
    def __init__(self):
        repo_id = 'sentence-transformers/all-MiniLM-L6-v2'
        model_path = get_local_model_path(repo_id)
        self.sentence_model = SentenceTransformer(model_path, local_files_only=haggingface_hub_local_files_only)
        self.client = Client(Settings(persist_directory="./chroma_db", is_persistent=True))
        self.collection = self.client.get_or_create_collection("collection1")

    # ---------------------------------------------------------------------
    #   Generates an embedding vector for the text.
    # -------------------------------------------------------------------
    def get_embedding(self, text: str) -> list:
        """
        Generate an embedding for the given text using Sentence Transformers.
        """
        try:
            embedding = self.sentence_model.encode(text).tolist()
            return embedding
        except Exception as e:
            print(f"[red]Error obtaining embedding: {e}[/red]")
            return None

    # ---------------------------------------------------------------------
    #   Queries the database for relevant context.
    # -------------------------------------------------------------------
    def query(self, query: str, k: int = 5) -> list:
        """
        1) Embed the query
        2) Retrieve top matches from ChromaDB
        3) If matches are relevant, pass them to the Ollama Chat model.
        4) Otherwise, ask the model as a general question.
        """
        # 1) Embed the user query
        query_embedding = self.get_embedding(query)
        if query_embedding is None:
            return "Error obtaining query embedding."

        # 2) Query ChromaDB
        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=1,
                include=["documents", "distances"] # Make sure to include distances
            )
            # print(f"ChromaDB results: {results}")
        except Exception as e:
            return f"Error querying ChromaDB: {str(e)}"

        # Check if there are any results and if the most relevant document is close enough
        if results and results["documents"] and results["documents"][0] and results["distances"][0][0] < 1.0:
            # Found relevant context
            documents = results["documents"][0]
            context = " ".join(documents)
            return context
        else:
            # No relevant context found
            return None

    # ---------------------------------------------------------------------
    #   Checks if a similar entry already exists.
    # -------------------------------------------------------------------
    def check_for_duplicate(self, query: str, threshold: float = 0.1) -> bool:
        """
        Checks if a similar query already exists in the collection.
        Returns True if a duplicate is found, False otherwise.
        """
        if not query:
            return False
            
        query_embedding = self.get_embedding(query)
        if query_embedding is None:
            return False # Cannot check if embedding fails

        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=1,
                include=["distances"]
            )
            if results and results["distances"] and results["distances"][0] and results["distances"][0][0] < threshold:
                print(f"[RAG] Duplicate found with distance {results['distances'][0][0]}")
                return True
        except Exception as e:
            print(f"[RAG] Error checking for duplicates: {e}")
        
        return False

    # ---------------------------------------------------------------------
    #   Adds a new entry to the vector database.
    # -------------------------------------------------------------------
    def add_entry(self, text: str, document_id: str):
        """
        Adds a new text entry to the ChromaDB collection.
        """
        if not text or not document_id:
            return

        embedding = self.get_embedding(text)
        if embedding is None:
            print("[RAG] Failed to add entry: could not generate embedding.")
            return

        try:
            self.collection.add(
                embeddings=[embedding],
                documents=[text],
                ids=[document_id],
                metadatas=[{"source": "ltm", "entry_id": document_id}]
            )
            print(f"[RAG] Successfully added entry with ID: {document_id}")
        except Exception as e:
            print(f"[RAG] Error adding entry to collection: {e}")