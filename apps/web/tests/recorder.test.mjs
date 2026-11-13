import assert from "node:assert/strict";
import test from "node:test";
import {
  RECORDER_STATES,
  computeMissingChunkIndices,
  createRecorderState,
  shouldWarnBeforeUnload,
  transitionRecorderState,
} from "../src/lib/recorder-state.mjs";

test("Recorder blocks start before notice confirmation and transitions through start/pause/resume/stop/upload/saved", () => {
  let state = createRecorderState({ selectedDeviceId: "mic-usb-1" });
  assert.equal(state.state, RECORDER_STATES.NOTICE_PENDING);
  assert.equal(shouldWarnBeforeUnload(state), false);

  assert.throws(
    () => transitionRecorderState(state, { type: "START_RECORDING" }),
    /Recording notice and consent reminder must be confirmed/
  );

  state = transitionRecorderState(state, {
    type: "CONFIRM_NOTICE",
    noticeVersion: "2026-11-v1",
  });
  assert.equal(state.state, RECORDER_STATES.READY);
  assert.equal(state.noticeConfirmed, true);

  state = transitionRecorderState(state, { type: "START_RECORDING" });
  assert.equal(state.state, RECORDER_STATES.RECORDING);
  assert.equal(shouldWarnBeforeUnload(state), true);

  state = transitionRecorderState(state, {
    type: "TICK",
    deltaMs: 5000,
    inputLevel: 0.75,
  });
  assert.equal(state.elapsedMs, 5000);
  assert.equal(state.inputLevel, 0.75);

  state = transitionRecorderState(state, { type: "PAUSE_RECORDING" });
  assert.equal(state.state, RECORDER_STATES.PAUSED);
  assert.equal(state.inputLevel, 0);
  assert.equal(shouldWarnBeforeUnload(state), true);

  state = transitionRecorderState(state, { type: "RESUME_RECORDING" });
  assert.equal(state.state, RECORDER_STATES.RECORDING);

  state = transitionRecorderState(state, {
    type: "STOP_AND_UPLOAD",
    totalChunks: 3,
  });
  assert.equal(state.state, RECORDER_STATES.UPLOADING);
  assert.equal(shouldWarnBeforeUnload(state), true);

  state = transitionRecorderState(state, {
    type: "CHUNK_UPLOADED",
    chunkIndex: 0,
  });
  assert.deepEqual(
    computeMissingChunkIndices(state.totalChunks, state.receivedChunks),
    [1, 2]
  );

  state = transitionRecorderState(state, { type: "UPLOAD_FINALIZED" });
  assert.equal(state.state, RECORDER_STATES.PROCESSING);

  state = transitionRecorderState(state, { type: "PROCESSING_SUCCEEDED" });
  assert.equal(state.state, RECORDER_STATES.SAVED);
  assert.equal(shouldWarnBeforeUnload(state), false);
});
