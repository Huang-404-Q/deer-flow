import { afterEach, describe, expect, it } from "@rstest/core";

import { getLocaleFromCookie } from "@/core/i18n/cookies";

afterEach(() => {
  document.cookie = "locale=; max-age=0; path=/";
});

describe("getLocaleFromCookie", () => {
  it("returns null for a malformed percent-encoded value", () => {
    document.cookie = "locale=%E0%A4%A; path=/";

    expect(getLocaleFromCookie()).toBeNull();
  });

  it("decodes a valid value", () => {
    document.cookie = "locale=zh-CN; path=/";

    expect(getLocaleFromCookie()).toBe("zh-CN");
  });
});
