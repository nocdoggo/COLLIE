import type { AuthorizationRequest, EventStateView, GrantView, PolicyDecision } from "../types";

export type AuthorizationState =
  /** The target grant's committed limit is still below the requested value. */
  | "open"
  /** A grant version now allows at least the requested value. */
  | "satisfied"
  | "grant_revoked"
  /** The target grant is not visible to this viewer. */
  | "grant_not_visible";

export interface AuthorizationItem {
  readonly request: AuthorizationRequest;
  readonly decision: PolicyDecision;
  readonly grant: GrantView | null;
  readonly state: AuthorizationState;
}

/**
 * Authorization requests from the policy's decisions, one per request_id (latest decision).
 * The state view has no explicit "answered" flag, so the state is derived from the current
 * version of the target grant.
 */
export function authorizationRequests(view: EventStateView): AuthorizationItem[] {
  const latest = new Map<string, PolicyDecision>();
  for (const decision of view.decisions) {
    const request = decision.authorization_request;
    if (request !== null) latest.set(request.request_id, decision);
  }
  const items: AuthorizationItem[] = [];
  for (const decision of latest.values()) {
    const request = decision.authorization_request as AuthorizationRequest;
    const grant = view.grants.find((g) => g.grant.grant_id === request.target_grant_id) ?? null;
    let state: AuthorizationState;
    if (grant === null) state = "grant_not_visible";
    else if (grant.revoked) state = "grant_revoked";
    else if (grant.grant.max_total_committed_cents >= request.requested_value) state = "satisfied";
    else state = "open";
    items.push({ request, decision, grant, state });
  }
  return items;
}

export const AUTHORIZATION_STATE_TEXT: Record<AuthorizationState, string> = {
  open: "Waiting for the organizer",
  satisfied: "Answered: the grant now allows this amount",
  grant_revoked: "Closed: the target grant is revoked",
  grant_not_visible: "Target grant not visible to this role",
};
