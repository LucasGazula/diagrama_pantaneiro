import { describe, expect, it } from "vitest";
import { formatLastUpdated } from "../../src/lib/format";

describe("formatLastUpdated", () => {
  it("returns dash for null/undefined/invalid", () => {
    expect(formatLastUpdated(null)).toBe("—");
    expect(formatLastUpdated(undefined)).toBe("—");
    expect(formatLastUpdated("invalid")).toBe("—");
  });

  it("formats today timestamp as 'hoje às HH:mm'", () => {
    const now = new Date();
    const result = formatLastUpdated(now.toISOString());
    expect(result).toMatch(/^hoje às \d{2}:\d{2}$/);
  });

  it("formats yesterday timestamp as 'ontem às HH:mm'", () => {
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    const result = formatLastUpdated(yesterday.toISOString());
    expect(result).toMatch(/^ontem às \d{2}:\d{2}$/);
  });
});
