"""Quick test script for rerank service router (Local/API)."""
import sys
import os
import warnings
import logging
import asyncio
import traceback

sys.path.insert(0, r"D:\full_chatbot_lightrag\project_lightrag\legal_ai_platform\backend")

from dotenv import load_dotenv
load_dotenv(r"D:\full_chatbot_lightrag\project_lightrag\legal_ai_platform\backend\.env", override=False)

# Suppress HF warnings
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

async def test():
    try:
        from app.core.config import settings
        from app.infrastructure.llm.rerank_service import rerank_service
        
        print(f"--- ĐANG KIỂM TRA RERANK ROUTER ---")
        print(f"Mode hiện tại từ .env (CHOOSE_RERANK): {settings.CHOOSE_RERANK}")
        
        print("\nStep 1: Khởi tạo mô hình (load_model)...")
        rerank_service.load_model()
        print("Step 1: OK!")

        query = "ly hon don phuong"
        documents = [
            "Thu tuc ly hon don phuong can nop don tai toa an",
            "Dieu kien ket hon theo luat dan su",
            "Quyen nuoi con sau ly hon",
        ]

        print("\nStep 2: Chạy rerank()...")
        results = await rerank_service.rerank(query, documents)
        
        print(f"\nStep 3: Kết quả trả về ({len(results)} items):")
        for res in results:
            idx = res['index']
            score = res['relevance_score']
            print(f"  [Index: {idx}] Score = {score:.4f} | Text: {documents[idx][:60]}")

        print("\n>>> TEST PASSED! Kết quả đã theo format chuẩn của LightRAG.")
    except Exception as e:
        traceback.print_exc()
        print(f"\n>>> TEST FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(test())
