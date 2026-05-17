"""
Rerank Service cho Legal AI Platform

Hỗ trợ 2 chế độ:
1. Local: Sử dụng CrossEncoder model (BAAI/bge-reranker-v2-m3)
2. API: Sử dụng Cohere API
"""

import asyncio
from typing import Any, Dict, List, Optional
import torch
from app.core.config import settings
from app.core.logger import logger
from cohere import ClientV2
from app.core.key_manager import cohere_key_manager
from sentence_transformers import CrossEncoder


class RerankService:
    def __init__(self):
        self.mode = settings.CHOOSE_RERANK
        self._local_model = None
        self._local_model_name = settings.RERANK_MODEL
        self.cohere_model = settings.COHERE_MODEL


    def load_model(self):
        if self.mode == "local":
            if self._local_model is not None:
                return
            logger.info(f"Loading local rerank model: {self._local_model_name} ...")
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
            self._local_model = CrossEncoder(self._local_model_name, trust_remote_code=True, device=device)
            logger.info(f"Local rerank model loaded on {device}")
        else:
            logger.info(f"Cohere API Rerank enabled with model: {self.cohere_model}")


    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: Optional[int] = None,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        if not documents:
            return []

        if self.mode == "local":
            return await self._rerank_local(query, documents, top_n)
        elif self.mode == "api":
            return await self._rerank_api(query, documents, top_n)
        else:
            logger.warning(f"Unknown rerank mode: {self.mode}. Falling back to local.")
            return await self._rerank_local(query, documents, top_n)


    async def _rerank_local(self, query: str, documents: List[str], top_n: Optional[int]) -> List[Dict]:
        if self._local_model is None:
            self.load_model()

        pairs = [(query, doc) for doc in documents]
        loop = asyncio.get_event_loop()
        scores = await loop.run_in_executor(
            None,
            lambda: self._local_model.predict(pairs).tolist(),
        )

        results = [
            {"index": i, "relevance_score": float(score)}
            for i, score in enumerate(scores)
        ]
        results.sort(key=lambda x: x["relevance_score"], reverse=True)

        if top_n is not None and top_n > 0:
            results = results[:top_n]

        logger.debug(f"[Local Rerank] {len(documents)} docs -> top {len(results)}")
        return results


    async def _rerank_api(self, query: str, documents: List[str], top_n: Optional[int]) -> List[Dict]:
        doc_contents = [
            doc.replace("_"," ").replace(' .', '.').replace(' ,', ',').replace(' !', '!').replace(' ?', '?').replace(' :', ':').replace(' ;', ';') 
            for doc in documents
        ]
        
        loop = asyncio.get_event_loop()
        
        def call_cohere():
            key = cohere_key_manager.get_next_key()
            if not key:
                raise ValueError("No Cohere API Key configured in environment variables.")
                
            co = ClientV2(key)
            limit = top_n if top_n else len(doc_contents)
            response = co.rerank(
                model=self.cohere_model,
                query=query,
                documents=doc_contents,
                top_n=limit,
            )
            return response.results

        try:
            results = await loop.run_in_executor(None, call_cohere)
            
            # Format chuẩn cho LightRAG
            formatted_results = [
                {"index": res.index, "relevance_score": float(res.relevance_score)}
                for res in results
            ]
            logger.debug(f"[Cohere API Rerank] {len(documents)} docs -> top {len(formatted_results)}")
            return formatted_results
            
        except Exception as e:
            logger.error(f"Cohere API Rerank failed: {e}")
            return []

rerank_service = RerankService()
