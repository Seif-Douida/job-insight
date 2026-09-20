import { expect, test, type Page } from "@playwright/test";

/**
 * What these tests are for.
 *
 * The dashboard renders numbers it did not compute, from marts it does not control. The
 * failure worth catching is not "the page crashed" — the build catches that — but "the
 * page published something that cannot be true", which renders perfectly and looks fine.
 *
 * So the checks below are mostly the site's own rules, asserted against what a visitor
 * actually sees: every percentage agrees with the count beside it, every published figure
 * states its sample size, and a thin cohort says so. A mart changing shape underneath us
 * fails here rather than in front of a reader.
 */

const ROUTES = [
  { path: "/", heading: "What companies ask for" },
  { path: "/role/data-engineer", heading: "Data Engineer" },
  { path: "/role/data-engineer/us", heading: "Data Engineer" },
  { path: "/skill/python", heading: "Python" },
  { path: "/compare/us/data-engineer/analytics-engineer", heading: /Data Engineer or/ },
  { path: "/methodology", heading: "Methodology" },
];

/** Console errors that are the page's fault, rather than the network being unavailable. */
function watchConsole(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  return errors;
}

for (const route of ROUTES) {
  test(`${route.path} renders and reports no errors`, async ({ page }) => {
    const errors = watchConsole(page);
    const response = await page.goto(route.path);

    expect(response?.status(), `${route.path} should be reachable`).toBe(200);
    await expect(page.getByRole("heading", { level: 1 })).toContainText(route.heading);
    expect(errors, `console errors on ${route.path}`).toEqual([]);
  });
}

test("unknown roles and skills are not invented", async ({ page }) => {
  for (const path of ["/role/nonsense/us", "/role/data-engineer/atlantis", "/skill/nonsense"]) {
    const response = await page.goto(path);
    expect(response?.status(), `${path} should be a 404`).toBe(404);
  }
});

test("the coverage matrix lists every role and region", async ({ page }) => {
  await page.goto("/");
  const matrix = page.getByRole("table", { name: /Postings analysed/ });

  await expect(matrix.locator("tbody tr")).toHaveCount(7);
  await expect(matrix.locator("thead th")).toHaveCount(5); // role + four regions

  // Every cell is either a link to that cohort or an explicit "nothing collected".
  const cells = await matrix.locator("tbody td").all();
  expect(cells.length).toBe(28);
  for (const cell of cells) {
    const link = cell.locator("a");
    const text = (await cell.innerText()).trim();
    if ((await link.count()) === 0) {
      expect(text, "a cell with no link must say so, not sit empty").toBe("—");
    } else {
      expect(Number(text), "a cohort link shows its sample size").toBeGreaterThan(0);
    }
  }
});

test("every skill percentage agrees with the count beside it", async ({ page }) => {
  await page.goto("/role/data-engineer/us");
  const rows = await page.getByRole("table", { name: "Skills by share of postings" })
    .locator("tbody tr")
    .all();

  expect(rows.length).toBeGreaterThan(10);

  for (const row of rows) {
    const text = (await row.innerText()).replace(/\s+/g, " ");
    const shown = text.match(/(\d+)%\s+(\d+) of (\d+)/);
    expect(shown, `a skill row must show a percentage and its counts: "${text}"`).not.toBeNull();

    const [, percent, withSkill, total] = shown!.map(Number);
    expect(Math.round((withSkill / total) * 100), `${text} does not add up`).toBe(percent);
    expect(withSkill, "a count cannot exceed its cohort").toBeLessThanOrEqual(total);
  }
});

test("a thin cohort says so, and a solid one does not", async ({ page }) => {
  // analytics-engineer/gulf rests on a handful of postings; data-engineer/us does not.
  await page.goto("/role/analytics-engineer/gulf");
  await expect(page.getByText(/thin sample/i)).toBeVisible();

  await page.goto("/role/data-engineer/us");
  await expect(page.getByText(/thin sample/i)).toHaveCount(0);
});

test("pay is published only with its sample size and never as an estimate", async ({ page }) => {
  await page.goto("/role/data-engineer/us");
  const pay = page.getByRole("table", { name: "Stated annual pay" });

  if ((await pay.count()) === 0) test.skip(true, "no cohort states pay today");

  for (const row of await pay.locator("tbody tr").all()) {
    const cells = await row.locator("th, td").allInnerTexts();
    const [currency, p25, median, p75, n] = cells.map((c) => c.trim());

    expect(currency, "pay is reported per currency").toMatch(/^[A-Z]{3}$/);
    expect(Number(n), "a published band states how many postings it rests on").toBeGreaterThan(0);

    const amounts = [p25, median, p75].map((value) => Number(value.replace(/[^0-9]/g, "")));
    expect(amounts[0]).toBeLessThanOrEqual(amounts[1]);
    expect(amounts[1]).toBeLessThanOrEqual(amounts[2]);
    expect(amounts[0], "an annual salary below this is an unlabelled hourly rate").toBeGreaterThanOrEqual(10_000);
  }
});

test("skill names survive the trip through a URL", async ({ page }) => {
  // The pair that collides if punctuation is simply stripped.
  await page.goto("/skill/c-plus-plus");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("C++");

  await page.goto("/skill/c-sharp");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("C#");
});

test("a skill page links back to the cohorts it came from", async ({ page }) => {
  await page.goto("/skill/python");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Python");

  const link = page.getByRole("link", { name: /Data Engineer/ }).first();
  await link.click();
  await expect(page).toHaveURL(/\/role\/data-engineer/);
});

test.describe("at phone width", () => {
  test.use({ viewport: { width: 360, height: 760 } });

  test("no page pushes the reader sideways", async ({ page }) => {
    for (const route of ROUTES) {
      await page.goto(route.path);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
      );
      expect(overflow, `${route.path} scrolls horizontally at 360px`).toBe(false);
    }
  });
});
