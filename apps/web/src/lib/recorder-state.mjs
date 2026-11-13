/**
 * Browser Microphone Recorder & Resumable Upload State Machine
 * Implements Phase 2 UX & reliability requirements (`docs/product/UX_AND_ACCESSIBILITY.md`).
 */

export const RECORDER_STATES = Object.freeze({
  NOTICE_PENDING: "notice_pending",
  READY: "ready",
  RECORDING: "recording",
  PAUSED: "paused",
  UPLOADING: "uploading",
  PROCESSING: "processing",
  SAVED: "saved",
  FAILED: "failed",
});

export function createRecorderState(options = {}) {
  return {
    state: RECORDER_STATES.NOTICE_PENDING,
    noticeConfirmed: false,
    noticeVersion: null,
    selectedDeviceId: options.selectedDeviceId || "default",
    inputLevel: 0,
    elapsedMs: 0,
    totalChunks: 0,
    receivedChunks: [],
    errorMessage: null,
  };
}

export function transitionRecorderState(current, action) {
  switch (action.type) {
    case "CONFIRM_NOTICE": {
      if (!action.noticeVersion) {
        throw new Error("noticeVersion is required to confirm recording notice.");
      }
      return {
        ...current,
        state: RECORDER_STATES.READY,
        noticeConfirmed: true,
        noticeVersion: action.noticeVersion,
        errorMessage: null,
      };
    }
    case "SELECT_INPUT_DEVICE": {
      return {
        ...current,
        selectedDeviceId: action.deviceId || "default",
      };
    }
    case "START_RECORDING": {
      if (!current.noticeConfirmed) {
        throw new Error(
          "Recording notice and consent reminder must be confirmed before starting capture."
        );
      }
      if (
        current.state !== RECORDER_STATES.READY &&
        current.state !== RECORDER_STATES.FAILED
      ) {
        throw new Error(`Cannot start recording from state '${current.state}'.`);
      }
      return {
        ...current,
        state: RECORDER_STATES.RECORDING,
        errorMessage: null,
      };
    }
    case "PAUSE_RECORDING": {
      if (current.state !== RECORDER_STATES.RECORDING) {
        throw new Error("Can only pause an active recording.");
      }
      return {
        ...current,
        state: RECORDER_STATES.PAUSED,
        inputLevel: 0,
      };
    }
    case "RESUME_RECORDING": {
      if (current.state !== RECORDER_STATES.PAUSED) {
        throw new Error("Can only resume from a paused recording.");
      }
      return {
        ...current,
        state: RECORDER_STATES.RECORDING,
      };
    }
    case "TICK": {
      if (current.state !== RECORDER_STATES.RECORDING) {
        return current;
      }
      const clampedLevel = Math.max(0, Math.min(1, Number(action.inputLevel ?? 0)));
      return {
        ...current,
        elapsedMs: current.elapsedMs + Math.max(0, Number(action.deltaMs ?? 0)),
        inputLevel: clampedLevel,
      };
    }
    case "STOP_AND_UPLOAD": {
      if (
        current.state !== RECORDER_STATES.RECORDING &&
        current.state !== RECORDER_STATES.PAUSED
      ) {
        throw new Error("Cannot stop recording when not recording or paused.");
      }
      return {
        ...current,
        state: RECORDER_STATES.UPLOADING,
        inputLevel: 0,
        totalChunks: Math.max(1, Number(action.totalChunks ?? 1)),
        receivedChunks: [],
      };
    }
    case "CHUNK_UPLOADED": {
      const updated = Array.from(
        new Set([...current.receivedChunks, action.chunkIndex])
      ).sort((a, b) => a - b);
      return {
        ...current,
        receivedChunks: updated,
      };
    }
    case "UPLOAD_FINALIZED": {
      return {
        ...current,
        state: RECORDER_STATES.PROCESSING,
      };
    }
    case "PROCESSING_SUCCEEDED": {
      return {
        ...current,
        state: RECORDER_STATES.SAVED,
        errorMessage: null,
      };
    }
    case "PROCESSING_FAILED": {
      return {
        ...current,
        state: RECORDER_STATES.FAILED,
        errorMessage: action.errorMessage || "Upload or media processing failed.",
      };
    }
    default:
      return current;
  }
}

/**
 * Warns user before navigating away if recording or upload is in progress.
 */
export function shouldWarnBeforeUnload(recorderState) {
  return [
    RECORDER_STATES.RECORDING,
    RECORDER_STATES.PAUSED,
    RECORDER_STATES.UPLOADING,
  ].includes(recorderState.state);
}

/**
 * Computes which chunk indices still need to be uploaded after a network interruption.
 */
export function computeMissingChunkIndices(totalChunks, receivedChunks = []) {
  const receivedSet = new Set(receivedChunks);
  const missing = [];
  for (let i = 0; i < totalChunks; i += 1) {
    if (!receivedSet.has(i)) {
      missing.push(i);
    }
  }
  return missing;
}
