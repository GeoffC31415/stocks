import type {} from "vitest/jsdom";
import { expect, test, vi } from "vitest";
import { state } from "./fixture";

// Runtime-only diagnostic; keep Node type packages out of the browser project.
const workerModule: string = "node:worker_threads";
const { threadId } = await import(/* @vite-ignore */ workerModule) as { threadId: number };
const { pid } = (globalThis as unknown as { process: { pid: number } }).process;

const marker = "__stocks_file_isolation__";

// Both files check pristine state, then deliberately leave it dirty. Do not add
// cleanup: that would hide leaks. test:isolation checks a single-worker run;
// override --pool=vmThreads to probe VM reuse. The pid/thread trace distinguishes
// shared workers from fresh forked processes.
export function isolationGuards(file: string) {
  console.info(`isolation-guard file=${file} pid=${pid} thread=${threadId}`);

  test("globals start fresh across files", () => {
    const scope = globalThis as unknown as Record<string, unknown>;
    expect(scope[marker]).toBeUndefined();
    scope[marker] = file;
  });

  test("window starts fresh across files", () => {
    const scope = window as unknown as Record<string, unknown>;
    expect(scope[`${marker}_window`]).toBeUndefined();
    scope[`${marker}_window`] = file;
  });

  test("localStorage starts fresh across files", () => {
    // Use the browser's storage, not Node 25's unrelated native global shim.
    const storage = jsdom.window.localStorage;
    expect(storage.getItem(marker)).toBeNull();
    storage.setItem(marker, file);
  });

  test("module-local state starts fresh across files", () => {
    expect(state.visits).toBe(0);
    state.visits++;
  });

  test("module mocks start fresh across files", async () => {
    const original = await import("./fixture");
    expect(original.identity()).toBe("real");
    expect(vi.isMockFunction(original.identity)).toBe(false);
    vi.doMock("./fixture", () => ({ state: { visits: -1 }, identity: vi.fn(() => file) }));
    const mocked = await import("./fixture");
    expect(vi.isMockFunction(mocked.identity)).toBe(true);
    expect(mocked.identity()).toBe(file);
  });
}
