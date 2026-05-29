"""
customer_rules.py — Customer-specific validation rule sets.

Each customer has a dictionary of field rules that the Validator Agent
uses to check extracted fields against expected values.

Supported match types:
  - "exact"     — case-insensitive string comparison with trimming;
                  also checks an ``alternatives`` list if present
  - "fuzzy"     — LLM-assisted semantic comparison with a confidence threshold
  - "regex"     — Python regex pattern match; also checks ``allowed_values`` list
  - "presence"  — value is not null and not empty
  - "contains"  — expected string is a substring of the extracted value
"""

CUSTOMER_RULES: dict = {
    "CUSTOMER_001": {
        "customer_name": "Acme Global Trading Ltd.",
        "rules": {
            "consignee_name": {
                "expected": "Acme Global Trading Ltd.",
                "match_type": "fuzzy",  # "exact" | "fuzzy" | "contains" | "regex"
                "fuzzy_threshold": 0.85,
                "required": True,
            },
            "hs_code": {
                "expected_pattern": r"^\d{6,8}$",
                "match_type": "regex",
                "required": True,
                "allowed_values": ["61091000", "61099090", "62034200"],
            },
            "port_of_discharge": {
                "expected": "USLAX",
                "match_type": "exact",
                "required": True,
                "alternatives": ["Los Angeles", "LA", "USLAX", "US LAX"],
            },
            "port_of_loading": {
                "expected": "INNSA",
                "match_type": "exact",
                "required": True,
                "alternatives": ["Nhava Sheva", "JNPT", "INNSA", "IN NSA"],
            },
            "incoterms": {
                "expected": "FOB",
                "match_type": "exact",
                "required": True,
                "allowed_values": ["FOB", "CIF", "CFR", "EXW", "DDP"],
            },
            "gross_weight": {
                "match_type": "presence",  # just check it's present and numeric
                "required": True,
            },
            "invoice_number": {
                "match_type": "presence",
                "required": True,
            },
            "description_of_goods": {
                "match_type": "presence",
                "required": True,
            },
        },
    }
}
