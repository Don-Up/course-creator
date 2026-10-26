import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const ROOT_PACKAGE_JSON = new URL("../package.json", import.meta.url);

async function readRootPackageJson() {
  return JSON.parse(await readFile(ROOT_PACKAGE_JSON, "utf8"));
}

test("root package.json exposes a non-empty test:contract script", async () => {
  const pkg = await readRootPackageJson();

  assert.ok(pkg.scripts, "package.json should define a scripts object");
  assert.ok(
    Object.prototype.hasOwnProperty.call(pkg.scripts, "test:contract"),
    "package.json should define scripts[\"test:contract\"]"
  );

  const script = pkg.scripts["test:contract"];
  assert.equal(typeof script, "string", "scripts[\"test:contract\"] should be a string");
  assert.ok(script.trim().length > 0, "scripts[\"test:contract\"] should not be empty");
});
