import asyncio
import numpy as np
from pyvi import ViTokenizer
from sentence_transformers import SentenceTransformer
from app.core.logger import logger
from app.core.config import settings


class EmbeddingService:
    def __init__(self):
        self.model_name = settings.EMBEDDING_NAME
        self.encoder = None
        self.embedding_dim = 768

    def load_model(self):
        if self.encoder is None:
            logger.info(f"🧠 Đang tải model Embedding: {self.model_name}...")
            self.encoder = SentenceTransformer(self.model_name)
            logger.info("✅ Tải Embedding thành công!")

    async def embed_texts(self, texts: list[str]) -> np.ndarray:
        if self.encoder is None:
            self.load_model()
            
        # Tokenize bằng PyVi trước khi đưa vào model
        tokenized_texts = [ViTokenizer.tokenize(t) for t in texts]
        
        # Chạy trong threadpool để không làm treo FastAPI
        embeddings = await asyncio.to_thread(
            self.encoder.encode, 
            tokenized_texts, 
            normalize_embeddings=True
        )
        return np.array(embeddings)

# Singleton instance
embedding_service = EmbeddingService()