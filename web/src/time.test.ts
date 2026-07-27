import { describe, expect, it } from "vitest";

import { formatChinaTime, isoToChinaInput, parseBackendTime } from "./time";

describe("backend time parsing", () => {
  it("treats timezone-less backend timestamps as UTC", () => {
    expect(parseBackendTime("2026-07-27T13:32:15").toISOString())
      .toBe("2026-07-27T13:32:15.000Z");
    expect(formatChinaTime("2026-07-27T13:32:15")).toContain("21:32:15");
    expect(isoToChinaInput("2026-07-27T13:32:15")).toBe("2026-07-27T21:32");
  });

  it("preserves timestamps that already include a timezone", () => {
    expect(parseBackendTime("2026-07-27T13:32:15+08:00").toISOString())
      .toBe("2026-07-27T05:32:15.000Z");
  });
});
