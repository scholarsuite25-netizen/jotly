"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { authenticatedFetch } from "@/lib/auth-session.mjs";
import {
  describeMedia,
  describeTranscripts,
  isSessionError,
  selectLatestTranscript,
  summariseMedia,
} from "@/lib/meeting-status.mjs";

/**
 * Dashboard screen: create/list meetings with per-meeting media and transcript
 * discovery (status + "open latest"), plus recorder/transcript hand-off.
 * Session-expiry errors are surfaced to the shell for a clean re-auth.
 */
export default function DashboardScreen({
  apiBaseUrl,
  organisationHeaders,
  organisationId,
  organisationName,
  onOpenRecorder,
  onOpenTranscript,
  onSessionExpired,
}) {
  const [meetings, setMeetings] = useState([]);
  const [workspaces, setWorkspaces] = useState([]);
  const [details, setDetails] = useState({});
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [workspaceId, setWorkspaceId] = useState("");
  const [transcriptIdInput, setTranscriptIdInput] = useState("");
  const [busyMeetingId, setBusyMeetingId] = useState(null);

  const headers = useCallback(() => organisationHeaders(), [organisationHeaders]);

  const fail = useCallback(
    (err) => {
      if (isSessionError(err)) {
        setError("Your session expired. Please sign in again.");
        if (onSessionExpired) onSessionExpired();
        return;
      }
      setError(err.message);
    },
    [onSessionExpired]
  );

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

      // Per-meeting discovery: media + transcripts (independent of the main list)
      const entries = await Promise.all(
        meetingItems.map(async (m) => {
          try {
            const [media, transcripts] = await Promise.all([
              authenticatedFetch(`${apiBaseUrl}/meetings/${m.id}/media`, {
                headers: headers(),
              }),
              authenticatedFetch(`${apiBaseUrl}/meetings/${m.id}/transcripts`, {
                headers: headers(),
              }),
            ]);
            return [
              m.id,
              {
                media: summariseMedia(media.items || []),
                transcripts: transcripts.items || [],
                error: null,
              },
            ];
          } catch (err) {
            if (isSessionError(err)) throw err;
            return [m.id, { media: null, transcripts: [], error: err.message }];
          }
        })
      );
      setDetails(Object.fromEntries(entries));
    } catch (err) {
      fail(err);
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl, fail, headers, organisationId, workspaceId]);

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
        fail(err);
      } finally {
        setCreating(false);
      }
    },
    [apiBaseUrl, fail, headers, refresh, title, workspaceId]
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
        fail(err);
      }
    },
    [apiBaseUrl, fail, headers]
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
        const queued = await authenticatedFetch(
          `${apiBaseUrl}/media/${firstAsset.id}/transcriptions`,
          {
            method: "POST",
            headers: headers(),
            body: JSON.stringify({ language_code: "en", enable_diarisation: false }),
          }
        );
        let tid = queued.transcript_id || null;
        let status = queued.status || "queued";
        if (!tid && queued.job_id) {
          const executed = await authenticatedFetch(
            `${apiBaseUrl}/media/${firstAsset.id}/transcriptions/${queued.job_id}/execute`,
            {
              method: "POST",
              headers: headers(),
              body: JSON.stringify({ language_code: "en", enable_diarisation: false }),
            }
          );
          tid = executed.transcript_id || null;
          status = executed.status || status;
        }
        if (tid) {
          setTranscriptIdInput(tid);
        }
        setNotice(
          tid
            ? `Transcription ${status} (transcript ${tid}).`
            : `Transcription ${status}.`
        );
        if (tid && onOpenTranscript) {
          await onOpenTranscript(tid);
        }
        await refresh();
      } catch (err) {
        fail(err);
      } finally {
        setBusyMeetingId(null);
      }
    },
    [apiBaseUrl, fail, headers, onOpenTranscript, refresh]
  );

  const openTranscriptById = useCallback(async () => {
    const id = transcriptIdInput.trim();
    if (!id || !onOpenTranscript) return;
    setError(null);
    try {
      await onOpenTranscript(id);
    } catch (err) {
      fail(err);
    }
  }, [fail, onOpenTranscript, transcriptIdInput]);

  const openTranscript = useCallback(
    async (transcriptId) => {
      setError(null);
      try {
        await onOpenTranscript(transcriptId);
      } catch (err) {
        fail(err);
      }
    },
    [fail, onOpenTranscript]
  );

  const rows = useMemo(
    () =>
      meetings.map((m) => {
        const detail = details[m.id] || {};
        const mediaSummary = detail.media;
        const transcripts = detail.transcripts || [];
        const latest = selectLatestTranscript(transcripts);
        return (
          <tr key={m.id}>
            <td>{m.title}</td>
            <td>
              {detail.error ? (
                <span style={{ color: "#b00020" }}>Unavailable</span>
              ) : mediaSummary ? (
                describeMedia(mediaSummary)
              ) : (
                "Loading…"
              )}
            </td>
            <td>
              {transcripts.length === 0 ? (
                <span>{detail.error ? "Unavailable" : describeTranscripts(transcripts)}</span>
              ) : (
                <>
                  <span>{describeTranscripts(transcripts)}</span>{" "}
                  {latest ? (
                    <button type="button" onClick={() => openTranscript(latest.id)}>
                      Open latest
                    </button>
                  ) : null}
                  {transcripts.slice(0, 3).map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      title={`Transcript ${t.id} (${t.status})`}
                      onClick={() => openTranscript(t.id)}
                    >
                      Open {t.status}
                    </button>
                  ))}
                </>
              )}
            </td>
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
        );
      }),
    [
      busyMeetingId,
      details,
      getPlayback,
      meetings,
      onOpenRecorder,
      openTranscript,
      startTranscription,
    ]
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
        <p>Paste a transcript ID, or use <strong>Transcribe/Open</strong> / <strong>Open latest</strong> on a meeting.</p>
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
        {meetings.length === 0 && !loading ? (
          <p role="status">No meetings yet — create one above to get started.</p>
        ) : null}
        <table>
          <caption>Meetings in the selected organisation</caption>
          <thead>
            <tr>
              <th scope="col">Title</th>
              <th scope="col">Media</th>
              <th scope="col">Transcripts</th>
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
