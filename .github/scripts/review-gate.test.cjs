'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');

const {
  MAX_NATIVE_REVIEW_ROUNDS,
  countNativeReviewRounds,
  evaluateReviewGate,
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
