"use client";

import { useCallback, useMemo, useState } from "react";
import {
  RECORDER_STATES,
  computeMissingChunkIndices,
  createRecorderState,
  shouldWarnBeforeUnload,
  transitionRecorderState,
} from "@/lib/recorder-state.mjs";

const CHUNK_SIZE_BYTES = 5 * 1024 * 1024;

function base64FromBytes(bytes) {
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

async function sha256Hex(bytes) {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * Recorder screen: notice gate → record (start/pause/resume) → resumable chunked upload.
 * Drives the tested recorder-state machine and the Phase 2 upload API.
 */
export default function RecorderScreen({
  meetingId,
  apiBaseUrl,
  organisationHeaders,
  noticeVersion = "2026-11-v1",
  onSaved,
}) {
  const [state, dispatchState] = useState(createRecorderState);
  const [mediaRecorder, setMediaRecorder] = useState(null);
  const [chunks, setChunks] = useState([]);

  const warn = shouldWarnBeforeUnload(state);

  const confirmNotice = useCallback(() => {
    dispatchState((prev) =>
      transitionRecorderState(prev, { type: "CONFIRM_NOTICE", noticeVersion })
    );
  }, [noticeVersion]);

  const startRecording = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const recorder = new MediaRecorder(stream);
    setMediaRecorder(recorder);
    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        setChunks((prev) => [...prev, event.data]);
      }
    };
    recorder.start(1000);
    dispatchState((prev) => transitionRecorderState(prev, { type: "START_RECORDING" }));
  }, []);

  const pauseRecording = useCallback(() => {
    if (mediaRecorder && mediaRecorder.state === "recording") {
      mediaRecorder.pause();
    }
    dispatchState((prev) => transitionRecorderState(prev, { type: "PAUSE_RECORDING" }));
  }, [mediaRecorder]);

  const resumeRecording = useCallback(() => {
    if (mediaRecorder && mediaRecorder.state === "paused") {
      mediaRecorder.resume();
    }
    dispatchState((prev) => transitionRecorderState(prev, { type: "RESUME_RECORDING" }));
  }, [mediaRecorder]);

  const stopAndUpload = useCallback(async () => {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
      mediaRecorder.stream.getTracks().forEach((track) => track.stop());
    }
    const blob = new Blob(chunks, { type: "audio/webm" });
    const bytes = new Uint8Array(await blob.arrayBuffer());
    const totalChunks = Math.max(1, Math.ceil(bytes.length / CHUNK_SIZE_BYTES));
    dispatchState((prev) =>
      transitionRecorderState(prev, { type: "STOP_AND_UPLOAD", totalChunks })
    );

    const expectedSha256 = await sha256Hex(bytes);
    const init = await fetch(`${apiBaseUrl}/meetings/${meetingId}/uploads`, {
      method: "POST",
      headers: { ...organisationHeaders(), "Idempotency-Key": `${meetingId}:${expectedSha256}` },
      body: JSON.stringify({
        file_name: `meeting-${meetingId}.webm`,
        mime_type: "audio/webm",
        declared_size_bytes: bytes.length,
        expected_sha256: expectedSha256,
      }),
    });
    const session = await init.json();
    if (!init.ok) {
      dispatchState((prev) =>
        transitionRecorderState(prev, {
          type: "PROCESSING_FAILED",
          errorMessage: session.error ? session.error.message : "Upload init failed.",
        })
      );
      return;
    }

    for (const index of computeMissingChunkIndices(session.total_chunks, session.received_chunks)) {
      const slice = bytes.subarray(index * CHUNK_SIZE_BYTES, (index + 1) * CHUNK_SIZE_BYTES);
      const checksum = await sha256Hex(slice);
      const resp = await fetch(
        `${apiBaseUrl}/meetings/${meetingId}/uploads/${session.upload_session_id}/chunks/${index}`,
        {
          method: "PUT",
          headers: organisationHeaders(),
          body: JSON.stringify({
            data_base64: base64FromBytes(slice),
            sha256_checksum: checksum,
          }),
        }
      );
      if (resp.ok) {
        dispatchState((prev) =>
          transitionRecorderState(prev, { type: "CHUNK_UPLOADED", chunkIndex: index })
        );
      }
    }

    const complete = await fetch(
      `${apiBaseUrl}/meetings/${meetingId}/uploads/${session.upload_session_id}/complete`,
      { method: "POST", headers: organisationHeaders() }
    );
    if (complete.ok) {
      dispatchState((prev) => transitionRecorderState(prev, { type: "UPLOAD_FINALIZED" }));
      dispatchState((prev) => transitionRecorderState(prev, { type: "PROCESSING_SUCCEEDED" }));
      if (onSaved) {
        onSaved();
      }
    } else {
      const err = await complete.json();
      dispatchState((prev) =>
        transitionRecorderState(prev, {
          type: "PROCESSING_FAILED",
          errorMessage: err.error ? err.error.message : "Finalisation failed.",
        })
      );
    }
  }, [apiBaseUrl, chunks, meetingId, mediaRecorder, onSaved, organisationHeaders]);

  const statusLabel = useMemo(() => state.state.replace(/_/g, " "), [state.state]);

  return (
    <section aria-label="Meeting recorder" data-recording-state={state.state}>
      <h2>Recorder</h2>
      <p role="status">State: {statusLabel}</p>

      {state.state === RECORDER_STATES.NOTICE_PENDING ? (
        <div role="dialog" aria-label="Recording notice">
          <p>
            <strong>Recording notice:</strong> This meeting will be recorded. As the host,
            ensure all participants are informed and have consented as required by your
            jurisdiction and meeting context. Recording consent is separate from any
            voice-profile permission.
          </p>
          <button type="button" onClick={confirmNotice}>
            I confirm the notice — enable recorder
          </button>
        </div>
      ) : null}

      {state.noticeConfirmed && state.state === RECORDER_STATES.READY ? (
        <button type="button" onClick={startRecording}>
          Start recording
        </button>
      ) : null}

      {state.state === RECORDER_STATES.RECORDING ? (
        <>
          <p aria-live="polite">
            Recording… {(state.elapsedMs / 1000).toFixed(0)}s · input level{" "}
            {(state.inputLevel * 100).toFixed(0)}%
          </p>
          <button type="button" onClick={pauseRecording}>
            Pause
          </button>
          <button type="button" onClick={stopAndUpload}>
            Stop &amp; upload
          </button>
        </>
      ) : null}

      {state.state === RECORDER_STATES.PAUSED ? (
        <>
          <p aria-live="polite">Paused</p>
          <button type="button" onClick={resumeRecording}>
            Resume
          </button>
          <button type="button" onClick={stopAndUpload}>
            Stop &amp; upload
          </button>
        </>
      ) : null}

      {state.state === RECORDER_STATES.UPLOADING ? (
        <p aria-live="polite">
          Uploading {state.receivedChunks.length}/{state.totalChunks} chunks…
        </p>
      ) : null}

      {state.state === RECORDER_STATES.PROCESSING ? (
        <p aria-live="polite">Processing media…</p>
      ) : null}

      {state.state === RECORDER_STATES.SAVED ? (
        <p role="status">Recording saved and validated.</p>
      ) : null}

      {state.state === RECORDER_STATES.FAILED && state.errorMessage ? (
        <p role="alert" style={{ color: "#b00020" }}>
          {state.errorMessage}
        </p>
      ) : null}

      {warn ? (
        <p className="sr-only" data-unload-warning="true">
          Unsaved recording in progress — confirm before leaving this page.
        </p>
      ) : null}
    </section>
  );
}
