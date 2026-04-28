#!/usr/bin/env python3
"""
RAGAS Evaluation Script cho Legal AI Platform

Đánh giá chất lượng RAG bằng RAGAS metrics:
- Faithfulness: Câu trả lời có đúng với context không?
- Answer Relevancy: Câu trả lời có liên quan đến câu hỏi không?
- Context Recall: Có retrieve đủ thông tin không?
- Context Precision: Context có sạch không (ít noise)?

Usage:
    # Chạy với dataset mặc định
    python -m app.evaluation.eval_legal_rag

    # Chạy với dataset tùy chỉnh
    python -m app.evaluation.eval_legal_rag --dataset path/to/dataset.json

    # Chạy chỉ N câu đầu tiên (để test)
    python -m app.evaluation.eval_legal_rag --limit 5

Kết quả lưu tại: app/evaluation/results/
    - results_YYYYMMDD_HHMMSS.json  (Chi tiết đầy đủ)
    - results_YYYYMMDD_HHMMSS.csv   (CSV để phân tích)

Yêu cầu:
    pip install ragas datasets langchain-openai
"""

import asyncio
import csv
import json
import math
import os
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

# Suppress deprecation warnings
warnings.filterwarnings(
    "ignore",
    message=".*LangchainLLMWrapper is deprecated.*",
    category=DeprecationWarning,
)
warnings.filterwarnings(
    "ignore",
    message=".*Unexpected type for token usage.*",
    category=UserWarning,
)

# Load .env từ thư mục backend
BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=BACKEND_DIR / ".env", override=False)

# Thêm backend vào sys.path để import app modules
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# ============================================================
# Conditional imports — chỉ fail nếu chạy evaluation
# ============================================================
try:
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import (
        AnswerRelevancy,
        ContextPrecision,
        ContextRecall,
        Faithfulness,
    )
    from ragas.llms import LangchainLLMWrapper
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings

    RAGAS_AVAILABLE = True
except ImportError:
    RAGAS_AVAILABLE = False


def _is_nan(value: Any) -> bool:
    return isinstance(value, float) and math.isnan(value)


# ============================================================
# Core Evaluator
# ============================================================
class LegalRAGEvaluator:
    """Đánh giá chất lượng hệ thống Legal AI Platform bằng RAGAS metrics."""

    def __init__(self, test_dataset_path: str = None, limit: int = None):
        """
        Args:
            test_dataset_path: Đường dẫn file JSON chứa test dataset.
            limit: Chỉ chạy N câu đầu tiên (để test nhanh).

        Biến môi trường cần thiết:
            OLLAMA_API_KEY: API key cho Ollama (dùng làm judge LLM)
            LLM_BASE_URL: Base URL của Ollama endpoint
            LLM_MODEL: Model name (mặc định: gpt-oss:120b-cloud)
        """
        if not RAGAS_AVAILABLE:
            raise ImportError(
                "RAGAS dependencies chưa cài đặt.\n"
                "Chạy: pip install ragas datasets langchain-openai"
            )

        # ── Judge LLM (dùng Ollama model đang chạy) ─────────
        ollama_api_key = os.getenv("OLLAMA_API_KEY")
        llm_base_url = os.getenv("LLM_BASE_URL")
        llm_model = os.getenv("LLM_MODEL", "gpt-oss:120b-cloud")

        if not ollama_api_key:
            raise EnvironmentError(
                "OLLAMA_API_KEY chưa được set trong .env"
            )

        # RAGAS cần LangChain ChatOpenAI-compatible wrapper
        base_llm = ChatOpenAI(
            model=llm_model,
            api_key=ollama_api_key,
            base_url=llm_base_url,
            max_retries=3,
            request_timeout=180,
        )

        try:
            self.eval_llm = LangchainLLMWrapper(
                langchain_llm=base_llm,
                bypass_n=True,  # Ollama không hỗ trợ param 'n'
            )
        except Exception:
            self.eval_llm = base_llm

        # ── Embeddings (dùng cùng embedding endpoint) ────────
        # RAGAS cần embeddings cho Answer Relevancy metric
        # Dùng cùng Ollama endpoint nếu hỗ trợ, hoặc skip metric này
        self.eval_embeddings = None
        eval_embedding_key = os.getenv("EVAL_EMBEDDING_API_KEY") or os.getenv("OLLAMA_API_KEY")
        eval_embedding_url = os.getenv("EVAL_EMBEDDING_BASE_URL") or os.getenv("LLM_BASE_URL")
        eval_embedding_model = os.getenv("EVAL_EMBEDDING_MODEL", "text-embedding-3-small")

        try:
            self.eval_embeddings = OpenAIEmbeddings(
                model=eval_embedding_model,
                api_key=eval_embedding_key,
                base_url=eval_embedding_url,
            )
        except Exception as e:
            print(f"⚠️  Không thể khởi tạo embedding cho RAGAS: {e}")
            print("    Answer Relevancy metric sẽ bị bỏ qua.")

        # ── Dataset ──────────────────────────────────────────
        if test_dataset_path is None:
            test_dataset_path = Path(__file__).parent / "legal_test_dataset.json"

        self.test_dataset_path = Path(test_dataset_path)
        self.results_dir = Path(__file__).parent / "results"
        self.results_dir.mkdir(exist_ok=True)
        self.limit = limit

        self.test_cases = self._load_test_dataset()

        # ── RAG Orchestrator (gọi trực tiếp, không qua HTTP) ─
        self.rag_orchestrator = None

        # Store config for display
        self.llm_model = llm_model
        self.llm_base_url = llm_base_url

    def _load_test_dataset(self) -> List[Dict[str, str]]:
        """Load test dataset từ JSON file."""
        if not self.test_dataset_path.exists():
            raise FileNotFoundError(
                f"Không tìm thấy test dataset: {self.test_dataset_path}\n"
                f"Tạo file JSON với format:\n"
                f'[{{"question": "...", "ground_truth": "..."}}]'
            )

        with open(self.test_dataset_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if self.limit:
            data = data[: self.limit]

        print(f"📂 Loaded {len(data)} test cases từ {self.test_dataset_path}")
        return data

    async def _init_orchestrator(self):
        """Khởi tạo RAG orchestrator (kết nối Milvus, Neo4j, PG)."""
        if self.rag_orchestrator is not None:
            return

        print("🔌 Đang khởi tạo LightRAG orchestrator...")
        from app.services.lightrag_orchestrator import LightRAGOrchestrator

        self.rag_orchestrator = LightRAGOrchestrator()
        await self.rag_orchestrator.initialize()
        print("✅ LightRAG orchestrator đã sẵn sàng.")

    async def generate_rag_response(self, question: str) -> Dict[str, Any]:
        """
        Gọi trực tiếp rag_orchestrator.query() để lấy answer + contexts.

        Returns:
            {
                "answer": str,
                "contexts": list[str],
                "entities_count": int,
                "relations_count": int,
                "chunks_count": int,
            }
        """
        await self._init_orchestrator()

        result = await self.rag_orchestrator.query(
            message=question,
            mode="mix",
            history=[],
            stream=False,  # Không stream để lấy full response
        )

        # Extract answer
        llm_response = result.get("llm_response", {})
        answer = llm_response.get("content", "")
        if not answer:
            answer = "Không tìm thấy thông tin liên quan."

        # Extract contexts từ chunks
        data = result.get("data", {})
        chunks = data.get("chunks", [])
        entities = data.get("entities", [])
        relationships = data.get("relationships", [])

        # Contexts = nội dung text của các chunks đã retrieve
        contexts = []
        for chunk in chunks:
            content = chunk.get("content", "")
            if content:
                contexts.append(content)

        # Fallback: nếu không có chunks, dùng entity descriptions làm context
        if not contexts:
            for entity in entities:
                desc = entity.get("description", "")
                if desc:
                    contexts.append(desc)

        return {
            "answer": answer,
            "contexts": contexts,
            "entities_count": len(entities),
            "relations_count": len(relationships),
            "chunks_count": len(chunks),
        }

    async def evaluate_single_case(
        self, idx: int, test_case: Dict[str, str]
    ) -> Dict[str, Any]:
        """Đánh giá 1 test case."""
        question = test_case["question"]
        ground_truth = test_case["ground_truth"]

        print(f"\n{'='*60}")
        print(f"📝 Test {idx}/{len(self.test_cases)}: {question[:80]}...")
        print(f"{'='*60}")

        # Stage 1: Gọi RAG
        try:
            print("  ⏳ Stage 1: Đang query RAG...")
            start = time.time()
            rag_response = await self.generate_rag_response(question)
            rag_time = time.time() - start
            print(
                f"  ✅ RAG response: {len(rag_response['answer'])} chars, "
                f"{len(rag_response['contexts'])} contexts, "
                f"{rag_response['entities_count']} entities, "
                f"{rag_response['relations_count']} relations "
                f"({rag_time:.1f}s)"
            )
        except Exception as e:
            print(f"  ❌ RAG error: {e}")
            return {
                "test_number": idx,
                "question": question,
                "error": str(e),
                "metrics": {},
                "ragas_score": 0,
                "timestamp": datetime.now().isoformat(),
            }

        # Stage 2: Chạy RAGAS evaluation
        retrieved_contexts = rag_response["contexts"]

        # Nếu không có contexts → skip RAGAS (sẽ cho score 0)
        if not retrieved_contexts:
            print("  ⚠️  Không có contexts — bỏ qua RAGAS evaluation")
            return {
                "test_number": idx,
                "question": question,
                "answer": rag_response["answer"][:200],
                "ground_truth": ground_truth[:200],
                "contexts_count": 0,
                "metrics": {
                    "faithfulness": 0.0,
                    "answer_relevance": 0.0,
                    "context_recall": 0.0,
                    "context_precision": 0.0,
                },
                "ragas_score": 0.0,
                "rag_time": rag_time,
                "timestamp": datetime.now().isoformat(),
            }

        eval_dataset = Dataset.from_dict(
            {
                "question": [question],
                "answer": [rag_response["answer"]],
                "contexts": [retrieved_contexts],
                "ground_truth": [ground_truth],
            }
        )

        # Chọn metrics dựa trên khả năng embeddings
        metrics = [Faithfulness(), ContextRecall(), ContextPrecision()]
        if self.eval_embeddings:
            metrics.append(AnswerRelevancy())

        try:
            print("  ⏳ Stage 2: Đang chạy RAGAS evaluation...")
            start = time.time()

            eval_kwargs = {
                "dataset": eval_dataset,
                "metrics": metrics,
                "llm": self.eval_llm,
            }
            if self.eval_embeddings:
                eval_kwargs["embeddings"] = self.eval_embeddings

            eval_results = evaluate(**eval_kwargs)
            eval_time = time.time() - start

            df = eval_results.to_pandas()
            scores_row = df.iloc[0]

            result_metrics = {
                "faithfulness": float(scores_row.get("faithfulness", 0)),
                "context_recall": float(scores_row.get("context_recall", 0)),
                "context_precision": float(
                    scores_row.get("context_precision", 0)
                ),
            }

            if self.eval_embeddings:
                result_metrics["answer_relevance"] = float(
                    scores_row.get("answer_relevancy", 0)
                )

            # Xử lý NaN
            for key, value in result_metrics.items():
                if _is_nan(value):
                    result_metrics[key] = 0.0

            # Tính RAGAS score trung bình
            valid_scores = [v for v in result_metrics.values() if not _is_nan(v)]
            ragas_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0.0

            print(f"  ✅ RAGAS evaluation hoàn thành ({eval_time:.1f}s)")
            print(f"     Faithfulness:      {result_metrics['faithfulness']:.3f}")
            print(f"     Context Recall:    {result_metrics['context_recall']:.3f}")
            print(f"     Context Precision: {result_metrics['context_precision']:.3f}")
            if "answer_relevance" in result_metrics:
                print(f"     Answer Relevance:  {result_metrics['answer_relevance']:.3f}")
            print(f"     ── RAGAS Score:    {ragas_score:.3f}")

            return {
                "test_number": idx,
                "question": question,
                "answer": rag_response["answer"][:300],
                "ground_truth": ground_truth[:300],
                "contexts_count": len(retrieved_contexts),
                "entities_count": rag_response["entities_count"],
                "relations_count": rag_response["relations_count"],
                "metrics": result_metrics,
                "ragas_score": ragas_score,
                "rag_time": rag_time,
                "eval_time": eval_time,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            print(f"  ❌ RAGAS evaluation error: {e}")
            return {
                "test_number": idx,
                "question": question,
                "answer": rag_response["answer"][:200],
                "error": f"RAGAS error: {str(e)}",
                "metrics": {},
                "ragas_score": 0,
                "timestamp": datetime.now().isoformat(),
            }

    async def run_evaluation(self) -> Dict[str, Any]:
        """Chạy evaluation cho toàn bộ test dataset."""
        total_start = time.time()

        print("\n" + "=" * 70)
        print("🏛️  LEGAL AI PLATFORM — RAGAS EVALUATION")
        print("=" * 70)
        print(f"  Judge LLM:      {self.llm_model}")
        print(f"  LLM Endpoint:   {self.llm_base_url}")
        print(f"  Test cases:     {len(self.test_cases)}")
        print(f"  Dataset:        {self.test_dataset_path}")
        print(f"  Embeddings:     {'✅ Available' if self.eval_embeddings else '❌ Not available (Answer Relevancy disabled)'}")
        print("=" * 70)

        results = []
        for idx, test_case in enumerate(self.test_cases, start=1):
            result = await self.evaluate_single_case(idx, test_case)
            results.append(result)

        total_time = time.time() - total_start

        # ── Tổng hợp kết quả ────────────────────────────────
        successful = [r for r in results if "error" not in r]
        failed = [r for r in results if "error" in r]

        if successful:
            avg_metrics = {}
            for key in successful[0]["metrics"]:
                values = [r["metrics"][key] for r in successful if key in r["metrics"]]
                avg_metrics[key] = sum(values) / len(values) if values else 0.0

            avg_ragas = sum(r["ragas_score"] for r in successful) / len(successful)
        else:
            avg_metrics = {}
            avg_ragas = 0.0

        # ── In summary ──────────────────────────────────────
        print("\n" + "=" * 70)
        print("📊 KẾT QUẢ ĐÁNH GIÁ TỔNG HỢP")
        print("=" * 70)
        print(f"  Tổng test cases:   {len(results)}")
        print(f"  Thành công:        {len(successful)}")
        print(f"  Thất bại:          {len(failed)}")
        print(f"  Tổng thời gian:    {total_time:.1f}s")
        print()

        if avg_metrics:
            print("  Điểm trung bình:")
            for key, value in avg_metrics.items():
                label = key.replace("_", " ").title()
                bar = "█" * int(value * 20) + "░" * (20 - int(value * 20))
                print(f"    {label:22s} {bar} {value:.3f}")
            print()
            bar = "█" * int(avg_ragas * 20) + "░" * (20 - int(avg_ragas * 20))
            print(f"    {'RAGAS Score':22s} {bar} {avg_ragas:.3f}")

        if avg_ragas >= 0.8:
            print("\n  🟢 Chất lượng TỐT — Pipeline hoạt động hiệu quả")
        elif avg_ragas >= 0.6:
            print("\n  🟡 Chất lượng TRUNG BÌNH — Cần cải thiện")
        else:
            print("\n  🔴 Chất lượng THẤP — Cần kiểm tra lại pipeline")

        print("=" * 70)

        # ── Lưu kết quả ─────────────────────────────────────
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report = {
            "evaluation_config": {
                "judge_llm": self.llm_model,
                "llm_endpoint": self.llm_base_url,
                "dataset": str(self.test_dataset_path),
                "total_cases": len(results),
                "successful": len(successful),
                "failed": len(failed),
                "total_time_seconds": round(total_time, 2),
            },
            "average_metrics": avg_metrics,
            "average_ragas_score": round(avg_ragas, 4),
            "detailed_results": results,
        }

        # Save JSON
        json_path = self.results_dir / f"results_{timestamp}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n💾 JSON report: {json_path}")

        # Save CSV
        csv_path = self.results_dir / f"results_{timestamp}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            header = [
                "test_number",
                "question",
                "ragas_score",
                "faithfulness",
                "context_recall",
                "context_precision",
                "answer_relevance",
                "contexts_count",
                "entities_count",
                "relations_count",
                "rag_time",
                "error",
            ]
            writer.writerow(header)
            for r in results:
                writer.writerow([
                    r.get("test_number", ""),
                    r.get("question", "")[:100],
                    r.get("ragas_score", ""),
                    r.get("metrics", {}).get("faithfulness", ""),
                    r.get("metrics", {}).get("context_recall", ""),
                    r.get("metrics", {}).get("context_precision", ""),
                    r.get("metrics", {}).get("answer_relevance", ""),
                    r.get("contexts_count", ""),
                    r.get("entities_count", ""),
                    r.get("relations_count", ""),
                    r.get("rag_time", ""),
                    r.get("error", ""),
                ])
        print(f"💾 CSV report:  {csv_path}")

        return report


# ============================================================
# CLI Entry Point
# ============================================================
def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Đánh giá chất lượng Legal AI Platform bằng RAGAS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ví dụ:
  python -m app.evaluation.eval_legal_rag
  python -m app.evaluation.eval_legal_rag --dataset my_questions.json
  python -m app.evaluation.eval_legal_rag --limit 5
        """,
    )
    parser.add_argument(
        "-d", "--dataset",
        type=str,
        default=None,
        help="Đường dẫn file JSON test dataset",
    )
    parser.add_argument(
        "-l", "--limit",
        type=int,
        default=None,
        help="Chỉ chạy N câu đầu tiên (để test nhanh)",
    )

    args = parser.parse_args()

    evaluator = LegalRAGEvaluator(
        test_dataset_path=args.dataset,
        limit=args.limit,
    )

    asyncio.run(evaluator.run_evaluation())


if __name__ == "__main__":
    main()
