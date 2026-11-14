"use client";

import { useCallback, useMemo, useState } from "react";
import { authenticatedFetch } from "@/lib/auth-session.mjs";

/**
 * Dashboard screen: meeting list, playback links, media status, and
 * quick navigation to the recorder and transcript editor.
 */
export default function DashboardScreen({ apiBaseUrl, organisationHeaders, organisationName }) {
  const [meetings, setMeetings] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const body = await authenticatedFetch(`${apiBaseUrl}/meetings`, {
        headers: organisationHeaders(),
      });
      setMeetings(body.items || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl, organisationHeaders]);

  const getPlayback = useCallback(
    async (meetingId) => {
      try {
        const media = await authenticatedFetch(
          `${apiBaseUrl}/meetings/${meetingId}/media`,
          { headers: organisationHeaders() }
        );
        const firstAsset = (media.items || [])[0];
        if (!firstAsset) {
          setError("No media asset for this meeting yet.");
          return;
        }
        const pb = await authenticatedFetch(
          `${apiBaseUrl}/media/${firstAsset.id}/playback-url`,
          { headers: organisationHeaders() }
        );
        window.open(pb.playback_url, "_blank", "noopener");
      } catch (err) {
        setError(err.message);
      }
    },
    [apiBaseUrl, organisationHeaders]
  );

  const tableRows = useMemo(
    () =>
      meetings.map((m) => (
        <tr key={m.id}>
          <td>{m.title}</td>
          <td>{m.recording_state}</td>
          <td>{m.notice_confirmed ? "confirmed" : "not confirmed"}</td>
          <td>
            <button type="button" onClick={() => getPlayback(m.id)}>
              Play media
            </button>
          </td>
        </tr>
      )),
    [getPlayback, meetings]
  );

  return (
    <main aria-label="Dashboard">
      <h1>{organisationName} — Meeting Dashboard</h1>
      <button type="button" onClick={refresh} disabled={loading}>
        {loading ? "Loading…" : "Refresh meetings"}
      </button>
      {error ? (
        <p role="alert" style={{ color: "#b00020" }}>
          {error}
        </p>
      ) : null}
      <table>
        <caption>Meetings in the selected organisation</caption>
        <thead>
          <tr>
            <th scope="col">Title</th>
            <th scope="col">Recording state</th>
            <th scope="col">Notice</th>
            <th scope="col">Media</th>
          </tr>
        </thead>
        <tbody>{tableRows}</tbody>
      </table>
    </main>
  );
}
