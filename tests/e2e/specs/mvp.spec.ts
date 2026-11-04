/**
 * MVP E2E scenarios (spec §15.2) against the REAL stack: Next.js UI, FastAPI,
 * embedded worker and the Docker sandbox. No mocks, no fixtures in the app path.
 * Scenarios run in order because they share one learner and one database.
 */
import { expect, test, type Page } from "@playwright/test";

import { startApi, stopApi } from "../servers";

const SUM_TWO_WRONG = "a = input()\nb = input()\nprint(a + b)\n";
const SUM_TWO_RIGHT = "a = int(input())\nb = int(input())\nprint(a + b)\n";
const GREETING_RIGHT = 'name = input()\nprint(f"Привет, {name.strip()}!")\n';
const DURATION_RIGHT = 'def format_duration(minutes):\n    h, m = divmod(minutes, 60)\n    return f"{h} ч {m:02d} мин"\n';
const COUNT_EVEN_RIGHT = "def count_even(nums):\n    return sum(1 for n in nums if n % 2 == 0)\n";

async function setCode(page: Page, code: string) {
  const editor = page.locator(".cm-content");
  await editor.click();
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.press("Delete");
  await page.keyboard.insertText(code);
  await expect(page.locator(".cm-content")).toContainText(code.split("\n")[0]!);
}

async function submitAndWait(page: Page, state: string | RegExp) {
  await page.getByRole("button", { name: "Проверить", exact: true }).click();
  await expect(page.getByTestId("job-summary")).toHaveAttribute("data-state", state, { timeout: 40_000 });
}

test.describe.serial("ML Forge MVP", () => {
  test("1. clean DB -> profile -> diagnostic -> roadmap", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/onboarding$/);
    await page.getByLabel("Как вас называть").fill("E2E Learner");
    await page.getByRole("button", { name: "Создать профиль" }).click();
    await expect(page.getByRole("heading", { name: "Стартовая диагностика" })).toBeVisible();

    await page.getByText("Уверенно").first().click();
    const predict = page.getByPlaceholder("Что напечатает программа?");
    await predict.first().fill("33 7");
    await predict.first().blur();
    await page.getByRole("link", { name: "Открыть задачу" }).click();
    await expect(page).toHaveURL(/\/practice\/diag\.count_even\?mode=diagnostic/);
    await expect(page.getByRole("tab", { name: /Подсказки/ })).toHaveCount(0); // no hints in diagnostic
    await setCode(page, COUNT_EVEN_RIGHT);
    await submitAndWait(page, "passed");
    await page.getByRole("link", { name: "Вернуться к диагностике" }).click();
    await page.getByRole("button", { name: "Завершить диагностику" }).click();
    await expect(page.getByRole("heading", { name: "Результат диагностики" })).toBeVisible();
    await expect(page.getByText(/Задача отправлена: 4 из 4/)).toBeVisible();
    await page.getByRole("link", { name: "Перейти к программе" }).click();
    await expect(page).toHaveURL(/\/roadmap$/);
    await expect(page.getByRole("link", { name: "Ввод/вывод и типы данных" })).toBeVisible();
  });

  test("2. open topic -> read lesson -> open exercise", async ({ page }) => {
    await page.goto("/roadmap");
    await page.getByRole("link", { name: /^Урок/ }).first().click();
    await expect(page.getByRole("heading", { name: "Ввод, вывод и типы данных" })).toBeVisible();
    await expect(page.getByText("Примеры проверены запуском")).toBeVisible();
    const q1 = page.locator("#check-q1");
    await q1.fill("555");
    await q1.press("Enter");
    await expect(page.getByText("Верно", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Отметить урок прочитанным" }).click();
    await expect(page.getByText("Урок прочитан")).toBeVisible();
    await page.getByRole("link", { name: "Сумма двух чисел" }).click();
    await expect(page.getByRole("heading", { name: "Сумма двух чисел" })).toBeVisible();
  });

  test("3. wrong solution -> real failing tests (hidden inputs not shown)", async ({ page }) => {
    await page.goto("/practice/io.sum_two");
    await setCode(page, SUM_TWO_WRONG);
    await submitAndWait(page, "failed");
    const results = page.getByTestId("test-result");
    await expect(results).toHaveCount(5);
    await expect(page.locator('[data-testid=test-result][data-passed=false][data-visibility=public]').first()).toContainText("23");
    const hidden = page.locator("[data-testid=test-result][data-visibility=hidden]");
    await expect(hidden.first()).toContainText("скрытый тест");
    await expect(hidden.first().getByText("Вход")).toHaveCount(0);
  });

  test("4. fix -> pass -> attempt and evidence recorded", async ({ page }) => {
    await page.goto("/practice/io.sum_two");
    await setCode(page, SUM_TWO_RIGHT);
    await submitAndWait(page, "passed");
    await expect(page.getByText("Засчитано как доказательство навыка")).toBeVisible();
    await page.getByRole("tab", { name: "Попытки" }).click();
    await expect(page.getByTestId("attempts").locator("li")).toHaveCount(2);
    await page.goto("/skills/python.io_types");
    await expect(page.getByText("io.sum_two").first()).toBeVisible();
    await expect(page.getByText("100% тестов").first()).toBeVisible();
  });

  test("5. reload keeps draft and progress", async ({ page }) => {
    await page.goto("/practice/io.celsius");
    await setCode(page, "# draft-marker-42\ndef celsius_to_fahrenheit(c):\n    return 0\n");
    await expect(page.getByTestId("draft-status")).toHaveText("Черновик сохранён");
    await page.reload();
    await expect(page.locator(".cm-content")).toContainText("draft-marker-42");
    await page.goto("/");
    await expect(page.getByText("io.sum_two").first()).toBeVisible();
  });

  test("6. API restart keeps progress", async ({ page }) => {
    await stopApi();
    await startApi();
    await page.goto("/skills/python.io_types");
    await expect(page.getByText("100% тестов").first()).toBeVisible();
    await page.goto("/practice/io.celsius");
    await expect(page.locator(".cm-content")).toContainText("draft-marker-42");
  });

  test("7. infinite loop -> timeout, UI stays responsive", async ({ page }) => {
    await page.goto("/practice/io.celsius");
    await setCode(page, "def celsius_to_fahrenheit(c):\n    while True:\n        pass\n");
    await page.getByRole("button", { name: "Проверить", exact: true }).click();
    await expect(page.getByTestId("job-summary")).toHaveAttribute("data-state", /queued|running/);
    // the rest of the UI keeps working while the sandbox runs
    await page.getByRole("tab", { name: "Консоль" }).click();
    await page.getByRole("tab", { name: /Подсказки/ }).click();
    await expect(page.getByTestId("hints")).toBeVisible();
    await expect(page.getByTestId("job-summary")).toHaveAttribute("data-state", "timeout", { timeout: 40_000 });
    await expect(page.getByText(/Превышено время выполнения/)).toBeVisible();
  });

  test("8. AI without key -> clear message, exercises still work", async ({ page }) => {
    await page.goto("/practice/io.greeting");
    await page.getByRole("tab", { name: "Наставник" }).click();
    await page.getByLabel("AI-наставник").fill("Почему тест падает?");
    await page.getByRole("button", { name: "Спросить" }).click();
    await expect(page.getByTestId("mentor").getByRole("alert")).toContainText("AI-наставник не настроен");
    await setCode(page, GREETING_RIGHT);
    await submitAndWait(page, "passed");
  });

  test("9. hidden tests and solutions cannot be fetched through the API", async ({ page }) => {
    const r = await page.request.get("/api/v1/exercises/io.celsius");
    const body = await r.text();
    expect(r.ok()).toBeTruthy();
    expect(body).not.toContain("celsius_to_fahrenheit(-40)"); // hidden test input
    expect(body).not.toContain("return c * 9 / 5 + 32"); // reference solution
    expect(body).not.toContain("wrong_solutions");
    const assessment = await page.request.get("/api/v1/exercises/io.duration");
    expect(assessment.status()).toBe(403);
    for (const p of ["/api/v1/exercises/io.celsius/tests", "/api/v1/exercises/io.celsius/solution"]) {
      expect((await page.request.get(p)).status()).toBe(404);
    }
  });

  test("10. independent assessment: no hints, unlock only by the rules", async ({ page }) => {
    await page.goto("/roadmap");
    const cond = page.locator("li", { hasText: "python.conditionals" });
    await expect(cond.getByText("Закрыто")).toBeVisible(); // 2 tasks solved, assessment not yet passed

    await page.goto("/assessment/python.io_types");
    await page.getByRole("button", { name: "Начать проверку" }).click();
    await expect(page).toHaveURL(/mode=independent/);
    await expect(page.getByText("Независимая проверка").first()).toBeVisible();
    await expect(page.getByRole("tab", { name: /Подсказки/ })).toHaveCount(0);
    await expect(page.getByRole("tab", { name: "Наставник" })).toHaveCount(0);
    const exerciseId = new URL(page.url()).pathname.split("/").pop()!;
    const hint = await page.request.post(`/api/v1/exercises/${exerciseId}/hint`, { data: { level: 1 } });
    expect(hint.status()).toBe(403);

    await setCode(page, DURATION_RIGHT);
    await submitAndWait(page, "passed");
    await expect(page.getByText("Проверка пройдена")).toBeVisible();
    await expect(page.getByRole("button", { name: "Проверить", exact: true })).toBeDisabled();

    await page.goto("/roadmap");
    await expect(page.locator("li", { hasText: "python.io_types" }).getByText("Освоено")).toBeVisible();
    await expect(page.locator("li", { hasText: "python.conditionals" }).getByText("Доступно")).toBeVisible();
    await expect(page.locator("li", { hasText: "python.loops" }).getByText("Закрыто")).toBeVisible();
    await page.goto("/review");
    await expect(page.getByText("Ввод/вывод и типы данных")).toBeVisible(); // review scheduled
  });

  test("11. keyboard: skip link, navigation and Ctrl/Cmd+Enter run", async ({ page }) => {
    await page.goto("/practice/cond.sign");
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Перейти к содержимому" })).toBeFocused();
    await page.locator(".cm-content").click();
    await page.keyboard.press("ControlOrMeta+Enter");
    await expect(page.getByTestId("job-summary")).toHaveAttribute("data-state", /passed|ran|ran_error|failed|partial/, {
      timeout: 40_000,
    });
    await expect(page.getByText("Это запуск: проверяются только открытые тесты")).toBeVisible();
    // result tabs are reachable and switchable with arrow keys
    await page.getByRole("tab", { name: "Тесты" }).click();
    await expect(page.getByRole("tab", { name: "Тесты" })).toBeFocused();
    await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("tab", { name: "Консоль" })).toBeFocused();
    await expect(page.getByRole("tab", { name: "Консоль" })).toHaveAttribute("aria-selected", "true");
    // the editor documents how to leave it with the keyboard
    await expect(page.locator(".cm-content")).toHaveAttribute("aria-describedby", "editor-help");
  });

  test("12. 390px mobile layout: no horizontal overflow, Run/Submit reachable", async ({ browser }) => {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: "ru-RU", hasTouch: true });
    const page = await ctx.newPage();
    for (const url of ["/", "/roadmap", "/learn/lesson.conditionals", "/skills/python.io_types", "/review", "/settings"]) {
      await page.goto(url);
      await page.waitForLoadState("networkidle");
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow, url).toBeLessThanOrEqual(0);
    }
    await page.goto("/practice/cond.sign");
    await page.getByRole("tab", { name: "Код" }).click();
    await expect(page.getByRole("button", { name: "Запустить" })).toBeInViewport();
    await expect(page.getByRole("button", { name: "Проверить", exact: true })).toBeInViewport();
    await page.getByRole("button", { name: "Запустить" }).click();
    await expect(page.getByRole("tab", { name: "Результат" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByTestId("job-summary")).toBeVisible({ timeout: 40_000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    await ctx.close();

    // tablet width also has no horizontal overflow
    const tablet = await browser.newContext({ viewport: { width: 768, height: 1024 }, locale: "ru-RU" });
    const tp = await tablet.newPage();
    for (const url of ["/", "/roadmap", "/practice/cond.sign", "/skills"]) {
      await tp.goto(url);
      await tp.waitForLoadState("networkidle");
      expect(await tp.evaluate(() => document.documentElement.scrollWidth - window.innerWidth), url).toBeLessThanOrEqual(0);
    }
    await tablet.close();
  });
});
