/** Presentation of stored evidence only. Absence must never synthesize a probe. */
export function redactEvidence(value: unknown): unknown {
  if (typeof value === 'string') return value
    .replace(/((?:authorization|cookie|set-cookie)\s*:\s*)[^\r\n]+/gi, '$1[REDACTED]')
    .replace(/(bearer\s+)[A-Za-z0-9._~+/=-]+/gi, '$1[REDACTED]')
    .replace(/((?:token|password|passwd|secret|api[_-]?key)=)[^&\s]+/gi, '$1[REDACTED]')
    .replace(/eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+/g, '[REDACTED_JWT]');
  if (Array.isArray(value)) return value.map(redactEvidence);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, val]) => [
    key, /^(authorization|cookie|set-cookie|password|passwd|token|secret|api[_-]?key|jwt)$/i.test(key) ? '[REDACTED]' : redactEvidence(val),
  ]));
  return value;
}

export function recordedEvidence(evidence: Record<string, unknown>, rawPayload?: string | null, missing = 'No recorded evidence for this field.') {
  const clean = (redactEvidence(evidence) || {}) as Record<string, unknown>;
  const format = (value: unknown): string => value === undefined || value === null || value === '' ? missing
    : typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  const headers = clean.headers && typeof clean.headers === 'object' && !Array.isArray(clean.headers)
    ? clean.headers as Record<string, unknown> : {};
  const explicitProof = clean.matched_content ?? clean.proof ?? clean.extracted_results ?? rawPayload;
  return {
    request: format(clean.request ?? clean.raw_request),
    response: format(clean.response ?? clean.raw_response ?? clean.body),
    headers,
    proof: format(explicitProof != null ? redactEvidence(explicitProof) : Object.keys(clean).length ? clean : undefined),
    curl: format(clean.curl_command ?? clean.replay_curl),
  };
}
