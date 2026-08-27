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
    return CODEX_REVIEWER_LOGINS.has(login) && state !== 'PENDING';
  }).length;
}

const READY_MARKER = '<!-- pr-ready-to-merge -->';
const LEGACY_READY_MARKER_PREFIX = '<!-- pr-ready-to-merge:';

function selectReadinessStatusComments(comments) {
  const matches = comments.filter((comment) => {
    const body = comment.body || '';
    return comment.user?.login === 'github-actions[bot]' &&
      (body.includes(READY_MARKER) || body.includes(LEGACY_READY_MARKER_PREFIX));
  });
  const canonical = matches.find((comment) =>
    (comment.body || '').includes(READY_MARKER)
  ) || matches.at(-1) || null;

  return {
    canonical,
    duplicates: matches.filter((comment) => comment.id !== canonical?.id),
  };
}

function evaluateReviewGate({
  accepted,
  nativeReviewRounds,
  unresolvedThreads,
  hasBudgetException,
}) {
  if (nativeReviewRounds < 1) {
    return { ready: false, reason: 'no submitted native review' };
  }
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
  READY_MARKER,
  selectReadinessStatusComments,
  countNativeReviewRounds,
  evaluateReviewGate,
};
