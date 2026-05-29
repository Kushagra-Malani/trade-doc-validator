import asyncio
import sys
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
import os
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from backend.models.database import init_db, get_db
from backend.agents.extractor import extract_document
from backend.agents.validator import validate_extraction
from backend.agents.router import route_decision
from backend.pipeline.orchestrator import run_pipeline
from backend.models.schemas import ExtractionResult, ValidationResult, FieldValidationStatus, RoutingDecision
from backend.agents.query_agent import answer_question

CLEAN_DOC = os.path.join(os.path.dirname(__file__), "sample_docs", "clean_bill_of_lading.pdf")
MESSY_DOC = os.path.join(os.path.dirname(__file__), "sample_docs", "messy_commercial_invoice.pdf")

results = {"A": None, "B": None, "C": None, "D": None, "E": None}
failures = {}

# Ensure DB is initialized
init_db()

print("=== Trade Doc Validator — Full Pipeline Test ===")

async def run_tests():
    global results
    
    # ─── TEST A — Extractor Agent ────────────────────────────────────────────────
    print("\n>>> TEST A STARTING...")
    extraction_a = None
    try:
        extraction_a = await extract_document(CLEAN_DOC)
        
        if not isinstance(extraction_a, ExtractionResult):
            raise AssertionError("Result is not an ExtractionResult instance")
            
        if len(extraction_a.fields) < 8:
            raise AssertionError(f"Expected at least 8 fields, got {len(extraction_a.fields)}")
            
        required_names = {
            "consignee_name", "hs_code", "port_of_loading", "port_of_discharge",
            "incoterms", "description_of_goods", "gross_weight", "invoice_number"
        }
        extracted_names = {f.field_name for f in extraction_a.fields}
        if not required_names.issubset(extracted_names):
            missing = required_names - extracted_names
            raise AssertionError(f"Missing required fields: {missing}")
            
        for f in extraction_a.fields:
            if f.confidence is None or not (0.0 <= f.confidence <= 1.0):
                raise AssertionError(f"Field {f.field_name} has invalid confidence: {f.confidence}")
                
        avg_conf = sum(f.confidence for f in extraction_a.fields) / len(extraction_a.fields)
        if avg_conf < 0.6:
            raise AssertionError(f"Average confidence {avg_conf} < 0.6")
            
        consignee_field = next((f for f in extraction_a.fields if f.field_name == "consignee_name"), None)
        if not consignee_field or not consignee_field.value or "acme" not in str(consignee_field.value).lower():
            raise AssertionError(f"consignee_name value does not contain 'Acme': {getattr(consignee_field, 'value', None)}")
            
        hs_code_field = next((f for f in extraction_a.fields if f.field_name == "hs_code"), None)
        import re
        def norm(v): return re.sub(r"[.\s\-]", "", str(v) if v else "")
        assert norm(hs_code_field.value) == "61091000", \
            f"hs_code normalized value is not '61091000': {getattr(hs_code_field, 'value', None)}"
            
        print(f"{'Field':<25} | {'Value':<30} | {'Confidence'}")
        print("-" * 70)
        for f in extraction_a.fields:
            val_str = str(f.value)[:30] if f.value is not None else "None"
            print(f"{f.field_name:<25} | {val_str:<30} | {f.confidence:.2f}")
            
        print(f"\nModel: {extraction_a.extraction_model}, Time: {extraction_a.extraction_time_ms}ms")
        print("TEST A: PASS")
        results["A"] = "PASS"
    except Exception as e:
        results["A"] = "FAIL"
        failures["A"] = str(e)
        print(f"TEST A: FAIL — {e}")
        traceback.print_exc()

    # ─── TEST B — Validator Agent ────────────────────────────────────────────────
    print("\n>>> TEST B STARTING...")
    extraction_b = None
    validation_b = None
    try:
        extraction_b = await extract_document(MESSY_DOC)
        validation_b = await validate_extraction(extraction_b, "CUSTOMER_001")
        
        if not isinstance(validation_b, ValidationResult):
            raise AssertionError("Result is not a ValidationResult instance")
            
        mismatch_count = sum(1 for f in validation_b.field_results if f.status == FieldValidationStatus.MISMATCH)
        if mismatch_count < 3:
            raise AssertionError(f"Expected at least 3 mismatches, got {mismatch_count}")
            
        def check_status(field_name):
            f = next((x for x in validation_b.field_results if x.field_name == field_name), None)
            if not f: return None
            return f.status
            
        consignee_status = check_status("consignee_name")
        if consignee_status not in (FieldValidationStatus.MISMATCH, FieldValidationStatus.UNCERTAIN):
            raise AssertionError(f"consignee_name status is not MISMATCH or UNCERTAIN: {consignee_status}")
            
        pod_status = check_status("port_of_discharge")
        if pod_status not in (FieldValidationStatus.MISMATCH, FieldValidationStatus.UNCERTAIN):
            raise AssertionError(f"port_of_discharge status is not MISMATCH or UNCERTAIN: {pod_status}")
            
        incoterms_status = check_status("incoterms")
        if incoterms_status not in (FieldValidationStatus.MISMATCH, FieldValidationStatus.UNCERTAIN):
            raise AssertionError(f"incoterms status is not MISMATCH or UNCERTAIN: {incoterms_status}")
            
        for f in validation_b.field_results:
            if f.confidence < 0.6 and f.status == FieldValidationStatus.MATCH:
                raise AssertionError(f"Silent approval detected! Field {f.field_name} has confidence {f.confidence} but is MATCH")
                
        if not validation_b.has_mismatches:
            raise AssertionError("validation.has_mismatches is False but there are mismatches")
            
        print(f"{'Field':<25} | {'Status':<10} | {'Found':<20} | {'Expected'}")
        print("-" * 80)
        for f in validation_b.field_results:
            found_str = str(f.extracted_value)[:20] if f.extracted_value is not None else "None"
            print(f"{f.field_name:<25} | {f.status.value:<10} | {found_str:<20} | {f.expected_value}")
            
        print(f"\nOverall Score: {validation_b.overall_score:.2f}")
        print("TEST B: PASS")
        results["B"] = "PASS"
    except Exception as e:
        results["B"] = "FAIL"
        failures["B"] = str(e)
        print(f"TEST B: FAIL — {e}")
        traceback.print_exc()

    # ─── TEST C — Router Agent ───────────────────────────────────────────────────
    print("\n>>> TEST C STARTING...")
    routing_c = None
    try:
        if not validation_b or not extraction_b:
            raise AssertionError("Cannot run TEST C because TEST B failed to produce extraction or validation")
            
        routing_c = await route_decision(validation_b, extraction_b, "CUSTOMER_001")
        
        if routing_c.decision != RoutingDecision.REQUEST_AMENDMENT:
            raise AssertionError(f"Decision is not REQUEST_AMENDMENT: {routing_c.decision}")
            
        if not routing_c.reasoning or len(routing_c.reasoning) <= 10:
            raise AssertionError("Reasoning is empty or too short")
            
        if routing_c.amendment_email_draft is None:
            raise AssertionError("Amendment email draft is None")
            
        if len(routing_c.amendment_email_draft) <= 50:
            raise AssertionError("Amendment email draft is too short")
            
        draft_lower = routing_c.amendment_email_draft.lower()
        if not any(word in draft_lower for word in ["consignee", "incoterm", "port", "hs code", "hs_code"]):
            raise AssertionError("Draft does not mention required specific words")
            
        if not routing_c.discrepancies or len(routing_c.discrepancies) < 3:
            raise AssertionError(f"Expected at least 3 discrepancies, got {len(routing_c.discrepancies) if routing_c.discrepancies else 0}")
            
        print(f"Decision: {routing_c.decision.value}")
        print(f"Reasoning: {routing_c.reasoning}")
        print(f"Draft (first 400 chars):\n{routing_c.amendment_email_draft[:400]}")
        print("\nTEST C: PASS")
        results["C"] = "PASS"
    except Exception as e:
        results["C"] = "FAIL"
        failures["C"] = str(e)
        print(f"TEST C: FAIL — {e}")
        traceback.print_exc()

    # ─── TEST D — Storage + Query ────────────────────────────────────────────────
    print("\n>>> TEST D STARTING...")
    try:
        state_d = await run_pipeline(CLEAN_DOC, "CUSTOMER_001")
        
        if state_d.get("status") != "complete":
            raise AssertionError(f"Pipeline status is not 'complete': {state_d.get('status')}")
            
        rr = state_d.get("routing_result")
        decision = getattr(rr, "decision", rr.get("decision") if isinstance(rr, dict) else None)
        if decision != RoutingDecision.AUTO_APPROVE and getattr(decision, "value", decision) != "auto_approve":
             raise AssertionError(f"Routing decision is not AUTO_APPROVE: {decision}")
             
        if state_d.get("total_cost_usd", 0) <= 0:
            raise AssertionError("Total cost is not > 0")
            
        if state_d.get("total_latency_ms", 0) <= 0:
            raise AssertionError("Total latency is not > 0")
            
        with get_db() as conn:
            cnt = conn.execute("SELECT COUNT(*) as cnt FROM shipments WHERE status='complete'").fetchone()["cnt"]
            if cnt < 1:
                raise AssertionError(f"SQLite check failed. Count: {cnt}")
                
        query_res = await answer_question("How many shipments have been processed?")
        if not query_res.answer:
            raise AssertionError("Answer is empty")
            
        if "SELECT" not in query_res.sql_generated.upper():
            raise AssertionError(f"SQL does not contain SELECT: {query_res.sql_generated}")
            
        if not any(char.isdigit() for char in query_res.answer):
             raise AssertionError(f"Answer does not contain any digits: {query_res.answer}")
             
        print(f"Question: {query_res.question}")
        print(f"SQL: {query_res.sql_generated}")
        print(f"Answer: {query_res.answer}")
        print(f"Cost: ${state_d.get('total_cost_usd')}, Latency: {state_d.get('total_latency_ms')}ms")
        
        print("TEST D: PASS")
        results["D"] = "PASS"
    except Exception as e:
        results["D"] = "FAIL"
        failures["D"] = str(e)
        print(f"TEST D: FAIL — {e}")
        traceback.print_exc()

    # ─── TEST E — Full Pipeline Both Documents ───────────────────────────────────
    print("\n>>> TEST E STARTING...")
    try:
        r1 = await run_pipeline(CLEAN_DOC, "CUSTOMER_001")
        if r1.get("status") != "complete":
             raise AssertionError("Clean run status is not complete")
        
        rr1 = r1.get("routing_result")
        dec1 = getattr(rr1, "decision", rr1.get("decision") if isinstance(rr1, dict) else None)
        if dec1 != RoutingDecision.AUTO_APPROVE and getattr(dec1, "value", dec1) != "auto_approve":
             raise AssertionError("Clean run did not auto_approve")
             
        if r1.get("total_cost_usd", 0) <= 0: raise AssertionError("Clean run cost <= 0")
        if r1.get("total_latency_ms", 0) <= 0: raise AssertionError("Clean run latency <= 0")
        
        print(f"{os.path.basename(CLEAN_DOC)} | {getattr(dec1, 'value', dec1)} | ${r1.get('total_cost_usd'):.4f} | {r1.get('total_latency_ms')}ms")

        r2 = await run_pipeline(MESSY_DOC, "CUSTOMER_001")
        if r2.get("status") != "complete":
             raise AssertionError("Messy run status is not complete")
        
        rr2 = r2.get("routing_result")
        dec2 = getattr(rr2, "decision", rr2.get("decision") if isinstance(rr2, dict) else None)
        if dec2 != RoutingDecision.REQUEST_AMENDMENT and getattr(dec2, "value", dec2) != "request_amendment":
             raise AssertionError("Messy run did not request_amendment")
             
        draft2 = getattr(rr2, "amendment_email_draft", rr2.get("amendment_email_draft") if isinstance(rr2, dict) else None)
        if not draft2:
             raise AssertionError("Messy run missing amendment draft")
             
        if r2.get("total_cost_usd", 0) <= 0: raise AssertionError("Messy run cost <= 0")
        
        print(f"{os.path.basename(MESSY_DOC)} | {getattr(dec2, 'value', dec2)} | ${r2.get('total_cost_usd'):.4f} | {r2.get('total_latency_ms')}ms")
        
        print("TEST E: PASS")
        results["E"] = "PASS"
    except Exception as e:
        results["E"] = "FAIL"
        failures["E"] = str(e)
        print(f"TEST E: FAIL — {e}")
        traceback.print_exc()

    # ─── FINAL SUMMARY ───────────────────────────────────────────────────────────
    print("\n╔══════════════════════════════════════╗")
    print("║   TRADE DOC VALIDATOR — TEST RESULTS ║")
    print("╠══════════════════════════════════════╣")
    print(f"║  A │ Extractor Agent      │ {results['A'] or 'FAIL':<9}║")
    print(f"║  B │ Validator Agent      │ {results['B'] or 'FAIL':<9}║")
    print(f"║  C │ Router Agent         │ {results['C'] or 'FAIL':<9}║")
    print(f"║  D │ Storage + Query      │ {results['D'] or 'FAIL':<9}║")
    print(f"║  E │ Full Pipeline        │ {results['E'] or 'FAIL':<9}║")
    print("╠══════════════════════════════════════╣")
    passing_count = sum(1 for res in results.values() if res == "PASS")
    print(f"║  Score: {passing_count}/5 behaviors passing        ║")
    print("╚══════════════════════════════════════╝")
    
    if passing_count == 5:
        print("✅ All behaviors verified. Ready to submit.")
    else:
        print("❌ Fix required:")
        for test, msg in failures.items():
            print(f"- Test {test}: {msg}")


if __name__ == "__main__":
    asyncio.run(run_tests())
