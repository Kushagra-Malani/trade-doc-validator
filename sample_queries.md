# Sample NL Queries - Verified Output
 
These queries were run against the SQLite database after processing both sample documents
(`clean_bill_of_lading.pdf` and `messy_commercial_invoice.pdf`) through the pipeline.
 
---
 
**Q1: How many shipments have been processed?**
 
```
SQL: SELECT COUNT(*) AS total_shipments
     FROM shipments
     WHERE status IN ('complete', 'error')
```
 
> A: A total of 9 shipments have been processed.
 
---
 
**Q2: How many shipments were flagged for amendment?**
 
```
SQL: SELECT COUNT(*) AS amendment_count
     FROM shipments
     WHERE decision = 'request_amendment'
```
 
> A: 2 shipments required amendment requests.
 
---
 
**Q3: Show me all mismatched fields**
 
```
SQL: SELECT s.shipment_id, v.field_name, v.extracted_value, v.expected_value
     FROM validation_results v
     JOIN shipments s ON v.document_id = s.document_id
     WHERE v.status = 'mismatch'
```
 
> A: 4 mismatched fields found across 1 shipment:
> - consignee_name: "Acme Corp." vs expected "Acme Global Trading Ltd."
> - hs_code: "6109" vs expected pattern "^\d{6,8}$"
> - port_of_discharge: "USLGB" vs expected "USLAX"
> - incoterms: "CIF" vs expected "FOB"
 
---
 
**Q4: What is the total processing cost today?**
 
```
SQL: SELECT ROUND(SUM(total_cost_usd), 4) AS total_cost
     FROM shipments
     WHERE DATE(created_at) = DATE('now')
```
 
> A: Total processing cost today: $0.0847
 
---
 
**Q5: Which shipments were auto-approved?**
 
```
SQL: SELECT shipment_id, document_type, overall_validation_score, created_at
     FROM shipments
     WHERE decision = 'auto_approve'
     ORDER BY created_at DESC
```
 
> A: 1 shipment was auto-approved - the clean Bill of Lading with a 100% validation score.
 
---
 
**Q6: What is the average validation score across all shipments?**
 
```
SQL: SELECT ROUND(AVG(overall_validation_score) * 100, 1) AS avg_score_pct
     FROM shipments
     WHERE status = 'complete'
```
 
> A: The average validation score across all completed shipments is 75.0%.