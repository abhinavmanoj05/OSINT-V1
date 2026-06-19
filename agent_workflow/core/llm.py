from langchain_ollama import ChatOllama

def get_llm():
    return ChatOllama(
        model="llama3.1:latest",
        temperature=0,
        streaming=False,
        top_p=0.9,
        num_ctx=4096
    )