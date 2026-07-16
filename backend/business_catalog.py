import hashlib
import json
import re


class BusinessCatalog:
    ENTITY_ALIASES = {
        "billing": ("bill", "billing", "invoice", "receivable"),
        "project": ("project", "site", "work"),
        "employee": ("employee", "emp", "staff", "worker"),
        "department": ("department", "dept", "division"),
        "customer": ("customer", "client"),
        "vendor": ("vendor", "supplier", "seller"),
        "product": ("product", "item", "material", "asset", "spare"),
        "payment": ("payment", "paid", "bank", "transaction"),
        "inventory": ("stock", "store", "inventory", "material", "grn"),
        "logistics": ("transport", "vehicle", "freight", "logistic"),
    }
    KPI_ALIASES = {
        "revenue": ("revenue", "sales", "bill", "billing", "invoice", "amount", "total"),
        "cost": ("cost", "expense", "spend"),
        "profit": ("profit", "margin", "loss"),
        "quantity": ("qty", "quantity", "count", "units"),
        "status": ("status", "state", "stage"),
        "date": ("date", "time", "created", "updated", "month", "year"),
    }
    NOISY_TABLE = re.compile(r"(?:hist|history|attachment|log|notification)", re.I)

    def __init__(self):
        self._cache = {}

    def fingerprint(self, schema):
        compact = {}
        for table, info in sorted(schema.items()):
            compact[table] = [
                self._column_name(column)
                for column in info.get("columns", [])
            ]
        return hashlib.sha256(
            json.dumps(compact, sort_keys=True).encode("utf-8")
        ).hexdigest()

    def build(self, schema, *, source_type="database", row_counts=None, fingerprint=None):
        fingerprint = fingerprint or self.fingerprint(schema)
        key = f"{source_type}:{fingerprint}"
        if key in self._cache:
            return self._cache[key]

        entities = self._entities(schema)
        joins = self._joins(schema)
        important_tables = self._important_tables(schema, row_counts or {})
        unsupported = self._unsupported_kpis(entities)
        catalog = {
            "source_type": source_type,
            "schema_fingerprint": fingerprint,
            "table_count": len(schema),
            "entities": entities,
            "aliases": self.ENTITY_ALIASES,
            "kpi_aliases": self.KPI_ALIASES,
            "important_tables": important_tables[:20],
            "join_paths": joins[:50],
            "unsupported_kpis": unsupported,
            "summary": self._summary(source_type, schema, entities),
        }
        self._cache[key] = catalog
        return catalog

    def overview(self, schema, *, source_type="database", row_counts=None, fingerprint=None):
        catalog = self.build(
            schema,
            source_type=source_type,
            row_counts=row_counts,
            fingerprint=fingerprint,
        )
        return {
            "source_type": catalog["source_type"],
            "schema_fingerprint": catalog["schema_fingerprint"],
            "table_count": catalog["table_count"],
            "detected_modules": list(catalog["entities"].keys())[:12],
            "important_tables": catalog["important_tables"][:12],
            "key_relationships": catalog["join_paths"][:12],
            "unsupported_kpis": catalog["unsupported_kpis"],
            "short_schema_summary": catalog["summary"],
        }

    def analyze_question(self, question, schema, *, source_type="database", row_counts=None, fingerprint=None):
        catalog = self.build(
            schema,
            source_type=source_type,
            row_counts=row_counts,
            fingerprint=fingerprint,
        )
        words = self._expanded_words(question)
        candidates = []
        for entity, detail in catalog["entities"].items():
            entity_words = set(self.ENTITY_ALIASES.get(entity, (entity,)))
            score = len(words & entity_words) * 10
            matched_tables = []
            for table in detail["tables"]:
                table_words = self._expanded_words(table["table"])
                column_hits = [
                    column for column in table["columns"]
                    if words & self._expanded_words(column["name"])
                ]
                table_score = len(words & table_words) * 6 + len(column_hits) * 3
                if table_score:
                    matched_tables.append({
                        "table": table["table"],
                        "columns": [column["name"] for column in column_hits][:10],
                        "score": table_score,
                    })
                score += table_score
            if score:
                candidates.append({
                    "entity": entity,
                    "score": score,
                    "tables": sorted(matched_tables, key=lambda item: -item["score"])[:8],
                })
        if not candidates:
            generic_tables = []
            for table, info in schema.items():
                table_score = len(words & self._expanded_words(table)) * 6
                column_hits = []
                for column in info.get("columns", []):
                    name = self._column_name(column)
                    if words & self._expanded_words(name):
                        column_hits.append(name)
                        table_score += 3
                if table_score:
                    generic_tables.append({
                        "table": table,
                        "columns": column_hits[:10],
                        "score": table_score,
                    })
            if generic_tables:
                candidates.append({
                    "entity": "general",
                    "score": max(table["score"] for table in generic_tables),
                    "tables": sorted(generic_tables, key=lambda item: -item["score"])[:8],
                })
        return {
            "question": question,
            "candidates": sorted(candidates, key=lambda item: -item["score"])[:10],
            "missing_kpis": self._missing_kpis(question, catalog),
            "schema_fingerprint": catalog["schema_fingerprint"],
        }

    def clear(self, fingerprint=None):
        if fingerprint is None:
            self._cache.clear()
            return
        for key in list(self._cache):
            if key.endswith(f":{fingerprint}"):
                self._cache.pop(key, None)

    def _entities(self, schema):
        entities = {}
        for entity, aliases in self.ENTITY_ALIASES.items():
            tables = []
            for table, info in schema.items():
                columns = [self._column(column) for column in info.get("columns", [])]
                text = " ".join([table, *[column["name"] for column in columns]]).lower()
                matches = [alias for alias in aliases if alias in text]
                if matches:
                    tables.append({
                        "table": table,
                        "columns": self._rank_columns(columns)[:16],
                        "matched_aliases": matches[:5],
                        "row_count": info.get("row_count"),
                    })
            if tables:
                entities[entity] = {
                    "aliases": aliases,
                    "tables": sorted(
                        tables,
                        key=lambda item: (
                            -len(item["matched_aliases"]),
                            self.NOISY_TABLE.search(item["table"]) is not None,
                            item["table"],
                        ),
                    )[:20],
                }
        return entities

    def _joins(self, schema):
        declared = []
        id_columns = {}
        primary_keys = {}
        for table, info in schema.items():
            for foreign_key in info.get("foreign_keys", []):
                column = foreign_key.get("column")
                ref_table = foreign_key.get("table")
                ref_column = foreign_key.get("references")
                if column and ref_table and ref_column:
                    declared.append({
                        "left_table": table,
                        "left_column": column,
                        "right_table": ref_table,
                        "right_column": ref_column,
                        "confidence": "high",
                        "evidence": "foreign_key",
                    })
            for column in info.get("columns", []):
                name = self._column_name(column)
                if column.get("primary_key") or column.get("COLUMN_KEY") == "PRI":
                    primary_keys.setdefault(name.lower(), []).append(table)
                if name.lower().endswith("_id") or name.lower() == "id":
                    id_columns.setdefault(name.lower(), []).append(table)

        inferred = []
        for column, tables in id_columns.items():
            if len(tables) < 2:
                continue
            evidence = "shared_id_column"
            confidence = "medium" if column in primary_keys else "low"
            inferred.append({
                "column": column,
                "tables": sorted(tables)[:10],
                "confidence": confidence,
                "evidence": evidence,
            })
        return declared + inferred

    def _important_tables(self, schema, row_counts):
        scored = []
        for table, info in schema.items():
            columns = info.get("columns", [])
            score = len(columns)
            lower = table.lower()
            if lower.endswith(("_master", "_mst", "_table")):
                score += 15
            if any(alias in lower for aliases in self.ENTITY_ALIASES.values() for alias in aliases):
                score += 12
            if self.NOISY_TABLE.search(lower):
                score -= 12
            score += min(20, int(row_counts.get(table, info.get("row_count") or 0) or 0) // 1000)
            scored.append({
                "table": table,
                "score": score,
                "row_count": row_counts.get(table, info.get("row_count")),
                "columns": [self._column_name(column) for column in columns[:12]],
            })
        return sorted(scored, key=lambda item: (-item["score"], item["table"]))

    def _unsupported_kpis(self, entities):
        available = " ".join(
            column["name"].lower()
            for entity in entities.values()
            for table in entity["tables"]
            for column in table["columns"]
        )
        unsupported = []
        if not any(word in available for word in ("cost", "expense", "margin", "profit", "loss")):
            unsupported.append("true_profit_loss")
        return unsupported

    def _missing_kpis(self, question, catalog):
        lower = question.lower()
        if any(word in lower for word in ("loss", "profit", "margin")):
            if "true_profit_loss" in catalog["unsupported_kpis"]:
                return ["true_profit_loss"]
        return []

    def _summary(self, source_type, schema, entities):
        modules = ", ".join(list(entities.keys())[:8]) or "no clear business modules"
        return f"{source_type} database with {len(schema)} tables. Detected modules: {modules}."

    def _column(self, column):
        return {
            "name": self._column_name(column),
            "type": column.get("type") or column.get("data_type") or column.get("DATA_TYPE"),
            "primary_key": bool(column.get("primary_key") or column.get("COLUMN_KEY") == "PRI"),
            "not_null": bool(column.get("not_null")),
        }

    def _column_name(self, column):
        return column.get("name") or column.get("column_name") or column.get("COLUMN_NAME")

    def _rank_columns(self, columns):
        markers = ("id", "name", "date", "amount", "total", "status", "type", "qty", "price", "cost")
        return sorted(
            columns,
            key=lambda column: (
                -sum(1 for marker in markers if marker in column["name"].lower()),
                column["name"],
            ),
        )

    def _expanded_words(self, text):
        words = set(re.findall(r"[a-z0-9]+", text.lower()))
        expanded = set(words)
        for word in words:
            if word.endswith("ies") and len(word) > 3:
                expanded.add(f"{word[:-3]}y")
            if word.endswith("s") and len(word) > 3:
                expanded.add(word[:-1])
            if word.endswith("ing") and len(word) > 5:
                expanded.add(word[:-3])
        return expanded


business_catalog = BusinessCatalog()
