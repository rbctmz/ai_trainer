'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');

const {
  MAX_NATIVE_REVIEW_ROUNDS,
  renderReadinessComment,
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

// Minimal public response from PR #682, issuecomment-6216769986.
const receiptCleanComment = {
  id: 6216769986,
  user: { login: 'chatgpt-codex-connector[bot]' },
  body: [
    '<!-- codex-review-receipt:v1 -->',
    '',
    "Codex Review: Didn't find any major issues. :tada:",
    '',
    '**Reviewed commit:** `9dc9039fb9`',
  ].join('\n'),
};

test('receipt-prefixed clean results preserve review identity and head scope', () => {
  const plainComment = {
    ...receiptCleanComment,
    body: receiptCleanComment.body.split('\n').slice(2).join('\n'),
  };
  const reviewedHead = '9dc9039fb9';
  const laterHead = '32ba1edb00ce1b9a5e3dfa31564e149980fc8d32';
  const reviews = [{
    user: { login: 'chatgpt-codex-connector[bot]' },
    state: 'COMMENTED',
    commit_id: '7af3dfb',
  }];

  assert.equal(cleanNativeReviewHead(receiptCleanComment), reviewedHead);
  assert.deepEqual(cleanNativeReviewStatus(receiptCleanComment), cleanNativeReviewStatus(plainComment));
  const status = {
    ...cleanNativeReviewStatus(receiptCleanComment),
    state: 'success',
    creator: { login: 'github-actions[bot]' },
  };
  assert.equal(status.context, 'review-gate/codex-clean/6216769986:9dc9039fb9');
  assert.equal(countNativeReviewRounds([], [plainComment, receiptCleanComment], [status]), 1);
  assert.equal(countNativeReviewRounds(reviews, [receiptCleanComment], [status]), 2);
  assert.equal(countNativeReviewRoundsForHead(reviews, reviewedHead, [receiptCleanComment]), 1);
  assert.equal(countNativeReviewRoundsForHead(reviews, laterHead, [receiptCleanComment], [status]), 0);
  assert.equal(shouldInvalidateAcceptance('issue_comment', 'created', receiptCleanComment), true);

  const gate = {
    accepted: true,
    nativeReviewRounds: countNativeReviewRounds(reviews, [receiptCleanComment], [status]),
    currentHeadNativeReviewRounds: 0,
    unresolvedThreads: 0,
    hasBudgetException: true,
  };
  assert.equal(evaluateReviewGate(gate).ready, true);
  assert.equal(evaluateReviewGate({ ...gate, accepted: false }).ready, false);
  assert.equal(evaluateReviewGate({ ...gate, hasBudgetException: false }).ready, false);
});

test('receipt marker does not authenticate maintainer or unrelated bot comments', () => {
  for (const login of ['rbctmz', 'unrelated[bot]']) {
    const comment = { ...receiptCleanComment, user: { login } };
    assert.equal(cleanNativeReviewHead(comment), null);
    assert.equal(cleanNativeReviewStatus(comment), null);
    assert.equal(countNativeReviewRounds([], [comment]), 0);
  }
});

test('receipt parsing rejects arbitrary prefixes and missing reviewed SHA', () => {
  const bodies = [
    `Other prefix\n${receiptCleanComment.body}`,
    receiptCleanComment.body.replace('codex-review-receipt:v1', 'codex-review-receipt:v2'),
    receiptCleanComment.body.replace('**Reviewed commit:** `9dc9039fb9`', ''),
    receiptCleanComment.body.replace('9dc9039fb9', 'not-a-sha'),
  ];
  for (const body of bodies) {
    const comment = { ...receiptCleanComment, body };
    assert.equal(cleanNativeReviewHead(comment), null);
    assert.equal(cleanNativeReviewStatus(comment), null);
    assert.equal(countNativeReviewRounds([], [comment]), 0);
  }
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

test('a native-review waiver never substitutes for explicit acceptance', () => {
  const decision = evaluateReviewGate({
    accepted: false,
    nativeReviewRounds: 0,
    currentHeadNativeReviewRounds: 0,
    unresolvedThreads: 0,
    hasBudgetException: false,
    hasNativeWaiver: true,
  });

  assert.deepEqual(decision, {
    ready: false,
    reason: 'review result is not accepted for the current head',
  });
});

test('a privileged native-review waiver plus acceptance passes and names the waiver', () => {
  const decision = evaluateReviewGate({
    accepted: true,
    nativeReviewRounds: 0,
    currentHeadNativeReviewRounds: 0,
    unresolvedThreads: 0,
    hasBudgetException: false,
    hasNativeWaiver: true,
  });

  assert.equal(decision.ready, true);
  assert.match(decision.reason, /native review waived by merge owner/);
  assert.match(decision.reason, /Codex unavailable/);
});

test('a native waiver is not enough on its own: every other guardrail still applies', () => {
  const base = {
    accepted: true,
    nativeReviewRounds: 0,
    currentHeadNativeReviewRounds: 0,
    unresolvedThreads: 0,
    hasBudgetException: false,
    hasNativeWaiver: true,
  };

  const cases = [
    { hasNativeWaiver: false },
    { accepted: false },
    { unresolvedThreads: 1 },
    { reviewDecision: 'CHANGES_REQUESTED' },
  ];

  for (const override of cases) {
    assert.equal(evaluateReviewGate({ ...base, ...override }).ready, false);
  }
});

test('a waiver does not excuse a native review that exists for the current head', () => {
  const decision = evaluateReviewGate({
    accepted: true,
    nativeReviewRounds: 1,
    currentHeadNativeReviewRounds: 1,
    unresolvedThreads: 0,
    hasBudgetException: false,
    hasNativeWaiver: true,
  });

  assert.equal(decision.ready, true);
  assert.doesNotMatch(decision.reason, /waived/);
});

// Execute the actual privileged job's inline JS against an in-memory GitHub
// boundary. No token, network, checkout or repository mutation occurs here.
const fs = require('node:fs');
const path = require('node:path');
const HEAD_A = 'a'.repeat(40);
const HEAD_B = 'b'.repeat(40);

function readinessHarness(overrides = {}) {
  const state = {
    pr: { number: 729, state: 'open', draft: true, mergeable: true,
      body: 'Closes #729', title: 'Review metrics',
      head: { sha: HEAD_A, ref: 'codex/issue-729-review-metrics' } },
    comments: [], reviews: [], statuses: [], events: [], labels: [], threads: [],
    checks: [{ name: 'Contributor-safe pytest', status: 'completed', conclusion: 'success' }],
    mutations: [], failures: [], ...overrides,
  };
  const issues = {
    getLabel: async () => ({ data: {} }),
    get: async () => ({ data: { labels: state.labels } }),
    addLabels: async ({ labels }) => { state.labels.push(...labels); state.mutations.push(['label', ...labels]); },
    removeLabel: async ({ name }) => { state.labels = state.labels.filter(v => v !== name); state.mutations.push(['remove', name]); },
    listComments: async () => ({ data: state.comments }),
    listEventsForTimeline: async () => ({ data: state.events }),
    createComment: async ({ body }) => {
      const comment = { id: 1000 + state.comments.length, body, user: { login: 'github-actions[bot]' } };
      state.comments.push(comment); state.mutations.push(['create', body]); return { data: comment };
    },
    updateComment: async ({ comment_id, body }) => {
      const found = state.comments.find(c => c.id === comment_id);
      assert.ok(found, 'update must name an existing comment');
      found.body = body; state.mutations.push(['update', comment_id, body]);
    },
  };
  const github = {
    paginate: async (endpoint, args) => (await endpoint(args)).data,
    graphql: async () => {
      if (state.reviewError) throw new Error('simulated private API failure');
      return { repository: { pullRequest: { reviewDecision: state.reviewDecision || null,
        reviewThreads: { nodes: state.threads, pageInfo: { hasNextPage: false, endCursor: null } } } } };
    },
    rest: { issues,
      pulls: { get: async () => ({ data: { ...state.pr, head: { ...state.pr.head } } }),
        listReviews: async () => ({ data: state.reviews }),
        listCommits: async () => ({ data: [{ sha: state.pr.head.sha }] }) },
      repos: { getCollaboratorPermissionLevel: async () => {
          if (state.permissionError) throw new Error('simulated permission API failure');
          return { data: { permission: 'maintain' } };
        },
        listCommitStatusesForRef: async () => ({ data: state.statuses }),
        createCommitStatus: async (item) => { const status = { ...item, creator: { login: 'github-actions[bot]' } }; state.statuses.push(status); return { data: status }; } },
      checks: { listForRef: async () => {
        if (state.checkError) throw new Error('simulated check API failure');
        return { data: { check_runs: state.checks } };
      } },
    },
  };
  const context = { eventName: 'workflow_dispatch', actor: 'rbctmz', repo: { owner: 'rbctmz', repo: 'ai_trainer' },
    payload: { inputs: { pr: '729' }, repository: { owner: { login: 'rbctmz' } } } };
  const core = { info() {}, warning() {}, setFailed: message => state.failures.push(message) };
  const workflow = fs.readFileSync(path.join(__dirname, '../workflows/pr-ready-to-merge.yml'), 'utf8');
  const job = workflow.split('  ready-to-merge:')[1].split('\n');
  const start = job.findIndex(line => line.trim() === 'script: |') + 1;
  assert.ok(start > 0, 'ready job script must be present');
  const script = job.slice(start).map(line => line.startsWith('            ') ? line.slice(12) : line).join('\n');
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
  return { state, github, context, run: () => new AsyncFunction('github', 'context', 'core', 'require', script)(github, context, core,
    modulePath => { assert.equal(modulePath, './.github/scripts/review-gate.cjs'); return require('./review-gate.cjs'); }) };
}

test('Draft gets one review summary before first ready without acquiring readiness', async () => {
  const h = readinessHarness();
  await h.run();
  assert.equal(h.state.comments.length, 1, 'Draft must show its first summary');
  assert.match(h.state.comments[0].body, /Native rounds \(PR\).*0 \/ 2/);
  assert.match(h.state.comments[0].body, /Open review threads.*0/);
  assert.match(h.state.comments[0].body, /PR is draft/);
  assert.deepEqual(h.state.labels, []);
});

function reviewedHarness(extra = {}) {
  const h = readinessHarness({
    comments: [{ id: 12, user: { login: 'chatgpt-codex-connector[bot]' },
      body: `Codex Review: Didn't find any major issues.\n\n**Reviewed commit:** \`${HEAD_A}\`` }],
    labels: ['status: review accepted'],
    events: [{ event: 'labeled', label: { name: 'status: review accepted' }, actor: { login: 'rbctmz' } }],
    ...extra,
  });
  h.state.pr.draft = false;
  return h;
}

function summary(h) {
  return h.state.comments.find(c => c.user.login === 'github-actions[bot]' && c.body.startsWith('<!-- pr-ready-to-merge -->'));
}

test('repeated Draft projections update one canonical comment without no-op writes', async () => {
  const h = readinessHarness();
  await h.run();
  h.state.mutations.length = 0;
  await h.run();
  assert.equal(h.state.comments.length, 1);
  assert.deepEqual(h.state.mutations, []);
});

test('clean comment/ledger is one round; thread resolution updates the same summary and readiness', async () => {
  const h = reviewedHarness({ threads: [{ isResolved: false }] });
  await h.run();
  const id = summary(h).id;
  assert.match(summary(h).body, /Native rounds \(PR\).*1 \/ 2/);
  assert.match(summary(h).body, /Native rounds \(current HEAD\).*1/);
  assert.match(summary(h).body, /Open review threads.*1/);
  assert.match(summary(h).body, /1 unresolved review thread/);
  assert.equal(h.state.labels.includes('status: ready to merge'), false);
  h.state.threads[0].isResolved = true;
  await h.run();
  assert.equal(summary(h).id, id);
  assert.match(summary(h).body, /Open review threads.*0/);
  assert.match(summary(h).body, /\*\*Ready to merge\*\*/);
  assert.ok(h.state.labels.includes('status: ready to merge'));
  assert.equal(h.state.comments.length, 2); // native receipt + our comment
});

test('a push preserves consumed budget while removing current-head acceptance and review', async () => {
  const h = reviewedHarness();
  await h.run();
  h.state.pr.head.sha = HEAD_B;
  h.context.eventName = 'pull_request_target';
  h.context.payload.action = 'synchronize';
  h.context.payload.pull_request = { number: 729 };
  await h.run();
  assert.match(summary(h).body, new RegExp(HEAD_B.slice(0, 12)));
  assert.match(summary(h).body, /Native rounds \(PR\).*1 \/ 2/);
  assert.match(summary(h).body, /Native rounds \(current HEAD\).*0/);
  assert.match(summary(h).body, /Review accepted by owner.*No/);
  assert.match(summary(h).body, /no submitted native review for the current head/);
  assert.deepEqual(h.state.labels, []);
});

for (const draft of [true, false]) {
  test(`review API failure shows unknown and fails closed (Draft=${draft})`, async () => {
    const h = readinessHarness({ reviewError: true });
    h.state.pr.draft = draft;
    await h.run();
    assert.match(summary(h).body, /Native rounds \(PR\).*unknown/);
    assert.match(summary(h).body, /Open review threads.*unknown/);
    assert.match(summary(h).body, /Review accepted by owner.*unknown/);
    assert.doesNotMatch(summary(h).body, /simulated private/);
    assert.match(summary(h).body, /\*\*Not ready to merge\*\*/);
    assert.ok(h.state.failures.length);
    assert.deepEqual(h.state.labels, []);
  });
}

test('check API failure keeps known review metrics and cannot publish readiness', async () => {
  const h = reviewedHarness({ checkError: true });
  await h.run();
  assert.match(summary(h).body, /Native rounds \(PR\).*1 \/ 2/);
  assert.match(summary(h).body, /review or check data unavailable/);
  assert.deepEqual(h.state.labels, ['status: review accepted']);
  assert.ok(h.state.failures.length);
});

test('unavailable permission API displays unknown owner acceptance without changing authentication rules', async () => {
  const h = reviewedHarness({ permissionError: true,
    events: [{ event: 'labeled', label: { name: 'status: review accepted' }, actor: { login: 'maintainer' } }] });
  await h.run();
  assert.match(summary(h).body, /Review accepted by owner.*unknown/);
  assert.match(summary(h).body, /review result is not accepted/);
  assert.equal(h.state.labels.includes('status: ready to merge'), false);
});

test('a changed head before publication suppresses stale comments and readiness labels', async () => {
  const h = reviewedHarness();
  const get = h.github.rest.pulls.get;
  let reads = 0;
  h.github.rest.pulls.get = async args => {
    if (++reads === 2) h.state.pr.head.sha = HEAD_B;
    return get(args);
  };
  await h.run();
  assert.equal(summary(h), undefined);
  assert.equal(h.state.labels.includes('status: ready to merge'), false);
});

test('only our bot-owned status is edited; legacy duplicates are neutralized once', async () => {
  const h = readinessHarness({ comments: [
    { id: 1, user: { login: 'rbctmz' }, body: '<!-- pr-ready-to-merge --> human' },
    { id: 2, user: { login: 'chatgpt-codex-connector[bot]' }, body: '<!-- codex-review-state:v1 --> native summary' },
    { id: 3, user: { login: 'github-actions[bot]' }, body: '<!-- pr-ready-to-merge:old --> old' },
    { id: 4, user: { login: 'github-actions[bot]' }, body: '<!-- pr-ready-to-merge --> current' },
  ] });
  await h.run();
  assert.equal(h.state.comments.length, 4);
  assert.equal(summary(h).id, 4);
  assert.equal(h.state.comments[0].body, '<!-- pr-ready-to-merge --> human');
  assert.equal(h.state.comments[1].body, '<!-- codex-review-state:v1 --> native summary');
  assert.match(h.state.comments[2].body, /pr-ready-to-merge-superseded/);
  h.state.mutations.length = 0;
  await h.run();
  assert.deepEqual(h.state.mutations, []);
});

test('closed PR without prior summary does not get a new notification', async () => {
  const h = readinessHarness();
  h.state.pr.state = 'closed';
  await h.run();
  assert.equal(h.state.comments.length, 0);
});

test('partial or wrong-head snapshots cannot be rendered as ready or zero', () => {
  const pr = { state: 'open', head: { sha: HEAD_A } };
  for (const metrics of [null, { headSha: HEAD_B, nativeReviewRounds: 1 },
    { headSha: HEAD_A, nativeReviewRounds: null, currentHeadNativeReviewRounds: 0, unresolvedThreads: NaN, accepted: null }]) {
    const body = renderReadinessComment({ pr, issueNums: [729], ready: true, reason: '', metrics });
    assert.match(body, /\*\*Not ready to merge\*\*/);
    assert.match(body, /Native rounds \(PR\).*unknown/);
    assert.match(body, /Open review threads.*unknown/);
    assert.match(body, /Review accepted by owner.*unknown/);
  }
});

test('dynamic failure reasons cannot inject extra Markdown rows', () => {
  const body = renderReadinessComment({ pr: { head: { sha: HEAD_A } }, issueNums: [729],
    ready: false, reason: 'lint|bad\n| forged row | Yes |', metrics: null });
  assert.match(body, /lint\\\|bad \\\| forged row/);
  assert.doesNotMatch(body, /\n\| forged row/);
});

test('a changed acceptance label before publication suppresses the stale snapshot', async () => {
  const h = reviewedHarness();
  const get = h.github.rest.issues.get;
  let reads = 0;
  h.github.rest.issues.get = async args => {
    if (++reads === 2) h.state.labels = [];
    return get(args);
  };
  await h.run();
  assert.equal(summary(h), undefined);
  assert.equal(h.state.labels.includes('status: ready to merge'), false);
});

test('unavailable comment API fails without blindly creating a duplicate', async () => {
  const h = readinessHarness();
  h.github.rest.issues.listComments = async () => { throw new Error('comments unavailable'); };
  await assert.rejects(h.run(), /comments unavailable/);
  assert.deepEqual(h.state.mutations, []);
});

test('an early list API rejection is reported as unknown while thread lookup is still pending', async () => {
  const h = readinessHarness();
  const graphql = h.github.graphql;
  h.github.graphql = async args => {
    await new Promise(resolve => setTimeout(resolve, 5));
    return graphql(args);
  };
  h.github.rest.pulls.listReviews = async () => { throw new Error('reviews unavailable'); };
  await h.run();
  assert.match(summary(h).body, /Native rounds \(PR\).*unknown/);
  assert.ok(h.state.failures.length);
});
