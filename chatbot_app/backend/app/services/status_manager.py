import random

class StatusManager:
    """
    Manages and provides dynamic, context-aware status messages for the RAG pipeline.
    """
    def __init__(self):
        self.messages = {
            "understanding": [
                "Analyzing your request...",
                "Deconstructing your query...",
                "Figuring out what you mean...",
                "Breaking down your question...",
                "Getting to the core of your query..."
            ],
            "searching": [
                "Searching the knowledge base...",
                "Looking for relevant documents...",
                "Scanning through the archives...",
                "Finding the right information...",
                "Digging through the data..."
            ],
            "hyde": [
                "Generating a hypothetical example to improve search...",
                "Creating a search template for better results...",
                "Thinking of a perfect answer to guide the search...",
                "Building an ideal example to find similar cases..."
            ],
            "sampling": [
                "Gathering a random sample of calls...",
                "Assembling a representative mix...",
                "Selecting a random batch of documents...",
                "Picking out a few random examples..."
            ],
            "synthesizing": [
                "Synthesizing the answer...",
                "Putting together a response...",
                "Crafting the perfect reply...",
                "Generating the final answer...",
                "Formulating a response..."
            ],
            "chitchat": [
                "Formulating a friendly response...",
                "Thinking of what to say...",
                "Just a moment...",
                "Coming up with a reply..."
            ]
        }

    def get_message(self, stage: str) -> str:
        """
        Gets a random message for a given pipeline stage.
        
        Args:
            stage: The name of the pipeline stage (e.g., 'understanding', 'searching').
            
        Returns:
            A random message string.
        """
        if stage in self.messages:
            return random.choice(self.messages[stage])
        return "Processing..."

# Instantiate a single manager for the app
status_manager = StatusManager()