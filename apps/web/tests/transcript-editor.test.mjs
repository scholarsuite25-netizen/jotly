import assert from "node:assert/strict";
import test from "node:test";
import { createTranscriptEditorState, transitionEditorState, decorateSpeakerForDisplay, EDITOR_STATES } from "../src/lib/transcript-editor.mjs";

const SEGMENTS = [
  {
    id: "seg-1",
    sequenceNumber: 0,
    startMs: 0,
    endMs: 2500,
    originalAsrText: "Good morning everyone.",
    currentText: "Good morning everyone.",
    confidence: 0.96,
    edited: false,
  },
  {
    id: "seg-2",
    sequenceNumber: 1,
    startMs: 2500,
    endMs: 5000,
    originalAsrText: "Sarah will lead the follow-up.",
    currentText: "Sarah will lead the follow-up.",
    confidence: 0.93,
    edited: false,
  },
];

test("Transcript editor applies human edit, tracks undo stack, and records immutable revisions", () => {
  let state = { ...createTranscriptEditorState(), segments: SEGMENTS };

  state = transitionEditorState(state, { type: "APPLY_EDIT", sequenceNumber: 0, newText: "Good afternoon everyone.", revisionNumber: 2 });
  assert.equal(state.segments[0].currentText, "Good afternoon everyone.");
  assert.equal(state.segments[0].edited, true);
  assert.equal(state.segments[0].originalAsrText, "Good morning everyone.");
  assert.equal(state.revisionHistory.length, 1);
  assert.equal(state.revisionHistory[0].changeType, "human_edit");

  state = transitionEditorState(state, { type: "UNDO_LAST_EDIT" });
  assert.equal(state.segments[0].currentText, "Good morning everyone.");
  assert.equal(state.segments[0].edited, false);
  assert.equal(state.undoStack.length, 0);

  assert.throws(
    () => transitionEditorState(state, { type: "UNDO_LAST_EDIT" }),
    /No edits to undo/
  );
});

test("Find/replace preview lists affected segments and apply updates text while preserving original ASR", () => {
  let state = { ...createTranscriptEditorState(), segments: SEGMENTS };

  state = transitionEditorState(state, { type: "PREVIEW_FIND_REPLACE", findText: "Sarah", replaceText: "Maya" });
  assert.deepEqual(state.findReplacePreview.affectedSequenceNumbers, [1]);
  assert.equal(state.state, EDITOR_STATES.PREVIEWING);

  state = transitionEditorState(state, { type: "APPLY_FIND_REPLACE", findText: "Sarah", replaceText: "Maya" });
  assert.equal(state.segments[1].currentText, "Maya will lead the follow-up.");
  assert.equal(state.segments[1].originalAsrText, "Sarah will lead the follow-up.");
  assert.equal(state.segments[1].edited, true);
});

test("Diarisation speakers are always model suggestions and never identity-verified", () => {
  const decorated = decorateSpeakerForDisplay({
    displayName: "Speaker 01",
    isModelSuggestion: true,
    identityVerified: true,
  });
  assert.equal(decorated.identityVerified, false);
  assert.equal(decorated.displayLabel, "Suggested: Speaker 01");

  assert.equal(decorateSpeakerForDisplay(null), null);
});
