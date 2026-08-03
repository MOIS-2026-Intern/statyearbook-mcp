import asyncio
import unittest

from unittest.mock import patch

from mcp.server.fastmcp import FastMCP

from app.tools.analyze_publications import (
    analyze_publications_data,
    build_query_plan,
    register,
)


class AnalyzePublicationsQueryPlanTests(unittest.TestCase):
    def test_count_statistics_uses_distinct_stat_id_and_year_parameter(self) -> None:
        plan = build_query_plan(
            operation="count",
            subject="statistics",
            group_by=None,
            applied_publication_year=2026,
            chapter_no=None,
            section_no=None,
            limit=50,
        )

        self.assertIn("COUNT(DISTINCT p.pub_id) AS matched_publications", plan.sql)
        self.assertIn("COUNT(DISTINCT s.stat_id) AS count", plan.sql)
        self.assertIn("LEFT JOIN statistics s ON s.pub_id = p.pub_id", plan.sql)
        self.assertNotIn("JOIN stat_tables", plan.sql)
        self.assertNotIn("JOIN contacts", plan.sql)
        self.assertIn("WHERE p.year = %s", plan.sql)
        self.assertEqual(plan.params, (2026,))

    def test_count_sections_uses_composite_hierarchy_key(self) -> None:
        plan = build_query_plan(
            operation="count",
            subject="sections",
            group_by=None,
            applied_publication_year=2026,
            chapter_no=3,
            section_no=None,
            limit=50,
        )

        self.assertIn(
            "COUNT(DISTINCT (s.year, s.chapter_no, s.section_no))",
            plan.sql,
        )
        self.assertIn("s.chapter_no = %s", plan.sql)
        self.assertEqual(plan.params, (2026, 3))

    def test_organization_count_joins_contacts_and_exposes_schema_basis(self) -> None:
        plan = build_query_plan(
            operation="count",
            subject="organizations",
            group_by=None,
            applied_publication_year=2026,
            chapter_no=None,
            section_no=None,
            limit=50,
        )

        self.assertIn("LEFT JOIN contacts c ON c.stat_id = s.stat_id", plan.sql)
        self.assertIn("BTRIM(c.dept)", plan.sql)
        self.assertEqual(
            plan.source_tables,
            ("publications", "statistics", "contacts"),
        )

    def test_breakdown_combines_metric_group_filters_and_limit_safely(self) -> None:
        plan = build_query_plan(
            operation="breakdown",
            subject="statistics",
            group_by="section",
            applied_publication_year=2026,
            chapter_no=2,
            section_no=None,
            limit=25,
        )

        self.assertIn(
            "s.chapter_no, s.section_no, MIN(s.section) AS section",
            plan.sql,
        )
        self.assertIn("GROUP BY s.chapter_no, s.section_no", plan.sql)
        self.assertIn("LIMIT %s", plan.sql)
        self.assertEqual(plan.params, (2026, 2, 25))

    def test_overview_uses_fixed_multi_metric_template(self) -> None:
        plan = build_query_plan(
            operation="overview",
            subject="statistics",
            group_by=None,
            applied_publication_year=2026,
            chapter_no=None,
            section_no=None,
            limit=50,
        )

        self.assertIn("statistics_count", plan.sql)
        self.assertIn("tables_count", plan.sql)
        self.assertIn("chapters_count", plan.sql)
        self.assertIn("sections_count", plan.sql)
        self.assertIn("organizations_count", plan.sql)
        self.assertIn("GROUP BY p.year, p.title, p.page_count", plan.sql)

    def test_list_contact_phones_preserves_rows_and_requires_only_phone(self) -> None:
        plan = build_query_plan(
            operation="list",
            subject="contacts",
            group_by=None,
            applied_publication_year=2026,
            chapter_no=None,
            section_no=None,
            fields=["phone"],
            required_fields=["phone"],
            deduplicate=False,
            limit=500,
            offset=0,
        )

        self.assertIn("SELECT NULLIF(BTRIM(c.phone), '') AS phone", plan.sql)
        self.assertNotIn("SELECT DISTINCT", plan.sql)
        self.assertIn("LEFT JOIN contacts c ON c.stat_id = s.stat_id", plan.sql)
        self.assertIn("NULLIF(BTRIM(c.phone), '') IS NOT NULL", plan.sql)
        self.assertIn("COUNT(*) OVER () AS _total_count", plan.sql)
        self.assertIn("ORDER BY phone", plan.sql)
        self.assertIn("LIMIT %s OFFSET %s", plan.sql)
        self.assertEqual(plan.params, (2026, 500, 0))

    def test_list_can_explicitly_deduplicate_phone_values(self) -> None:
        plan = build_query_plan(
            operation="list",
            subject="contacts",
            group_by=None,
            applied_publication_year=2026,
            chapter_no=None,
            section_no=None,
            fields=["phone"],
            required_fields=["phone"],
            deduplicate=True,
            limit=500,
        )

        self.assertIn(
            "SELECT DISTINCT NULLIF(BTRIM(c.phone), '') AS phone",
            plan.sql,
        )

    def test_list_contact_details_can_include_statistic_context(self) -> None:
        plan = build_query_plan(
            operation="list",
            subject="contacts",
            group_by=None,
            applied_publication_year=2026,
            chapter_no=1,
            section_no=None,
            fields=[
                "statistic_title",
                "department",
                "officer",
                "phone",
                "source_system",
                "source_url",
            ],
            required_fields=["phone"],
            limit=100,
            offset=20,
        )

        self.assertIn("s.title_ko AS statistic_title", plan.sql)
        self.assertIn("BTRIM(c.officer)", plan.sql)
        self.assertIn("BTRIM(c.phone)", plan.sql)
        where_sql = plan.sql.split("WHERE", 1)[1]
        self.assertNotIn("BTRIM(c.officer), '\\s+'", where_sql)
        self.assertNotIn("BTRIM(c.source_url)", where_sql)
        self.assertEqual(plan.params, (2026, 1, 100, 20))


class AnalyzePublicationsDataTests(unittest.TestCase):
    @patch(
        "app.tools.analyze_publications._execute_plan",
        return_value=[{"matched_publications": 1, "count": 319}],
    )
    @patch(
        "app.tools.analyze_publications._latest_publication_year",
        return_value=2026,
    )
    def test_defaults_to_latest_publication_and_returns_count_basis(
        self,
        latest_publication_year_mock,
        execute_plan_mock,
    ) -> None:
        result = analyze_publications_data(
            operation="count",
            subject="statistics",
        )

        self.assertEqual(result["count"], 319)
        self.assertEqual(result["matched_publications"], 1)
        self.assertEqual(result["applied_publication_year"], 2026)
        self.assertTrue(result["publication_year_defaulted"])
        self.assertIn("statistics.stat_id", result["basis"])
        self.assertIn("파싱 결과 기준", result["limitations"][0])
        latest_publication_year_mock.assert_called_once_with()
        self.assertEqual(execute_plan_mock.call_args.args[0].params, (2026,))

    @patch(
        "app.tools.analyze_publications._execute_plan",
        return_value=[{"matched_publications": 1, "count": 34}],
    )
    def test_specific_year_does_not_query_latest_publication(
        self,
        _execute_plan_mock,
    ) -> None:
        with patch(
            "app.tools.analyze_publications._latest_publication_year"
        ) as latest_publication_year_mock:
            result = analyze_publications_data(
                operation="count",
                subject="sections",
                publication_year=2025,
            )

        self.assertEqual(result["applied_publication_year"], 2025)
        self.assertFalse(result["publication_year_defaulted"])
        latest_publication_year_mock.assert_not_called()

    def test_rejects_conflicting_or_incomplete_template_arguments(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot be used together"):
            analyze_publications_data(
                operation="count",
                subject="statistics",
                publication_year=2026,
                all_publication_years=True,
            )

        with self.assertRaisesRegex(ValueError, "requires group_by"):
            analyze_publications_data(
                operation="breakdown",
                subject="statistics",
            )

        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            analyze_publications_data(
                operation="list",
                subject="statistics",
                fields=["phone"],
            )

        with self.assertRaisesRegex(ValueError, "only be used with list"):
            analyze_publications_data(
                operation="count",
                subject="contacts",
                fields=["phone"],
            )

        with self.assertRaisesRegex(ValueError, "must also be selected"):
            analyze_publications_data(
                operation="list",
                subject="contacts",
                fields=["department"],
                required_fields=["phone"],
            )

        with self.assertRaisesRegex(ValueError, "unsupported required_fields"):
            analyze_publications_data(
                operation="list",
                subject="statistics",
                fields=["statistic_title"],
                required_fields=["statistic_title"],
            )

    @patch(
        "app.tools.analyze_publications._execute_plan",
        return_value=[
            {"phone": "02-1234-5678", "_total_count": 2},
        ],
    )
    def test_list_returns_total_and_removes_internal_window_field(
        self,
        _execute_plan_mock,
    ) -> None:
        result = analyze_publications_data(
            operation="list",
            subject="contacts",
            fields=["phone"],
            required_fields=["phone"],
            deduplicate=False,
            publication_year=2026,
            limit=1,
        )

        self.assertEqual(result["selected_fields"], ["phone"])
        self.assertEqual(result["required_fields"], ["phone"])
        self.assertFalse(result["deduplicated"])
        self.assertIn("중복 제거하지 않고 유지", result["basis"])
        self.assertEqual(result["total_count"], 2)
        self.assertEqual(result["result_count"], 1)
        self.assertNotIn("_total_count", result["results"][0])
        self.assertTrue(result["truncated"])
        self.assertEqual(result["next_offset"], 1)

    def test_tool_schema_exposes_template_and_whitelisted_dimensions(self) -> None:
        mcp = FastMCP("analyze-publications-test")
        register(mcp)

        tools = asyncio.run(mcp.list_tools())
        tool = next(tool for tool in tools if tool.name == "analyze_publications")
        properties = tool.inputSchema["properties"]

        self.assertEqual(
            properties["operation"]["enum"],
            ["overview", "count", "breakdown", "list"],
        )
        self.assertIn("statistics", properties["subject"]["enum"])
        self.assertIn("sections", properties["subject"]["enum"])
        self.assertIn("organizations", properties["subject"]["enum"])
        self.assertIn("contacts", properties["subject"]["enum"])
        self.assertIn("footnotes", properties["subject"]["enum"])
        self.assertIn("fields", properties)
        field_array_schema = next(
            schema
            for schema in properties["fields"]["anyOf"]
            if schema.get("type") == "array"
        )
        self.assertIn("phone", field_array_schema["items"]["enum"])
        self.assertIn("officer", field_array_schema["items"]["enum"])
        self.assertIn("required_fields", properties)
        self.assertIn("deduplicate", properties)
        self.assertIn("offset", properties)
        self.assertNotIn("sql", properties)
        self.assertNotIn("query", properties)


if __name__ == "__main__":
    unittest.main()
