export interface OrganisationMembershipSummary {
  id: string;
  slug: string;
  name: string;
  roles: string[];
  permissions: string[];
}

export interface AuthenticatedSessionView {
  userId: string;
  email: string;
  fullName: string;
  mfaVerified: boolean;
  activeOrganisation: OrganisationMembershipSummary | null;
}

export function canAccessPermission(
  session: AuthenticatedSessionView | null,
  permissionCode: string
): boolean {
  if (!session || !session.activeOrganisation) {
    return false;
  }
  const perms = session.activeOrganisation.permissions;
  return perms.includes(permissionCode) || perms.includes("tenant.admin");
}
