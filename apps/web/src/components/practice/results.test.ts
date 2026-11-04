import { describe, expect, it } from "vitest";

import type { Job } from "@/lib/types";

import { displayState } from "./results";

const base: Job = {
  id: "j", status: "completed", exit_reason: "all_passed", passed: 3, total: 3, score: 1, error_type: null,
  edge_cases_passed: 1, edge_cases_total: 1, duration_ms: 500, max_test_ms: 2, submission_id: "s",
  exercise_id: "e", kind: "submit", mode: "practice", memory_limit_mb: 256, time_budget_s: 5, results: [],
  run_output: null,
};

describe("displayState", () => {
  it.each([
    [{ status: "queued" }, "queued"],
    [{ status: "running" }, "running"],
    [{ status: "cancelled" }, "cancelled"],
    [{ status: "timed_out" }, "timeout"],
    [{ status: "failed", exit_reason: "memory_limit" }, "memory"],
    [{ status: "failed", exit_reason: "runner_unavailable" }, "runner_failed"],
    [{}, "passed"],
    [{ passed: 2 }, "partial"],
    [{ passed: 0 }, "failed"],
    [{ kind: "run", total: 0, passed: 0, exit_reason: "ran" }, "ran"],
    [{ kind: "run", total: 0, passed: 0, exit_reason: "NameError" }, "ran_error"],
  ] as [Partial<Job>, string][])("%o -> %s", (patch, expected) => {
    expect(displayState({ ...base, ...patch })).toBe(expected);
  });

  it("empty without a job", () => {
    expect(displayState(null)).toBe("empty");
  });
});
