'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');

const {
  MAX_NATIVE_REVIEW_ROUNDS,
  cleanNativeReviewHead,
  cleanNativeReviewStatus,
  countNativeReviewRounds,
  countNativeReviewRoundsForHead,
  evaluateReviewGate,
  isPrivilegedRepositoryPermission,
  latestLabelActor,
  persistCleanReviewStatuses,
  selectReadinessStatusComments,
  shouldInvalidateAcceptance,
} = require('./review-gate.cjs');

test('counts every submitted native Codex pass and ignores maintainer replies', () => {
  const reviews = [
    { user: { login: 'chatgpt-codex-connector[bot]' }, state: 'COMMENTED' },
    { user: { login: 'chatgpt-codex-connector[bot]' }, state: 'COMMENTED' },
    { user: { login: 'chatgpt-codex-connector[bot]' }, state: 'PENDING' },
    { user: { login: 'rbctmz' }, state: 'COMMENTED' },
  ];

  assert.equal(countNativeReviewRounds(reviews), 2);
});

test('dismissed submitted reviews still consume the native review budget', () => {
  const reviews = [
    { user: { login: 'chatgpt-codex-connector[bot]' }, state: 'DISMISSED' },
    { user: { login: 'chatgpt-codex-connector[bot]' }, state: 'COMMENTED' },
    { user: { login: 'chatgpt-codex-connector[bot]' }, state: 'COMMENTED' },
  ];

  assert.equal(countNativeReviewRounds(reviews), 3);
  assert.equal(
    evaluateReviewGate({
      accepted: true,
      nativeReviewRounds: countNativeReviewRounds(reviews),
      unresolvedThreads: 0,
      hasBudgetException: false,
    }).ready,
    false,
  );
});

test('acceptance cannot substitute for a missing native review', () => {
  assert.deepEqual(
    evaluateReviewGate({
      accepted: true,
      nativeReviewRounds: 0,
      unresolvedThreads: 0,
      hasBudgetException: false,
    }),
    { ready: false, reason: 'no submitted native review for the current head' },
  );
});

test('historical native reviews cannot satisfy the current-head gate', () => {
  const reviews = [
    {
      user: { login: 'chatgpt-codex-connector[bot]' },
      state: 'COMMENTED',
      commit_id: 'head-a',
    },
  ];

  assert.equal(countNativeReviewRounds(reviews), 1);
  assert.equal(countNativeReviewRoundsForHead(reviews, 'head-b'), 0);
  assert.deepEqual(
    evaluateReviewGate({
      accepted: true,
      nativeReviewRounds: 1,
      currentHeadNativeReviewRounds: countNativeReviewRoundsForHead(reviews, 'head-b'),
      unresolvedThreads: 0,
      hasBudgetException: false,
    }),
    { ready: false, reason: 'no submitted native review for the current head' },
  );
});

test('clean Codex result comments count as current-head native review rounds', () => {
  const cleanComment = {
    id: 5444669954,
    user: { login: 'chatgpt-codex-connector[bot]' },
    body: [
      "Codex Review: Didn't find any major issues. Another round soon, please!",
      '',
      '**Reviewed commit:** `800c618311`',
    ].join('\n'),
  };
  const headSha = '800c618311a79c2cf4b0d9a7fb2421a5bbe6587c';

  assert.equal(cleanNativeReviewHead(cleanComment), '800c618311');
  assert.equal(countNativeReviewRounds([], [cleanComment]), 1);
  assert.equal(countNativeReviewRoundsForHead([], headSha, [cleanComment]), 1);
  assert.equal(countNativeReviewRoundsForHead([], 'deadbeef00000000000000000000000000000000', [cleanComment]), 0);
  assert.equal(shouldInvalidateAcceptance('issue_comment', 'created', cleanComment), true);
});

test('persisted clean-result statuses keep rounds after source comment deletion', () => {
  const comments = [
    {
      id: 101,
      user: { login: 'chatgpt-codex-connector[bot]' },
      body: "Codex Review: Didn't find any major issues.\n\n**Reviewed commit:** `aaa0001`",
    },
    {
      id: 102,
      user: { login: 'chatgpt-codex-connector[bot]' },
      body: "Codex Review: Didn't find any major issues.\n\n**Reviewed commit:** `bbb0002`",
    },
    {
      id: 103,
      user: { login: 'chatgpt-codex-connector[bot]' },
      body: "Codex Review: Didn't find any major issues.\n\n**Reviewed commit:** `ccc0003`",
    },
  ];
  const statuses = comments.map(comment => ({
    ...cleanNativeReviewStatus(comment),
    state: 'success',
    creator: { login: 'github-actions[bot]' },
  }));

  assert.equal(countNativeReviewRounds([], comments, statuses), 3);
  assert.equal(countNativeReviewRounds([], [], statuses), 3);
  assert.equal(countNativeReviewRoundsForHead([], 'ccc00030000', [], statuses), 1);
  assert.equal(
    evaluateReviewGate({
      accepted: true,
      nativeReviewRounds: countNativeReviewRounds([], [], statuses),
      currentHeadNativeReviewRounds: 1,
      unresolvedThreads: 0,
      hasBudgetException: false,
    }).ready,
    false,
  );
});

test('untrusted commit statuses cannot forge clean review rounds', () => {
  const cleanComment = {
    id: 201,
    user: { login: 'chatgpt-codex-connector[bot]' },
    body: "Codex Review: Didn't find any major issues.\n\n**Reviewed commit:** `abcdef1234`",
  };
  const status = {
    ...cleanNativeReviewStatus(cleanComment),
    state: 'success',
    creator: { login: 'rbctmz' },
  };

  assert.equal(countNativeReviewRounds([], [], [status]), 0);
});

test('persists each authenticated clean result as one uniquely keyed commit status', async () => {
  const listCommits = Symbol('listCommits');
  const listStatuses = Symbol('listStatuses');
  const created = [];
  const comment = {
    id: 301,
    html_url: 'https://github.com/rbctmz/ai_trainer/pull/513#issuecomment-301',
    user: { login: 'chatgpt-codex-connector[bot]' },
    body: "Codex Review: Didn't find any major issues.\n\n**Reviewed commit:** `abcdef1234`",
  };
  const github = {
    paginate: async (endpoint) => {
      if (endpoint === listCommits) return [{ sha: 'abcdef12340000000000000000000000000000000' }];
      if (endpoint === listStatuses) return [];
      throw new Error('unexpected endpoint');
    },
    rest: {
      pulls: { listCommits },
      repos: {
        listCommitStatusesForRef: listStatuses,
        createCommitStatus: async (payload) => {
          created.push(payload);
          return {
            data: {
              ...payload,
              creator: { login: 'github-actions[bot]' },
            },
          };
        },
      },
    },
  };

  const statuses = await persistCleanReviewStatuses({
    github,
    owner: 'rbctmz',
    repo: 'ai_trainer',
    pr: { number: 513, html_url: 'https://github.com/rbctmz/ai_trainer/pull/513' },
    comments: [comment],
  });

  assert.equal(created.length, 1);
  assert.equal(created[0].sha, 'abcdef12340000000000000000000000000000000');
  assert.equal(created[0].context, 'review-gate/codex-clean/301:abcdef1234');
  assert.equal(statuses.length, 1);
});

test('carries a surviving historical clean round across a rebase without qualifying the new head', async () => {
  const listCommits = Symbol('listCommits');
  const listStatuses = Symbol('listStatuses');
  const created = [];
  const comment = {
    id: 302,
    html_url: 'https://github.com/rbctmz/ai_trainer/pull/514#issuecomment-302',
    user: { login: 'chatgpt-codex-connector[bot]' },
    body: "Codex Review: Didn't find any major issues.\n\n**Reviewed commit:** `aaaaaaa`",
  };
  const currentHead = 'bbbbbbb000000000000000000000000000000000';
  const github = {
    paginate: async (endpoint) => {
      if (endpoint === listCommits) return [{ sha: currentHead }];
      if (endpoint === listStatuses) return [];
      throw new Error('unexpected endpoint');
    },
    rest: {
      pulls: { listCommits },
      repos: {
        listCommitStatusesForRef: listStatuses,
        createCommitStatus: async (payload) => {
          created.push(payload);
          return {
            data: {
              ...payload,
              creator: { login: 'github-actions[bot]' },
            },
          };
        },
      },
    },
  };

  const statuses = await persistCleanReviewStatuses({
    github,
    owner: 'rbctmz',
    repo: 'ai_trainer',
    pr: {
      number: 514,
      head: { sha: currentHead },
      html_url: 'https://github.com/rbctmz/ai_trainer/pull/514',
    },
    comments: [comment],
  });

  assert.equal(created.length, 1);
  assert.equal(created[0].sha, currentHead);
  assert.equal(created[0].context, 'review-gate/codex-clean/302:aaaaaaa');
  assert.equal(countNativeReviewRounds([], [], statuses), 1);
  assert.equal(countNativeReviewRoundsForHead([], currentHead, [], statuses), 0);
});

test('maintainer text cannot spoof a clean native review result', () => {
  const spoofed = {
    user: { login: 'rbctmz' },
    body: "Codex Review: Didn't find any major issues.\n\n**Reviewed commit:** `800c618311`",
  };
  const unrelatedBotComment = {
    user: { login: 'chatgpt-codex-connector[bot]' },
    body: 'Codex finished another task.',
  };

  assert.equal(cleanNativeReviewHead(spoofed), null);
  assert.equal(cleanNativeReviewHead(unrelatedBotComment), null);
  assert.equal(countNativeReviewRounds([], [spoofed, unrelatedBotComment]), 0);
  assert.equal(shouldInvalidateAcceptance('issue_comment', 'created', spoofed), false);
});

test('a submitted review invalidates prior acceptance and readiness', () => {
  assert.equal(shouldInvalidateAcceptance('pull_request_review', 'submitted'), true);
  assert.equal(shouldInvalidateAcceptance('pull_request', 'synchronize'), true);
  assert.equal(shouldInvalidateAcceptance('pull_request_target', 'synchronize'), true);
  assert.equal(shouldInvalidateAcceptance('pull_request_review', 'dismissed'), false);
  assert.equal(shouldInvalidateAcceptance('pull_request', 'labeled'), false);
});

test('privileged labels require the latest authorized label actor', () => {
  const events = [
    {
      id: 1,
      event: 'labeled',
      created_at: '2026-08-27T07:00:00Z',
      label: { name: 'status: review accepted' },
      actor: { login: 'untrusted-bot[bot]' },
    },
    {
      id: 2,
      event: 'unlabeled',
      created_at: '2026-08-27T07:01:00Z',
      label: { name: 'status: review accepted' },
      actor: { login: 'rbctmz' },
    },
    {
      id: 3,
      event: 'labeled',
      created_at: '2026-08-27T07:02:00Z',
      label: { name: 'status: review accepted' },
      actor: { login: 'rbctmz' },
    },
  ];

  assert.equal(latestLabelActor(events, 'status: review accepted'), 'rbctmz');
  assert.equal(latestLabelActor(events.slice(0, 2), 'status: review accepted'), null);
  assert.equal(isPrivilegedRepositoryPermission('admin'), true);
  assert.equal(isPrivilegedRepositoryPermission('maintain'), true);
  assert.equal(isPrivilegedRepositoryPermission('write'), false);
});

test('green CI cannot substitute for explicit review acceptance', () => {
  assert.deepEqual(
    evaluateReviewGate({
      accepted: false,
      nativeReviewRounds: 1,
      unresolvedThreads: 0,
      hasBudgetException: false,
    }),
    { ready: false, reason: 'review result is not accepted for the current head' },
  );
});

test('an unresolved thread blocks an accepted review', () => {
  assert.deepEqual(
    evaluateReviewGate({
      accepted: true,
      nativeReviewRounds: 2,
      unresolvedThreads: 1,
      hasBudgetException: false,
    }),
    { ready: false, reason: '1 unresolved review thread(s)' },
  );
});

test('an active changes-requested review blocks readiness without a thread', () => {
  assert.deepEqual(
    evaluateReviewGate({
      accepted: true,
      nativeReviewRounds: 1,
      unresolvedThreads: 0,
      hasBudgetException: false,
      reviewDecision: 'CHANGES_REQUESTED',
    }),
    { ready: false, reason: 'an active review requests changes' },
  );
});

test('a third native review requires an explicit budget exception', () => {
  const withoutException = evaluateReviewGate({
    accepted: true,
    nativeReviewRounds: MAX_NATIVE_REVIEW_ROUNDS + 1,
    unresolvedThreads: 0,
    hasBudgetException: false,
  });
  const withException = evaluateReviewGate({
    accepted: true,
    nativeReviewRounds: MAX_NATIVE_REVIEW_ROUNDS + 1,
    unresolvedThreads: 0,
    hasBudgetException: true,
  });

  assert.equal(withoutException.ready, false);
  assert.match(withoutException.reason, /budget exceeded/);
  assert.equal(withException.ready, true);
});

test('a privileged human can accept a post-budget fix head without another native round', () => {
  const decision = evaluateReviewGate({
    accepted: true,
    nativeReviewRounds: MAX_NATIVE_REVIEW_ROUNDS,
    currentHeadNativeReviewRounds: 0,
    unresolvedThreads: 0,
    hasBudgetException: true,
  });

  assert.equal(decision.ready, true);
  assert.match(decision.reason, /human post-budget exception/);
});

test('post-budget human acceptance stays fail-closed without every guardrail', () => {
  const base = {
    accepted: true,
    nativeReviewRounds: MAX_NATIVE_REVIEW_ROUNDS,
    currentHeadNativeReviewRounds: 0,
    unresolvedThreads: 0,
    hasBudgetException: true,
  };

  const cases = [
    { hasBudgetException: false },
    { accepted: false },
    { nativeReviewRounds: MAX_NATIVE_REVIEW_ROUNDS - 1 },
    { unresolvedThreads: 1 },
    { reviewDecision: 'CHANGES_REQUESTED' },
  ];

  for (const override of cases) {
    assert.equal(evaluateReviewGate({ ...base, ...override }).ready, false);
  }
});

test('accepted review within budget and without threads passes', () => {
  const decision = evaluateReviewGate({
    accepted: true,
    nativeReviewRounds: 2,
    unresolvedThreads: 0,
    hasBudgetException: false,
  });

  assert.equal(decision.ready, true);
  assert.match(decision.reason, /review accepted/);
});

test('keeps one canonical readiness comment and identifies every duplicate', () => {
  const comments = [
    {
      id: 1,
      user: { login: 'github-actions[bot]' },
      body: '<!-- pr-ready-to-merge:old-head -->\n**Ready to merge**',
    },
    {
      id: 2,
      user: { login: 'github-actions[bot]' },
      body: '<!-- pr-ready-to-merge -->\n**Not ready to merge**',
    },
    {
      id: 3,
      user: { login: 'github-actions[bot]' },
      body: '<!-- pr-ready-to-merge:newer-head -->\n**Ready to merge**',
    },
    { id: 4, user: { login: 'rbctmz' }, body: '<!-- pr-ready-to-merge -->' },
  ];

  const selection = selectReadinessStatusComments(comments);

  assert.equal(selection.canonical.id, 2);
  assert.deepEqual(selection.duplicates.map((comment) => comment.id), [1, 3]);
});

test('promotes the newest legacy readiness comment when no canonical exists', () => {
  const comments = [
    {
      id: 1,
      user: { login: 'github-actions[bot]' },
      body: '<!-- pr-ready-to-merge:first -->',
    },
    {
      id: 2,
      user: { login: 'github-actions[bot]' },
      body: '<!-- pr-ready-to-merge:second -->',
    },
  ];

  const selection = selectReadinessStatusComments(comments);

  assert.equal(selection.canonical.id, 2);
  assert.deepEqual(selection.duplicates.map((comment) => comment.id), [1]);
});
