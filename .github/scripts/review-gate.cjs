'use strict';

const MAX_NATIVE_REVIEW_ROUNDS = 2;
const CODEX_REVIEWER_LOGINS = new Set([
  'chatgpt-codex-connector',
  'chatgpt-codex-connector[bot]',
]);
const PRIVILEGED_REPOSITORY_PERMISSIONS = new Set(['admin', 'maintain']);
const CLEAN_NATIVE_REVIEW_STATUS_PREFIX = 'review-gate/codex-clean/';
const CLEAN_NATIVE_REVIEW_STATUS_DESCRIPTION = 'Authenticated Codex clean review round';

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

function cleanNativeReviewStatus(comment) {
  const head = cleanNativeReviewHead(comment);
  const sourceId = String(comment.id || '');
  if (!head || !/^\d+$/.test(sourceId)) return null;
  return {
    context: `${CLEAN_NATIVE_REVIEW_STATUS_PREFIX}${sourceId}:${head}`,
    description: CLEAN_NATIVE_REVIEW_STATUS_DESCRIPTION,
    head,
    sourceId,
  };
}

function cleanNativeReviewEntryFromStatus(status) {
  if (status.creator?.login !== 'github-actions[bot]' ||
      String(status.state || '').toLowerCase() !== 'success' ||
      status.description !== CLEAN_NATIVE_REVIEW_STATUS_DESCRIPTION) {
    return null;
  }
  const escapedPrefix = CLEAN_NATIVE_REVIEW_STATUS_PREFIX.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = String(status.context || '').match(
    new RegExp(`^${escapedPrefix}(\\d+):([0-9a-f]{7,40})$`, 'i')
  );
  return match ? { sourceId: match[1], head: match[2].toLowerCase() } : null;
}

function cleanNativeReviewRounds(comments, statuses) {
  const rounds = new Map();
  for (const comment of comments) {
    const status = cleanNativeReviewStatus(comment);
    if (status) rounds.set(status.sourceId, { sourceId: status.sourceId, head: status.head });
  }
  for (const status of statuses) {
    const entry = cleanNativeReviewEntryFromStatus(status);
    if (entry) rounds.set(entry.sourceId, entry);
  }
  return [...rounds.values()];
}

async function persistCleanReviewStatuses({ github, owner, repo, pr, comments }) {
  const commits = await github.paginate(github.rest.pulls.listCommits, {
    owner,
    repo,
    pull_number: pr.number,
    per_page: 100,
  });
  const statusBatches = await Promise.all(commits.map(commit =>
    github.paginate(github.rest.repos.listCommitStatusesForRef, {
      owner,
      repo,
      ref: commit.sha,
      per_page: 100,
    })
  ));
  const statuses = statusBatches.flat();
  const existingContexts = new Set(statuses.map(status => status.context));
  for (const comment of comments) {
    const marker = cleanNativeReviewStatus(comment);
    if (!marker || existingContexts.has(marker.context)) continue;
    const commit = commits.find(item => item.sha.startsWith(marker.head));
    if (!commit) {
      throw new Error(`Reviewed commit ${marker.head} is not in PR #${pr.number}`);
    }
    const { data: created } = await github.rest.repos.createCommitStatus({
      owner,
      repo,
      sha: commit.sha,
      state: 'success',
      context: marker.context,
      description: marker.description,
      target_url: comment.html_url || pr.html_url,
    });
    statuses.push(created);
    existingContexts.add(marker.context);
  }
  return statuses;
}

function commitMatchesHead(candidate, headSha) {
  const normalizedCandidate = String(candidate || '').toLowerCase();
  const normalizedHead = String(headSha || '').toLowerCase();
  return normalizedCandidate.length >= 7 && normalizedHead.startsWith(normalizedCandidate);
}

function countNativeReviewRounds(reviews, comments = [], statuses = []) {
  return reviews.filter(isSubmittedNativeReview).length +
    cleanNativeReviewRounds(comments, statuses).length;
}

function countNativeReviewRoundsForHead(reviews, headSha, comments = [], statuses = []) {
  const submittedForHead = reviews.filter((review) => {
    const reviewHead = review.commit_id || review.commit?.oid || review.commit?.sha || '';
    return isSubmittedNativeReview(review) && commitMatchesHead(reviewHead, headSha);
  }).length;
  const cleanForHead = cleanNativeReviewRounds(comments, statuses).filter(round =>
    commitMatchesHead(round.head, headSha)
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
  cleanNativeReviewStatus,
  persistCleanReviewStatuses,
  countNativeReviewRounds,
  countNativeReviewRoundsForHead,
  evaluateReviewGate,
};
