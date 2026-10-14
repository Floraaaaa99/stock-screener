import { describe, expect, it } from "vitest";
import {
  fiscalLabel,
  formatCompactMoney,
  formatDate,
  formatMillions,
  formatNasdaqFileTime,
  formatPercent,
  formatPrice,
} from "./format";

describe("missing values render as N/A, never zero", () => {
  it.each([null, undefined, Number.NaN])("%s", (v) => {
    expect(formatCompactMoney(v)).toBe("N/A");
    expect(formatMillions(v)).toBe("N/A");
    expect(formatPrice(v)).toBe("N/A");
    expect(formatPercent(v)).toBe("N/A");
  });
  it("dates and fiscal labels", () => {
    expect(formatDate(null)).toBe("N/A");
    expect(formatDate("not a date")).toBe("N/A");
    expect(fiscalLabel(null, 3)).toBe("N/A");
  });
});

describe("formatCompactMoney", () => {
  it("scales to T/B/M/K", () => {
    expect(formatCompactMoney(1.234e12)).toBe("$1.23T");
    expect(formatCompactMoney(123.45e9)).toBe("$123.5B");
    expect(formatCompactMoney(12_587_200_000)).toBe("$12.59B");
    expect(formatCompactMoney(-1_917_000)).toBe("−$1.92M");
    expect(formatCompactMoney(0)).toBe("$0");
  });
  it("labels non-USD currencies", () => {
    expect(formatCompactMoney(2.5e9, "EUR")).toBe("€2.50B EUR");
    expect(formatCompactMoney(2.5e9, "DKK")).toBe("2.50B DKK");
  });
});

describe("formatMillions", () => {
  it("shows full precision in millions", () => {
    expect(formatMillions(1_167_175_000)).toBe("$1,167.2M");
    expect(formatMillions(166_496_000)).toBe("$166.5M");
    expect(formatMillions(-1_917_000)).toBe("−$1.917M");
  });
});

describe("other formats", () => {
  it("formats prices, percentages, dates", () => {
    expect(formatPrice(1234.5)).toBe("$1,234.50");
    expect(formatPercent(10.2345)).toBe("+10.2%");
    expect(formatPercent(-4.04)).toBe("−4.0%");
    expect(formatPercent(0)).toBe("0.0%");
    expect(formatDate("2025-06-30")).toBe("Jun 30, 2025");
    expect(fiscalLabel(2026, 1)).toBe("FY2026 Q1");
  });
  it("parses NASDAQ Trader file creation times", () => {
    expect(formatNasdaqFileTime("1013202618:01")).toBe("Oct 13, 2026 18:01 ET");
    expect(formatNasdaqFileTime("garbage")).toBe("garbage");
  });
});
