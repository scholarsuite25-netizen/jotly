"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import DashboardScreen from "./dashboard-screen";
import RecorderScreen from "./recorder-screen";
import TranscriptEditorScreen from "./transcript-editor-screen";
import { authenticatedFetch, clearSessionToken } from "@/lib/auth-session.mjs";
import {
  createOrgSelectionState,
  organisationHeaders as buildOrgHeaders,
  selectOrganisation,
} from "@/lib/org-selection.mjs";

/**
 * Authenticated application shell: organisation selection/creation and navigation
 * between dashboard, recorder, and transcript editor views.
 */
export default function AppShell({ apiBaseUrl, initialIdentity, onSignOut }) {
  const [identity, setIdentity] = useState(initialIdentity);
  const memberships = (identity && identity.organisations) || [];
  const [orgState, setOrgState] = useState(() => createOrgSelectionState(memberships));
  const [view, setView] = useState({ name: "dashboard" });
  const [notice, setNotice] = useState(null);
  const [error, setError] = useState(null);
  const [creatingOrg, setCreatingOrg] = useState(false);
  const [orgName, setOrgName] = useState("");

  // Keep org selection in sync if identity changes.
  useEffect(() => {
    const nextMemberships = (identity && identity.organisations) || [];
    setOrgState((prev) => {
      const stillValid =
        prev.selectedOrgId && nextMemberships.some((m) => m.id === prev.selectedOrgId);
      if (stillValid) {
        return { ...prev, memberships: nextMemberships };
      }
      return createOrgSelectionState(nextMemberships);
    });
  }, [identity]);

  const selectedMembership = useMemo(
    () => memberships.find((m) => m.id === orgState.selectedOrgId) || null,
    [memberships, orgState.selectedOrgId]
  );

  const activeOrgName =
    (identity &&
      identity.active_organisation &&
      identity.active_organisation.id === orgState.selectedOrgId &&
      identity.active_organisation.name) ||
    (selectedMembership && selectedMembership.name) ||
    "Organisation";

  const organisationHeaders = useCallback(() => buildOrgHeaders(orgState), [orgState]);

  const refreshIdentity = useCallback(async () => {
    const fresh = await authenticatedFetch(`${apiBaseUrl}/me`);
    setIdentity(fresh);
    return fresh;
  }, [apiBaseUrl]);

  const handleSelectOrg = useCallback((orgId) => {
    setOrgState((prev) => selectOrganisation(prev, orgId));
    setView({ name: "dashboard" });
    setError(null);
  }, []);

  const handleCreateOrganisation = useCallback(
    async (event) => {
      event.preventDefault();
      const name = orgName.trim();
      if (!name) {
        setError("Enter an organisation name.");
        return;
      }
      setCreatingOrg(true);
      setError(null);
      try {
        await authenticatedFetch(`${apiBaseUrl}/organisations`, {
          method: "POST",
          body: JSON.stringify({ name }),
        });
        const fresh = await refreshIdentity();
        const freshMemberships = (fresh && fresh.organisations) || [];
        if (freshMemberships.length === 1) {
          setOrgState(createOrgSelectionState(freshMemberships));
        }
        setOrgName("");
        setNotice("Organisation created. You are the organisation admin.");
        setView({ name: "dashboard" });
      } catch (err) {
        setError(err.message || "Failed to create organisation.");
      } finally {
        setCreatingOrg(false);
      }
    },
    [apiBaseUrl, orgName, refreshIdentity]
  );

  const handleSignOut = useCallback(() => {
    clearSessionToken();
    if (onSignOut) onSignOut();
  }, [onSignOut]);

  const openRecorder = useCallback((meetingId) => {
    setView({ name: "recorder", meetingId });
    setError(null);
  }, []);

  const openTranscript = useCallback(async (transcriptId) => {
    if (!transcriptId) return;
    setError(null);
    try {
      const transcript = await authenticatedFetch(`${apiBaseUrl}/transcripts/${transcriptId}`, {
        headers: organisationHeaders(),
      });
      setView({ name: "transcript", transcript });
    } catch (err) {
      setError(err.message || "Failed to load transcript.");
    }
  }, [apiBaseUrl, organisationHeaders]);

  const refreshTranscript = useCallback(async () => {
    if (view.name !== "transcript" || !view.transcript) return;
    try {
      const transcript = await authenticatedFetch(
        `${apiBaseUrl}/transcripts/${view.transcript.id}`,
        { headers: organisationHeaders() }
      );
      setView({ name: "transcript", transcript });
    } catch (err) {
      setError(err.message || "Failed to refresh transcript.");
    }
  }, [apiBaseUrl, organisationHeaders, view]);

  const userEmail = identity && identity.user ? identity.user.email : "your account";

  // No organisation memberships yet: prompt to create one.
  if (memberships.length === 0) {
    return (
      <main>
        <h1>Welcome to Jotly</h1>
        <p>Signed in as {userEmail}.</p>
        <p>Create your first organisation to continue. You will become the organisation admin.</p>
        <form onSubmit={handleCreateOrganisation} aria-label="Create organisation form">
          <label htmlFor="org-name">Organisation name</label>
          <input
            id="org-name"
            value={orgName}
            onChange={(e) => setOrgName(e.target.value)}
            disabled={creatingOrg}
            required
            minLength={2}
          />
          <button type="submit" disabled={creatingOrg}>
            {creatingOrg ? "Creating…" : "Create organisation"}
          </button>
        </form>
        {notice ? <p role="status">{notice}</p> : null}
        {error ? <p role="alert" style={{ color: "#b00020" }}>{error}</p> : null}
        <button type="button" onClick={handleSignOut}>Sign out</button>
      </main>
    );
  }

  // Multiple memberships and none selected yet: require explicit selection.
  if (!orgState.selectedOrgId) {
    return (
      <main>
        <h1>Select organisation</h1>
        <p>Signed in as {userEmail}.</p>
        <ul aria-label="Organisation memberships">
          {memberships.map((org) => (
            <li key={org.id}>
              <button type="button" onClick={() => handleSelectOrg(org.id)}>
                {org.name} ({(org.roles || []).join(", ")})
              </button>
            </li>
          ))}
        </ul>
        {orgState.error ? <p role="alert" style={{ color: "#b00020" }}>{orgState.error}</p> : null}
        <button type="button" onClick={handleSignOut}>Sign out</button>
      </main>
    );
  }

  return (
    <div>
      <header style={{ marginBottom: "1rem" }}>
        <p>
          Signed in as <strong>{userEmail}</strong> · Organisation: <strong>{activeOrgName}</strong>
        </p>
        <nav aria-label="App navigation">
          <button type="button" onClick={() => setView({ name: "dashboard" })} disabled={view.name === "dashboard"}>
            Dashboard
          </button>{" "}
          <button type="button" onClick={handleSignOut}>Sign out</button>
        </nav>
        {memberships.length > 1 ? (
          <label>
            Switch organisation{" "}
            <select
              value={orgState.selectedOrgId}
              onChange={(e) => handleSelectOrg(e.target.value)}
            >
              {memberships.map((org) => (
                <option key={org.id} value={org.id}>{org.name}</option>
              ))}
            </select>
          </label>
        ) : null}
      </header>

      {notice ? <p role="status">{notice}</p> : null}
      {error ? <p role="alert" style={{ color: "#b00020" }}>{error}</p> : null}

      {view.name === "dashboard" ? (
        <DashboardScreen
          apiBaseUrl={apiBaseUrl}
          organisationHeaders={organisationHeaders}
          organisationId={orgState.selectedOrgId}
          organisationName={activeOrgName}
          onOpenRecorder={openRecorder}
          onOpenTranscript={openTranscript}
        />
      ) : null}

      {view.name === "recorder" ? (
        <div>
          <button type="button" onClick={() => setView({ name: "dashboard" })}>← Back to dashboard</button>
          <RecorderScreen
            meetingId={view.meetingId}
            apiBaseUrl={apiBaseUrl}
            organisationHeaders={organisationHeaders}
            onSaved={() => setNotice("Recording uploaded. You can start transcription from the dashboard.")}
          />
        </div>
      ) : null}

      {view.name === "transcript" && view.transcript ? (
        <div>
          <button type="button" onClick={() => setView({ name: "dashboard" })}>← Back to dashboard</button>
          <TranscriptEditorScreen
            transcript={view.transcript}
            apiBaseUrl={apiBaseUrl}
            organisationHeaders={organisationHeaders}
            onRefresh={refreshTranscript}
          />
        </div>
      ) : null}
    </div>
  );
}
