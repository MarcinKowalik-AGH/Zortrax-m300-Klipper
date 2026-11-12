#!/usr/bin/env python3
"""Bounded, fail-closed GitHub Actions retry. Logs are DATA, never executable.

Run from the trusted default-branch workflow, NOT from a failed PR checkout.
Without --apply it records a decision and never sends a rerun request.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.parse import quote, urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler, urlopen

MAX_ATTEMPTS = 3  # initial attempt plus at most TWO automated reruns
MAX_LOG_BYTES = 4 * 1024 * 1024
WORKFLOWS = {'.github/workflows/build-m300.yml', '.github/workflows/publish-release.yml'}
NETWORK_STEPS = {
    'Set up job', 'Checkout M300 sources', 'Run actions/checkout@v4',
    'Select Python 3.12', 'Install GNU ARM and native test compiler',
    'Fetch checksum-pinned upstream Klipper', 'Install pinned native Klippy test dependencies',
    'Select Node 24', 'Run pnpm/action-setup@v4', 'Build and test the Fluidd diagram',
    'Upload the ready-to-install package', 'Retrieve the verified build',
    'Publish the compact Git deployment',
    'Publish one immutable prerelease from the successful build',
}
# Hard failures always win, even if a network warning occurs in the same step.
HARD = re.compile(
    r'AssertionError|SyntaxError|TypeError|ReferenceError|ModuleNotFoundError|'
    r'\bFAIL(?:ED)?\b[^\n]*(?:test|spec\.|::)|FAILED\s*\(|'
    r'(?:[1-9][0-9]*\s+(?:failed|failing)\b)|'
    r'error TS[0-9]+|\berror:\s|undefined reference|compilation terminated|'
    r'overflowed by|will not fit in region|out of memory|No space left on device|'
    r'checksum[^\n]*(?:mismatch|failed)|integrity[^\n]*(?:mismatch|failed)|'
    r'hash[^\n]*mismatch|signature[^\n]*(?:invalid|failed)|'
    r'(?:HTTP(?: Error)?|status(?: code)?|API error)[:\s]+(?:401|403|404)\b|'
    r'Permission denied|authentication failed|certificate verify failed|'
    r'ESLint found too many warnings|ERR_PNPM_OUTDATED_LOCKFILE|'
    r'ERR_PNPM_NO_MATCHING_VERSION|No matching distribution found', re.I)
TRANSIENT = re.compile(
    r'Temporary failure in name resolution|Could not resolve host|'
    r'\b(?:EAI_AGAIN|ECONNRESET|ETIMEDOUT)\b|Connection reset by peer|'
    r'curl:\s*\((?:6|7|28|35|52|56)\)|'
    r'(?:HTTP(?: Error)?|status(?: code)?|API error|server returned|response code)[:\s]+(?:429|500|502|503|504)\b|'
    r'request failed[^\n]*\b(?:429|502|503|504)\b|'
    r'The runner has lost communication with the server|'
    r'The hosted runner[^\n]*(?:lost|unavailable)|'
    r'The service is temporarily unavailable', re.I)
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
TIMESTAMP = re.compile(r'^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.\d+)?Z\s(.*)$')


def classify_failure(text, step):
    text = ANSI.sub('', text)
    if HARD.search(text):
        return False, 'deterministic-error-or-integrity-failure'
    if step not in NETWORK_STEPS:
        return False, 'step-not-eligible-for-network-retry'
    if TRANSIENT.search(text):
        return True, 'recognized-transient-infrastructure-error'
    return False, 'unknown-failure-no-automatic-retry'


def eligible(run, repo, repo_id):
    if run.get('head_repository', {}).get('id') != repo_id:
        return False, 'foreign-or-fork-head-repository'
    if run.get('repository', {}).get('id') != repo_id:
        return False, 'foreign-run-repository'
    if run.get('path') not in WORKFLOWS:
        return False, 'unapproved-workflow'
    if run.get('status') != 'completed' or run.get('conclusion') != 'failure':
        return False, 'not-a-completed-failure'
    attempt = run.get('run_attempt')
    if type(attempt) is not int or not 1 <= attempt < MAX_ATTEMPTS:
        return False, 'attempt-limit-or-invalid-attempt'
    if run.get('event') not in ('push', 'pull_request', 'workflow_dispatch', 'workflow_run'):
        return False, 'unsupported-event'
    if run.get('event') != 'pull_request' and run.get('head_branch') != 'main':
        return False, 'non-main-push-or-dispatch'
    if not re.fullmatch(r'[0-9a-f]{40}', str(run.get('head_sha', ''))):
        return False, 'invalid-head-sha'
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        return False, 'invalid-repository'
    return True, 'eligible'


def failed_step_text(log, step):
    """Restrict classification to the failed step, not earlier passed steps."""
    start, end = step.get('started_at'), step.get('completed_at')
    if not start or not end:
        return None
    # GitHub job timestamps have seconds precision; retain fractional log lines
    # from the same boundary seconds. Missing timestamped logs fail closed.
    lower = dt.datetime.fromisoformat(start.replace('Z', '+00:00')).strftime('%Y-%m-%dT%H:%M:%S')
    upper = dt.datetime.fromisoformat(end.replace('Z', '+00:00')).strftime('%Y-%m-%dT%H:%M:%S')
    lines = []
    for line in log.splitlines():
        match = TIMESTAMP.match(line)
        if match and lower <= match[1] <= upper:
            lines.append(match[2])
    return '\n'.join(lines) if lines else None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GitHubAPI:
    def __init__(self, repo, token):
        self.repo = repo
        self.token = token
        self.opener = build_opener(NoRedirect)

    def request(self, path, method='GET'):
        if not path.startswith('/') or path.startswith('//'):
            raise ValueError('Invalid repository API path')
        req = Request('https://api.github.com/repos/' + self.repo + path,
                      data=b'{}' if method == 'POST' else None, method=method,
                      headers={'Authorization': 'Bearer ' + self.token,
                               'Accept': 'application/vnd.github+json',
                               'X-GitHub-Api-Version': '2022-11-28',
                               'Content-Type': 'application/json'})
        return self.opener.open(req, timeout=30)

    def json(self, path):
        with self.request(path) as response:
            raw = response.read(MAX_LOG_BYTES + 1)
        if len(raw) > MAX_LOG_BYTES:
            raise ValueError('API response exceeds bounded size')
        return json.loads(raw)

    def logs(self, job_id):
        try:
            response = self.request('/actions/jobs/' + str(int(job_id)) + '/logs')
        except HTTPError as exc:
            if exc.code not in (301, 302, 303, 307, 308):
                raise
            address = exc.headers.get('Location', '')
            parsed = urlparse(address)
            host = parsed.hostname or ''
            if (parsed.scheme != 'https' or parsed.username or parsed.password
                    or not (host.endswith('.blob.core.windows.net')
                            or host.endswith('.actions.githubusercontent.com')
                            or host.endswith('.githubusercontent.com'))):
                raise ValueError('Unexpected log redirect destination') from exc
            # Critical: never forward the GitHub token to a signed download URL.
            response = urlopen(Request(address), timeout=30)
        with response:
            raw = response.read(MAX_LOG_BYTES + 1)
        if len(raw) > MAX_LOG_BYTES:
            raise ValueError('Job log too large for safe automatic classification')
        return raw.decode('utf-8', errors='replace')

    def rerun(self, run_id):
        with self.request('/actions/runs/' + str(int(run_id)) + '/rerun-failed-jobs', 'POST') as response:
            if response.status != 201:
                raise ValueError('Unexpected rerun acknowledgement')


def latest_source(api, run, repo_id):
    if run['event'] == 'pull_request':
        prs = run.get('pull_requests', [])
        if len(prs) != 1:
            return False
        pr = api.json('/pulls/' + str(int(prs[0]['number'])))
        return (pr.get('state') == 'open' and not pr.get('merged')
                and pr.get('head', {}).get('repo', {}).get('id') == repo_id
                and pr['head'].get('sha') == run['head_sha'])
    current = api.json('/git/ref/heads/' + quote(run['head_branch'], safe=''))
    return current.get('object', {}).get('sha') == run['head_sha']


def failed_jobs(api, run):
    all_jobs = []
    for page in range(1, 11):
        result = api.json('/actions/runs/{}/attempts/{}/jobs?per_page=100&page={}'.format(
            run['id'], run['run_attempt'], page))
        jobs = result['jobs']; all_jobs.extend(jobs)
        if len(all_jobs) >= result['total_count']:
            return [j for j in all_jobs if j.get('conclusion') in ('failure', 'timed_out', 'cancelled')]
        if not jobs:
            break
    raise ValueError('Incomplete job list; retry refused')


def evaluate(api, run, repo, repo_id):
    ok, reason = eligible(run, repo, repo_id)
    result = dict(run_id=run.get('id'), attempt=run.get('run_attempt'),
                  source_sha=run.get('head_sha'), maximum_attempts=MAX_ATTEMPTS,
                  eligible=False, reason=reason, jobs=[])
    if not ok:
        return result
    if not latest_source(api, run, repo_id):
        result['reason'] = 'superseded-or-closed-source'
        return result
    jobs = failed_jobs(api, run)
    if not jobs:
        result['reason'] = 'no-failed-job-evidence'
        return result
    for job in jobs:
        if job.get('conclusion') != 'failure':
            result['reason'] = 'timeout-or-cancellation-needs-review'
            return result
        steps = [s for s in job.get('steps', []) if s.get('conclusion') == 'failure']
        if not steps:
            result['reason'] = 'missing-failed-step-evidence'
            return result
        log = api.logs(job['id'])
        for step in steps:
            text = failed_step_text(log, step)
            if text is None:
                ok, why = False, 'missing-timestamped-step-log'
            else:
                ok, why = classify_failure(text, step['name'])
            result['jobs'].append(dict(job_id=job['id'], step=step['name'], retryable=ok, reason=why))
            if not ok:
                result['reason'] = why
                return result
    result.update(eligible=True, reason='all-failed-steps-are-recognized-transient-errors')
    return result


def execute(api, run_id, repo, repo_id, apply=False, sleep=time.sleep):
    run = api.json('/actions/runs/' + str(run_id))
    decision = evaluate(api, run, repo, repo_id)
    decision['rerun_requested'] = False
    if not decision['eligible'] or not apply:
        return decision
    # A duplicate workflow_run delivery must not create a rerun loop. Re-read
    # status/attempt and source AFTER backoff, just before the one allowed POST.
    delay = 30 * run['run_attempt']
    sleep(delay)
    fresh = api.json('/actions/runs/' + str(run_id))
    if (not eligible(fresh, repo, repo_id)[0]
            or fresh['run_attempt'] != run['run_attempt']
            or fresh['head_sha'] != run['head_sha']
            or not latest_source(api, fresh, repo_id)):
        decision.update(eligible=False, reason='run-or-source-changed-before-retry')
        return decision
    api.rerun(run_id)
    decision.update(rerun_requested=True, backoff_seconds=delay)
    return decision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('.ci/reports/CI_RETRY_DECISION.json'))
    args = parser.parse_args()
    decision = {'eligible': False, 'rerun_requested': False}
    try:
        event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
        repo = os.environ['GITHUB_REPOSITORY']
        repo_id = int(os.environ['GITHUB_REPOSITORY_ID'])
        run_id = int(event['workflow_run']['id'])
        api = GitHubAPI(repo, os.environ['GH_TOKEN'])
        decision = execute(api, run_id, repo, repo_id, args.apply)
    except Exception as exc:
        # Do not expose raw API/log messages, tokens or signed log URLs.
        decision['reason'] = 'fail-closed-api-or-validation-error:' + type(exc).__name__
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(decision, indent=2) + '\n')
    print(json.dumps(decision))
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a') as stream:
            stream.write('## M300 bounded retry\n\n```json\n' + json.dumps(decision, indent=2) + '\n```\n')


if __name__ == '__main__':
    main()
