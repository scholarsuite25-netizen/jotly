/**
 * Transcript Editor State Machine (Phase 3)
 * Human editing, find/replace preview, undo stack, and immutable revision tracking.
 */

export const EDITOR_STATES = Object.freeze({
  IDLE: "idle",
  EDITING: "editing",
  PREVIEWING: "previewing",
  UNDOING: "undoing",
  SAVED: "saved",
  ERROR: "error",
});

export function createTranscriptEditorState() {
  return {
    state: EDITOR_STATES.IDLE,
    segments: [],
    revisionHistory: [],
    undoStack: [],
    errorMessage: null,
  };
}

export function transitionEditorState(current, action) {
  switch (action.type) {
    case "LOAD_TRANSCRIPT": {
      if (!Array.isArray(action.segments)) {
        throw new Error("LOAD_TRANSCRIPT requires a segments array.");
      }
      return {
        ...current,
        state: EDITOR_STATES.IDLE,
        segments: action.segments.map((seg) => ({ ...seg })),
        revisionHistory: Array.isArray(action.revisions)
          ? [...action.revisions]
          : [],
        undoStack: [],
        errorMessage: null,
      };
    }
    case "BEGIN_EDIT": {
      const seg = current.segments[action.sequenceNumber];
      if (!seg) {
        throw new Error(`Segment at sequence ${action.sequenceNumber} not found.`);
      }
      const nextSegments = [...current.segments];
      nextSegments[action.sequenceNumber] = { ...seg, editing: true };
      return { ...current, state: EDITOR_STATES.EDITING, segments: nextSegments };
    }
    case "APPLY_EDIT": {
      const seg = current.segments[action.sequenceNumber];
      if (!seg) {
        throw new Error(`Segment at sequence ${action.sequenceNumber} not found.`);
      }
      const nextSegments = [...current.segments];
      nextSegments[action.sequenceNumber] = {
        ...seg,
        currentText: action.newText,
        edited: true,
        editing: false,
      };
      return {
        ...current,
        state: EDITOR_STATES.SAVED,
        segments: nextSegments,
        undoStack: [
          ...current.undoStack,
          { sequenceNumber: action.sequenceNumber, previousText: seg.currentText },
        ],
        revisionHistory: [
          ...current.revisionHistory,
          {
            revisionNumber: action.revisionNumber ?? current.revisionHistory.length + 1,
            segmentId: seg.id,
            changeType: "human_edit",
            previousText: seg.currentText,
            newText: action.newText,
          },
        ],
        errorMessage: null,
      };
    }
    case "UNDO_LAST_EDIT": {
      if (current.undoStack.length === 0) {
        throw new Error("No edits to undo.");
      }
      const last = current.undoStack[current.undoStack.length - 1];
      const nextSegments = [...current.segments];
      const seg = nextSegments[last.sequenceNumber];
      nextSegments[last.sequenceNumber] = {
        ...seg,
        currentText: last.previousText,
        edited: last.previousText !== seg.originalAsrText,
        editing: false,
      };
      return {
        ...current,
        state: EDITOR_STATES.SAVED,
        segments: nextSegments,
        undoStack: current.undoStack.slice(0, -1),
        errorMessage: null,
      };
    }
    case "PREVIEW_FIND_REPLACE": {
      const affected = current.segments
        .map((seg, idx) => ({ seg, idx }))
        .filter(({ seg }) => seg.currentText.includes(action.findText));
      return {
        ...current,
        state: EDITOR_STATES.PREVIEWING,
        findReplacePreview: {
          findText: action.findText,
          replaceText: action.replaceText,
          affectedSequenceNumbers: affected.map(({ idx }) => idx),
        },
      };
    }
    case "APPLY_FIND_REPLACE": {
      const { findText, replaceText } = action;
      if (!findText) {
        throw new Error("findText is required.");
      }
      const nextSegments = current.segments.map((seg) => ({
        ...seg,
        currentText: seg.currentText.split(findText).join(replaceText),
        edited: seg.currentText.split(findText).join(replaceText) !== seg.originalAsrText,
      }));
      return {
        ...current,
        state: EDITOR_STATES.SAVED,
        segments: nextSegments,
        findReplacePreview: null,
        errorMessage: null,
      };
    }
    default:
      return current;
  }
}

/**
 * Diarisation speakers are ALWAYS presented as model suggestions, never verified identity.
 */
export function decorateSpeakerForDisplay(speaker) {
  if (!speaker) {
    return null;
  }
  return {
    ...speaker,
    displayLabel: speaker.isModelSuggestion
      ? `Suggested: ${speaker.displayName}`
      : speaker.displayName,
    identityVerified: false,
  };
}
