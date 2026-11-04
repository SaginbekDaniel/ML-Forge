import { describe, expect, it } from "vitest";

import { en } from "./en";
import { translate } from "./index";
import { ru } from "./ru";

describe("i18n", () => {
  it("en has exactly the same keys as ru", () => {
    expect(Object.keys(en).sort()).toEqual(Object.keys(ru).sort());
  });

  it("every placeholder in ru exists in en", () => {
    const vars = (s: string) => (s.match(/\{(\w+)\}/g) ?? []).sort();
    for (const key of Object.keys(ru) as (keyof typeof ru)[]) {
      expect(vars(en[key]), key).toEqual(vars(ru[key]));
    }
  });

  it("interpolates and keeps unknown placeholders visible", () => {
    expect(translate("ru", "results.partial", { passed: 3, total: 5 })).toBe("Пройдено 3 из 5");
    expect(translate("en", "results.partial", { passed: 3 })).toBe("Passed 3 of {total}");
  });

  it("has no empty translations", () => {
    for (const [k, v] of Object.entries(en)) expect(v.trim(), k).not.toBe("");
    for (const [k, v] of Object.entries(ru)) expect(v.trim(), k).not.toBe("");
  });
});
