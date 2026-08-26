'use strict';

const MAX_NATIVE_REVIEW_ROUNDS = 2;
const CODEX_REVIEWER_LOGINS = new Set([
  'chatgpt-codex-connector',
  'chatgpt-codex-connector[bot]',
]);

function countNativeReviewRounds(reviews) {
  return reviews.filter((review) => {
    const login = review.user?.login || review.author?.login || '';
    const state = String(review.state || '').toUpperCase();
    return CODEX_REVIEWER_LOGINS.has(login) && !['DISMISSED', 'PENDING'].includes(state);
  }).length;
}

function evaluateReviewGate({
  accepted,
  nativeReviewRounds,
  unresolvedThreads,
  hasBudgetException,
}) {
  if (!accepted) {
    return { ready: false, reason: 'review result is not accepted for the current head' };
  }
  if (unresolvedThreads > 0) {
    return {
      ready: false,
      reason: `${unresolvedThreads} unresolved review thread(s)`,
    };
  }
  if (nativeReviewRounds > MAX_NATIVE_REVIEW_ROUNDS && !hasBudgetException) {
    return {
      ready: false,
      reason: `native review budget exceeded: ${nativeReviewRounds}/${MAX_NATIVE_REVIEW_ROUNDS}`,
    };
  }
  return {
    ready: true,
    reason: `review accepted; ${nativeReviewRounds}/${MAX_NATIVE_REVIEW_ROUNDS} native round(s); no unresolved threads`,
  };
}

module.exports = {
  MAX_NATIVE_REVIEW_ROUNDS,
  countNativeReviewRounds,
  evaluateReviewGate,
};
