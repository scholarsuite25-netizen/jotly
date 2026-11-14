"use client";

import { useCallback, useMemo, useState } from "react";
import {
  decorateSpeakerForDisplay,
  transitionEditorState,
} from "@/lib/transcript-editor.mjs";

/**
 * Transcript editor screen: segment editing with revision history, undo,
 * find/replace, and speaker relabel. Diarisation labels always render as
 * model suggestions (never verified identity), per the tested lib contract.
 */
export default function TranscriptEditorScreen({
  transcript,
  apiBaseUrl,
  organisationHeaders,
  onRefresh,
}) {
  const [state, dispatchState] = useState(() => ({
    state: "idle",
    segments: (transcript.segments || []).map((seg) => ({ ...seg })),
    undoStack: [],
    errorMessage: null,
    findText: "",
    replaceText: "",
  }));

  const segments = state.segments;

  const saveSegment = useCallback(
    async (segmentId, newText) => {
      const resp = await fetch(
        `${apiBaseUrl}/transcripts/${transcript.id}/segments/${segmentId}`,
        {
          method: "PATCH",
          headers: organisationHeaders(),
          body: JSON.stringify({ new_text: newText }),
        }
      );
      const body = await resp.json();
      if (resp.ok) {
        if (onRefresh) onRefresh();
      } else if (body.error) {
        dispatchState((prev) => ({ ...prev, errorMessage: body.error.message }));
      }
    },
    [apiBaseUrl, organisationHeaders, onRefresh, transcript.id]
  );

  const undoSegment = useCallback(
    async (segmentId) => {
      const resp = await fetch(
        `${apiBaseUrl}/transcripts/${transcript.id}/segments/${segmentId}/undo`,
        { method: "POST", headers: organisationHeaders() }
      );
      if (resp.ok && onRefresh) onRefresh();
    },
    [apiBaseUrl, organisationHeaders, onRefresh, transcript.id]
  );

  const runFindReplace = useCallback(async () => {
    const resp = await fetch(
      `${apiBaseUrl}/transcripts/${transcript.id}/find-replace`,
      {
        method: "POST",
        headers: organisationHeaders(),
        body: JSON.stringify({
          find_text: state.findText,
          replace_text: state.replaceText,
        }),
      }
    );
    const body = await resp.json();
    if (resp.ok) {
      dispatchState((prev) => ({
        ...prev,
        segments: prev.segments.map((seg) => ({
          ...seg,
          current_text: seg.current_text
            .split(state.findText)
            .join(state.replaceText),
        })),
        findText: "",
        replaceText: "",
      }));
      if (onRefresh) onRefresh();
    } else if (body.error) {
      dispatchState((prev) => ({ ...prev, errorMessage: body.error.message }));
    }
  }, [apiBaseUrl, organisationHeaders, onRefresh, state.findText, state.replaceText, transcript.id]);

  const relabelSpeaker = useCallback(
    async (speakerId, displayName) => {
      const resp = await fetch(
        `${apiBaseUrl}/transcripts/${transcript.id}/speakers/${speakerId}/relabel`,
        {
          method: "POST",
          headers: organisationHeaders(),
          body: JSON.stringify({ display_name: displayName }),
        }
      );
      if (resp.ok && onRefresh) onRefresh();
    },
    [apiBaseUrl, organisationHeaders, onRefresh, transcript.id]
  );

  const exportOptions = useMemo(
    () => [
      { format: "txt", label: "Export TXT" },
      { format: "srt", label: "Export SRT" },
      { format: "vtt", label: "Export VTT" },
    ],
    []
  );

  const exportTranscript = useCallback(
    async (format) => {
      const resp = await fetch(
        `${apiBaseUrl}/transcripts/${transcript.id}/exports`,
        {
          method: "POST",
          headers: organisationHeaders(),
          body: JSON.stringify({ format }),
        }
      );
      if (resp.ok) {
        const body = await resp.json();
        const blob = new Blob([body.content || ""], { type: "text/plain" });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `transcript-${transcript.id}.${format}`;
        anchor.click();
        URL.revokeObjectURL(url);
      }
    },
    [apiBaseUrl, organisationHeaders, transcript.id]
  );

  return (
    <section aria-label="Transcript editor">
      <h2>Transcript</h2>
      <p>
        Detected language: {transcript.detected_language} · ASR model:{" "}
        {transcript.asr_model_id} · AI output and human edits are tracked separately.
      </p>

      <div aria-label="Find and replace">
        <label htmlFor="find-text">Find</label>
        <input
          id="find-text"
          value={state.findText}
          onChange={(e) =>
            dispatchState((prev) => ({ ...prev, findText: e.target.value }))
          }
        />
        <label htmlFor="replace-text">Replace with</label>
        <input
          id="replace-text"
          value={state.replaceText}
          onChange={(e) =>
            dispatchState((prev) => ({ ...prev, replaceText: e.target.value }))
          }
        />
        <button type="button" onClick={runFindReplace} disabled={!state.findText}>
          Replace all
        </button>
      </div>

      <ol aria-label="Transcript segments">
        {segments.map((seg) => (
          <li key={seg.id} data-segment-id={seg.id}>
            <span className="timestamp">
              {(seg.start_ms / 1000).toFixed(1)}s → {(seg.end_ms / 1000).toFixed(1)}s
            </span>{" "}
            {seg.speaker_id ? (
              <button
                type="button"
                title="Click to relabel this speaker"
                onClick={() => {
                  const name = window.prompt("New speaker label", seg.speaker_display_name || "");
                  if (name) relabelSpeaker(seg.speaker_id, name);
                }}
              >
                {decorateSpeakerForDisplay({
                  displayName: seg.speaker_display_name || "Unknown",
                  isModelSuggestion: seg.speaker_is_model_suggestion,
                }).displayLabel}
              </button>
            ) : null}{" "}
            <SegmentTextInput
              initialValue={seg.current_text}
              originalText={seg.original_asr_text}
              edited={seg.is_edited}
              onSave={(newText) => saveSegment(seg.id, newText)}
              onUndo={() => undoSegment(seg.id)}
            />
            {seg.is_edited ? <em> (edited — original ASR text preserved)</em> : null}
          </li>
        ))}
      </ol>

      <fieldset aria-label="Exports">
        <legend>Exports</legend>
        {exportOptions.map((opt) => (
          <button key={opt.format} type="button" onClick={() => exportTranscript(opt.format)}>
            {opt.label}
          </button>
        ))}
      </fieldset>

      {state.errorMessage ? (
        <p role="alert" style={{ color: "#b00020" }}>
          {state.errorMessage}
        </p>
      ) : null}
    </section>
  );
}

function SegmentTextInput({ initialValue, originalText, edited, onSave, onUndo }) {
  const [value, setValue] = useState(initialValue);
  return (
    <span>
      <input
        aria-label="Segment text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => {
          if (value !== initialValue) onSave(value);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && value !== initialValue) {
            onSave(value);
          }
        }}
      />
      {edited ? (
        <button type="button" onClick={onUndo} title={`Restore previous revision (original ASR: ${originalText})`}>
          Undo
        </button>
      ) : null}
    </span>
  );
}
