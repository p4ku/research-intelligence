"""
Activity logs are an audit trail of what each person opened, from where and
when — so a researcher reads only their own, and no row keeps a response body.
Before this, any member of a workspace could read every colleague's rows, and a
colleague opening a chat session wrote the whole transcript into one of them.
"""
import json
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from chat.models import PaperChatSession, PaperChatMessage
from research_intelligence.models import Paper, PipelineRun, UserActivityLog, Workspace, WorkspaceMember

User = get_user_model()

SECRET_QUESTION = "Which company are we acquiring?"
SECRET_ANSWER = "The target named in section 4 is Qubitron GmbH."


class ActivityLogOwnerScopeTest(TestCase):
    def setUp(self):
        self.password = "Secr3tP@ssw0rd!"
        self.workspace = Workspace.objects.create(name="Shared Lab")
        self.alice = self.member("alice", "researcher")
        self.bob = self.member("bob", "researcher")
        self.carol = self.member("carol", "admin")

        run = PipelineRun.objects.create(workspace=self.workspace)
        paper = Paper.objects.create(
            workspace=self.workspace, pipeline_run=run, hash_id="sha256_scope", title="Scope Paper",
        )
        self.session = PaperChatSession.objects.create(
            workspace=self.workspace, paper=paper, user=self.alice, title="Alice's thread",
        )
        PaperChatMessage.objects.create(
            session=self.session, sender='user', status='completed',
            question=SECRET_QUESTION, message=SECRET_ANSWER,
        )

    def member(self, username, role):
        user = User.objects.create_user(username=username, email=f"{username}@corp.com", password=self.password)
        WorkspaceMember.objects.create(workspace=self.workspace, user=user, role=role)
        return user

    def client_for(self, user):
        # A real login, not force_authenticate: the audit middleware reads the
        # user off the request the way it does in production.
        client = APIClient()
        res = client.post('/api/auth/login/', {'username': user.username, 'password': self.password}, format='json')
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {res.data["access"]}')
        return client

    def alice_opens_her_thread(self):
        res = self.client_for(self.alice).get(f'/api/chat/sessions/{self.session.id}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        return UserActivityLog.objects.get(user=self.alice, action_name=f"GET /api/chat/sessions/{self.session.id}/")

    def test_researcher_reads_only_their_own_rows(self):
        self.alice_opens_her_thread()
        bob = self.client_for(self.bob)
        bob.get('/api/chat/sessions/')  # a row of Bob's own, so the list below is not empty by accident

        for query in ('', f'?workspace={self.workspace.id}'):
            with self.subTest(query=query):
                res = bob.get(f'/api/activity-logs/{query}')
                self.assertEqual(res.status_code, status.HTTP_200_OK)
                users = {row['user_username'] for row in res.data}
                if not query:
                    self.assertIn('bob', users)
                self.assertNotIn('alice', users)
                self.assertNotIn('alice@corp.com', json.dumps(res.data, default=str))

    def test_admin_reads_the_workspace_trail(self):
        row = self.alice_opens_her_thread()
        res = self.client_for(self.carol).get('/api/activity-logs/')
        self.assertIn(str(row.id), [r['id'] for r in res.data])

    def test_a_response_body_is_never_stored(self):
        row = self.alice_opens_her_thread()
        stored = json.dumps(row.output_summary)
        self.assertNotIn(SECRET_QUESTION, stored)
        self.assertNotIn(SECRET_ANSWER, stored)
        self.assertNotIn('messages', row.output_summary)
        # ...while the ids that place the row still survive, so workspace
        # resolution from the response keeps working
        self.assertEqual(row.output_summary['id'], str(self.session.id))
        self.assertEqual(row.workspace_id, self.workspace.id)

    def test_summarise_output_keeps_only_listed_scalars(self):
        self.assertEqual(
            UserActivityLog.summarise_output({
                'id': 'abc', 'status': 'success', 'session_id': 's1',
                'workspace': {'nested': 'dropped'}, 'answer': SECRET_ANSWER, 'token': 'x',
            }),
            {'id': 'abc', 'status': 'success', 'session_id': 's1'},
        )
        for payload in (None, [], 'text', [{'id': 'abc'}]):
            with self.subTest(payload=payload):
                self.assertEqual(UserActivityLog.summarise_output(payload), {})
