/** Mirror the API lifecycle, keeping claimed fixes separate from verified resolution. */
export const FINDING_STATUSES = [
  'NEW', 'NEEDS_TRIAGE', 'CONFIRMED', 'ASSIGNED', 'IN_PROGRESS',
  'FIXED_PENDING_RETEST', 'RESOLVED', 'REOPENED', 'ACCEPTED_RISK', 'FALSE_POSITIVE',
] as const;

export const TRIAGE_STATUSES = FINDING_STATUSES.filter((status) => status !== 'RESOLVED');

const LEGACY: Record<string, string> = {
  OPEN: 'NEEDS_TRIAGE', POTENTIAL: 'NEEDS_TRIAGE', IN_REMEDIATION: 'IN_PROGRESS',
  FIXED: 'FIXED_PENDING_RETEST', NOT_AFFECTED: 'FALSE_POSITIVE', MUTED: 'ACCEPTED_RISK',
};

export function canonicalFindingStatus(status: string | null | undefined): string {
  const value = (status || 'NEW').toUpperCase();
  return LEGACY[value] || value;
}

export function findingStage(status: string | null | undefined): string {
  const value = canonicalFindingStatus(status);
  if (['NEW', 'NEEDS_TRIAGE', 'CONFIRMED', 'ASSIGNED'].includes(value)) return 'TRIAGE';
  if (['IN_PROGRESS', 'FIXED_PENDING_RETEST', 'RESOLVED', 'REOPENED'].includes(value)) return value;
  // Preserve visibility of dismissed and unfamiliar historical statuses.
  return 'OTHER';
}
