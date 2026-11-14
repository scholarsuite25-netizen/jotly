"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { authenticatedFetch } from "@/lib/auth-session.mjs";

/**
 * Dashboard screen: create/list meetings, open recorder, and access transcripts/media.
 */
export default function DashboardScreen({
  apiBaseUrl,
  organisationHeaders,
  organisationId,
  organisationName,
  onOpenRecorder,
  onOpenTranscript,
}) {
  const [meetings, setMeetings] = useState([]);
  const [workspaces, setWorkspaces] = useState([]);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [workspaceId, setWorkspaceId] = useState("");
  const [transcriptIdInput, setTranscriptIdInput] = useState("");
  const [busyMeetingId, setBusyMeetingId] = useState(null);

  const headers = useCallback(() => organisationHeaders(), [organisationHeaders]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [meetingsBody, wsBody] = await Promise.all([
        authenticatedFetch(`${apiBaseUrl}/meetings`, { headers: headers() }),
        organisationId
          ? authenticatedFetch(`${apiBaseUrl}/organisations/${organisationId}/workspaces`, {
              headers: headers(),
            })
          : Promise.resolve({ items: [] }),
      ]);
      const meetingItems = meetingsBody.items || [];
      const wsItems = wsBody.items || [];
      setMeetings(meetingItems);
      setWorkspaces(wsItems);
      if (!workspaceId && wsItems.length > 0) {
        setWorkspaceId(wsItems[0].id);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl, headers, organisationId, workspaceId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const createMeeting = useCallback(
    async (event) => {
      event.preventDefault();
      if (!title.trim() || !workspaceId) {
        setError("Enter a meeting title and select a workspace.");
        return;
      }
      setCreating(true);
      setError(null);
      setNotice(null);
      try {
        await authenticatedFetch(`${apiBaseUrl}/meetings`, {
          method: "POST",
          headers: headers(),
          body: JSON.stringify({ title: title.trim(), workspace_id: workspaceId }),
        });
        setTitle("");
        setNotice("Meeting created.");
        await refresh();
      } catch (err) {
        setError(err.message);
      } finally {
        setCreating(false);
      }
    },
    [apiBaseUrl, headers, refresh, title, workspaceId]
  );

  const getPlayback = useCallback(
    async (meetingId) => {
      setError(null);
      try {
        const media = await authenticatedFetch(`${apiBaseUrl}/meetings/${meetingId}/media`, {
          headers: headers(),
        });
        const firstAsset = (media.items || [])[0];
        if (!firstAsset) {
          setError("No media asset for this meeting yet.");
          return;
        }
        const pb = await authenticatedFetch(`${apiBaseUrl}/media/${firstAsset.id}/playback-url`, {
          headers: headers(),
        });
        window.open(pb.playback_url, "_blank", "noopener");
      } catch (err) {
        setError(err.message);
      }
    },
    [apiBaseUrl, headers]
  );

  const startTranscription = useCallback(
    async (meetingId) => {
      setBusyMeetingId(meetingId);
      setError(null);
      setNotice(null);
      try {
        const media = await authenticatedFetch(`${apiBaseUrl}/meetings/${meetingId}/media`, {
          headers: headers(),
        });
        const firstAsset = (media.items || [])[0];
        if (!firstAsset) {
          setError("No media asset found for this meeting. Record or upload media first.");
          return;
        }
        const body = await authenticatedFetch(
          `${apiBaseUrl}/meetings/${meetingId}/media/${firstAsset.id}/transcriptions`,
          {
            method: "POST",
            headers: headers(),
            body: JSON.stringify({ language_code: "en", enable_diarisation: false }),
          }
        );
        const tid = body.transcript_id;
        setNotice(`Transcription ${body.status || "queued"} (transcript ${tid}).`);
        if (tid && onOpenTranscript) {
          await onOpenTranscript(tid);
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setBusyMeetingId(null);
      }
    },
    [apiBaseUrl, headers, onOpenTranscript]
  );

  const openTranscriptById = useCallback(async () => {
    const id = transcriptIdInput.trim();
    if (!id || !onOpenTranscript) return;
    setError(null);
    await onOpenTranscript(id);
  }, [onOpenTranscript, transcriptIdInput]);

  const rows = useMemo(
    () =>
      meetings.map((m) => (
        <tr key={m.id}>
          <td>{m.title}</td>
          <td>{m.recording_state}</td>
          <td>{m.notice_confirmed ? "confirmed" : "not confirmed"}</td>
          <td>
            <button type="button" onClick={() => onOpenRecorder && onOpenRecorder(m.id)}>
              Record
            </button>{" "}
            <button type="button" onClick={() => getPlayback(m.id)}>Play</button>{" "}
            <button
              type="button"
              onClick={() => startTranscription(m.id)}
              disabled={busyMeetingId === m.id}
            >
              {busyMeetingId === m.id ? "Working…" : "Transcribe/Open"}
            </button>
          </td>
        </tr>
      )),
    [busyMeetingId, getPlayback, meetings, onOpenRecorder, startTranscription]
  );

  return (
    <main aria-label="Dashboard">
      <h1>{organisationName} — Meeting Dashboard</h1>

      <section aria-label="Create meeting">
        <h2>Create meeting</h2>
        <form onSubmit={createMeeting}>
          <label htmlFor="meeting-title">Title</label>
          <input
            id="meeting-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            minLength={2}
            disabled={creating}
          />
          <label htmlFor="meeting-workspace">Workspace</label>
          <select
            id="meeting-workspace"
            value={workspaceId}
            onChange={(e) => setWorkspaceId(e.target.value)}
            disabled={creating || workspaces.length === 0}
          >
            {workspaces.length === 0 ? <option value="">No workspace found</option> : null}
            {workspaces.map((ws) => (
              <option key={ws.id} value={ws.id}>{ws.name}</option>
            ))}
          </select>
          <button type="submit" disabled={creating || !workspaceId}>
            {creating ? "Creating…" : "Create meeting"}
          </button>
        </form>
      </section>

      <section aria-label="Open transcript">
        <h2>Open transcript</h2>
        <label htmlFor="transcript-id">Transcript ID</label>
        <input
          id="transcript-id"
          value={transcriptIdInput}
          onChange={(e) => setTranscriptIdInput(e.target.value)}
          placeholder="Paste transcript ID"
        />
        <button type="button" onClick={openTranscriptById} disabled={!transcriptIdInput.trim()}>
          Open transcript
        </button>
      </section>

      <section aria-label="Meetings">
        <h2>Meetings</h2>
        <button type="button" onClick={refresh} disabled={loading}>
          {loading ? "Loading…" : "Refresh"}
        </button>
        {notice ? <p role="status">{notice}</p> : null}
        {error ? <p role="alert" style={{ color: "#b00020" }}>{error}</p> : null}
        <table>
          <caption>Meetings in the selected organisation</caption>
          <thead>
            <tr>
              <th scope="col">Title</th>
              <th scope="col">Recording state</th>
              <th scope="col">Notice</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </section>
    </main>
  );
}
