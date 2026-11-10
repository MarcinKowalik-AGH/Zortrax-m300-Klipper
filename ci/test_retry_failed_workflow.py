"""Offline fixtures for automatic retry; never sends a real GitHub POST."""
from copy import deepcopy
from io import BytesIO
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
import retry_failed_workflow as m

REPO='owner/M300'; RID=123; SHA='a'*40

def run():
    return dict(id=7,head_repository=dict(id=RID),repository=dict(id=RID),
                path='.github/workflows/build-m300.yml',status='completed',conclusion='failure',
                run_attempt=1,event='push',head_branch='main',head_sha=SHA)

def job(text=None, name='Install GNU ARM and native test compiler'):
    return dict(id=9,conclusion='failure',steps=[dict(name=name,conclusion='failure',
                started_at='2026-11-10T18:00:01Z',completed_at='2026-11-10T18:00:03Z')])

class FakeAPI:
    def __init__(self):
        self.run=run();self.fresh=None;self.source=SHA;self.jobs=[job()];self.posts=[];self.reads=0
        self.text='2026-11-10T18:00:02.123Z Temporary failure in name resolution'
        self.pr=dict(state='open',merged=False,head=dict(sha=SHA,repo=dict(id=RID)))
    def json(self,path):
        if path=='/actions/runs/7':
            self.reads+=1
            return deepcopy(self.fresh if self.reads>1 and self.fresh else self.run)
        if path.startswith('/git/ref/heads/'):
            return dict(object=dict(sha=self.source))
        if path.startswith('/pulls/'):
            return deepcopy(self.pr)
        if '/attempts/' in path:
            return dict(total_count=len(self.jobs),jobs=deepcopy(self.jobs))
        raise AssertionError('Unexpected API path: '+path)
    def logs(self,_):return self.text
    def rerun(self,run_id):self.posts.append(run_id)

class RetryPolicyTests(unittest.TestCase):
    def test_transient_signatures_in_network_step(self):
        messages=('Temporary failure in name resolution','Could not resolve host: github.com',
                  'request failed with status code 503','HTTP Error 502','HTTP 429',
                  'curl: (28) Operation timed out','ECONNRESET','getaddrinfo EAI_AGAIN',
                  'The runner has lost communication with the server')
        for text in messages:
            with self.subTest(text=text):self.assertTrue(m.classify_failure(text,'Build and test the Fluidd diagram')[0])

    def test_deterministic_errors_win_over_network_noise(self):
        messages=('AssertionError: wrong','TypeError: invalid','SyntaxError: invalid',
                  'error TS1234: bad type','error: build failed','undefined reference to main',
                  "region ROM overflowed by 20 bytes",'No space left on device',
                  'checksum mismatch','integrity check failed','hash mismatch',
                  'HTTP 403','HTTP Error 404','API error 401','Permission denied',
                  'ESLint found too many warnings','ERR_PNPM_OUTDATED_LOCKFILE',
                  'ERR_PNPM_NO_MATCHING_VERSION','FAILED (failures=1)','1 failed | 139 passed')
        for text in messages:
            with self.subTest(text=text):
                self.assertFalse(m.classify_failure('ECONNRESET\n'+text,'Build and test the Fluidd diagram')[0])

    def test_unknown_and_timeout_only_errors_refused(self):
        for text in ('exit code 1','timed out','unknown error','500ms operation','printed 503 bytes',''):
            with self.subTest(text=text):self.assertFalse(m.classify_failure(text,'Build and test the Fluidd diagram')[0])

    def test_validation_steps_not_auto_retried(self):
        for name in ('Fresh complete STM32F103 build','Validate host, startup, guards, cooling and actual Klippy FILEOUTPUT',
                     'Assemble the complete Orange Pi artifact','something new'):
            self.assertFalse(m.classify_failure('ECONNRESET',name)[0])

    def test_maximum_two_automated_reruns(self):
        for attempt,expected in [(1,True),(2,True),(3,False),(50,False),(0,False),(True,False)]:
            value=run();value['run_attempt']=attempt
            self.assertEqual(m.eligible(value,REPO,RID)[0],expected)

    def test_fork_and_wrong_repo_and_workflow_rejected(self):
        for key,value in [('head_repository',dict(id=999)),('repository',dict(id=999)),
                          ('path','.github/workflows/untrusted.yml')]:
            d=run();d[key]=value;self.assertFalse(m.eligible(d,REPO,RID)[0])

    def test_statuses_and_events_rejected(self):
        for key,value in [('status','in_progress'),('conclusion','success'),('conclusion','cancelled'),
                          ('conclusion','timed_out'),('event','pull_request_target'),('head_branch','old')]:
            d=run();d[key]=value;self.assertFalse(m.eligible(d,REPO,RID)[0])

    def test_invalid_identifiers_rejected(self):
        d=run();d['head_sha']='$(touch x)';self.assertFalse(m.eligible(d,REPO,RID)[0])
        self.assertFalse(m.eligible(run(),'owner/repo/../../',RID)[0])

    def test_only_failed_step_logs_classified(self):
        log=('2026-11-10T17:59:59Z AssertionError from an unrelated earlier fixture\n'
             '2026-11-10T18:00:02.456Z ECONNRESET\n'
             '2026-11-10T18:00:06Z TypeError from next step')
        self.assertEqual(m.failed_step_text(log,job()['steps'][0]),'ECONNRESET')

    def test_missing_timestamps_refused(self):
        self.assertIsNone(m.failed_step_text('ECONNRESET',job()['steps'][0]))
        self.assertIsNone(m.failed_step_text('ECONNRESET',{}))

    def test_dry_run_cannot_post_or_sleep(self):
        api=FakeAPI()
        with patch.object(m.time,'sleep',side_effect=AssertionError):
            d=m.execute(api,7,REPO,RID,apply=False)
        self.assertTrue(d['eligible']);self.assertFalse(d['rerun_requested']);self.assertEqual(api.posts,[])

    def test_transient_failure_posts_once_after_backoff(self):
        api=FakeAPI();delays=[]
        d=m.execute(api,7,REPO,RID,True,sleep=delays.append)
        self.assertTrue(d['rerun_requested']);self.assertEqual(delays,[30]);self.assertEqual(api.posts,[7])

    def test_second_retry_has_longer_backoff(self):
        api=FakeAPI();api.run['run_attempt']=2;delays=[]
        self.assertTrue(m.execute(api,7,REPO,RID,True,sleep=delays.append)['rerun_requested'])
        self.assertEqual(delays,[60])

    def test_deterministic_failure_never_posts(self):
        api=FakeAPI();api.text='2026-11-10T18:00:02Z ECONNRESET\n2026-11-10T18:00:03Z AssertionError: wrong'
        self.assertFalse(m.execute(api,7,REPO,RID,True,sleep=lambda _:None)['eligible']);self.assertEqual(api.posts,[])

    def test_superseded_source_never_posts(self):
        api=FakeAPI();api.source='b'*40
        self.assertEqual(m.execute(api,7,REPO,RID,True)['reason'],'superseded-or-closed-source')
        self.assertEqual(api.posts,[])

    def test_rerun_already_requested_during_backoff(self):
        api=FakeAPI();api.fresh=run();api.fresh.update(status='queued',run_attempt=2)
        self.assertFalse(m.execute(api,7,REPO,RID,True,sleep=lambda _:None)['rerun_requested'])
        self.assertEqual(api.posts,[])

    def test_source_changed_during_backoff(self):
        api=FakeAPI()
        d=m.execute(api,7,REPO,RID,True,sleep=lambda _:setattr(api,'source','b'*40))
        self.assertFalse(d['rerun_requested']);self.assertEqual(api.posts,[])

    def test_all_failed_jobs_must_be_transient(self):
        api=FakeAPI();api.jobs.append(job(name='Fresh complete STM32F103 build'))
        self.assertFalse(m.execute(api,7,REPO,RID,True)['eligible']);self.assertEqual(api.posts,[])

    def test_canceled_or_timed_out_job_requires_review(self):
        for conclusion in ('cancelled','timed_out'):
            api=FakeAPI();api.jobs[0]['conclusion']=conclusion
            self.assertFalse(m.execute(api,7,REPO,RID,True)['eligible']);self.assertEqual(api.posts,[])

    def test_no_failed_steps_or_jobs_requires_review(self):
        for jobs in ([],[dict(id=1,conclusion='failure',steps=[])]):
            api=FakeAPI();api.jobs=jobs
            self.assertFalse(m.execute(api,7,REPO,RID,True)['eligible'])

    def test_same_repo_open_current_pr_allowed(self):
        api=FakeAPI();api.run.update(event='pull_request',head_branch='fix/port',pull_requests=[dict(number=5)])
        self.assertTrue(m.execute(api,7,REPO,RID,False)['eligible'])

    def test_changed_closed_foreign_pr_rejected(self):
        for change in ('closed','foreign','new-sha','missing'):
            api=FakeAPI();api.run.update(event='pull_request',head_branch='fix/port',pull_requests=[dict(number=5)])
            if change=='closed':api.pr['state']='closed'
            if change=='foreign':api.pr['head']['repo']['id']=987
            if change=='new-sha':api.pr['head']['sha']='b'*40
            if change=='missing':api.run['pull_requests']=[]
            self.assertFalse(m.execute(api,7,REPO,RID,False)['eligible'])

    def test_original_binary_and_source_are_not_rewritten(self):
        import inspect
        text=inspect.getsource(m)
        self.assertNotIn('subprocess',text)
        self.assertNotIn('exec(',text)
        self.assertNotIn('eval(',text)
        self.assertNotIn('unzip',text)
        self.assertNotIn('continue-on-error',text)

    def test_token_not_forwarded_to_logs_storage(self):
        api=m.GitHubAPI(REPO,'PRIVATE_TOKEN')
        error=HTTPError('https://api.github.com/',302,'Found',
                        {'Location':'https://example.blob.core.windows.net/log?sig=abc'},None)
        stream=BytesIO(b'log')
        with patch.object(api,'request',side_effect=error),patch.object(m,'urlopen',return_value=stream) as fetch:
            self.assertEqual(api.logs(9),'log')
            request=fetch.call_args.args[0]
            self.assertNotIn('Authorization',request.headers)

    def test_unapproved_redirect_host_refused(self):
        api=m.GitHubAPI(REPO,'PRIVATE_TOKEN')
        for target in ('http://example.blob.core.windows.net/log','https://evil.example/log',
                       'https://github.com@evil.example/log'):
            error=HTTPError('https://api.github.com/',302,'Found',{'Location':target},None)
            with patch.object(api,'request',side_effect=error),patch.object(m,'urlopen') as fetch:
                with self.assertRaises(ValueError):api.logs(9)
                fetch.assert_not_called()

    def test_truncated_log_refused(self):
        api=m.GitHubAPI(REPO,'PRIVATE_TOKEN')
        with patch.object(api,'request',return_value=BytesIO(b'x'*(m.MAX_LOG_BYTES+1))):
            with self.assertRaises(ValueError):api.logs(9)

    def test_workflow_uses_trusted_default_commit_only(self):
        from pathlib import Path
        text=(Path(__file__).resolve().parents[1]/'.github/workflows/retry-transient.yml').read_text()
        self.assertIn('ref: ${{ github.sha }}',text)
        self.assertNotIn('ref: ${{ github.event.workflow_run.head_sha }}',text)
        self.assertNotIn('contents: write',text)
        self.assertIn('actions: write',text)
        self.assertIn('run_attempt < 3',text)
        self.assertNotIn('continue-on-error',text)

if __name__=='__main__':unittest.main(verbosity=2)
