from business_catalog import BusinessCatalog


def test_different_databases_get_different_dynamic_catalogs():
    catalog = BusinessCatalog()
    sales_schema = {
        "invoices": {
            "columns": [
                {"name": "invoice_id", "type": "int", "primary_key": True},
                {"name": "customer_id", "type": "int"},
                {"name": "invoice_total", "type": "decimal"},
            ],
            "foreign_keys": [],
        },
        "customers": {
            "columns": [
                {"name": "customer_id", "type": "int", "primary_key": True},
                {"name": "customer_name", "type": "text"},
            ],
            "foreign_keys": [],
        },
    }
    hr_schema = {
        "employees": {
            "columns": [
                {"name": "employee_id", "type": "int", "primary_key": True},
                {"name": "department_id", "type": "int"},
                {"name": "salary", "type": "int"},
            ],
            "foreign_keys": [],
        },
        "departments": {
            "columns": [
                {"name": "department_id", "type": "int", "primary_key": True},
                {"name": "department_name", "type": "text"},
            ],
            "foreign_keys": [],
        },
    }

    sales = catalog.build(sales_schema, source_type="sqlite")
    hr = catalog.build(hr_schema, source_type="sqlite")

    assert sales["schema_fingerprint"] != hr["schema_fingerprint"]
    assert "customer" in sales["entities"]
    assert "employee" in hr["entities"]


def test_catalog_detects_missing_profit_loss_kpi():
    schema = {
        "invoices": {
            "columns": [
                {"name": "invoice_id", "type": "int"},
                {"name": "invoice_total", "type": "decimal"},
            ],
            "foreign_keys": [],
        }
    }

    analysis = BusinessCatalog().analyze_question(
        "What is the company loss?",
        schema,
        source_type="sqlite",
    )

    assert analysis["missing_kpis"] == ["true_profit_loss"]


def test_catalog_cache_is_fingerprint_specific():
    catalog = BusinessCatalog()
    schema = {
        "projects": {
            "columns": [{"name": "project_id", "type": "int"}],
            "foreign_keys": [],
        }
    }
    first = catalog.build(schema, source_type="sqlite")
    second = catalog.build(schema, source_type="sqlite")

    assert first is second
