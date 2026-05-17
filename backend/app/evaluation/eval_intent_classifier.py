#!/usr/bin/env python3
"""
Intent Classifier Evaluation Script cho Legal AI Platform

Đánh giá chất lượng 9-intent classifier:
  - Overall Accuracy
  - Per-intent Precision / Recall / F1
  - Confusion Matrix
  - Follow-up detection rate
  - Critical misclassification analysis (legal_query bị nhầm)

Usage:
    python -m app.evaluation.eval_intent_classifier
    python -m app.evaluation.eval_intent_classifier --limit 10
    python -m app.evaluation.eval_intent_classifier --dataset path/to/custom.json

Kết quả lưu tại: app/evaluation/results/
    - intent_eval_YYYYMMDD_HHMMSS.json
    - intent_eval_YYYYMMDD_HHMMSS.csv
"""

import asyncio
import csv
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# ── Fix Windows console encoding for emoji/unicode ──────────
import io
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── Paths & Env ──────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=BACKEND_DIR / ".env", override=False)

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# ── Constants ────────────────────────────────────────────────
ALL_INTENTS = [
    "greeting", "farewell", "acknowledge", "capability",
    "legal_query", "out_of_domain", "toxic", "unsafe", "unclear",
]

INTENT_LABELS = {
    "greeting": "GRT", "farewell": "FRW", "acknowledge": "ACK",
    "capability": "CAP", "legal_query": "LEG", "out_of_domain": "OOD",
    "toxic": "TOX", "unsafe": "UNS", "unclear": "UNC",
}


# ── Evaluator ────────────────────────────────────────────────
class IntentClassifierEvaluator:
    """Đánh giá chất lượng Intent Classifier."""

    def __init__(self, test_dataset_path: str = None, limit: int = None):
        from app.services.prompt_manager import prompt_manager
        prompt_manager.load_prompts()

        from app.services.classifier_query import IntentRouter
        self.router = IntentRouter()

        if test_dataset_path is None:
            test_dataset_path = Path(__file__).parent / "intent_test_dataset.json"

        self.test_dataset_path = Path(test_dataset_path)
        self.results_dir = Path(__file__).parent / "results"
        self.results_dir.mkdir(exist_ok=True)
        self.limit = limit
        self.test_cases = self._load_dataset()

        from app.core.config import settings
        self.llm_model = settings.LLM_MODEL
        self.llm_base_url = settings.LLM_BASE_URL

    def _load_dataset(self) -> list[dict]:
        if not self.test_dataset_path.exists():
            raise FileNotFoundError(f"Không tìm thấy dataset: {self.test_dataset_path}")

        with open(self.test_dataset_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if self.limit:
            data = data[: self.limit]

        print(f"📂 Loaded {len(data)} test cases từ {self.test_dataset_path.name}")
        return data

    # ── Evaluate single case ─────────────────────────────────
    async def evaluate_single(self, idx: int, test_case: dict) -> dict:
        input_text = test_case["input"]
        expected = test_case["expected_intent"]
        history = test_case.get("history", [])
        description = test_case.get("description", "")

        start = time.time()
        try:
            result = await self.router.classify_intent(input_text, history)
        except Exception as e:
            return {
                "test_number": idx,
                "input": input_text,
                "description": description,
                "expected": expected,
                "predicted": "ERROR",
                "confidence": 0.0,
                "correct": False,
                "has_history": len(history) > 0,
                "is_followup": test_case.get("expected_intent") == "legal_query" and len(history) > 0,
                "time": round(time.time() - start, 2),
                "error": str(e),
            }

        elapsed = time.time() - start
        predicted = result["intent"]
        confidence = result["confidence"]

        return {
            "test_number": idx,
            "input": input_text,
            "description": description,
            "expected": expected,
            "predicted": predicted,
            "confidence": confidence,
            "correct": predicted == expected,
            "has_history": len(history) > 0,
            "is_followup": expected == "legal_query" and len(history) > 0,
            "time": round(elapsed, 2),
        }

    # ── Compute metrics ──────────────────────────────────────
    @staticmethod
    def _compute_metrics(results: list[dict]) -> dict:
        total = len(results)
        correct = sum(1 for r in results if r["correct"])

        # Confusion matrix
        confusion = defaultdict(lambda: defaultdict(int))
        for r in results:
            confusion[r["expected"]][r["predicted"]] += 1

        # Per-intent metrics
        per_intent = {}
        for intent in ALL_INTENTS:
            tp = confusion[intent][intent]
            fp = sum(confusion[other][intent] for other in ALL_INTENTS if other != intent)
            fn = sum(confusion[intent][other] for other in ALL_INTENTS if other != intent)

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
            support = sum(confusion[intent].values())

            per_intent[intent] = {
                "precision": round(precision, 3),
                "recall": round(recall, 3),
                "f1": round(f1, 3),
                "support": support,
                "tp": tp, "fp": fp, "fn": fn,
            }

        # Follow-up detection
        followup_cases = [r for r in results if r["is_followup"]]
        followup_correct = sum(1 for r in followup_cases if r["correct"])

        # Critical: legal_query misclassified as something else
        legal_cases = [r for r in results if r["expected"] == "legal_query"]
        legal_misclassed = [r for r in legal_cases if not r["correct"]]

        # Confidence stats
        confidences = [r["confidence"] for r in results]
        correct_confs = [r["confidence"] for r in results if r["correct"]]
        wrong_confs = [r["confidence"] for r in results if not r["correct"]]

        # Fallback rate (confidence=0 → DEFAULT_RESULT)
        fallback_count = sum(1 for r in results if r["confidence"] == 0.0)

        return {
            "overall": {
                "accuracy": round(correct / total, 4) if total > 0 else 0,
                "correct": correct,
                "total": total,
                "avg_latency": round(sum(r["time"] for r in results) / total, 2) if total > 0 else 0,
            },
            "per_intent": per_intent,
            "confusion": {k: dict(v) for k, v in confusion.items()},
            "followup": {
                "total": len(followup_cases),
                "correct": followup_correct,
                "rate": round(followup_correct / len(followup_cases), 3) if followup_cases else 0,
            },
            "critical": {
                "legal_total": len(legal_cases),
                "legal_misclassed": len(legal_misclassed),
                "legal_misclass_rate": round(len(legal_misclassed) / len(legal_cases), 3) if legal_cases else 0,
                "details": [
                    {"input": r["input"][:60], "predicted": r["predicted"], "confidence": r["confidence"]}
                    for r in legal_misclassed
                ],
            },
            "confidence": {
                "avg_all": round(sum(confidences) / len(confidences), 3) if confidences else 0,
                "avg_correct": round(sum(correct_confs) / len(correct_confs), 3) if correct_confs else 0,
                "avg_wrong": round(sum(wrong_confs) / len(wrong_confs), 3) if wrong_confs else 0,
                "fallback_count": fallback_count,
                "fallback_rate": round(fallback_count / total, 3) if total > 0 else 0,
            },
        }

    # ── Print report ─────────────────────────────────────────
    @staticmethod
    def _print_report(metrics: dict, results: list[dict]):
        o = metrics["overall"]
        pi = metrics["per_intent"]
        fu = metrics["followup"]
        cr = metrics["critical"]
        co = metrics["confidence"]
        cm = metrics["confusion"]

        pct = o["accuracy"] * 100

        print()
        print("=" * 70)
        print("🧠  INTENT CLASSIFIER EVALUATION")
        print("=" * 70)
        print(f"  Total test cases:   {o['total']}")
        print(f"  Avg latency:        {o['avg_latency']}s / case")
        print()

        # ── Overall Accuracy ──
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        color = "🟢" if pct >= 85 else ("🟡" if pct >= 70 else "🔴")
        print(f"  {color} Accuracy: {bar}  {pct:.1f}%  ({o['correct']}/{o['total']})")
        print()

        # ── Per-intent table ──
        print("-" * 70)
        print(f"  {'Intent':<16s} {'Prec':>6s} {'Rec':>6s} {'F1':>6s} {'Support':>8s}")
        print("-" * 70)
        macro_f1_values = []
        for intent in ALL_INTENTS:
            m = pi.get(intent, {})
            p, r, f1, s = m.get("precision", 0), m.get("recall", 0), m.get("f1", 0), m.get("support", 0)
            if s > 0:
                macro_f1_values.append(f1)
            flag = " ⚠️" if r < 0.6 and s > 0 else ""
            print(f"  {intent:<16s} {p:>6.3f} {r:>6.3f} {f1:>6.3f} {s:>8d}{flag}")

        macro_f1 = sum(macro_f1_values) / len(macro_f1_values) if macro_f1_values else 0
        print("-" * 70)
        print(f"  {'Macro Avg F1':<16s} {'':>6s} {'':>6s} {macro_f1:>6.3f}")
        print()

        # ── Confusion Matrix ──
        print("-" * 70)
        print("  CONFUSION MATRIX  (rows = actual, cols = predicted)")
        print("-" * 70)

        present = [i for i in ALL_INTENTS if any(cm.get(i, {}).values()) or any(cm.get(j, {}).get(i, 0) for j in ALL_INTENTS)]
        if not present:
            present = ALL_INTENTS

        labels = [INTENT_LABELS[i] for i in present]
        header = "  " + f"{'':>5s}" + "".join(f"{lb:>5s}" for lb in labels)
        print(header)

        for actual in present:
            row_label = INTENT_LABELS[actual]
            cells = []
            for predicted in present:
                count = cm.get(actual, {}).get(predicted, 0)
                if actual == predicted and count > 0:
                    cells.append(f"\033[92m{count:>5d}\033[0m")  # Green for diagonal
                elif count > 0:
                    cells.append(f"\033[91m{count:>5d}\033[0m")  # Red for errors
                else:
                    cells.append(f"{'·':>5s}")
            print(f"  {row_label:>5s}" + "".join(cells))
        print()

        # ── Follow-up Detection ──
        print("-" * 70)
        fu_pct = fu["rate"] * 100
        fu_color = "🟢" if fu_pct >= 80 else ("🟡" if fu_pct >= 60 else "🔴")
        print(f"  {fu_color} Follow-up detection:  {fu_pct:.0f}%  ({fu['correct']}/{fu['total']})")

        # ── Critical Misclassification ──
        cr_pct = cr["legal_misclass_rate"] * 100
        cr_color = "🟢" if cr_pct <= 5 else ("🟡" if cr_pct <= 15 else "🔴")
        print(f"  {cr_color} Legal misclass rate:  {cr_pct:.0f}%  ({cr['legal_misclassed']}/{cr['legal_total']})")

        if cr["details"]:
            print()
            print("  ❌ Legal_query misclassified as:")
            for d in cr["details"]:
                print(f"     \"{d['input']}\"  →  {d['predicted']} (conf: {d['confidence']})")
        print()

        # ── Confidence Stats ──
        print("-" * 70)
        print(f"  Confidence avg (all):      {co['avg_all']:.3f}")
        print(f"  Confidence avg (correct):  {co['avg_correct']:.3f}")
        print(f"  Confidence avg (wrong):    {co['avg_wrong']:.3f}")
        print(f"  Fallback rate (conf=0):    {co['fallback_rate']*100:.0f}%  ({co['fallback_count']}/{metrics['overall']['total']})")
        print()

        # ── Misclassified cases ──
        misclassed = [r for r in results if not r["correct"]]
        if misclassed:
            print("-" * 70)
            print(f"  ❌ ALL MISCLASSIFIED CASES ({len(misclassed)}):")
            print("-" * 70)
            for r in misclassed:
                hist_tag = " [+hist]" if r["has_history"] else ""
                print(f"  #{r['test_number']:>2d}  \"{r['input'][:50]}\"")
                print(f"       Expected: {r['expected']}  →  Predicted: {r['predicted']}  (conf: {r['confidence']}){hist_tag}")
        else:
            print("  ✅ Không có case nào bị phân loại sai!")

        print("=" * 70)

    # ── Save results ─────────────────────────────────────────
    def _save_results(self, metrics: dict, results: list[dict]) -> tuple[Path, Path]:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # JSON
        report = {
            "evaluation_config": {
                "llm_model": self.llm_model,
                "llm_endpoint": self.llm_base_url,
                "dataset": str(self.test_dataset_path),
                "total_cases": metrics["overall"]["total"],
                "timestamp": datetime.now().isoformat(),
            },
            "metrics": metrics,
            "detailed_results": results,
        }

        json_path = self.results_dir / f"intent_eval_{timestamp}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # CSV
        csv_path = self.results_dir / f"intent_eval_{timestamp}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "test_number", "input", "description", "expected", "predicted",
                "confidence", "correct", "has_history", "is_followup", "time",
            ])
            for r in results:
                writer.writerow([
                    r["test_number"], r["input"][:100], r.get("description", ""),
                    r["expected"], r["predicted"], r["confidence"],
                    r["correct"], r["has_history"], r["is_followup"], r["time"],
                ])

        return json_path, csv_path

    # ── Main runner ──────────────────────────────────────────
    async def run_evaluation(self) -> dict:
        total_start = time.time()

        print()
        print("=" * 70)
        print("🧠  LEGAL AI — INTENT CLASSIFIER EVALUATION")
        print("=" * 70)
        print(f"  LLM Model:    {self.llm_model}")
        print(f"  LLM Endpoint: {self.llm_base_url}")
        print(f"  Test cases:   {len(self.test_cases)}")
        print(f"  Dataset:      {self.test_dataset_path.name}")
        print("=" * 70)

        results = []
        for idx, test_case in enumerate(self.test_cases, start=1):
            input_short = test_case["input"][:40]
            expected = test_case["expected_intent"]
            hist_tag = " [+hist]" if test_case.get("history") else ""

            print(f"  [{idx:>2d}/{len(self.test_cases)}] \"{input_short}\" (expect: {expected}){hist_tag}", end="", flush=True)

            result = await self.evaluate_single(idx, test_case)
            results.append(result)

            status = "✅" if result["correct"] else "❌"
            print(f"  → {result['predicted']} (conf: {result['confidence']:.2f}) {status}  [{result['time']}s]")

            # Small delay to avoid rate limiting
            await asyncio.sleep(0.3)

        total_time = time.time() - total_start

        # Compute metrics
        metrics = self._compute_metrics(results)
        metrics["total_time"] = round(total_time, 1)

        # Print report
        self._print_report(metrics, results)

        # Save
        json_path, csv_path = self._save_results(metrics, results)
        print(f"\n💾 JSON: {json_path}")
        print(f"💾 CSV:  {csv_path}")
        print(f"⏱️  Total time: {total_time:.1f}s")
        print()

        return {"metrics": metrics, "results": results}


# ── CLI ──────────────────────────────────────────────────────
def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Đánh giá Intent Classifier cho Legal AI Platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ví dụ:
  python -m app.evaluation.eval_intent_classifier
  python -m app.evaluation.eval_intent_classifier --limit 10
  python -m app.evaluation.eval_intent_classifier --dataset custom.json
        """,
    )
    parser.add_argument("-d", "--dataset", type=str, default=None, help="Đường dẫn JSON test dataset")
    parser.add_argument("-l", "--limit", type=int, default=None, help="Chỉ chạy N test cases đầu tiên")

    args = parser.parse_args()

    evaluator = IntentClassifierEvaluator(
        test_dataset_path=args.dataset,
        limit=args.limit,
    )

    asyncio.run(evaluator.run_evaluation())


if __name__ == "__main__":
    main()
