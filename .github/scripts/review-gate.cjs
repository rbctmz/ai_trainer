'use strict';

const MAX_NATIVE_REVIEW_ROUNDS = 2;
const CODEX_REVIEWER_LOGINS = new Set([
  'chatgpt-codex-connector',
  'chatgpt-codex-connector[bot]',
]);
const PRIVILEGED_REPOSITORY_PERMISSIONS = new Set(['admin', 'maintain']);

function isSubmittedNativeReview(review) {
  const login = review.user?.login || review.author?.login || '';
  const state = String(review.state || '').toUpperCase();
  return CODEX_REVIEWER_LOGINS.has(login) && state !== 'PENDING';
}

function cleanNativeReviewHead(comment) {
  const login = comment.user?.login || comment.author?.login || '';
  const body = String(comment.body || '');
  if (!CODEX_REVIEWER_LOGINS.has(login) ||
      !body.startsWith("Codex Review: Didn't find any major issues.")) {
    return null;
  }
  const match = body.match(/\*\*Reviewed commit:\*\*\s*`([0-9a-f]{7,40})`/i);
  return match ? match[1].toLowerCase() : null;
}

function commitMatchesHead(candidate, headSha) {
  const normalizedCandidate = String(candidate || '').toLowerCase();
  const normalizedHead = String(headSha || '').toLowerCase();
  return normalizedCandidate.length >= 7 && normalizedHead.startsWith(normalizedCandidate);
}

function countNativeReviewRounds(reviews, comments = []) {
  return reviews.filter(isSubmittedNativeReview).length +
    comments.filter(comment => cleanNativeReviewHead(comment) !== null).length;
}

function countNativeReviewRoundsForHead(reviews, headSha, comments = []) {
  const submittedForHead = reviews.filter((review) => {
    const reviewHead = review.commit_id || review.commit?.oid || review.commit?.sha || '';
    return isSubmittedNativeReview(review) && commitMatchesHead(reviewHead, headSha);
  }).length;
  const cleanForHead = comments.filter(comment =>
    commitMatchesHead(cleanNativeReviewHead(comment), headSha)
  ).length;
  return submittedForHead + cleanForHead;
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

function shouldInvalidateAcceptance(eventName, action, comment = null) {
  return (['pull_request', 'pull_request_target'].includes(eventName) &&
      action === 'synchronize') ||
    (eventName === 'pull_request_review' && action === 'submitted') ||
    (eventName === 'issue_comment' && ['created', 'edited'].includes(action) &&
      cleanNativeReviewHead(comment) !== null);
}

function latestLabelActor(events, labelName) {
  const ordered = [...events].sort((left, right) => {
    const timeOrder = String(left.created_at || '').localeCompare(String(right.created_at || ''));
    return timeOrder || Number(left.id || 0) - Number(right.id || 0);
  });
  let actor = null;
  for (const event of ordered) {
    if (event.label?.name !== labelName) continue;
    if (event.event === 'labeled') actor = event.actor?.login || null;
    if (event.event === 'unlabeled') actor = null;
  }
  return actor;
}

function isPrivilegedRepositoryPermission(permission) {
  return PRIVILEGED_REPOSITORY_PERMISSIONS.has(String(permission || '').toLowerCase());
}

function evaluateReviewGate({
  accepted,
  nativeReviewRounds,
  currentHeadNativeReviewRounds = nativeReviewRounds,
  unresolvedThreads,
  hasBudgetException,
  reviewDecision = null,
}) {
  if (currentHeadNativeReviewRounds < 1) {
    return { ready: false, reason: 'no submitted native review for the current head' };
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
  if (String(reviewDecision || '').toUpperCase() === 'CHANGES_REQUESTED') {
    return { ready: false, reason: 'an active review requests changes' };
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
  shouldInvalidateAcceptance,
  latestLabelActor,
  isPrivilegedRepositoryPermission,
  cleanNativeReviewHead,
  countNativeReviewRounds,
  countNativeReviewRoundsForHead,
  evaluateReviewGate,
};
