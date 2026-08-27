'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');

const {
  MAX_NATIVE_REVIEW_ROUNDS,
  countNativeReviewRounds,
  evaluateReviewGate,
  selectReadinessStatusComments,
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
    { ready: false, reason: 'no submitted native review' },
  );
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
