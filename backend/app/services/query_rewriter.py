from ollama import AsyncClient
from app.core.config import settings
from app.core.logger import logger
from app.services.prompt_manager import prompt_manager

class QueryRewriterService:
    async def rewrite(self, user_query: str, history: list) -> str:
        if not history:
            return user_query

        # 1. Xây dựng mảng messages
        system_prompt = prompt_manager.get_prompt("query_rewriter")
        messages = [{"role": "system", "content": system_prompt}]
        
        for msg in history[-3:]:
            role = msg.get("role", "user") 
            messages.append({"role": role, "content": msg.get("content", "")})
            
        messages.append({
            "role": "user", 
            "content": f"Hãy viết lại câu hỏi này: {user_query}"
        })

        # 2. Cấu hình Headers (Auth)
        headers = {}
        if settings.OLLAMA_API_KEY:
            headers['Authorization'] = f'Bearer {settings.OLLAMA_API_KEY}'

        try:
            client = AsyncClient(host=settings.LLM_BASE_URL, headers=headers)
            response = await client.chat(
                model=settings.LLM_MODEL,
                messages=messages
            )
            rewritten = response.get("message", {}).get("content", "").strip()
            
            if rewritten:
                logger.info(f"🔄 Đã Rewrite: '{user_query}' -> '{rewritten}'")
                return rewritten
            return user_query
                
        except Exception as e:
            logger.error(f"❌ Lỗi Query Rewriter: {str(e)}")
            return user_query

query_rewriter = QueryRewriterService()