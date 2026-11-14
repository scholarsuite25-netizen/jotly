/**
 * Organisation selection view model: lets a multi-org member pick the active
 * organisation; the choice is sent as X-Organisation-ID and validated server-side
 * on every request (the client never grants access by itself).
 */

export function createOrgSelectionState(memberships = []) {
  return {
    memberships,
    selectedOrgId: memberships.length === 1 ? memberships[0].id : null,
    error: null,
  };
}

export function selectOrganisation(state, orgId) {
  const exists = state.memberships.some((m) => m.id === orgId);
  if (!exists) {
    return {
      ...state,
      selectedOrgId: null,
      error: "Selected organisation is not in your memberships.",
    };
  }
  return { ...state, selectedOrgId: orgId, error: null };
}

/** Returns request headers for the selected organisation context. */
export function organisationHeaders(state) {
  if (!state.selectedOrgId) {
    throw new Error("Select an organisation before making organisation-scoped requests.");
  }
  return { "X-Organisation-ID": state.selectedOrgId };
}
