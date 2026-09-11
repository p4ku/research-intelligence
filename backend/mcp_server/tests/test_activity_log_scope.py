"""
The MCP side of activity-log scoping: the diagnostics tool follows the REST
rule (own rows, or everyone's where you administer the workspace), and the tool
wrapper records how a call ended — never what it answered.
"""
import json
from research_intelligence.models import UserActivityLog
from mcp_server.server.app import with_db_connection
from mcp_server.tools import list_user_activity_logs_logic
from .base import BaseMCPTestCase

SECRET_ANSWER = "The target named in section 4 is Qubitron GmbH."


class MCPActivityLogScopeTest(BaseMCPTestCase):
    def setUp(self):
        super().setUp()
        self.add_member(self.workspace, self.researcher, role="researcher")
        self.colleague = self.create_user(username="mcp_colleague")
        self.add_member(self.workspace, self.colleague, role="researcher")
        self.own_row = UserActivityLog.log_action(user=self.researcher, workspace=self.workspace, action_name="own_action")
        self.colleague_row = UserActivityLog.log_action(user=self.colleague, workspace=self.workspace, action_name="colleague_action")

    def ids(self, user, **kwargs):
        res = self.parse_res(list_user_activity_logs_logic(user, **kwargs))
        self.assertEqual(res["status"], "success")
        return [row["id"] for row in res["logs"]]

    def test_researcher_sees_own_rows_not_a_colleagues(self):
        for kwargs in ({}, {"workspace_id": str(self.workspace.id)}):
            with self.subTest(**kwargs):
                ids = self.ids(self.researcher, **kwargs)
                self.assertIn(str(self.own_row.id), ids)
                self.assertNotIn(str(self.colleague_row.id), ids)

    def test_workspace_admin_sees_every_row(self):
        for kwargs in ({}, {"workspace_id": str(self.workspace.id)}):
            with self.subTest(**kwargs):
                ids = self.ids(self.admin, **kwargs)
                self.assertIn(str(self.own_row.id), ids)
                self.assertIn(str(self.colleague_row.id), ids)

    def test_wrapper_records_the_outcome_not_the_answer(self):
        @with_db_connection
        def probe_json_tool():
            return json.dumps({"status": "success", "session_id": "s-1", "answer": SECRET_ANSWER})

        @with_db_connection
        def probe_text_tool():
            return SECRET_ANSWER

        with self.patch_auth(user=self.researcher, workspace=self.workspace):
            probe_json_tool()
            probe_text_tool()

        json_row = UserActivityLog.objects.get(action_name="probe_json_tool")
        self.assertEqual(json_row.output_summary["status"], "success")
        self.assertEqual(json_row.output_summary["session_id"], "s-1")
        self.assertNotIn("answer", json_row.output_summary)

        text_row = UserActivityLog.objects.get(action_name="probe_text_tool")
        self.assertEqual(text_row.output_summary, {"result_length": len(SECRET_ANSWER)})

        for row in (json_row, text_row):
            self.assertNotIn(SECRET_ANSWER, json.dumps(row.output_summary))
