/**
 * A URL-safe name for a skill.
 *
 * Skill names are written the way employers write them, which means `C++`, `C#`, `A/B
 * testing` and `.NET` all have to survive a trip through a path segment. Stripping
 * punctuation alone would collapse `C++` and `C#` onto the same page, so the two
 * characters that distinguish real languages are spelled out rather than dropped.
 *
 * `pipeline/tests/test_skill_slugs.py` checks that no two skills in the marts share a slug.
 */
export function skillSlug(name: string): string {
  return name
    .toLowerCase()
    .replace(/\+/g, "-plus")
    .replace(/#/g, "-sharp")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}
