from ollama import AsyncClient
from app.core.key_manager import ollama_key_manager
from app.core.config import settings
from lightrag.llm.ollama import ollama_model_complete

def get_ollama_client() -> AsyncClient:
    key = ollama_key_manager.get_next_key()
    headers = {}
    if key:
        headers['Authorization'] = f'Bearer {key}'
    
    return AsyncClient(host=settings.LLM_BASE_URL, headers=headers)

async def custom_ollama_model_complete(
    prompt,
    system_prompt=None,
    history_messages=None,
    enable_cot: bool = False,
    **kwargs,
):
    if history_messages is None:
        history_messages = []
        
    key = ollama_key_manager.get_next_key()
    if key:
        kwargs["api_key"] = key
        
    return await ollama_model_complete(
        prompt,
        system_prompt=system_prompt,
        history_messages=history_messages,
        enable_cot=enable_cot,
        **kwargs,
    )
